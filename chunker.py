def split_text_recursive(text: str, max_chunk_size: int = 1000, overlap: int = 200) -> list[str]:
    """
    Recursively splits text into chunks of maximum size max_chunk_size with overlap.
    Tries to split on paragraphs, then sentences, then spaces.
    """
    if len(text) <= max_chunk_size:
        return [text]

    # Delimiters to try in order of priority (paragraphs, lines, sentences, spaces)
    delimiters = ["\n\n", "\n", ". ", " ", ""]
    
    def split_helper(txt: str, separators: list[str]) -> list[str]:
        if len(txt) <= max_chunk_size:
            return [txt]
            
        if not separators:
            # Fallback to hard split if no delimiters left
            return [txt[i:i+max_chunk_size] for i in range(0, len(txt), max_chunk_size - overlap)]
            
        sep = separators[0]
        remaining_seps = separators[1:]
        
        # Split text by current separator
        if sep == "":
            parts = list(txt)
        else:
            parts = txt.split(sep)
            
        chunks = []
        current_chunk = []
        current_len = 0
        
        for part in parts:
            part_len = len(part) + (len(sep) if current_chunk else 0)
            
            # If a single part exceeds max_chunk_size, recursively split it with remaining separators
            if part_len > max_chunk_size:
                # Flush current chunk first
                if current_chunk:
                    chunks.append(sep.join(current_chunk))
                    current_chunk = []
                    current_len = 0
                
                sub_chunks = split_helper(part, remaining_seps)
                chunks.extend(sub_chunks)
            elif current_len + part_len <= max_chunk_size:
                current_chunk.append(part)
                current_len += part_len
            else:
                # Flush and start new chunk with overlap
                if current_chunk:
                    chunks.append(sep.join(current_chunk))
                
                # Create overlap: back off elements until we are within overlap size
                overlap_chunk = []
                overlap_len = 0
                for p in reversed(current_chunk):
                    p_len = len(p) + (len(sep) if overlap_chunk else 0)
                    if overlap_len + p_len <= overlap:
                        overlap_chunk.insert(0, p)
                        overlap_len += p_len
                    else:
                        break
                
                current_chunk = overlap_chunk + [part]
                current_len = sum(len(p) for p in current_chunk) + (len(sep) * (len(current_chunk) - 1))
                
        if current_chunk:
            chunks.append(sep.join(current_chunk))
            
        return chunks

    return split_helper(text, delimiters)


def chunk_documents(documents: list[dict], max_chunk_size: int = 1000, overlap: int = 200) -> list[dict]:
    """
    Takes parsed documents and returns a list of chunks, where each chunk is a dict:
    {
        "text": chunk_text,
        "metadata": { ...original_metadata, "chunk_index": index }
    }
    """
    chunks = []
    
    for doc in documents:
        text = doc.get("text", "")
        metadata = doc.get("metadata", {})
        
        if not text:
            continue
            
        text_chunks = split_text_recursive(text, max_chunk_size, overlap)
        
        for i, text_chunk in enumerate(text_chunks):
            # Clean chunk
            text_chunk = text_chunk.strip()
            if not text_chunk:
                continue
                
            chunk_metadata = metadata.copy()
            chunk_metadata["chunk_index"] = i
            
            chunks.append({
                "text": text_chunk,
                "metadata": chunk_metadata
            })
            
    return chunks
