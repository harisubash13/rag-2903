import os
import logging
from google import genai
from google.genai import types
from google.genai.errors import APIError

logger = logging.getLogger(__name__)

class GeminiClient:
    def __init__(self, api_key: str = None):
        # Resolve API key: parameter first, then environment variable
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        self.client = None
        if self.api_key:
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.error(f"Failed to initialize Gemini Client: {e}")

    def is_configured(self) -> bool:
        """Returns True if the client is initialized with an API key."""
        return self.client is not None

    def set_key(self, api_key: str):
        """Dynamically re-initialize the client with a new API key."""
        if api_key:
            self.api_key = api_key
            self.client = genai.Client(api_key=api_key)

    def get_embedding(self, text: str) -> list[float]:
        """
        Generates vector embedding for the input text using gemini-embedding-2.
        """
        if not self.is_configured():
            raise ValueError("Gemini API Client is not configured. Please supply an API key.")
        
        try:
            # We use gemini-embedding-2 as the active text embedding model
            response = self.client.models.embed_content(
                model="gemini-embedding-2",
                contents=text
            )
            # Inspect the structure of the response
            # google-genai response for embed_content has: response.embeddings[0].values
            if response.embeddings:
                return response.embeddings[0].values
            elif hasattr(response, 'embedding') and hasattr(response.embedding, 'values'):
                return response.embedding.values
            else:
                raise ValueError("Could not find embedding values in the response.")
        except APIError as e:
            logger.error(f"Gemini API Error during embedding generation: {e}")
            raise ValueError(f"Gemini API Error: {e.message}")
        except Exception as e:
            logger.error(f"Unexpected error during embedding generation: {e}")
            raise ValueError(f"Failed to generate embedding: {str(e)}")

    def generate_answer(self, query: str, context_chunks: list[dict]) -> str:
        """
        Queries Gemini model (gemini-2.5-flash) with context retrieved from documents.
        """
        if not self.is_configured():
            raise ValueError("Gemini API Client is not configured. Please supply an API key.")

        # Build context prompt
        formatted_context = ""
        for idx, chunk in enumerate(context_chunks):
            meta = chunk.get("metadata", {})
            source = meta.get("source", "Unknown Source")
            ref_info = f"Source: {source}"
            if "page" in meta:
                ref_info += f" (Page {meta['page']})"
            elif "sheet" in meta:
                ref_info += f" (Sheet '{meta['sheet']}', Rows {meta['rows']})"
                
            formatted_context += f"--- [Context Chunk #{idx+1} | {ref_info}] ---\n"
            formatted_context += f"{chunk['text']}\n\n"

        system_instruction = (
            "You are a helpful AI assistant powered by a RAG system. "
            "Your task is to answer the user's question using the provided context chunks. "
            "Follow these rules strictly:\n"
            "1. Answer the question thoroughly and accurately using ONLY the provided context blocks.\n"
            "2. If the context does not contain the answer, say honestly that you cannot find the answer in the uploaded files. Do not make up answers.\n"
            "3. Cite your sources clearly when referring to facts (e.g., refer to 'Source: doc.pdf (Page 3)' or 'Sheet Sales, Rows 2-10').\n"
            "4. Keep your formatting clean, readable, and professional using markdown."
        )

        prompt = f"User Question:\n{query}\n\nRetrieved Context:\n{formatted_context}\nAnswer:"

        try:
            # We use gemini-2.5-flash as the default model
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.2,
                )
            )
            return response.text or "No response generated."
        except APIError as e:
            logger.error(f"Gemini API Error during generation: {e}")
            raise ValueError(f"Gemini API Error: {e.message}")
        except Exception as e:
            logger.error(f"Unexpected error during generation: {e}")
            raise ValueError(f"Failed to generate answer: {str(e)}")

    def parse_pdf_via_gemini(self, file_bytes: bytes, filename: str) -> list[dict]:
        """
        Uploads a PDF to Gemini File API, extracts text page-by-page,
        and returns a list of dictionaries in the standard parser output format.
        """
        if not self.is_configured():
            raise ValueError("Gemini API Client is not configured. Please supply an API key.")

        import tempfile
        import re
        
        # Write bytes to a temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            temp_file.write(file_bytes)
            temp_path = temp_file.name

        try:
            logger.info(f"Uploading PDF {filename} to Gemini File API for OCR parsing...")
            gemini_file = self.client.files.upload(file=temp_path)
            
            prompt = (
                "Extract all text content from this PDF page-by-page. "
                "Structure your output strictly like this:\n"
                "=== PAGE 1 ===\n"
                "[Page 1 Content...]\n"
                "=== PAGE 2 ===\n"
                "[Page 2 Content...]\n"
                "and so on. Do not summarize, format, or comment. Output only the page separators and raw text."
            )
            
            logger.info(f"Running multimodal generation/OCR on {filename} via Gemini...")
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[gemini_file, prompt]
            )
            
            # Clean up the file from Gemini File API immediately
            try:
                self.client.files.delete(name=gemini_file.name)
            except Exception as delete_err:
                logger.warning(f"Failed to delete temp file from Gemini API: {delete_err}")
                
            extracted_text = response.text or ""
            
            # Parse the response into page-by-page document dictionaries
            page_blocks = re.split(r'=== PAGE \d+ ===', extracted_text)
            page_nums = [int(num) for num in re.findall(r'=== PAGE (\d+) ===', extracted_text)]
            
            documents = []
            
            # The first block might be text before "=== PAGE 1 ===", ignore it
            content_blocks = page_blocks[1:] if len(page_blocks) > 1 else page_blocks
            
            for idx, block in enumerate(content_blocks):
                text = block.strip()
                if text:
                    page_num = page_nums[idx] if idx < len(page_nums) else (idx + 1)
                    documents.append({
                        "text": text,
                        "metadata": {
                            "source": filename,
                            "page": page_num,
                            "total_pages": len(content_blocks),
                            "type": "pdf_ocr"
                        }
                    })
            return documents
            
        except APIError as e:
            logger.error(f"Gemini API Error during PDF parsing: {e}")
            raise ValueError(f"Gemini API Error during PDF parsing: {e.message}")
        except Exception as e:
            logger.error(f"Unexpected error during PDF parsing via Gemini: {e}")
            raise ValueError(f"Failed to parse PDF via Gemini OCR: {str(e)}")
        finally:
            # Clean up local temp file
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception as cleanup_err:
                    logger.warning(f"Failed to remove local temp file: {cleanup_err}")
