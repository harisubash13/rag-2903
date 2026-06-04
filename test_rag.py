import os
from parser import parse_file
from chunker import chunk_documents
from vector_store import VectorStore

def run_tests():
    print("=== Running Offline RAG Component Tests ===")
    
    # 1. Test Text Parser
    print("\n[1/4] Testing Plain Text Parser...")
    dummy_text = "This is a test document about Antigravity AI. It has multiple lines.\nThis is the second line."
    text_bytes = dummy_text.encode('utf-8')
    parsed_docs = parse_file(text_bytes, "test.txt")
    
    assert len(parsed_docs) == 1, "Expected exactly 1 parsed document"
    assert parsed_docs[0]["text"] == dummy_text, "Parsed text doesn't match input text"
    assert parsed_docs[0]["metadata"]["source"] == "test.txt", "Metadata source mismatch"
    assert parsed_docs[0]["metadata"]["type"] == "txt", "Metadata type mismatch"
    print("[OK] Text Parser passed!")
    
    # 2. Test Chunker
    print("\n[2/4] Testing Recursive Character Split Chunker...")
    dummy_long_text = (
        "Introduction to RAG. Retrieval-Augmented Generation is a technique. "
        "It combines retrieval of relevant documents with LLM generation. "
        "This helps prevent hallucinations. We chunk files to fit context windows.\n\n"
        "Second paragraph starts here. We want to test paragraph splitting. "
        "A good chunker splits on paragraphs first, then sentences. "
        "Let's see if this splits nicely and preserves context."
    )
    docs_to_chunk = [{"text": dummy_long_text, "metadata": {"source": "long_test.txt", "type": "txt"}}]
    
    # Chunk with small size to force split
    chunks = chunk_documents(docs_to_chunk, max_chunk_size=150, overlap=30)
    print(f"Generated {len(chunks)} chunks:")
    for idx, c in enumerate(chunks):
        print(f"  Chunk {idx}: {repr(c['text'])}")
        assert len(c['text']) <= 150, f"Chunk {idx} exceeds max_chunk_size of 150"
        assert c['metadata']['source'] == "long_test.txt"
        assert c['metadata']['chunk_index'] == idx
        
    assert len(chunks) > 1, "Expected multiple chunks for long text"
    print("[OK] Chunker passed!")

    # 3. Test Vector Store Cosine Similarity & Profile Isolation
    print("\n[3/4] Testing Vector Store similarity search & profile isolation...")
    store_a = VectorStore(profile_name="profile_a")
    store_b = VectorStore(profile_name="profile_b")
    
    # Clean previous test runs
    store_a.clear()
    store_b.clear()
    
    test_chunks = [
        {"text": "Python is a popular programming language.", "metadata": {"source": "doc1.txt"}},
        {"text": "FastAPI is a modern web framework for Python.", "metadata": {"source": "doc2.txt"}},
    ]
    mock_embeddings = [
        [0.99, 0.05],
        [0.80, 0.50]
    ]
    
    # Add chunks to A
    store_a.add_chunks(test_chunks, mock_embeddings)
    
    # Verify B is isolated and remains empty
    assert len(store_b.chunks) == 0, "Profile B should be empty, but has chunks!"
    assert len(store_a.chunks) == 2, "Profile A should have exactly 2 chunks!"
    print("  [OK] Profile data isolation verified.")
    
    # Search on A
    query_emb = [1.0, 0.0]
    results = store_a.search(query_emb, top_k=2)
    
    print("Search results in Profile A (top 2):")
    for r in results:
        print(f"  Similarity {r['similarity']:.4f}: {r['text']} (from {r['metadata']['source']})")
        
    assert len(results) == 2, "Expected 2 search results"
    assert results[0]["metadata"]["source"] == "doc1.txt", "Expected doc1.txt to be top result"
    assert results[0]["similarity"] > 0.9, "Doc1 similarity should be very high"
    
    # Clean up test files
    store_a.clear()
    store_b.clear()
    print("[OK] Vector Store similarity and profile isolation passed!")

    # 4. Excel Row Formatting Parsing Test
    print("\n[4/4] Testing Excel parser mockup...")
    try:
        import pandas as pd
        import openpyxl
        # We can construct a dummy DataFrame and bytes
        df = pd.DataFrame({
            "Name": ["Alice", "Bob"],
            "Role": ["Engineer", "Designer"],
            "Salary": [80000, 75000]
        })
        import io
        excel_io = io.BytesIO()
        with pd.ExcelWriter(excel_io, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name="Employees", index=False)
        excel_bytes = excel_io.getvalue()
        
        parsed_excel = parse_file(excel_bytes, "employees.xlsx")
        print(f"Excel chunks generated: {len(parsed_excel)}")
        assert len(parsed_excel) == 1, "Expected 1 Excel block"
        text_block = parsed_excel[0]["text"]
        print("Excel text representation:")
        print(text_block)
        
        assert "Excel Sheet: Employees" in text_block
        assert "Row 2: Name: Alice | Role: Engineer | Salary: 80000" in text_block
        assert "Row 3: Name: Bob | Role: Designer | Salary: 75000" in text_block
        print("[OK] Excel Parser passed!")
    except Exception as e:
        print(f"[FAIL] Excel Parser test failed or skipped: {e}")
        raise e

    print("\n=== All Offline Component Tests Passed Successfully! ===")

if __name__ == "__main__":
    run_tests()
