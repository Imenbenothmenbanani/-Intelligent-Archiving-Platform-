"""
Pipeline Service - Clean Implementation
Imports functions directly from services (except OCR which uses subprocess for Python 3.10 isolation)
"""
import sys
import os
import json
import tempfile
import uuid
import subprocess
import time
import logging
import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# ============================================================================
# Setup paths to all services
# ============================================================================

_PIPELINE_DIR = Path(__file__).parent.resolve()
_APP_DIR = _PIPELINE_DIR.parent.resolve()
_PROJECT_ROOT = _APP_DIR.parent.resolve()

_STORAGE_DIR = _PROJECT_ROOT / "storage_service"
_CHUNK_DIR = _PROJECT_ROOT / "chunk_service"
_EMBED_DIR = _PROJECT_ROOT / "embendding_service"
_OCR_DIR = _PROJECT_ROOT / "ocr_service"

# Add service directories to Python path (matching demo/pipeline_index.py pattern)
for _p in [str(_STORAGE_DIR), str(_STORAGE_DIR / "config"), str(_CHUNK_DIR), str(_EMBED_DIR), str(_EMBED_DIR / "config")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

logger = logging.getLogger(__name__)

# ============================================================================
# Import service functions
# ============================================================================

# Storage Service (Python 3.10+)
from bucket import create_bucket, list_buckets
from object import upload_file, get_file_stream, list_files

# Chunk Service (Python 3.11+)
from chunk_builder import build_chunks

# Embedding Service (Python 3.11+)
from embedder import index_chunks, search as embed_search
from opensearch_client import index_doc, hybrid_search
from reranker import rerank, candidates_from_hits

# ============================================================================
# Constants
# ============================================================================

BUCKET_DOCS = "docs"
BUCKET_CHUNKS = "chunks"

# Session storage for Human-in-the-Loop
_session_store: Dict[str, Any] = {}

# Temp directories
OCR_OUTPUT_DIR = _APP_DIR / "ocr_tmp"
CHUNK_DIR_OUT = _APP_DIR / "chunk_tmp"
OCR_OUTPUT_DIR.mkdir(exist_ok=True)
CHUNK_DIR_OUT.mkdir(exist_ok=True)

# ============================================================================
# Initialize FastAPI
# ============================================================================

app = FastAPI(
    title="Intelligent Archiving Pipeline Service",
    description="Orchestrates OCR → Chunk → Embed → Index with Human-in-the-Loop",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    """Create and verify buckets on startup"""
    print("\n" + "="*60)
    print("  Pipeline Service Starting")
    print("="*60)
    
    try:
        buckets = list_buckets()
        print(f"Existing buckets: {buckets}")
        
        if BUCKET_DOCS not in buckets:
            print(f"Creating '{BUCKET_DOCS}' bucket...")
            create_bucket(BUCKET_DOCS)
        
        if BUCKET_CHUNKS not in buckets:
            print(f"Creating '{BUCKET_CHUNKS}' bucket...")
            create_bucket(BUCKET_CHUNKS)
        
        buckets = list_buckets()
        print(f"✓ Buckets ready: {buckets}")
        assert BUCKET_DOCS in buckets, f"Bucket '{BUCKET_DOCS}' not found!"
        assert BUCKET_CHUNKS in buckets, f"Bucket '{BUCKET_CHUNKS}' not found!"
        
        print("="*60 + "\n")
    except Exception as e:
        print(f"\n✗ Startup failed: {e}")
        import traceback
        traceback.print_exc()
        raise

# ============================================================================
# OCR via Subprocess (Python 3.10 isolation)
# ============================================================================

def run_ocr_subprocess(input_path: str, output_dir: str, opts: dict) -> dict:
    """Run OCR service in its own Python 3.10 environment"""
    ocr_python = _OCR_DIR / ".venv" / "Scripts" / "python.exe"
    if not ocr_python.exists():
        ocr_python = _OCR_DIR / ".venv" / "bin" / "python"
    if not ocr_python.exists():
        raise RuntimeError(f"OCR venv not found at {ocr_python}. Expected: {_OCR_DIR / '.venv'}")
    
    cmd = [str(ocr_python), "main.py", "--input", input_path, "--output", output_dir]
    
    flag_map = {
        "use_doc_orientation_classify": "--orientation",
        "use_doc_unwarping": "--unwarp",
        "use_layout_detection": "--layout",
        "use_ocr_for_image_block": "--ocr-images",
        "format_block_content": "--format",
        "merge_layout_blocks": "--merge-layout",
    }
    
    for key, cli_flag in flag_map.items():
        if opts.get(key, False):
            cmd.append(cli_flag)
    
    print(f"[OCR] Running: {' '.join(cmd)}")
    print(f"[OCR] Input file: {input_path}")
    print(f"[OCR] Output dir: {output_dir}")
    print(f"[OCR] Options: {opts}")
    
    t0 = time.perf_counter()
    
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(_OCR_DIR),
            capture_output=True,
            text=True,
            timeout=600,
            env=env
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"OCR subprocess timed out after 600 seconds")
    except FileNotFoundError as e:
        raise RuntimeError(f"OCR Python executable not found: {ocr_python}")
    
    elapsed = time.perf_counter() - t0
    print(f"[OCR] Completed in {elapsed:.1f}s (exit code: {proc.returncode})")
    
    if proc.stdout:
        print(f"[OCR] STDOUT:\n{proc.stdout}")
    if proc.stderr:
        print(f"[OCR] STDERR:\n{proc.stderr}")
    
    if proc.returncode != 0:
        error_detail = proc.stderr[-1000:] if proc.stderr else proc.stdout[-1000:] if proc.stdout else "Unknown error"
        raise RuntimeError(f"OCR failed (exit {proc.returncode}):\n{error_detail}")
    
    # Find result JSON file
    stem = Path(input_path).stem
    json_path = Path(output_dir) / stem / "result.json"
    
    if not json_path.exists():
        candidates = list(Path(output_dir).rglob("*.json"))
        if not candidates:
            raise RuntimeError(f"No JSON output found in {output_dir}. Available files: {list(Path(output_dir).rglob('*'))}")
        json_path = candidates[0]
        print(f"[OCR] Using JSON from: {json_path}")
    
    print(f"[OCR] Reading result from: {json_path}")
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_text_from_ocr_json(ocr_json: dict) -> str:
    """Extract all readable text from PaddleOCR-VL result, stripping HTML/markdown tags and error messages"""
    import re
    
    def find_texts(obj, depth=0):
        texts = []
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key in ["text", "content", "block_content", "rec_texts"]:
                    if isinstance(value, list):
                        texts.extend([str(t) for t in value if t])
                    elif value:
                        texts.append(str(value))
                elif depth < 5:
                    texts.extend(find_texts(value, depth + 1))
        elif isinstance(obj, list):
            for item in obj:
                texts.extend(find_texts(item, depth + 1))
        return texts
    
    all_text = find_texts(ocr_json)
    raw_text = "\n\n".join(all_text) if all_text else "No text extracted"
    
    print(f"[Text Extraction] Raw text length: {len(raw_text)}")
    print(f"[Text Extraction] First 200 chars: {raw_text[:200]}")
    
    # Remove HTML tags (more robust)
    clean_text = re.sub(r'<[^>]*>', '', raw_text)
    
    # Remove markdown
    clean_text = re.sub(r'[#*`_~\[\]()]', '', clean_text)
    
    # Remove common OCR error messages and placeholders
    error_patterns = [
        r'\bblurry\s+text\b.*?(?:\n|$)',
        r"couldn't extract\b.*?(?:\n|$)",
        r'\bcouldn\'t extract\b.*?(?:\n|$)',
        r'\berror\s+extracting\b.*?(?:\n|$)',
        r'\b(OCR|extraction)\s+failed\b.*?(?:\n|$)',
        r'\[.*?(error|placeholder|unknown).*?\]',
        r'<(error|placeholder)>.*?</\1>',
    ]
    
    for pattern in error_patterns:
        clean_text = re.sub(pattern, '', clean_text, flags=re.IGNORECASE | re.DOTALL)
    
    # Remove extra whitespace but preserve meaningful line breaks
    lines = [line.strip() for line in clean_text.split('\n')]
    # Filter empty lines and lines that are just whitespace or special characters
    clean_lines = [
        line for line in lines 
        if line and not re.match(r'^[\s\-_=*+]+$', line)
    ]
    clean_text = '\n'.join(clean_lines)
    
    # Limit to reasonable length and remove excessive blank lines
    clean_text = re.sub(r'\n\n\n+', '\n\n', clean_text)
    
    print(f"[Text Extraction] Clean text length: {len(clean_text)}")
    print(f"[Text Extraction] First 200 chars: {clean_text[:200]}")
    print(f"[Text Extraction] Cleaned {len(raw_text) - len(clean_text)} characters")
    
    return clean_text if clean_text else "No text extracted"

# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "buckets": list_buckets()
    }


@app.post("/pipeline/ocr")
async def step1_upload_and_ocr(
    file: UploadFile = File(...),
    document_id: str = Query(None),
    use_orientation: bool = Query(True),
    use_unwarp: bool = Query(True),
    use_layout: bool = Query(True),
    use_ocr_for_image_block: bool = Query(False),
    use_format: bool = Query(True),
    merge_tables: bool = Query(False)
):
    """
    Step 1: Upload to Ceph 'docs' bucket → Run OCR → Return text for review
    Pipeline pauses here for Human-in-the-Loop
    """
    try:
        suffix = Path(file.filename or "document.pdf").suffix.lower()
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name
        
        # Use provided document_id or generate one
        if not document_id:
            document_id = f"{Path(file.filename).stem}_{uuid.uuid4().hex[:8]}"
        else:
            # Remove file extension from document_id if present
            document_id = Path(document_id).stem
        
        # Upload to Ceph docs bucket with original file extension preserved
        print(f"\n[1/3] Uploading '{document_id}' to Ceph '{BUCKET_DOCS}' bucket...")
        # Use document_id with the original suffix/extension
        object_name_in_ceph = f"{document_id}{suffix}"
        upload_result = upload_file(BUCKET_DOCS, tmp_path, object_name_in_ceph)
        print(f"✓ {upload_result}\n")
        
        # Run OCR via subprocess
        print("[2/3] Running OCR...")
        ocr_output_dir = OCR_OUTPUT_DIR / document_id
        ocr_output_dir.mkdir(parents=True, exist_ok=True)
        
        ocr_options = {
            "use_doc_orientation_classify": use_orientation,
            "use_doc_unwarping": use_unwarp,
            "use_layout_detection": use_layout,
            "use_ocr_for_image_block": use_ocr_for_image_block,
            "format_block_content": use_format,
            "merge_layout_blocks": merge_tables,
        }
        
        # Run OCR directly (blocking, as requested)
        ocr_json = run_ocr_subprocess(tmp_path, str(ocr_output_dir), ocr_options)
        print("✓ OCR completed\n")
        
        extracted_text = extract_text_from_ocr_json(ocr_json)
        print(f"[3/3] Extracted {len(extracted_text)} characters of text\n")
        
        session_id = str(uuid.uuid4())
        _session_store[session_id] = {
            "document_id": document_id,
            "file_path": tmp_path,
            "ocr_json": ocr_json,
            "extracted_text": extracted_text,
        }
        
        return {
            "success": True,
            "session_id": session_id,
            "document_id": document_id,
            "extracted_text": extracted_text,
            "message": "OCR completed. Review and correct text, then confirm to continue."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        print(f"✗ OCR failed: {error_msg}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"OCR Error: {error_msg}")


@app.post("/pipeline/confirm")
async def step2_confirm_and_index(
    session_id: str = Query(...),
    corrected_text: str = Query(...),
    max_tokens: int = Query(500),
    overlap_ratio: float = Query(0.2)
):
    """
    Step 2: User confirms/corrects text → Chunk → Upload to Ceph 'chunks' → Embed & Index
    """
    try:
        print(f"\n[CONFIRM] Session ID: {session_id}")
        print(f"[CONFIRM] Corrected text length: {len(corrected_text) if corrected_text else 0}")
        print(f"[CONFIRM] Max tokens: {max_tokens}, Overlap ratio: {overlap_ratio}")
        
        if session_id not in _session_store:
            print(f"[CONFIRM] ERROR: Session '{session_id}' not found in session store")
            print(f"[CONFIRM] Available sessions: {list(_session_store.keys())}")
            raise HTTPException(status_code=404, detail="Session not found or expired")
        
        session = _session_store[session_id]
        document_id = session["document_id"]
        ocr_json = session["ocr_json"]
        
        print(f"\n{'='*60}")
        print(f"Step 2/3: Indexing document '{document_id}'")
        print(f"{'='*60}\n")
        
        # Create chunks
        print("[1/3] Creating chunks...")
        chunks_result = build_chunks(
            ocr_json=ocr_json,
            document_id=document_id,
            max_tokens=max_tokens,
            min_tokens=150,
            overlap_ratio=overlap_ratio,
            dry_run=False,
            output_dir=str(CHUNK_DIR_OUT),
        )
        
        chunk_file = CHUNK_DIR_OUT / f"{document_id}_chunks.json"
        chunk_count = chunks_result.get("chunk_count", 0)
        print(f"✓ Created {chunk_count} chunks\n")
        
        # Upload chunks to Ceph
        print(f"[2/3] Uploading chunks to Ceph '{BUCKET_CHUNKS}' bucket...")
        chunk_object = f"{document_id}_chunks.json"
        upload_result = upload_file(BUCKET_CHUNKS, str(chunk_file), chunk_object)
        print(f"✓ {upload_result}\n")
        
        # Embed and index
        print("[3/3] Embedding and indexing...")
        indexed_docs = index_chunks(str(chunk_file), upload=True)
        chunks_indexed = len(indexed_docs)
        print(f"✓ Indexed {chunks_indexed} chunks in OpenSearch\n")
        
        del _session_store[session_id]
        try:
            os.unlink(session["file_path"])
        except:
            pass
        
        print(f"{'='*60}")
        print(f"✓ Indexing completed successfully!")
        print(f"{'='*60}\n")
        
        return {
            "success": True,
            "session_id": session_id,
            "document_id": document_id,
            "chunks_created": chunk_count,
            "chunks_indexed": chunks_indexed,
            "storage": {
                "document_bucket": BUCKET_DOCS,
                "chunks_bucket": BUCKET_CHUNKS,
            },
            "message": "Document indexed successfully with user confirmation"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"✗ Indexing failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/pipeline/query")
async def query_docs(
    query_text: str = Query(...),
    top_k: int = Query(50),
    rerank_top_n: int = Query(5)
):
    """Query documents with hybrid search + reranking"""
    try:
        print(f"\n{'='*60}")
        print(f"[QUERY] Searching for: '{query_text[:80]}...'")
        print(f"[QUERY] Top K: {top_k}, Rerank Top N: {rerank_top_n}")
        print(f"{'='*60}\n")
        
        if not query_text.strip():
            return {"success": False, "message": "Empty query"}
            
        print("[1/3] Running hybrid search...")
        # Run search in a separate thread since it's blocking
        hits = await asyncio.to_thread(embed_search, query=query_text, top_k=top_k)
        print(f"✓ Found {len(hits)} raw candidates\n")
        
        if not hits:
            return {
                "success": True,
                "query": query_text,
                "totalHits": 0,
                "returnedCount": 0,
                "results": [],
                "message": "No results found"
            }
            
        print(f"[2/3] Reranking top {rerank_top_n} candidates...")
        candidates = await asyncio.to_thread(candidates_from_hits, hits)
        ranked = await asyncio.to_thread(rerank, query_text, candidates, top_n=rerank_top_n)
        print(f"✓ Reranking completed\n")
        
        print("[3/3] Resolving chunk metadata...")
        results = []
        for r in ranked:
            # Simple resolution for now, using document_id from chunk_id
            chunk_id = r.chunk_id
            parts = chunk_id.rsplit("_p", 1)
            document_id = parts[0] if len(parts) == 2 else chunk_id
            
            results.append({
                "rank": r.rank,
                "chunk_id": chunk_id,
                "document_id": document_id,
                "text": r.text,
                "score": r.score if hasattr(r, 'score') else None
            })
            
        print(f"✓ Return {len(results)} finalized results")
        print(f"{'='*60}\n")
        
        return {
            "success": True,
            "query": query_text,
            "totalHits": len(hits),
            "returnedCount": len(results),
            "results": results,
            "message": "Query completed successfully"
        }
    except Exception as e:
        print(f"✗ Query failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/pipeline/chunk/{chunk_id}")
async def get_chunk_details(chunk_id: str):
    """Retrieve chunk details (text, bbox, page, etc.) from Ceph bucket 'chunks'"""
    try:
        # Extract document_id from chunk_id
        # Chunk format: document_id_pPAGE_cINDEX
        parts = chunk_id.rsplit("_p", 1)
        document_id = parts[0] if len(parts) == 2 else chunk_id
        
        # Fetch the chunks file from Ceph
        chunks_file_name = f"{document_id}_chunks.json"
        
        try:
            stream = get_file_stream(BUCKET_CHUNKS, chunks_file_name)
            if not stream:
                raise HTTPException(status_code=404, detail=f"Chunks file for {document_id} not found")
            
            # Read stream into bytes
            chunks_data = b""
            for chunk in stream:
                chunks_data += chunk
            
            # Parse JSON
            chunks_json = json.loads(chunks_data.decode('utf-8'))
            
            # Find the specific chunk
            for chunk in chunks_json.get("chunks", []):
                if chunk["chunk_id"] == chunk_id:
                    return {
                        "success": True,
                        "chunk": chunk,
                        "message": "Chunk details retrieved successfully"
                    }
            
            raise HTTPException(status_code=404, detail=f"Chunk {chunk_id} not found in chunks file")
            
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=500, detail=f"Failed to parse chunks JSON: {str(e)}")
        except Exception as e:
            if isinstance(e, HTTPException):
                raise
            raise HTTPException(status_code=500, detail=f"Failed to retrieve chunk: {str(e)}")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving chunk details: {str(e)}")


@app.get("/pipeline/document/{document_id}")
async def get_document_image(document_id: str):
    """Retrieve original file bytes from Ceph bucket 'docs' for traceback visualization."""
    try:
        all_files = list_files(BUCKET_DOCS)
        if isinstance(all_files, str): # Error message returned
            print(f"[DEBUG] list_files error: {all_files}")
            all_files = []
    except Exception as e:
        print(f"[DEBUG] Error listing files: {e}")
        all_files = []
        
    target_file = None
    # 1. Exact match
    if document_id in all_files:
        target_file = document_id
    # 2. Prefix match
    if not target_file:
        for f in all_files:
            if f.startswith(f"{document_id}."):
                target_file = f
                break
    # 3. Base ID match
    if not target_file:
        base_id = Path(document_id).stem
        for f in all_files:
            if f == base_id or f.startswith(f"{base_id}."):
                target_file = f
                break
                
    if target_file:
        try:
            stream = get_file_stream(BUCKET_DOCS, target_file)
            if stream:
                ext = Path(target_file).suffix.lower()
                media_type = "application/pdf" if ext == ".pdf" else f"image/{ext[1:].replace('jpg', 'jpeg')}" if ext else "application/octet-stream"
                
                # Yield chunks to ensure FastAPI handles BytesIO correctly
                def iterfile():
                    stream.seek(0)
                    while chunk := stream.read(8192):
                        yield chunk
                        
                return StreamingResponse(iterfile(), media_type=media_type)
        except Exception as e:
            print(f"[DEBUG] Fetch failed for '{target_file}': {e}")
            
    raise HTTPException(status_code=404, detail=f"Document image for {document_id} not found in Ceph")

if __name__ == "__main__":
    print("\n" + "="*60)
    print("  Starting Pipeline Service on port 8082")
    print("="*60 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=8082)
