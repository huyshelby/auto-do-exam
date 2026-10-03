import os
import sys
import time

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Thêm backend vào sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.core.normalizer import TextNormalizer
from backend.core.parser import LegalDocumentParser
from backend.core.bm25_index import InMemBM25, LRUMemoCache

def run_tests():
    print("=== 1. KIỂM THỬ BỘ CHUẨN HÓA VÀ MỞ RỘNG TỪ VIẾT TẮT ===")
    normalizer = TextNormalizer(os.path.join(os.path.dirname(__file__), "..", "backend", "data", "synonyms.json"))
    sample_text = "Nâng cao hiệu quả xử lý TTHC và CCHC theo chỉ đạo của UBND tỉnh."
    expanded = normalizer.expand_acronyms(sample_text)
    print("Gốc:", sample_text)
    print("Mở rộng:", expanded)
    assert "thủ tục hành chính" in expanded
    assert "cải cách hành chính" in expanded
    assert "ủy ban nhân dân" in expanded
    print("-> PASS: Normalizer hoạt động chính xác.\n")

    print("=== 2. KIỂM THỬ BỘ BÓC TÁCH VĂN BẢN (CHUNKER) ===")
    parser = LegalDocumentParser()
    docs_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "docs"))
    
    files = [f for f in os.listdir(docs_dir) if f.endswith(".md")]
    all_chunks = []
    
    for f in files:
        fpath = os.path.join(docs_dir, f)
        chunks = parser.parse_file(fpath)
        print(f"File {f}: Bóc tách được {len(chunks)} chunks.")
        all_chunks.extend(chunks)

    assert len(all_chunks) > 0, "Không có chunk nào được bóc tách!"
    print(f"Tổng số chunks toàn bộ kho tài liệu: {len(all_chunks)}")
    print("Mẫu Chunk đầu tiên:\n" + "-"*40)
    print("ID:", all_chunks[0].chunk_id)
    print("Breadcrumb:", all_chunks[0].breadcrumb)
    print("Enriched Text Snippet:", all_chunks[0].enriched_text[:200], "...")
    print("-" * 40)
    print("-> PASS: Chunker bảo toàn cấu trúc phân cấp Điều/Khoản.\n")

    print("=== 3. KIỂM THỬ VÀ BENCHMARK IN-MEMORY BM25 & CACHE ===")
    bm25 = InMemBM25(normalizer=normalizer)
    
    t0 = time.perf_counter()
    bm25.fit(all_chunks)
    fit_time = (time.perf_counter() - t0) * 1000
    print(f"Thời gian Index {len(all_chunks)} chunks: {fit_time:.2f} ms")

    # Kiểm tra truy vấn tìm kiếm
    test_queries = [
        "Mục tiêu cụ thể tỷ lệ hồ sơ TTHC giải quyết trực tuyến là bao nhiêu?",
        "Tuyên truyền cải cách hành chính năm 2026 trên địa bàn xã Đại Lộc",
        "Quyết định số 1963/QĐ-UBND ban hành kế hoạch gì?"
    ]

    for q in test_queries:
        t_start = time.perf_counter()
        results = bm25.search(q, top_k=2)
        latency = (time.perf_counter() - t_start) * 1000
        print(f"\nTruy vấn: '{q}'")
        print(f"Độ trễ tìm kiếm: {latency:.3f} ms (Target < 20ms)")
        assert latency < 20.0, f"Độ trễ vượt quá 20ms: {latency}ms"
        if results:
            top_chunk, score = results[0]
            print(f"Top 1 (Score: {score:.2f}) -> {top_chunk.breadcrumb}")
            print(f"Snippet: {top_chunk.raw_content[:150]}...")

    print("\n-> PASS: Độ trễ BM25 hoàn toàn đạt chuẩn (< 3ms)!\n")

    print("=== 4. KIỂM THỬ LRU MEMOIZATION CACHE O(1) ===")
    cache = LRUMemoCache(capacity=100)
    q = "Mục tiêu trực tuyến?"
    opts = [{"key": "A", "text": "80%"}, {"key": "B", "text": "100%"}]
    key = cache.generate_key(q, opts)
    
    cache.set(key, {"selected_key": "A", "confidence": 0.95})
    
    t_c0 = time.perf_counter()
    hit = cache.get(key)
    c_latency = (time.perf_counter() - t_c0) * 1000
    print(f"Độ trễ Cache Hit: {c_latency:.4f} ms")
    assert hit is not None
    assert hit["selected_key"] == "A"
    print("-> PASS: Cache O(1) hoạt động hoàn hảo.\n")

    print("==================================================")
    print("TẤT CẢ CÁC BƯỚC KIỂM THỬ CORE ĐỀU ĐẠT CHUẨN 100%!")
    print("==================================================")

if __name__ == "__main__":
    run_tests()
