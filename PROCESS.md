# HỆ THỐNG LOCAL RAG & QA AUTOMATION: SO SÁNH MODEL CỤC BỘ
## TÀI LIỆU CHUYỂN GIAO PHIÊN LÀM VIỆC (HANDOVER & PROCESS CONTINUATION)

> **Mục đích tài liệu:** tóm tắt trạng thái kỹ thuật, những gì đã làm trong phiên gần nhất, những gì chưa kiểm chứng và các bước tiếp theo, để phiên mới tiếp tục ngay mà không mất ngữ cảnh.
> **Cập nhật lần cuối:** 2026-10-05 (nội dung phiên làm việc ngày 2026-10-04).

---

## 1. TỔNG QUAN

- **Mục tiêu**: pipeline kiểm thử tự động cho bài thi trắc nghiệm trực tuyến. Đọc câu hỏi và đáp án, tra tài liệu cục bộ, để LLM chạy cục bộ chọn đáp án.
- **Cơ chế cốt lõi**:
  1. Tra cứu **BM25 trong bộ nhớ** trên các văn bản ở `docs/` (không dùng cloud hay API ngoài).
  2. Suy luận bằng **Local LLM qua Ollama** theo chế độ **một token đáp án** (kiểu "decision model" của Jev): prompt kết thúc bằng `Đáp án:`, `num_predict=1`, độ tin cậy lấy từ softmax logprob của token đầu trên các key hợp lệ. Nếu LLM lỗi hoặc timeout thì rơi về **heuristic fallback** (n-gram, số liệu, khoảng cách từ khóa) và có ghi log cảnh báo.
  3. Backend trả thêm `suggested_delay_ms` (Gauss 3–6 s) để client mô phỏng nhịp đọc.
- **Quyết định (2026-10-05): chỉ giữ MỘT model là `qwen2.5:3b`, bỏ qua `qwen2.5:7b`.** Lý do: 3b (2,07 GB) chạy 100% trên GPU, còn 7b (5,06 GB) chỉ có 12/29 lớp lên GPU nên chậm gấp nhiều lần (xem 2.6). Model 7b đã được **xóa khỏi Ollama** (`ollama rm qwen2.5:7b`, giải phóng ~4,7 GB); muốn dùng lại phải `ollama pull qwen2.5:7b`. Tham số `model` của `/solve` vẫn còn nhưng chỉ còn một model để chọn. Ollama 0.35.1. Phần cứng: GTX 1650 4 GB VRAM, RAM 23,7 GB.

---

## 2. TRẠNG THÁI HIỆN TẠI

### 2.1. Backend (`http://127.0.0.1:8000`)
- Đang chạy với model mặc định `qwen2.5:3b` (nếu không còn chạy, xem lệnh khởi động bên dưới). Chỉ mục 115 chunk.
- Endpoint:
  - `GET /health`: trạng thái, model mặc định.
  - `GET /models`: danh sách model trên Ollama.
  - `POST /solve`: nhận `question` (tối đa 4000 ký tự), `options` (tối đa 10 mục; `key` ≤ 8 ký tự, `text` ≤ 1000 ký tự) và `model` tùy chọn. Trả `selected_key`, `confidence`, `matched_chunk`, `suggested_delay_ms`, `from_cache`, `model`, `source` (`llm` hoặc `fallback`), `inference_ms` và **`timing`** (mới: `load_ms`, `prompt_eval_ms`, `eval_ms`, `prompt_tokens` lấy từ Ollama).
  - `POST /reload-docs`: nạp lại tài liệu và xóa cache.
- Cache LRU khóa theo (câu hỏi + đáp án + model).
- Khởi động: `python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000`. Biến môi trường (xem `backend/config.py`):

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `LLM_MODEL` | `qwen2.5:3b` | model mặc định |
| `LLM_MODE` | `token` | `token` = đáp án một token (nhanh); `json` = JSON schema (cách cũ) |
| `LLM_TIMEOUT_SECONDS` | `45` | timeout gọi Ollama |
| `LLM_KEEP_ALIVE` | `30m` | thời gian giữ model trong VRAM |
| `LLM_NUM_CTX` | `3072` | cố định để Ollama không cấp phát lại KV cache |
| `CONTEXT_TOP_K` | `2` | số đoạn ngữ cảnh đưa vào prompt |
| `CONTEXT_CHUNK_CHARS` | `1500` | số ký tự tối đa mỗi đoạn |

### 2.2. Pipeline truy xuất và suy luận
- `backend/core/llm_runner.py`: `solve()` giữ chữ ký cũ (trả bộ 3), `solve_ex()` trả thêm `timing`. Dùng `requests.Session` chung. Chế độ `token` có system prompt riêng (`SYSTEM_PROMPT_TOKEN`) và hàm `_first_token_choice()`; chế độ `json` giữ nguyên logic cũ. Nếu Ollama không trả logprobs thì đọc chữ cái đầu của văn bản sinh ra, độ tin cậy 0,85.
- `backend/core/parser.py`: chunk **header** (số hiệu, ngày, tiêu đề) và chunk **chữ ký/nơi nhận**.
- `backend/main.py`:
  - `retrieve_context`: truy vấn tổng + truy vấn riêng cho từng đáp án, hợp nhất RRF, lấy top `CONTEXT_TOP_K`.
  - Số hiệu văn bản trong câu hỏi (vd `244/KH-UBND`) bị loại khỏi truy vấn BM25 và chỉ dùng để **lọc đúng văn bản** (`detect_doc_hint`).
  - `expand_with_neighbor`: ghép chunk liền kề cùng mục.

### 2.3. Trang đánh giá một model (`tests/mock_assessment_page.html`)
- Đã **đơn giản hóa từ trang so sánh hai model thành trang một model** (2026-10-05): một cột, chọn model từ `/models` (mặc định `qwen2.5:3b`), nhịp Nhanh hoặc Nhịp người; có điểm số, bốn chỉ số, phiếu trả lời 30 ô, màn hình kết quả (điểm, thời gian TB, độ tin cậy TB, danh sách câu sai, bảng từng câu) và nút Tải kết quả (.json, tên `ket-qua-model.json`). Đã bỏ chế độ Lần lượt/Song song và phần so sánh giữa hai bên.
- **File này được sinh ra, đừng sửa trực tiếp.** Nguồn: `tests/mock_assessment_page.template.html` + 30 câu hỏi. Sau khi sửa mẫu, chạy `python tests/build_mock_page.py`.
- Dữ liệu 30 câu = 5 câu trong `tests/test_multi_questions.py` + 25 câu trong `tests/eval_set.json`.
- Đã bỏ Behavioral Telemetry Monitor và các selector cũ của `client/quiz_agent.user.js`. Trang mới tự chạy bằng JS nội bộ, gọi `/solve` bằng `fetch`.
- Mở trang: cần backend ở cổng 8000; mở trực tiếp file hoặc `python -m http.server 8791` trong `tests/` rồi vào `http://127.0.0.1:8791/mock_assessment_page.html`. Tham số `?api=<url>` đổi địa chỉ backend.
- **Lưu ý:** trang chưa được cập nhật để hiển thị trường `timing` mới và chưa kiểm chứng với cấu hình tối ưu (xem 2.4).

### 2.4. Đã kiểm chứng và chưa kiểm chứng
- **Đã kiểm chứng (phiên này):** bộ 30 câu với 3b ở các cấu hình khác nhau (bảng mục 4); đo phân rã thời gian bằng `timing`; chẩn đoán nguyên nhân 7b chậm (mục 2.6).
- **Chưa kiểm chứng:**
  - Chạy trọn bộ 30 câu với 7b ở cấu hình mới: **không còn cần**, đã bỏ 7b (mới chỉ đo 6 câu đầu: 5,9–12,5 s/câu).
  - Trang một model: đã chạy trọn 30 câu bằng Playwright, kết quả 30/30, TB 3,2 s/câu, màn hình kết quả hiện đúng (30 dòng bảng, 0 câu sai); chỉ có lỗi 404 favicon. **Chưa kiểm tra:** bố cục màn hình hẹp, nút Tải kết quả (.json), nhịp Nhịp người. Ảnh chụp: `.playwright-mcp/single-model-results.png` (đã bị `.gitignore`).
  - Kết quả 3b có nhiễu giữa các lần chạy (cùng cấu hình `top_k=2`: 29/30 rồi 30/30; 1,1 s rồi 2,1 s/câu). Mỗi con số chỉ từ 1–2 lần chạy.

### 2.5. Tiến trình nền có thể còn chạy
- Backend uvicorn ở cổng 8000.
- **Ollama đang chạy từ phiên trước** do lệnh `ollama serve` ẩn (không phải ứng dụng khay hệ thống), có `OLLAMA_DEBUG=1`; log nằm ở `%TEMP%\ollama_serve.log` và `%TEMP%\ollama_out.log`. Nên tắt tiến trình `ollama` và mở lại ứng dụng Ollama bình thường.
- `python -m http.server` ở cổng 8791 (nếu còn). Cổng 8765 trả 401 vì dịch vụ khác chiếm, đừng dùng.
- Trình duyệt Playwright có thể còn mở; ảnh chụp trong `.playwright-mcp/` (đã nằm trong `.gitignore`).

### 2.6. Chẩn đoán: vì sao 7b chậm
- **Nguyên nhân gốc:** 7b (5,06 GB) không vừa 4 GB VRAM. Log Ollama: `offloaded 12/29 layers to GPU`; `ollama ps`: `size_vram` 2,27 GB trên tổng 5,06 GB. Các lớp còn lại chạy trên CPU nên bước xử lý prompt chậm: ~84 token/giây (3b: 230–870 token/giây).
- Bước sinh đáp án gần như bằng 0 (`eval_ms=0`); thời gian gần như toàn bộ là `prompt_eval_ms`.
- **Cạm bẫy đã gặp:** bật `OLLAMA_FLASH_ATTENTION=1` + `OLLAMA_KV_CACHE_TYPE=q8_0` làm mọi yêu cầu tới **7b treo** (kể cả prompt "1+1=" không trả lời trong 600 s; backend timeout 45 s rồi rơi vào heuristic). Bỏ hai biến này thì 7b nạp trong 8,5 s và chạy bình thường. Với 3b, hai biến này không cải thiện gì. **Đừng bật chúng** khi dùng 7b.
- **Lỗi cache (đã sửa):** trước đây `/solve` lưu cả kết quả `source="fallback"` vào cache theo khóa của model, nên các lần timeout bị cache thành kết quả heuristic và lần sau trả ngay trong 0,0 s, làm số đo trông nhanh nhưng sai. Giờ chỉ cache kết quả `source == "llm"` (`backend/main.py`). Đã kiểm chứng: câu dùng LLM lần hai trả `from_cache=true`; câu với model không tồn tại (rơi vào fallback) hai lần đều `from_cache=false`.

### 2.7. Trạng thái Git
- Nhánh `master`, các commit của phiên này (mới nhất ở trên):
  - `c1437b5` perf: đáp án một token, keep_alive, ngữ cảnh 2 đoạn, phân rã `timing`, giới hạn kích thước đầu vào.
  - `55baf89` docs: cập nhật PROCESS.md (bản trước).
  - `9182b47` feat(tests): trang so sánh hai model sinh từ mẫu.
  - `51c7aec` test: bộ chấm 30 câu và bộ câu hỏi mở rộng.
  - `617a465` feat(backend): schema JSON + logprob, chunk header/chữ ký, truy xuất có lọc.
  - `155c9f0` chore: `.gitignore` cho `__pycache__/`, `*.pyc`, `.playwright-mcp/`; gỡ `.pyc` khỏi chỉ mục.
- Chưa commit: bản `PROCESS.md` này. `reverse-skill` (submodule) hiện ở trạng thái đã sửa, **không thuộc công việc này**, đã cố ý không đụng tới.
- Chưa push lên remote.

---

## 3. CẤU TRÚC THƯ MỤC

```text
backend/
  config.py                 # Host, port, timeout LLM, chế độ token/json, keep_alive, num_ctx, CONTEXT_TOP_K, pacing
  main.py                   # FastAPI: /solve /models /health /reload-docs; retrieve_context, lọc văn bản, ghép chunk kề
  core/
    normalizer.py           # Mở rộng từ viết tắt TTHC/CCHC, token hóa
    parser.py               # Chia chunk theo Điều/Khoản + chunk header + chunk chữ ký
    bm25_index.py           # Okapi BM25 trong bộ nhớ + LRU cache
    llm_runner.py           # Gọi Ollama (chế độ token/json, logprob, timing) + heuristic fallback
  data/synonyms.json
client/
  quiz_agent.user.js        # Userscript Tampermonkey (không còn khớp selector của trang đánh giá mới)
  src/                      # config.js, pacing.js, event_dispatcher.js
docs/                       # 1963.QD.UBND...md, 244.KH.UBND...md
tests/
  mock_assessment_page.template.html   # NGUỒN giao diện đánh giá một model
  mock_assessment_page.html            # SINH RA bởi build_mock_page.py, đừng sửa tay
  build_mock_page.py                   # Ghép mẫu + 30 câu hỏi thành trang HTML
  eval_set.json                        # 25 câu hỏi bổ sung (có đáp án chuẩn, trường doc)
  eval_bench.py                        # Chấm 30 câu qua /solve, in đúng/sai, thời gian và phân rã timing trung bình
  test_multi_questions.py              # 5 câu gốc (QUESTIONS) + chạy nhanh
  test_chunker_and_bm25.py, test_server_endpoints.py
SPEC.md, README.md, PROCESS.md
```

---

## 4. KẾT QUẢ ĐÁNH GIÁ

Chạy: `python tests/eval_bench.py` (cần backend chạy; model chọn bằng `LLM_MODEL=<model>` khi khởi động server). Script tự gọi `/reload-docs` để xóa cache trước khi đo.

**Chính xác theo giai đoạn (bộ 30 câu):**

| Giai đoạn | qwen2.5:3b | qwen2.5:7b |
|---|---|---|
| Ban đầu (5 câu, timeout 1,1 s nên luôn rơi vào heuristic) | 2/5 | 3/5 |
| Sau sửa LLM + chunk chữ ký/header + truy vấn theo đáp án (5 câu) | 5/5 | 5/5 |
| Bộ 30 câu, trước khi lọc văn bản + ghép chunk kề | 25/30 | 27/30 |
| Bộ 30 câu, sau khi lọc theo số hiệu văn bản + ghép chunk kề (JSON, 3 đoạn) | 29/30 (~5 s/câu) | 30/30 (~13 s/câu) |

**Tối ưu tốc độ với 3b (phiên này):**

| Cấu hình | Đúng | Thời gian/câu | Token prompt | Xử lý prompt |
|---|---|---|---|---|
| Bản gốc (JSON, 3 đoạn × 1500 ký tự) | 29/30 | 5,4 s | ~1207 | — |
| Chế độ token + keep_alive + Session | 28/30 | 5,4 s | 1207 | 5,16 s |
| + flash attention, KV q8_0 (không có ích, làm 7b treo) | 28/30 | 5,4 s | 1207 | 5,19 s |
| `CONTEXT_TOP_K=2`, 1500 ký tự mỗi đoạn | 29/30, rồi 30/30 | 1,1 s, rồi 2,1 s | 874 | 1,0 s, rồi 2,0 s |
| `CONTEXT_TOP_K=3`, 800 ký tự mỗi đoạn | 27/30 | 2,9 s | 979 | 2,8 s |

- Kết luận: **xử lý prompt là nút thắt, không phải bước sinh đáp án.** Trên GTX 1650, prompt dưới ~900 token xử lý nhanh hơn rõ (nguyên nhân có thể là VRAM gần đầy, chưa kiểm chứng). Giảm số đoạn tốt hơn cắt ký tự mỗi đoạn. Mặc định hiện là `CONTEXT_TOP_K=2`.
- Câu hay sai của 3b: **n08** (đúng là D "Phòng Kinh tế") và **n03**, thay đổi giữa các lần chạy.
- Bộ 30 câu do chính nhóm soạn từ hai văn bản trong `docs/`, và pipeline đã được chỉnh dựa trên các câu sai, nên điểm số lạc quan hơn so với câu hỏi lạ.
- Cơ chế lọc văn bản chỉ hoạt động khi câu hỏi nêu số hiệu dạng `244/KH`. Câu chỉ ghi "xã Đại Lộc" thì chưa được lọc.

**Đánh giá các hướng thay thế (đã quyết định không dùng):**
- **Jev** (TypeSafe): API đóng, trả phí, không tự host được; trái nguyên tắc "không dùng cloud/API ngoài".
- **Kev** (jaredpalmer/kev, Apache-2.0): bản thay thế mã nguồn mở của Jev trên nền Qwen; 0.8B cần ≥4 GB VRAM, 4B/9B cần ~17 GB; không có Ollama/GGUF; README không nói gì về tiếng Việt.
- **Laya** (encoder ModernBERT/mmBERT, Apache-2.0): bản gốc zero-shot kém (0.362), ngữ cảnh chỉ 512/1024 token, đa ngôn ngữ yếu (MASSIVE 0.227), cần fine-tune. Thông tin lấy từ bài viết, chưa kiểm tra repo chính thức.
- Giữ Qwen qua Ollama; ý tưởng "một lượt xử lý rồi đọc xác suất" đã được áp dụng trực tiếp lên Qwen (chế độ token).

---

## 5. VIỆC CẦN LÀM TIẾP

1. **~~Xếp tầng 3b → 7b~~ (đã hủy do chỉ giữ một model).** Thay bằng: nếu muốn nhanh hơn nữa, thử cho heuristic có biên điểm rõ bỏ qua LLM, hoặc đo xem model nhỏ hơn có đủ chính xác không. Trang đánh giá đã được đơn giản hóa thành một model (xem 2.3).
2. **Kiểm chứng nốt giao diện một model:** thử màn hình hẹp, nút Tải kết quả (.json) và nhịp Nhịp người (lượt chạy đầy đủ và màn hình kết quả đã kiểm chứng, xem 2.4). Cân nhắc hiển thị trường `timing` trên trang. Sửa mẫu rồi chạy `build_mock_page.py`.
3. **Mở rộng chế độ một token cho yes/no và score** (phương án đã đề xuất, chưa làm): yes/no dùng hai token `Đúng`/`Sai`, score dùng các token chữ số `1–5` và tính điểm kỳ vọng ∑ k·P(k); thêm trường `type` vào `/solve`.
4. **Cải thiện độ chính xác nếu cần:** hybrid retrieval (embedding như `bge-m3`) + reranker, lọc văn bản theo tên đơn vị ("xã Đại Lộc"), mở rộng bộ đánh giá bằng câu hỏi diễn đạt khác từ khóa, thử Qwen3-8B. Việc giảm số đoạn ngữ cảnh làm chất lượng xếp hạng chunk quan trọng hơn.
5. **Quyết định còn mở:** có khôi phục Telemetry Monitor và khả năng chạy bằng userscript trên một trang riêng hay không.
6. **Bảo mật cơ bản:** thông báo review sau commit nêu rủi ro cạn tài nguyên và gọi chéo nguồn ở `backend/main.py` nhưng không có chi tiết. Đã thêm giới hạn kích thước đầu vào cho `/solve`. CORS vẫn là `allow_origins=["*"]` (trang đánh giá mở bằng `file://` cần nó); server chỉ nghe trên `127.0.0.1`. Nếu mở ra ngoài máy cục bộ thì phải siết lại.
7. Khi thêm tài liệu vào `docs/`: gọi `POST /reload-docs`; chunk header/chữ ký được sinh tự động cho mọi file `.md`/`.txt`.

---

## 6. LƯU Ý KỸ THUẬT CHO PHIÊN SAU

- **Không dùng `python - <<EOF` (heredoc) để sửa file có dấu gạch chéo ngược, dấu nháy ba hoặc xuống dòng.** Trong môi trường này `\n`, `\b`, `\d` trong chuỗi bị biến dạng, và heredoc có `'''` làm lỗi cú pháp shell. Hãy dùng công cụ Edit/Write. `sed` cũng làm mất dấu gạch chéo ngược.
- `backend/main.py` lẫn kết thúc dòng CRLF và LF, `backend/config.py` dùng CRLF. Python vẫn chạy bình thường; công cụ Edit khớp được.
- Console Windows dùng cp1252: chạy script in tiếng Việt với `PYTHONIOENCODING=utf-8`. `curl` với dữ liệu tiếng Việt qua shell có thể báo lỗi body; dùng Python `requests`.
- **Ollama trên máy này:** không bật `OLLAMA_FLASH_ATTENTION` / `OLLAMA_KV_CACHE_TYPE` nếu sau này dùng lại 7b (xem 2.6); với 3b hai biến này không có tác dụng. Đừng chạy hai model cùng lúc vì VRAM 4 GB không đủ.
- Phân biệt "7b chậm" với "7b treo": nếu `timing` rỗng và `inference_ms` ≈ `LLM_TIMEOUT_SECONDS` thì LLM không trả lời và kết quả là heuristic.
- Playwright MCP chỉ lưu ảnh trong thư mục dự án. `browser_wait_for` với `text` bị timeout 5 s, nên dùng `time` hoặc đọc trạng thái bằng `browser_evaluate`.
- Dừng backend trên Windows: `Get-NetTCPConnection -LocalPort 8000 -State Listen | % { Stop-Process -Id $_.OwningProcess -Force }` (PowerShell). Trong PowerShell, `Remove-Item Env:...` có thể bị chặn; đặt `$env:VAR = $null` để xóa biến môi trường.
