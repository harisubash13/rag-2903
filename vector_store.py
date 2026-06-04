import os
import json
import logging

logger = logging.getLogger(__name__)

# Try importing numpy for optimized vector calculations
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    logger.warning("NumPy is not installed. Falling back to pure Python calculations for vector similarity.")

import re

def sanitize_profile_name(name: str) -> str:
    """Removes non-alphanumeric characters to prevent directory traversal."""
    if not name:
        return "default"
    # Allow alphanumeric and underscore
    sanitized = re.sub(r'[^a-zA-Z0-9_]', '', name)
    return sanitized if sanitized else "default"

class VectorStore:
    def __init__(self, profile_name: str = "default"):
        self.profile_name = sanitize_profile_name(profile_name)
        self.storage_path = f"rag_store_{self.profile_name}.json"
        self.chunks = []      # list of dicts: {"text": str, "metadata": dict}
        self.embeddings = []  # list of list of floats: [ [v1, v2, ...], ... ]
        self.load()

    def add_chunks(self, chunks: list[dict], embeddings: list[list[float]]):
        """Adds chunks and their corresponding embeddings to the database, then saves to disk."""
        if len(chunks) != len(embeddings):
            raise ValueError("The number of chunks must match the number of embeddings.")
        
        self.chunks.extend(chunks)
        self.embeddings.extend(embeddings)
        self.save()

    def clear(self):
        """Clears all stored data and removes the storage file."""
        self.chunks = []
        self.embeddings = []
        if os.path.exists(self.storage_path):
            try:
                os.remove(self.storage_path)
            except Exception as e:
                logger.error(f"Failed to delete storage file: {e}")
        self.save()

    def save(self):
        """Saves current state to a JSON file."""
        data = {
            "chunks": self.chunks,
            "embeddings": self.embeddings
        }
        try:
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save vector store to '{self.storage_path}': {e}")

    def load(self):
        """Loads state from the JSON file if it exists."""
        if not os.path.exists(self.storage_path):
            self.chunks = []
            self.embeddings = []
            return
            
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.chunks = data.get("chunks", [])
                self.embeddings = data.get("embeddings", [])
        except Exception as e:
            logger.error(f"Failed to load vector store from '{self.storage_path}': {e}. Initializing empty store.")
            self.chunks = []
            self.embeddings = []

    def _cosine_similarity_numpy(self, query_vector: list[float]) -> list[float]:
        """Calculates cosine similarity for all embeddings using NumPy."""
        q = np.array(query_vector)
        # Reshape or compute norm
        q_norm = np.linalg.norm(q)
        if q_norm == 0:
            return [0.0] * len(self.embeddings)
            
        E = np.array(self.embeddings)
        # Compute dot products
        dot_products = np.dot(E, q)
        # Compute norms for all embeddings
        e_norms = np.linalg.norm(E, axis=1)
        
        # Avoid division by zero
        e_norms[e_norms == 0] = 1e-10
        
        similarities = dot_products / (e_norms * q_norm)
        return similarities.tolist()

    def _cosine_similarity_python(self, query_vector: list[float]) -> list[float]:
        """Calculates cosine similarity using pure Python list operations."""
        import math
        
        def dot_product(v1, v2):
            return sum(x * y for x, y in zip(v1, v2))
            
        def magnitude(v):
            return math.sqrt(sum(x * x for x in v))
            
        q_mag = magnitude(query_vector)
        if q_mag == 0:
            return [0.0] * len(self.embeddings)
            
        similarities = []
        for emb in self.embeddings:
            emb_mag = magnitude(emb)
            if emb_mag == 0:
                similarities.append(0.0)
                continue
            sim = dot_product(query_vector, emb) / (emb_mag * q_mag)
            similarities.append(sim)
            
        return similarities

    def search(self, query_embedding: list[float], top_k: int = 5) -> list[dict]:
        """
        Searches for top_k most similar chunks to query_embedding.
        Returns a list of dicts with keys 'text', 'metadata', and 'similarity'.
        """
        if not self.embeddings:
            return []
            
        if HAS_NUMPY:
            try:
                similarities = self._cosine_similarity_numpy(query_embedding)
            except Exception as e:
                logger.error(f"NumPy similarity calculation failed, using fallback: {e}")
                similarities = self._cosine_similarity_python(query_embedding)
        else:
            similarities = self._cosine_similarity_python(query_embedding)
            
        # Combine index, chunk and similarity
        results = []
        for idx, (chunk, sim) in enumerate(zip(self.chunks, similarities)):
            results.append({
                "text": chunk["text"],
                "metadata": chunk["metadata"],
                "similarity": float(sim)
            })
            
        # Sort by similarity in descending order
        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:top_k]

    def get_unique_files(self) -> list[dict]:
        """Returns a list of dictionary metadata about processed files."""
        file_map = {}
        for chunk in self.chunks:
            meta = chunk.get("metadata", {})
            source = meta.get("source", "Unknown")
            file_type = meta.get("type", "unknown")
            
            if source not in file_map:
                file_map[source] = {
                    "name": source,
                    "type": file_type,
                    "chunks": 0
                }
            file_map[source]["chunks"] += 1
            
        return list(file_map.values())
