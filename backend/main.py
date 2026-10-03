import os
import sys
import time

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .config import (
    DOCS_DIR,
    SYNONYMS_FILE,
    SERVER_HOST,
    SERVER_PORT,
    OLLAMA_API_URL,
    LLM_MODEL
)
from .core.normalizer import TextNormalizer
from .core.parser import LegalDocumentParser, DocumentChunk
from .core.bm25_index import InMemBM25, LRUMemoCache
from .core.llm_runner import LLMReasoningEngine

app = FastAPI(
    title="Low-Latency Local Legal RAG & Realistic QA Engine",
    description="Pipeline RAG cục bộ phục vụ kiểm thử tự động với mô phỏng nhịp độ sinh học con người.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------- SCHEMAS -----------------
class OptionItem(BaseModel):
    key: str = Field(..., description="Ký tự định danh đáp án (A, B, C, D...)")
    text: str = Field(..., description="Nội dung đáp án")

class SolveRequest(BaseModel):
    question: str = Field(..., description="Nội dung câu hỏi trắc nghiệm")
    options: List[OptionItem] = Field(..., description="Danh sách các phương án trả lời")

class SolveResponse(BaseModel):
    selected_key: str = Field(..., description="Phương án được chọn")
    confidence: float = Field(..., description="Mức độ tin cậy của đáp án (0.0 - 1.0)")
    matched_chunk: str = Field(..., description="Trích đoạn ngữ cảnh tài liệu khớp nhất")
    suggested_delay_ms: int = Field(..., description="Thời gian trễ mô phỏng hành vi đọc con người (ms)")
    from_cache: bool = Field(False, description="Kết quả được lấy trực tiếp từ In-memory Cache")

class ReloadDocsResponse(BaseModel):
    status: str
    indexed_chunks_count: int
    elapsed_ms: float

# ----------------- APPLICATION STATE -----------------
normalizer = TextNormalizer(SYNONYMS_FILE)
parser = LegalDocumentParser()
bm25_engine = InMemBM25(normalizer=normalizer)
cache_engine = LRUMemoCache(capacity=2000)
reasoning_engine = LLMReasoningEngine()
start_time = time.time()

def load_and_index_documents():
    """Đọc toàn bộ file trong docs/ và lập chỉ mục In-memory BM25."""
    t0 = time.perf_counter()
    all_chunks: List[DocumentChunk] = []

    if os.path.exists(DOCS_DIR):
        for fname in os.listdir(DOCS_DIR):
            if fname.endswith(".md") or fname.endswith(".txt"):
                fpath = os.path.join(DOCS_DIR, fname)
                try:
                    file_chunks = parser.parse_file(fpath)
                    all_chunks.extend(file_chunks)
                except Exception as e:
                    print(f"[Error] Không thể parse file {fname}: {e}")

    if not all_chunks:
        # Fallback chunk mặc định nếu docs/ trống
        default_chunk = DocumentChunk(
            chunk_id="default_001",
            doc_name="default",
            breadcrumb="[Default Policy]",
            raw_content="Chính sách mặc định của hệ thống kiểm thử.",
            enriched_text="[Default Policy] Chính sách mặc định của hệ thống kiểm thử."
        )
        all_chunks.append(default_chunk)

    bm25_engine.fit(all_chunks)
    cache_engine.clear()
    elapsed = (time.perf_counter() - t0) * 1000
    print(f"[Init] Đã lập chỉ mục {len(all_chunks)} chunks trong {elapsed:.2f} ms.")
    return len(all_chunks), elapsed

@app.on_event("startup")
def startup_event():
    load_and_index_documents()

# ----------------- API ENDPOINTS -----------------
@app.get("/health")
def get_health():
    return {
        "status": "online",
        "uptime_seconds": round(time.time() - start_time, 2),
        "indexed_chunks": bm25_engine.n_docs,
        "cached_entries": len(cache_engine.cache),
        "llm_model": LLM_MODEL,
        "ollama_endpoint": OLLAMA_API_URL
    }

@app.post("/reload-docs", response_model=ReloadDocsResponse)
def reload_documents():
    chunks_count, elapsed = load_and_index_documents()
    return ReloadDocsResponse(
        status="success",
        indexed_chunks_count=chunks_count,
        elapsed_ms=round(elapsed, 2)
    )

@app.post("/solve", response_model=SolveResponse)
def solve(req: SolveRequest):
    if not req.options:
        raise HTTPException(status_code=400, detail="Danh sách phương án không được rỗng.")

    options_dict = [{"key": opt.key, "text": opt.text} for opt in req.options]

    # 1. Tra cứu Cache O(1)
    cache_key = cache_engine.generate_key(req.question, options_dict)
    cached_val = cache_engine.get(cache_key)
    if cached_val:
        return SolveResponse(
            selected_key=cached_val["selected_key"],
            confidence=cached_val["confidence"],
            matched_chunk=cached_val["matched_chunk"],
            suggested_delay_ms=cached_val["suggested_delay_ms"],
            from_cache=True
        )

    # 2. In-memory BM25 Retrieval
    search_query = req.question + " " + " ".join(opt.text for opt in req.options)
    retrieved = bm25_engine.search(search_query, top_k=2)

    if retrieved:
        top_chunk, score = retrieved[0]
        context_text = top_chunk.enriched_text
    else:
        context_text = "Không tìm thấy dữ liệu đối chiếu trong kho tài liệu."

    # 3. Suy luận AI (Local LLM / Heuristic Fallback)
    selected_key, confidence, matched_fact = reasoning_engine.solve(
        question=req.question,
        options=options_dict,
        context_text=context_text
    )

    # 4. Tính toán thời gian trễ mô phỏng đọc tự nhiên
    full_text_to_read = req.question + " " + " ".join(f"{o.key} {o.text}" for o in req.options)
    suggested_delay = reasoning_engine.calculate_gaussian_delay(full_text_to_read)

    result_data = {
        "selected_key": selected_key,
        "confidence": round(confidence, 2),
        "matched_chunk": context_text[:300],
        "suggested_delay_ms": suggested_delay
    }

    # Lưu vào Cache LRU
    cache_engine.set(cache_key, result_data)

    return SolveResponse(
        selected_key=result_data["selected_key"],
        confidence=result_data["confidence"],
        matched_chunk=result_data["matched_chunk"],
        suggested_delay_ms=result_data["suggested_delay_ms"],
        from_cache=False
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=SERVER_HOST, port=SERVER_PORT, reload=False)
