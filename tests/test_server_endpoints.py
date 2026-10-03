import os
import sys
import time

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from backend.main import app, load_and_index_documents

def test_endpoints():
    print("=== KIỂM THỬ TÍCH HỢP FASTAPI SERVER & SOLVER ===")
    # Nạp chỉ mục tài liệu
    load_and_index_documents()

    client = TestClient(app)

    # 1. Test /health
    print("\n1. GET /health")
    res_health = client.get("/health")
    assert res_health.status_code == 200
    data_health = res_health.json()
    print("Health response:", data_health)
    assert data_health["status"] == "online"
    assert data_health["indexed_chunks"] > 0

    # 2. Test /solve (Lần 1: Cache Miss -> BM25 + Solver)
    print("\n2. POST /solve (Lần 1: Chưa có cache)")
    payload = {
        "question": "Theo Kế hoạch số 244/KH-UBND, mục tiêu chung của công tác tuyên truyền CCHC là gì?",
        "options": [
            {"key": "A", "text": "Nâng cao nhận thức, trách nhiệm của cán bộ quản lý, công chức và sự đồng thuận của nhân dân"},
            {"key": "B", "text": "Cắt giảm 100% biên chế cấp xã"},
            {"key": "C", "text": "Dừng toàn bộ tiếp nhận thủ tục hành chính trực tiếp"},
            {"key": "D", "text": "Chuyển giao quyền quản lý cho doanh nghiệp tư nhân"}
        ]
    }

    t0 = time.perf_counter()
    res_solve = client.post("/solve", json=payload)
    latency_solve = (time.perf_counter() - t0) * 1000

    assert res_solve.status_code == 200
    data_solve = res_solve.json()
    print(f"Thời gian xử lý: {latency_solve:.2f} ms")
    print("Đáp án chọn:", data_solve["selected_key"])
    print("Độ tin cậy:", data_solve["confidence"])
    print("Ngữ cảnh trích xuất:", data_solve["matched_chunk"][:120], "...")
    print("Thời gian trễ đề xuất (Human Pacing):", data_solve["suggested_delay_ms"], "ms")
    print("From cache:", data_solve["from_cache"])

    assert data_solve["from_cache"] is False
    assert data_solve["selected_key"] == "A"
    assert 3000 <= data_solve["suggested_delay_ms"] <= 6000

    # 3. Test /solve (Lần 2: Cache Hit -> O(1))
    print("\n3. POST /solve (Lần 2: Cache Hit)")
    t1 = time.perf_counter()
    res_cache = client.post("/solve", json=payload)
    latency_cache = (time.perf_counter() - t1) * 1000

    assert res_cache.status_code == 200
    data_cache = res_cache.json()
    print(f"Thời gian xử lý Cache Hit: {latency_cache:.3f} ms (Target < 1.0ms)")
    print("From cache:", data_cache["from_cache"])
    assert data_cache["from_cache"] is True
    assert data_cache["selected_key"] == "A"

    # 4. Test /reload-docs
    print("\n4. POST /reload-docs")
    res_reload = client.post("/reload-docs")
    assert res_reload.status_code == 200
    data_reload = res_reload.json()
    print("Reload response:", data_reload)
    assert data_reload["status"] == "success"

    print("\n==================================================")
    print("TẤT CẢ ENDPOINT ĐÃ HOẠT ĐỘNG HOÀN TOÀN CHÍNH XÁC!")
    print("==================================================")

if __name__ == "__main__":
    test_endpoints()
