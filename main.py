import os
import logging
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Header, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Import local modules
from parser import parse_file
from chunker import chunk_documents
from vector_store import VectorStore
from gemini_client import GeminiClient
import auth

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Initialize user database
auth.init_db()

# Initialize session manager and profile stores cache
sessions = auth.SessionManager()
profile_stores = {}

# Initialize FastAPI App
app = FastAPI(title="Minimal & Premium RAG API", version="1.0.0")

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request models
class QueryRequest(BaseModel):
    query: str

class UserAuthRequest(BaseModel):
    username: str
    password: str

def get_db(authorization: Optional[str] = Header(None)) -> VectorStore:
    """
    Resolves and returns the VectorStore corresponding to the authenticated user.
    Requires 'Authorization: Bearer <token>' header.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication token required. Please sign in.")
    
    token = authorization.split(" ")[1]
    username = sessions.get_username(token)
    if not username:
        raise HTTPException(status_code=401, detail="Session expired or invalid. Please sign in again.")
        
    if username not in profile_stores:
        logger.info(f"Instantiating new VectorStore for user: {username}")
        profile_stores[username] = VectorStore(profile_name=username)
    return profile_stores[username]

def get_client(gemini_api_key_header: Optional[str] = Header(None, alias="X-Gemini-API-Key")) -> GeminiClient:
    """
    Helper function to resolve and return the Gemini Client.
    Prioritizes the key passed from the client headers (UI-configured), 
    then falls back to environment variables.
    """
    key = gemini_api_key_header or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise HTTPException(
            status_code=401, 
            detail="Gemini API Key missing. Please set it in the UI configuration or as a backend environment variable."
        )
    return GeminiClient(api_key=key)

@app.post("/api/register")
async def api_register(request: UserAuthRequest):
    username = request.username.strip().lower()
    
    # Basic validation: only alphanumeric + underscores, max 20 chars
    from vector_store import sanitize_profile_name
    sanitized = sanitize_profile_name(username)
    if not sanitized or sanitized != username:
        raise HTTPException(
            status_code=400,
            detail="Username must contain only alphanumeric characters or underscores (no spaces/symbols)."
        )
    
    if len(request.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters long.")

    success = auth.register_user(username, request.password)
    if not success:
        raise HTTPException(status_code=400, detail="Username already exists or registration failed.")
    
    return {"message": "Registration successful. You can now log in."}

@app.post("/api/login")
async def api_login(request: UserAuthRequest):
    username = request.username.strip().lower()
    is_valid = auth.authenticate_user(username, request.password)
    
    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    
    token = sessions.create_session(username)
    return {"token": token, "username": username}

@app.post("/api/logout")
async def api_logout(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header.")
    
    token = authorization.split(" ")[1]
    sessions.remove_session(token)
    return {"message": "Logged out successfully."}

@app.get("/api/status")
async def get_status(
    authorization: Optional[str] = Header(None),
    x_gemini_api_key: Optional[str] = Header(None, alias="X-Gemini-API-Key")
):
    """
    Returns system status. If authenticated, returns user document statistics.
    """
    api_key_provided = bool(x_gemini_api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    
    # Resolve optional session
    username = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        username = sessions.get_username(token)
        
    if username:
        if username not in profile_stores:
            profile_stores[username] = VectorStore(profile_name=username)
        db = profile_stores[username]
        return {
            "status": "online",
            "authenticated": True,
            "username": username,
            "api_key_configured": api_key_provided,
            "files_count": len(db.get_unique_files()),
            "chunks_count": len(db.chunks)
        }
    else:
        return {
            "status": "online",
            "authenticated": False,
            "api_key_configured": api_key_provided,
            "files_count": 0,
            "chunks_count": 0
        }

@app.post("/api/upload")
async def upload_file(
    file: UploadFile = File(...),
    x_gemini_api_key: Optional[str] = Header(None, alias="X-Gemini-API-Key"),
    db: VectorStore = Depends(get_db)
):
    """
    Handles file upload, parses, chunks, generates embeddings, and indexes in the VectorStore.
    """
    filename = file.filename
    _, ext = os.path.splitext(filename.lower())
    if ext not in ['.pdf', '.xlsx', '.txt']:
        raise HTTPException(status_code=400, detail="Only .pdf, .xlsx, and .txt files are supported.")

    # Read file content
    try:
        content_bytes = await file.read()
    except Exception as e:
        logger.error(f"Failed to read file {filename}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to read file: {str(e)}")

    # Initialize Gemini client
    try:
        client = get_client(x_gemini_api_key)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"API Client initialization failed: {str(e)}")

    # Ingestion Pipeline
    try:
        # 1. Parse File
        logger.info(f"Parsing file: {filename}")
        parsed_docs = parse_file(content_bytes, filename)
        if not parsed_docs:
            if ext == '.pdf':
                logger.info(f"Local PDF parsing returned no text. Falling back to Gemini File API OCR for: {filename}")
                try:
                    parsed_docs = client.parse_pdf_via_gemini(content_bytes, filename)
                except Exception as ocr_err:
                    logger.error(f"Gemini OCR fallback failed: {ocr_err}")
                    raise HTTPException(
                        status_code=400, 
                        detail=f"The file could not be parsed locally (scanned/empty PDF?), and Gemini OCR fallback failed: {str(ocr_err)}"
                    )
            
            if not parsed_docs:
                raise HTTPException(status_code=400, detail="The file was parsed successfully but no readable text was extracted.")

        # 2. Chunk Documents
        logger.info(f"Chunking file: {filename}")
        chunks = chunk_documents(parsed_docs, max_chunk_size=1000, overlap=200)
        if not chunks:
            raise HTTPException(status_code=400, detail="No chunks generated from the file content.")

        # 3. Generate Embeddings for each chunk
        logger.info(f"Generating embeddings for {len(chunks)} chunks of: {filename}")
        embeddings = []
        for idx, chunk in enumerate(chunks):
            # Call Gemini API to get embedding
            emb = client.get_embedding(chunk["text"])
            embeddings.append(emb)

        # 4. Save to Vector Store
        db.add_chunks(chunks, embeddings)
        logger.info(f"Ingestion successful for {filename}. Added {len(chunks)} chunks.")

        return {
            "message": f"Successfully ingested '{filename}'",
            "chunks_count": len(chunks)
        }

    except ValueError as e:
        logger.error(f"Validation or parsing error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error during ingestion: {e}")
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")

@app.post("/api/query")
async def query_rag(
    request: QueryRequest,
    x_gemini_api_key: Optional[str] = Header(None, alias="X-Gemini-API-Key"),
    db: VectorStore = Depends(get_db)
):
    """
    RAG Query endpoint. Retrieves top relevant chunks and returns generation from Gemini.
    """
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    if not db.chunks:
        raise HTTPException(
            status_code=400, 
            detail="No documents have been ingested yet. Please upload files before asking questions."
        )

    # Initialize Gemini client
    try:
        client = get_client(x_gemini_api_key)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"API Client initialization failed: {str(e)}")

    try:
        # 1. Get query embedding
        query_embedding = client.get_embedding(query)

        # 2. Retrieve top-k chunks (default top 5)
        top_k = min(5, len(db.chunks))
        relevant_chunks = db.search(query_embedding, top_k=top_k)

        # 3. Generate Answer using the retrieved chunks
        answer = client.generate_answer(query, relevant_chunks)

        return {
            "answer": answer,
            "sources": [
                {
                    "text": chunk["text"],
                    "metadata": chunk["metadata"],
                    "similarity": chunk["similarity"]
                }
                for chunk in relevant_chunks
            ]
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying RAG system: {e}")
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")

@app.get("/api/files")
async def get_files(db: VectorStore = Depends(get_db)):
    """Lists all files that have been digested."""
    return db.get_unique_files()

@app.post("/api/clear")
async def clear_database(db: VectorStore = Depends(get_db)):
    """Clears all parsed documents and resets the vector store."""
    db.clear()
    return {"message": "Database cleared successfully."}

# Serving the static frontend
# Create static directory if it doesn't exist
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)

# Mount static folder for serving stylesheet and scripts
app.mount("/assets", StaticFiles(directory=static_dir), name="static")

# Catch-all route to serve index.html at root
@app.get("/")
async def read_root():
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return JSONResponse(
        status_code=404,
        content={"message": "Frontend index.html not found. Please place static files in d:/rag/static/"}
    )
