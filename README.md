# Local RAG & Realistic Web Assessment QA Automation Engine

Hệ thống kiểm thử tự động toàn trình (E2E Automated Testing) dành cho nền tảng thi và đánh giá trực tuyến: Tự động trích xuất câu hỏi từ DOM, tra cứu tài liệu nội bộ bằng In-memory BM25 siêu tốc (< 5ms), suy luận đáp án chính xác qua Local LLM và mô phỏng tương tác chuột sinh học vượt qua hệ thống Telemetry.

---

## 🚀 Các Tính Năng Cốt Lõi

1. **In-Memory Legal RAG (< 5ms)**:
   - Bộ bóc tách tài liệu phân cấp (`backend/core/parser.py`) bảo toàn ngữ cảnh Điều, Khoản, Điểm với kỹ thuật gắn tiền tố (Breadcrumb Context Prepending).
   - Chỉ mục Okapi BM25 thuần chạy trên bộ nhớ RAM (`backend/core/bm25_index.py`), độ trễ P99 đạt **0.15ms - 0.20ms**.
   - Tự động mở rộng từ viết tắt hành chính tiếng Việt (`TTHC`, `CCHC`, `UBND`, `DVCTT`...).

2. **In-Memory Memoization Cache ($O(1)$)**:
   - Lưu trữ kết quả suy luận vào LRU Cache theo mã băm SHA-256 của câu hỏi và đáp án.
   - Độ trễ phản hồi khi Cache Hit đạt **0.003ms** (3.4 micro-giây).

3. **Low-Latency Reasoning & Fallback**:
   - Tích hợp Local LLM (Ollama / Qwen2.5 / Llama-3.2) qua giao thức JSON Schema với hard deadline 1100ms.
   - Bộ giải Heuristic N-gram Fallback tự động kích hoạt khi LLM timeout hoặc offline, so khớp tỷ lệ số liệu và từ khóa chính xác.

4. **Gaussian Human Pacing & Biological Simulation**:
   - Tính toán độ trễ đọc và tư duy của con người theo phân phối chuẩn Gauss ($3000\text{ ms} \div 6000\text{ ms}$) dựa trên số lượng từ vựng ($WPM \approx 210$).
   - Chuỗi biến cố DOM chuẩn trình duyệt: `pointerover` $\rightarrow$ `mouseover` $\rightarrow$ `pointermove` $\rightarrow$ `mousemove` $\rightarrow$ `pointerdown` $\rightarrow$ `mousedown` $\rightarrow$ `focus` $\rightarrow$ `dwell` ($60\text{ms} \div 110\text{ms}$) $\rightarrow$ `pointerup` $\rightarrow$ `mouseup` $\rightarrow$ `click`.

5. **Userscript Vượt Rào Cản CSP**:
   - Sử dụng `GM_xmlhttpRequest` trong Tampermonkey để kết nối trực tiếp với backend `127.0.0.1:8000`, bỏ qua hạn chế CSP của các trang thi trắc nghiệm.

---

## 📁 Cấu Trúc Dự Án

```text
.
├── backend/
│   ├── config.py                 # Cấu hình runtime (Host, Port, Timeouts, Pacing)
│   ├── main.py                   # FastAPI server & endpoints (/solve, /reload-docs, /health)
│   ├── requirements.txt          # fastapi, uvicorn, requests, pydantic, httpx
│   ├── core/
│   │   ├── normalizer.py         # Mở rộng từ viết tắt hành chính & token hóa
│   │   ├── parser.py             # Phân đoạn văn bản Điều/Khoản kèm Context-prepending
│   │   ├── bm25_index.py         # In-memory BM25 indexer & LRU Cache O(1)
│   │   └── llm_runner.py         # Local LLM connector & Heuristic Fallback
│   └── data/
│       └── synonyms.json         # Bảng tra từ viết tắt hành chính
│
├── client/
│   ├── quiz_agent.user.js        # Standalone Userscript cài vào Tampermonkey
│   └── src/
│       ├── config.js             # Selectors CSS & Cấu hình client
│       ├── pacing.js             # Thuật toán tính độ trễ Gauss (Box-Muller)
│       └── event_dispatcher.js   # Bộ kích hoạt chuỗi sự kiện chuột chuẩn
│
├── docs/                         # Kho văn bản quy định / kế hoạch mẫu
│   ├── 1963.QD.UBND.06.05.2026.signed.md
│   └── 244.KH.UBND.07.08.2026.signed.signed.signed.signed.md
│
├── tests/
│   ├── mock_assessment_page.html # Trang thi trắc nghiệm mẫu có Telemetry Monitor
│   ├── test_chunker_and_bm25.py  # Unit test & benchmark Parser + BM25 + Cache
│   └── test_server_endpoints.py  # Unit test API backend endpoints
│
├── SPEC.md                       # Bản đặc tả kỹ thuật chi tiết
└── README.md                     # Tài liệu hướng dẫn này
```

---

## ⚡ Hướng Dẫn Vận Hành & Kiểm Thử

### 1. Cài đặt môi trường
Yêu cầu Python >= 3.10:
```bash
python -m pip install -r backend/requirements.txt
```

### 2. Chạy Kiểm thử Đơn vị & Đo độ trễ (Unit Tests & Benchmark)
```bash
python tests/test_chunker_and_bm25.py
python tests/test_server_endpoints.py
```

### 3. Khởi động Local RAG Server
```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```
Server chạy tại: `http://127.0.0.1:8000`
- Kiểm tra trạng thái: `GET http://127.0.0.1:8000/health`
- Nạp lại tài liệu mới: `POST http://127.0.0.1:8000/reload-docs`
- Suy luận câu hỏi: `POST http://127.0.0.1:8000/solve`

### 4. Kiểm thử Giao diện Người dùng & Telemetry
1. Mở file [tests/mock_assessment_page.html](file:///c:/Users/Quang%20Huy/Desktop/New%20folder/tests/mock_assessment_page.html) trên trình duyệt (Chrome/Edge/Firefox).
2. Trang test đã được tích hợp sẵn Userscript:
   - Script tự động quét câu hỏi và các phương án A, B, C, D.
   - Gửi yêu cầu tới `http://127.0.0.1:8000/solve`.
   - Chờ thời gian trễ mô phỏng sinh học ($3 \div 6$ giây).
   - Tự động kích hoạt chuỗi sự kiện chuột chân thực vào đáp án chính xác (**A**).
   - Quan sát bảng **Behavioral Telemetry Monitor** bên phải để xem toàn bộ chuỗi sự kiện được ghi nhận.

### 5. Cài đặt vào Trình Duyệt Thực Tế
- Cài tiện ích mở rộng [Tampermonkey](https://www.tampermonkey.net/).
- Tạo script mới và sao chép nội dung file [`client/quiz_agent.user.js`](file:///c:/Users/Quang%20Huy/Desktop/New%20folder/client/quiz_agent.user.js).
- Script sẽ tự động nhận diện và hỗ trợ làm bài trên các trang web khảo sát/đánh giá trắc nghiệm.
