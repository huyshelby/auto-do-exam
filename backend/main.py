import os
import re
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
    model: Optional[str] = Field(None, description="Model Ollama dùng cho riêng yêu cầu này (mặc định: LLM_MODEL)")

class SolveResponse(BaseModel):
    selected_key: str = Field(..., description="Phương án được chọn")
    confidence: float = Field(..., description="Mức độ tin cậy của đáp án (0.0 - 1.0)")
    matched_chunk: str = Field(..., description="Trích đoạn ngữ cảnh tài liệu khớp nhất")
    suggested_delay_ms: int = Field(..., description="Thời gian trễ mô phỏng hành vi đọc con người (ms)")
    from_cache: bool = Field(False, description="Kết quả được lấy trực tiếp từ In-memory Cache")
    model: str = Field("", description="Model đã xử lý yêu cầu")
    source: str = Field("llm", description="'llm' nếu model trả lời, 'fallback' nếu phải dùng heuristic")
    inference_ms: int = Field(0, description="Tổng thời gian truy xuất + suy luận phía server (ms)")

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

RE_DOC_REF = re.compile(r"\b(\d{1,5})\s*/\s*[\wĐđ-]+", re.UNICODE)

def detect_doc_hint(question: str) -> List[str]:
    """Số hiệu văn bản trong câu hỏi (vd '244/KH-UBND' -> '244') -> các file docs/ có tên bắt đầu bằng số đó."""
    nums = {m.group(1) for m in RE_DOC_REF.finditer(question)}
    names = {c.doc_name for c in bm25_engine.chunks}
    return sorted(n for n in names if any(n.startswith(num + ".") for num in nums))

def retrieve_context(question: str, options: List[dict], top_k: int = 3, per_query_k: int = 8, rrf_k: int = 60):
    """
    Truy xuất đa truy vấn: 1 truy vấn tổng (câu hỏi + mọi đáp án) và 1 truy vấn riêng cho từng đáp án
    (câu hỏi + đáp án đó), hợp nhất bằng Reciprocal Rank Fusion để mỗi đáp án đều có bằng chứng riêng.
    - Số hiệu văn bản bị loại khỏi truy vấn (nó kéo về các chunk Căn cứ/tiêu đề) và chỉ dùng để lọc đúng văn bản.
    - Chunk liền kề cùng mục được ghép thêm để không cắt mất phần trả lời nằm ở chunk sau.
    """
    clean_q = RE_DOC_REF.sub(" ", question)
    queries = [clean_q + " " + " ".join(o["text"] for o in options)]
    queries += [f"{clean_q} {o['text']}" for o in options]
    allowed_docs = set(detect_doc_hint(question))

    fused: Dict[str, float] = {}
    by_id: Dict[str, DocumentChunk] = {}
    for qi, q in enumerate(queries):
        weight = 1.5 if qi == 0 else 1.0
        hits = [h for h in bm25_engine.search(q, top_k=per_query_k) if not allowed_docs or h[0].doc_name in allowed_docs]
        for rank, (chunk, _score) in enumerate(hits):
            by_id[chunk.chunk_id] = chunk
            fused[chunk.chunk_id] = fused.get(chunk.chunk_id, 0.0) + weight / (rrf_k + rank + 1)

    ranked = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
    return [expand_with_neighbor(by_id[cid]) for cid, _ in ranked]

def expand_with_neighbor(chunk: DocumentChunk) -> DocumentChunk:
    """Ghép chunk kế tiếp nếu cùng văn bản và cùng mục (level_2) với chunk được chọn."""
    chunks = bm25_engine.chunks
    idx = next((i for i, c in enumerate(chunks) if c.chunk_id == chunk.chunk_id), -1)
    if idx < 0 or idx + 1 >= len(chunks):
        return chunk
    nxt = chunks[idx + 1]
    same_section = (
        nxt.doc_name == chunk.doc_name
        and nxt.metadata.get("level_2") == chunk.metadata.get("level_2")
        and nxt.metadata.get("level_1") == chunk.metadata.get("level_1")
        and not nxt.metadata.get("kind")
        and not chunk.metadata.get("kind")
    )
    if not same_section:
        return chunk
    merged = chunk.model_copy()
    merged.enriched_text = chunk.enriched_text + "\n" + nxt.raw_content
    return merged

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
    model_name = req.model or LLM_MODEL
    t_start = time.perf_counter()
    cache_key = cache_engine.generate_key(req.question, options_dict) + "|" + model_name
    cached_val = cache_engine.get(cache_key)
    if cached_val:
        return SolveResponse(
            selected_key=cached_val["selected_key"],
            confidence=cached_val["confidence"],
            matched_chunk=cached_val["matched_chunk"],
            suggested_delay_ms=cached_val["suggested_delay_ms"],
            from_cache=True,
            model=model_name,
            source=cached_val.get("source", "llm"),
            inference_ms=cached_val.get("inference_ms", 0)
        )

    # 2. In-memory BM25 Retrieval
    retrieved = retrieve_context(req.question, options_dict)

    if retrieved:
        context_text = "\n\n".join(f"[Đoạn {i}] {c.enriched_text[:1500]}" for i, c in enumerate(retrieved, 1))
    else:
        context_text = "Không tìm thấy dữ liệu đối chiếu trong kho tài liệu."

    # 3. Suy luận AI (Local LLM / Heuristic Fallback)
    selected_key, confidence, matched_fact = reasoning_engine.solve(
        question=req.question,
        options=options_dict,
        context_text=context_text,
        model=model_name
    )
    source = "llm" if matched_fact.startswith("LLM ") else "fallback"
    inference_ms = int((time.perf_counter() - t_start) * 1000)

    # 4. Tính toán thời gian trễ mô phỏng đọc tự nhiên
    full_text_to_read = req.question + " " + " ".join(f"{o.key} {o.text}" for o in req.options)
    suggested_delay = reasoning_engine.calculate_gaussian_delay(full_text_to_read)

    result_data = {
        "selected_key": selected_key,
        "confidence": round(confidence, 2),
        "matched_chunk": context_text[:300],
        "suggested_delay_ms": suggested_delay,
        "source": source,
        "inference_ms": inference_ms
    }

    # Lưu vào Cache LRU
    cache_engine.set(cache_key, result_data)

    return SolveResponse(
        selected_key=result_data["selected_key"],
        confidence=result_data["confidence"],
        matched_chunk=result_data["matched_chunk"],
        suggested_delay_ms=result_data["suggested_delay_ms"],
        from_cache=False,
        model=model_name,
        source=source,
        inference_ms=inference_ms
    )

@app.get("/models")
def list_models():
    """Danh sách model đang có trên Ollama (cho giao diện so sánh)."""
    import requests
    tags_url = OLLAMA_API_URL.replace("/api/generate", "/api/tags")
    try:
        data = requests.get(tags_url, timeout=3).json()
        names = sorted(m["name"] for m in data.get("models", []))
    except Exception:
        names = []
    return {"default": LLM_MODEL, "models": names}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=SERVER_HOST, port=SERVER_PORT, reload=False)
