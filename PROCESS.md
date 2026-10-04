# HỆ THỐNG LOCAL RAG & QA AUTOMATION: SO SÁNH MODEL CỤC BỘ
## TÀI LIỆU CHUYỂN GIAO PHIÊN LÀM VIỆC (HANDOVER & PROCESS CONTINUATION)

> **Mục đích tài liệu:** tóm tắt trạng thái kỹ thuật, những gì đã làm trong phiên gần nhất, những gì chưa kiểm chứng và các bước tiếp theo, để phiên mới tiếp tục ngay mà không mất ngữ cảnh.
> **Cập nhật lần cuối:** 2026-10-04.

---

## 1. TỔNG QUAN

- **Mục tiêu**: pipeline kiểm thử tự động cho bài thi trắc nghiệm trực tuyến. Đọc câu hỏi và đáp án, tra tài liệu cục bộ, để LLM chạy cục bộ chọn đáp án.
- **Cơ chế cốt lõi**:
  1. Tra cứu **BM25 trong bộ nhớ** trên các văn bản ở `docs/` (không dùng cloud hay API ngoài).
  2. Suy luận bằng **Local LLM qua Ollama** (JSON schema, độ tin cậy lấy từ logprob). Nếu LLM lỗi hoặc timeout thì rơi về **heuristic fallback** (n-gram, số liệu, khoảng cách từ khóa) và có ghi log cảnh báo.
  3. Backend trả thêm `suggested_delay_ms` (Gauss 3–6 s) để client mô phỏng nhịp đọc.
- **Hai model hiện có trên máy**: `qwen2.5:3b` và `qwen2.5:7b` (Ollama 0.35.1). Phần cứng: GTX 1650 4 GB VRAM, RAM 23,7 GB.

---

## 2. TRẠNG THÁI HIỆN TẠI

### 2.1. Backend (`http://127.0.0.1:8000`)
- Đang chạy với model mặc định `qwen2.5:3b`. Chỉ mục 115 chunk (111 chunk cũ + 4 chunk header/chữ ký của 2 văn bản).
- Endpoint:
  - `GET /health`: trạng thái, model mặc định.
  - `GET /models`: danh sách model trên Ollama (mới, cho giao diện so sánh).
  - `POST /solve`: nhận `question`, `options` và **`model` tùy chọn** (mới). Trả `selected_key`, `confidence`, `matched_chunk`, `suggested_delay_ms`, `from_cache` và các trường mới `model`, `source` (`llm` hoặc `fallback`), `inference_ms`.
  - `POST /reload-docs`: nạp lại tài liệu và xóa cache.
- Cache LRU khóa theo (câu hỏi + đáp án + **model**), nên hai model không dùng chung kết quả.
- Khởi động: `python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000` (đặt `LLM_MODEL=<model>` để đổi model mặc định, `LLM_TIMEOUT_SECONDS` để đổi timeout).

### 2.2. Pipeline truy xuất và suy luận (đã sửa trong phiên này)
- `backend/config.py`: `LLM_TIMEOUT_SECONDS` mặc định **45 s** (trước là 1,1 s nên mọi lần gọi LLM đều timeout và luôn rơi vào heuristic).
- `backend/core/llm_runner.py`: LLM trả JSON schema chỉ có `selected_key` (enum theo các key hợp lệ), độ tin cậy là softmax logprob của token đáp án, prompt được viết lại, có `logger.warning` khi fallback, `solve(..., model=...)` cho phép ghi đè model theo từng lần gọi.
- `backend/core/parser.py`: thêm chunk **header** (số hiệu, ngày, tiêu đề) và chunk **chữ ký/nơi nhận** (sửa lỗi câu 1 "ai ký thay Chủ tịch").
- `backend/main.py`:
  - `retrieve_context`: truy vấn tổng + truy vấn riêng cho từng đáp án, hợp nhất RRF, lấy top 3.
  - Số hiệu văn bản trong câu hỏi (vd `244/KH-UBND`) bị loại khỏi truy vấn BM25 và chỉ dùng để **lọc đúng văn bản** (`detect_doc_hint`).
  - `expand_with_neighbor`: ghép chunk liền kề cùng mục để không cắt mất phần trả lời. Mỗi đoạn ngữ cảnh tối đa 1500 ký tự.

### 2.3. Giao diện so sánh hai model (`tests/mock_assessment_page.html`)
Trang được **thiết kế lại hoàn toàn** thành màn hình so sánh hai model:
- Chia hai bên: bên trái và bên phải mỗi bên chọn một model (danh sách lấy từ `/models`, mặc định 3b bên trái, 7b bên phải). Mỗi bên có điểm số lớn, bốn chỉ số (đã trả lời, thời gian TB, độ tin cậy TB, số câu dùng heuristic), thanh tiến độ, thẻ câu hỏi (đáp án đúng và lựa chọn của model được tô màu, có đoạn tài liệu model đã đọc) và **phiếu trả lời 30 ô** (bấm một ô để xem lại câu đó).
- Điều khiển: chạy **Lần lượt** (mặc định) hoặc **Song song**; nhịp **Nhanh** hoặc **Nhịp người (3–6 s/câu)**; nút Bắt đầu, Làm lại. Trước khi chạy trang nạp sẵn model và gọi `/reload-docs` để thời gian đo không dính lần nạp model hay cache.
- Sau khi cả hai bên xong, trang hiển thị phần **đánh giá**: kết luận bên nào chính xác hơn (hoặc hòa kèm so sánh tốc độ), biểu đồ thanh cho 5 chỉ số, danh sách các câu hai model khác nhau hoặc sai, bảng từng câu, nút Chạy lại và Tải kết quả (.json).
- **File này được sinh ra, đừng sửa trực tiếp.** Nguồn là `tests/mock_assessment_page.template.html` (giao diện và JS) cộng 30 câu hỏi. Sau khi sửa mẫu, chạy `python tests/build_mock_page.py` để ghi lại `mock_assessment_page.html`.
- Dữ liệu 30 câu = 5 câu trong `tests/test_multi_questions.py` + 25 câu trong `tests/eval_set.json`.
- **Đã bỏ khỏi trang:** Behavioral Telemetry Monitor và các selector cũ mà `client/quiz_agent.user.js` dùng. Userscript vẫn khớp `file:///*` nhưng sẽ không điều khiển được trang mới. Trang mới tự chạy bằng JS nội bộ, gọi `/solve` bằng `fetch` (CORS đã bật).
- Mở trang: cần backend chạy ở cổng 8000. Có thể mở trực tiếp file hoặc phục vụ qua `python -m http.server 8791` trong thư mục `tests/`, rồi vào `http://127.0.0.1:8791/mock_assessment_page.html`. Tham số `?api=<url>` đổi địa chỉ backend.

### 2.4. Đã kiểm chứng và chưa kiểm chứng
- **Đã kiểm chứng:** API `/models` và `/solve` với `model`; trang tải không lỗi (chỉ 404 favicon); bố cục hai bên, thẻ câu hỏi, phiếu trả lời, chỉ số trực tiếp (chụp màn hình trong lúc chạy); chạy lần lượt tới câu 24/30 của bên trái, điểm 23/24, TB ~6 s/câu.
- **Chưa kiểm chứng:** một lượt chạy trọn 30 câu hai bên và **màn hình đánh giá cuối** chưa được xem tận mắt (phiên bị ngắt khi bên trái 24/30, bên phải 0/30). Cần chạy lại trọn một lượt, kiểm tra phần kết quả, bố cục trên màn hình hẹp và tải JSON.
- **Phát hiện về phần cứng:** chạy **Song song** làm mỗi câu mất ~30 s ở cả hai bên (GPU 4 GB không chứa nổi cả hai model, Ollama phải đổi model). Chạy riêng 3b khoảng 4–6 s/câu, 7b khoảng 10–13 s/câu. Vì vậy chế độ mặc định là Lần lượt.

### 2.5. Tiến trình nền có thể còn chạy
- Backend uvicorn ở cổng 8000.
- `python -m http.server` ở cổng 8791 (thư mục `tests/`, chỉ phục vụ để xem trang). Cổng 8765 trả 401 vì có dịch vụ khác chiếm, đừng dùng.
- Trình duyệt Playwright còn mở trang so sánh. Ảnh chụp nằm trong `.playwright-mcp/` (có thể xóa).

### 2.6. Trạng thái Git
- Commit gần nhất: `7b95337 feat: multi-question quiz flow, enhanced heuristic solver, and session handover document`.
- **Chưa commit** các thay đổi của phiên này: `backend/config.py`, `backend/core/llm_runner.py`, `backend/core/parser.py`, `backend/main.py`, `tests/test_multi_questions.py` (timeout client 5 s lên 120 s), `PROCESS.md`, và các file mới `tests/eval_bench.py`, `tests/eval_set.json`, `tests/build_mock_page.py`, `tests/mock_assessment_page.template.html`, cùng `tests/mock_assessment_page.html` đã được sinh lại.
- `backend/core/__pycache__/*.pyc` và `tests/__pycache__/` đang bị theo dõi hoặc hiện ở trạng thái chưa theo dõi. Nên thêm `__pycache__/` vào `.gitignore` rồi gỡ `.pyc` khỏi chỉ mục (`git rm -r --cached`).

---

## 3. CẤU TRÚC THƯ MỤC

```text
backend/
  config.py                 # Host, port, timeout LLM (45 s), pacing
  main.py                   # FastAPI: /solve /models /health /reload-docs; retrieve_context, lọc văn bản, ghép chunk kề
  core/
    normalizer.py           # Mở rộng từ viết tắt TTHC/CCHC, token hóa
    parser.py               # Chia chunk theo Điều/Khoản + chunk header + chunk chữ ký
    bm25_index.py           # Okapi BM25 trong bộ nhớ + LRU cache
    llm_runner.py           # Gọi Ollama (JSON schema, logprob) + heuristic fallback
  data/synonyms.json
client/
  quiz_agent.user.js        # Userscript Tampermonkey (không còn khớp selector của trang so sánh)
  src/                      # config.js, pacing.js, event_dispatcher.js
docs/                       # 1963.QD.UBND...md, 244.KH.UBND...md
tests/
  mock_assessment_page.template.html   # NGUỒN giao diện so sánh hai model
  mock_assessment_page.html            # SINH RA bởi build_mock_page.py, đừng sửa tay
  build_mock_page.py                   # Ghép mẫu + 30 câu hỏi thành trang HTML
  eval_set.json                        # 25 câu hỏi bổ sung (có đáp án chuẩn, trường doc)
  eval_bench.py                        # Chấm 30 câu qua /solve, in đúng/sai và thời gian
  test_multi_questions.py              # 5 câu gốc (QUESTIONS) + chạy nhanh
  test_chunker_and_bm25.py, test_server_endpoints.py
SPEC.md, README.md, PROCESS.md
```

---

## 4. KẾT QUẢ ĐÁNH GIÁ

Chạy: `python tests/eval_bench.py` (cần backend chạy; chọn model bằng `LLM_MODEL=<model>` khi khởi động server, hoặc xem so sánh trực quan ở trang mới).

| Giai đoạn | qwen2.5:3b | qwen2.5:7b |
|---|---|---|
| Ban đầu (5 câu, timeout 1,1 s nên luôn rơi vào heuristic) | 2/5 | 3/5 |
| Sau sửa LLM (schema + logprob, timeout 45 s) + chunk chữ ký/header + truy vấn theo đáp án (5 câu) | 5/5 | 5/5 |
| Bộ 30 câu, trước khi lọc văn bản + ghép chunk kề | 25/30 | 27/30 |
| Bộ 30 câu, sau khi lọc theo số hiệu văn bản, bỏ số hiệu khỏi truy vấn BM25, ghép chunk kề | **29/30** (~5 s/câu) | **30/30** (~13 s/câu) |

- Câu còn sai của 3b là **n08** (đơn vị chủ trì tham mưu kinh phí của xã Đại Lộc: chọn B, đúng là D "Phòng Kinh tế", tin cậy 0,76).
- Bộ 30 câu do chính nhóm soạn từ hai văn bản trong `docs/`, và pipeline đã được chỉnh dựa trên các câu sai, nên điểm số lạc quan hơn so với câu hỏi lạ.
- Cơ chế lọc văn bản chỉ hoạt động khi câu hỏi nêu số hiệu dạng `244/KH`. Câu chỉ ghi "xã Đại Lộc" thì chưa được lọc.

---

## 5. VIỆC CẦN LÀM TIẾP

1. **Kiểm chứng giao diện đầy đủ:** bật backend, mở trang, bấm Bắt đầu ở chế độ Lần lượt (cả lượt mất khoảng 9–10 phút với 3b + 7b), xem màn hình đánh giá cuối, thử màn hình hẹp, thử Tải kết quả (.json), thử chế độ Nhịp người. Sửa lỗi nếu có (sửa `tests/mock_assessment_page.template.html` rồi chạy `build_mock_page.py`).
2. **Commit** theo nhóm: (a) backend và pipeline, (b) bộ đánh giá, (c) trang so sánh. Thêm `.gitignore` cho `__pycache__/` và `.playwright-mcp/`.
3. **Cải thiện độ chính xác** nếu cần: hybrid retrieval (embedding như `bge-m3`) + reranker, thử Qwen3-8B, lọc văn bản theo tên đơn vị ("xã Đại Lộc", "thành phố"), mở rộng bộ đánh giá bằng câu hỏi diễn đạt khác từ khóa. Câu "gây nhiễu" kiểu n08 vẫn là điểm yếu của 3b.
4. **Quyết định còn mở:** có khôi phục Telemetry Monitor và khả năng chạy bằng userscript trên một trang riêng hay không (trang cũ đã bị thay hoàn toàn).
5. Khi thêm tài liệu vào `docs/`: gọi `POST /reload-docs`, và nhớ rằng chunk header/chữ ký được sinh tự động cho mọi file `.md`/`.txt`.

---

## 6. LƯU Ý KỸ THUẬT CHO PHIÊN SAU

- **Không dùng `python - <<EOF` (heredoc) để sửa file có dấu gạch chéo ngược hoặc xuống dòng.** Trong môi trường này `\n`, `\b`, `\d` trong chuỗi bị biến dạng (xuống dòng thật hoặc ký tự điều khiển), làm hỏng regex và chuỗi. Hãy dùng công cụ Edit/Write. `sed` cũng làm mất dấu gạch chéo ngược.
- `backend/main.py` đang lẫn kết thúc dòng CRLF và LF. Python vẫn chạy bình thường.
- Console Windows dùng cp1252: chạy script in tiếng Việt với `PYTHONIOENCODING=utf-8`. `curl` với dữ liệu tiếng Việt qua shell có thể báo "error parsing the body"; hãy dùng Python `requests` để thử API.
- Playwright MCP chỉ lưu ảnh trong thư mục dự án (ví dụ `.playwright-mcp/`). `browser_wait_for` với `text` bị timeout 5 s, nên dùng `time` hoặc đọc trạng thái bằng `browser_evaluate`.
- Dừng backend trên Windows: `Get-NetTCPConnection -LocalPort 8000 -State Listen | % { Stop-Process -Id $_.OwningProcess -Force }` (PowerShell).
