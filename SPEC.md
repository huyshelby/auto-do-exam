# HỆ THỐNG KIỂM THỬ TỰ ĐỘNG THI TRẮC NGHIỆM TRỰC TUYẾN DỰA TRÊN LOCAL RAG & REALISTIC INTERACTION SIMULATION
## TÀI LIỆU ĐẶC TẢ KỸ THUẬT CHI TIẾT (TECHNICAL SPECIFICATION)

---

## 1. TỔNG QUAN HỆ THỐNG (EXECUTIVE SUMMARY)

### 1.1. Mục tiêu dự án
Xây dựng một pipeline kiểm thử tự động toàn trình (End-to-End Automated Testing / QA Agent) cho các nền tảng đánh giá và thi trắc nghiệm trực tuyến (Web-based Assessment Platforms). Hệ thống có khả năng:
1. **Trích xuất thông minh**: Đọc câu hỏi và các phương án trả lời trực tiếp từ DOM của trình duyệt mà không cần cơ sở dữ liệu câu hỏi - đáp án định sẵn.
2. **Suy luận cục bộ độ trễ thấp (Low-Latency Local RAG)**: Truy xuất thông tin tức thời (< 20ms) từ kho tài liệu văn bản nội bộ (PDF/DOCX/Markdown pháp quy, quy định hành chính) và phân tích đáp án chính xác qua Local LLM trong thời gian < 1.0 giây.
3. **Mô phỏng sinh học con người (Realistic Biological Simulation)**: Tái tạo hành vi đọc, thời gian ra quyết định theo phân phối Gauss (Gaussian Human Pacing: 3 - 6 giây/câu) và chuỗi sự kiện tương tác chuột chuẩn trình duyệt để kiểm thử tải và kiểm thử tính toàn vẹn của hệ thống giám sát hành vi (Telemetry / Anti-cheat Analytics).
4. **Độc lập 100% (Zero-Cloud Dependency)**: Toàn bộ quá trình lập chỉ mục, tìm kiếm và suy luận đều chạy trên phần cứng cục bộ, không phụ thuộc vào các dịch vụ vector database hoặc API đám mây của bên thứ ba.

### 1.2. Ngân sách hiệu năng (Latency & Resource Budgets)

| Thành phần | Chỉ tiêu kỹ thuật (KPI) | Ghi chú kỹ thuật |
| :--- | :--- | :--- |
| **DOM Extraction** | $< 15\text{ ms}$ | Parse trực tiếp trên DOM bằng querySelector native |
| **SHA-256 Memoization Cache** | $< 0.5\text{ ms}$ | Truy xuất bảng băm $O(1)$ trong RAM |
| **In-Memory Retrieval (BM25)** | $< 5\text{ ms}$ (P99: $< 15\text{ ms}$) | Okapi BM25 Index chạy trên CPU, không đĩa/mạng |
| **Local LLM Inference** | $500\text{ ms} \div 900\text{ ms}$ | Qwen2.5-3B-Instruct / Llama-3.2-3B Quantized Q4_K_M |
| **Backend Total Turnaround** | $< 1200\text{ ms}$ | Bao gồm cả I/O nội bộ `localhost` |
| **Human Pacing Delay** | $3000\text{ ms} \div 6000\text{ ms}$ | Cố tình duy trì nhịp độ tự nhiên chống Telemetry flag |
| **Bộ nhớ tiêu thụ Backend** | $< 350\text{ MB}$ (Chưa gồm LLM) | RAM cho chỉ mục văn bản 50,000 chunks |

---

## 2. KIẾN TRÚC TỔNG THỂ (SYSTEM ARCHITECTURE)

```mermaid
flowchart TB
    subgraph Browser["MÔI TRƯỜNG TRÌNH DUYỆT (Client-Side)"]
        DOM["Giao diện bài thi trắc nghiệm (DOM)"]
        Extractor["DOM Extractor & Normalizer"]
        Pacing["Gaussian Human Pacing Engine"]
        Dispatcher["Synthetic Event Cascade Dispatcher"]
    end

    subgraph Userscript["Userscript Bridge (Tampermonkey)"]
        GMXHR["GM_xmlhttpRequest (Bypass CSP)"]
    end

    subgraph Backend["LOCAL RAG SERVICE (127.0.0.1:8000)"]
        Router["FastAPI /solve Endpoint"]
        Cache[("In-Memory LRU Cache O(1)")]
        Acronym["Acronym Expander & Tokenizer"]
        BM25["In-Memory Okapi BM25 Index"]
        PacingCalc["Delay Calculator"]
        LLM["Local LLM Engine (Ollama / llama.cpp)"]
        Fallback["Heuristic N-gram Fallback"]
    end

    subgraph Storage["LOCAL DOCS REPOSITORY"]
        Docs[("Tài liệu quy định / Chính sách (docs/)")]
    end

    DOM -->|Trích xuất text| Extractor
    Extractor -->|Payload JSON| GMXHR
    GMXHR -->|POST /solve| Router

    Router -->|1. Hash lookup| Cache
    Cache -->|Cache Hit (0.1ms)| Router
    Cache -->|Cache Miss| Acronym
    
    Docs -.->|Khởi động & Chunking| BM25
    Acronym -->|Expanded Query| BM25
    BM25 -->|Top-2 Chunks| LLM
    LLM -->|JSON Response| Router
    LLM -.->|Timeout / Low Conf| Fallback
    Fallback -.-> Router
    Router --> PacingCalc

    Router -->|selected_key, delay_ms, chunk| GMXHR
    GMXHR --> Pacing
    Pacing -->|Chờ T(delay)| Dispatcher
    Dispatcher -->|Chuỗi sự kiện native| DOM
```

---

## 3. THIẾT KẾ CÁC MODULE CỐT LÕI

### 3.1. MODULE 1: PRE-PROCESSING & IN-MEMORY SEARCH INDEX

#### 3.1.1. Phân đoạn tài liệu pháp lý chuyên sâu (Hierarchical Legal Chunking)
- **Đặc điểm văn bản mục tiêu**: Các văn bản pháp quy, kế hoạch cải cách hành chính (như mẫu `244/KH-UBND`, `1963/QĐ-UBND`) được cấu trúc thành:
  - Cấp 1: Phần / Chương (`I. MỤC TIÊU, YÊU CẦU, ĐỐI TƯỢNG`, `Chương II`)
  - Cấp 2: Mục lớn (`1. Mục tiêu`, `2. Yêu cầu`)
  - Cấp 3: Khoản (`a) Mục tiêu chung`, `b) Mục tiêu cụ thể`, `1. Chỉ tiêu...`)
  - Cấp 4: Điểm / Gạch đầu dòng (`- Tối thiểu 80%...`, `+ Cán bộ...`)
- **Nguyên lý Context-Prepending**:
  Mỗi chunk sinh ra **bắt buộc** phải giữ cấu trúc tiền tố (Breadcrumb metadata). Không bao giờ lưu một dòng rời rạc như:
  `"Tối thiểu 80% hồ sơ TTHC được xử lý hoàn toàn trực tuyến"`
  Thay vào đó, Chunk đầy đủ sẽ được chuẩn hóa thành:
  `"[244/KH-UBND] > [Mục tiêu cụ thể] > [Chỉ tiêu dịch vụ công]: Tối thiểu 80% hồ sơ TTHC được xử lý hoàn toàn trực tuyến."`
- **Thông số Chunk**:
  - Max chunk size: $350$ tokens.
  - Min chunk size: $80$ tokens.
  - Overlap: Giữ ngữ cảnh tiêu đề cha, không overlap ngắt đoạn tùy tiện giữa các dòng số liệu.

#### 3.1.2. Thuật toán tìm kiếm trong bộ nhớ (In-memory BM25)
Áp dụng công thức Okapi BM25 chuẩn hóa:
$$\text{Score}(D, Q) = \sum_{i=1}^{n} \text{IDF}(q_i) \cdot \frac{f(q_i, D) \cdot (k_1 + 1)}{f(q_i, D) + k_1 \cdot \left(1 - b + b \cdot \frac{|D|}{\text{avgdl}}\right)}$$

Trong đó:
- $k_1 = 1.5$ (điều chỉnh độ bão hòa tần suất từ khóa).
- $b = 0.75$ (điều chỉnh mức phạt độ dài đoạn văn bản).
- Bộ từ điển nghịch đảo (Inverted Index) được lưu trực tiếp trên mảng băm của tiến trình Python/Node.js, đảm bảo tra cứu P99 dưới $3\text{ ms}$.

#### 3.1.3. Bảng mở rộng từ viết tắt (Acronym Normalizer)
Tự động ánh xạ trước khi token hóa truy vấn:
- `TTHC` $\rightarrow$ `thủ tục hành chính`
- `CCHC` $\rightarrow$ `cải cách hành chính`
- `UBND` $\rightarrow$ `ủy ban nhân dân`
- `HĐND` $\rightarrow$ `hội đồng nhân dân`
- `DVCTT` $\rightarrow$ `dịch vụ công trực tuyến`
- `CBCCVC` $\rightarrow$ `cán bộ công chức viên chức`

#### 3.1.4. In-Memory Memoization Cache ($O(1)$)
- Khóa: $\text{Key} = \text{SHA256}(\text{trim}(Q) + \text{sort}(\text{options}))$.
- Dung lượng tối đa: $2000$ mục theo chính sách **LRU (Least Recently Used)**.
- Khi Cache Hit: Bỏ qua toàn bộ BM25, LLM và Pacing tính toán lại, trả kết quả ngay trong $< 0.1\text{ ms}$.

---

### 3.2. MODULE 2: LOW-LATENCY REASONING ENGINE

#### 3.2.1. System Prompt tối ưu hóa Token
Để giảm tối đa số token sinh ra và triệt tiêu hoàn toàn ảo giác (hallucination), System Prompt được thiết kế cực ngắn gọn và ép buộc chế độ trả về JSON:

```text
Bạn là bộ phân tích trích xuất dữ liệu bài thi trắc nghiệm. Nhiệm vụ: Chọn DUY NHẤT 1 đáp án chính xác từ câu hỏi và tài liệu tham chiếu.

QUY TẮC BẮT BUỘC:
1. Chỉ dựa vào [NGỮ CẢNH]. Không tự suy đoán nếu ngữ cảnh không có thông tin.
2. Trả về DUY NHẤT một chuỗi JSON hợp lệ tuân thủ Schema đã định sẵn. Tuyệt đối không thêm markdown ```json.
3. Nếu thông tin không đủ để kết luận, gán confidence < 0.5.
```

#### 3.2.2. JSON Schema Output Contract
```json
{
  "type": "object",
  "properties": {
    "selected_key": {
      "type": "string",
      "enum": ["A", "B", "C", "D"]
    },
    "confidence": {
      "type": "number",
      "minimum": 0.0,
      "maximum": 1.0
    },
    "matched_fact": {
      "type": "string",
      "maxLength": 150
    }
  },
  "required": ["selected_key", "confidence", "matched_fact"],
  "additionalProperties": false
}
```

#### 3.2.3. Chiến lược Fallback đa tầng (Multi-tier Fallback Matrix)

```
[Request đến]
    │
    ▼
[Kiểm tra Cache SHA-256] ──(Hit)──► Trả về kết quả tức thì (0.1ms)
    │ (Miss)
    ▼
[Truy xuất BM25 Top-2 Chunks]
    │
    ▼
[Gọi Local LLM (Timeout: 1100ms)]
    │
    ├─► Thành công (confidence >= 0.70) ──► Trả kết quả + Lưu Cache
    │
    └─► Thất bại (Timeout / Error / confidence < 0.70)
            │
            ▼
        [Heuristic Keyword & Number Matcher]
            │ - So khớp các số liệu (80%, 2026...) trong Option với Chunk
            │ - Tính Jaccard similarity giữa Option và Chunk
            │
            ├─► Tìm thấy phương án có độ trùng khớp cao nhất (confidence = 0.60)
            │
            └─► Không tìm thấy ──► Fallback mặc định phương án an toàn ("A")
```

---

### 3.3. MODULE 3: AUTOMATION & REALISTIC INTERACTION SIMULATION

#### 3.3.1. Kiến trúc kết nối Client - Server qua Userscript
- Các trang web thi trắc nghiệm thường kích hoạt Content Security Policy (`connect-src 'self' ...`).
- **Giải pháp**: Sử dụng **Tampermonkey Userscript** với cờ `@grant GM_xmlhttpRequest`. Hàm này chạy trên context đặc quyền của extension, bỏ qua hoàn toàn rào cản CSP của trang web để giao tiếp trực tiếp với `http://127.0.0.1:8000/solve`.

#### 3.3.2. Thuật toán mô phỏng tốc độ đọc tự nhiên (Gaussian Human Pacing)
Thời gian trễ mô phỏng hành vi con người được tính toán bởi hàm mật độ xác suất Gauss kết hợp độ dài văn bản:

$$T_{\text{delay}} = \text{Clamp}\left( \frac{N_{\text{words}}}{V_{\text{read}}} \times 1000 + T_{\text{decision}} + T_{\text{jitter}}, \, 3000\text{ ms}, \, 6000\text{ ms} \right)$$

Trong đó:
- $N_{\text{words}}$: Tổng số từ trong câu hỏi và 4 phương án trả lời.
- $V_{\text{read}} \sim \mathcal{N}(\mu=3.5, \sigma=0.4)$ (từ/giây, tương đương $210 \pm 24\text{ WPM}$).
- $T_{\text{decision}} \sim \mathcal{N}(\mu=1200, \sigma=200)\text{ ms}$ (thời gian mắt quét lại phương án chọn).
- $T_{\text{jitter}} = \text{Random}(-200, 350)\text{ ms}$.

#### 3.3.3. Chuỗi sự kiện DOM chuẩn trình duyệt (Canonical Event Cascade)
Các hệ thống chống gian lận kiểm tra luồng sự kiện tương tác để xác định bot. Không được dùng lệnh `element.click()` đơn lẻ. Chuỗi kích hoạt chuẩn:

```
[Bắt đầu tương tác]
    │
    ▼
1. Pointer Enter:  element.dispatchEvent('pointerover', { bubbles: true, cancelable: true })
                   element.dispatchEvent('mouseover',   { bubbles: true, cancelable: true })
    │
    ▼
2. Pointer Move:   element.dispatchEvent('pointermove', { clientX, clientY, screenX, screenY })
                   element.dispatchEvent('mousemove',   { clientX, clientY, screenX, screenY })
    │
    ▼
3. Mouse Press:    element.dispatchEvent('pointerdown', { buttons: 1, button: 0 })
                   element.dispatchEvent('mousedown',   { buttons: 1, button: 0 })
                   element.focus()
    │
    ▼ (Giữ chuột ngẫu nhiên: 60ms - 110ms mô phỏng cơ sinh học ngón tay)
    │
4. Mouse Release:  element.dispatchEvent('pointerup',   { buttons: 0, button: 0 })
                   element.dispatchEvent('mouseup',     { buttons: 0, button: 0 })
    │
    ▼
5. Final Action:   element.dispatchEvent('click',       { detail: 1 })
                   radioInput.checked = true
                   radioInput.dispatchEvent('change',   { bubbles: true })
                   radioInput.dispatchEvent('input',    { bubbles: true })
```

---

## 4. ĐẶC TẢ GIAO DIỆN DỮ LIỆU (API CONTRACTS)

### 4.1. Endpoint: `POST /solve`
- **Mục đích**: Nhận thông tin câu hỏi và trả về phương án tối ưu cùng thời gian trễ mô phỏng.

#### Request Body
```json
{
  "question": "Theo Kế hoạch 244/KH-UBND, mục tiêu cụ thể về tỷ lệ hồ sơ thủ tục hành chính được xử lý trực tuyến là bao nhiêu?",
  "options": [
    { "key": "A", "text": "Tối thiểu 50%" },
    { "key": "B", "text": "Tối thiểu 70%" },
    { "key": "C", "text": "Tối thiểu 80%" },
    { "key": "D", "text": "Đạt 100%" }
  ]
}
```

#### Response Body (200 OK)
```json
{
  "selected_key": "C",
  "confidence": 0.98,
  "matched_chunk": "[244/KH-UBND] [Mục tiêu cụ thể] Tối thiểu 80% hồ sơ TTHC được xử lý hoàn toàn trực tuyến...",
  "suggested_delay_ms": 4120
}
```

### 4.2. Endpoint: `POST /reload-docs`
- **Mục đích**: Tải lại và tái lập chỉ mục BM25 khi có file tài liệu mới trong thư mục `docs/`.

#### Response Body (200 OK)
```json
{
  "status": "success",
  "indexed_chunks_count": 142,
  "elapsed_ms": 18.4
}
```

### 4.3. Endpoint: `GET /health`
- **Mục đích**: Trả về tình trạng sức khỏe của Local RAG Server, số lượng chunk đã index và trạng thái kết nối Local LLM.

---

## 5. CẤU TRÚC THƯ MỤC DỰ ÁN (PROJECT DIRECTORY STRUCTURE)

```text
local-rag-qa-automation/
│
├── docs/                                  # Thư mục chứa tài liệu tham chiếu gốc
│   ├── 1963.QD.UBND.06.05.2026.signed.md
│   └── 244.KH.UBND.07.08.2026.signed.signed.signed.signed.md
│
├── backend/                               # Dịch vụ Local RAG & Solver Engine
│   ├── core/
│   │   ├── __init__.py
│   │   ├── parser.py                      # Bộ phân đoạn tài liệu hành chính theo Điều/Khoản
│   │   ├── bm25_index.py                  # Thuật toán In-memory Okapi BM25 & LRU Cache
│   │   ├── normalizer.py                  # Xử lý từ viết tắt (TTHC, CCHC, UBND...)
│   │   └── llm_runner.py                  # Kết nối Local LLM (Ollama API / llama.cpp)
│   ├── data/
│   │   └── synonyms.json                  # Từ điển đồng nghĩa và mở rộng viết tắt
│   ├── config.py                          # Cấu hình cổng, timeout, ngưỡng confidence
│   ├── main.py                            # FastAPI app, endpoints (/solve, /health)
│   └── requirements.txt                   # fastapi, uvicorn, requests, pydantic
│
├── client/                                # Thành phần tự động hóa phía trình duyệt
│   ├── src/
│   │   ├── config.js                      # Cấu hình selector CSS và endpoint
│   │   ├── extractor.js                   # Trích xuất dữ liệu câu hỏi từ DOM
│   │   ├── pacing.js                      # Tính toán độ trễ Gaussian
│   │   └── event_dispatcher.js            # Kích hoạt chuỗi sự kiện chuột chuẩn
│   └── quiz_agent.user.js                 # Userscript hoàn chỉnh nạp vào Tampermonkey
│
├── tests/                                 # Bộ kiểm thử tự động
│   ├── mock_assessment_page.html          # Trang web bài thi trắc nghiệm giả lập phục vụ QA E2E
│   ├── test_chunker.py                    # Unit test bộ parser tài liệu pháp lý
│   └── test_bm25_latency.py               # Benchmark tốc độ tìm kiếm < 5ms
│
├── SPEC.md                                # Bản đặc tả kỹ thuật này
└── README.md                              # Hướng dẫn cài đặt và vận hành nhanh
```

---

## 6. LỘ TRÌNH TRIỂN KHAI VÀ CHECKLIST PHỐI HỢP AI AGENT

### Giai đoạn 1: Xây dựng Bộ Tiền xử lý & In-Memory Index (Backend Core)
- [ ] **Task 1.1**: Tạo file `backend/requirements.txt` (`fastapi`, `uvicorn`, `requests`, `pydantic`).
- [ ] **Task 1.2**: Xây dựng `backend/core/normalizer.py` chứa bảng từ điển viết tắt chuẩn tiếng Việt.
- [ ] **Task 1.3**: Xây dựng `backend/core/parser.py` thực hiện phân đoạn văn bản dạng cây Điều/Khoản/Điểm gắn tiền tố ngữ cảnh (Context-prepending).
- [ ] **Task 1.4**: Xây dựng `backend/core/bm25_index.py` chứa class `InMemBM25` với cơ chế tính điểm Okapi BM25 thuần Python và `LRUCache`.
- [ ] **Task 1.5**: Viết script `tests/test_chunker.py` kiểm tra trích xuất trên tài liệu thực tế trong `docs/`.

### Giai đoạn 2: Tích hợp Bộ suy luận & REST API (Backend Service)
- [ ] **Task 2.1**: Xây dựng `backend/core/llm_runner.py` kết nối tới local Ollama instance (`/api/generate`) với tham số `stream=False, format=json, timeout=1.1s`.
- [ ] **Task 2.2**: Xây dựng cơ chế Heuristic Fallback (so khớp từ khóa, số liệu tỷ lệ phần trăm khi LLM timeout hoặc confidence < 0.70).
- [ ] **Task 2.3**: Hoàn thiện `backend/main.py` với endpoint `POST /solve`, tích hợp hàm tính `suggested_delay_ms` theo phân phối Gauss.
- [ ] **Task 2.4**: Kiểm thử độ trễ backend end-to-end đảm bảo $< 1.2\text{s}$.

### Giai đoạn 3: Phát triển Client Tự động hóa & Mô phỏng Sinh học
- [ ] **Task 3.1**: Tạo trang kiểm thử cục bộ `tests/mock_assessment_page.html` mô phỏng giao diện thi trắc nghiệm với đồng hồ đếm ngược và bộ ghi nhận telemetry sự kiện.
- [ ] **Task 3.2**: Xây dựng `client/src/pacing.js` cài đặt thuật toán Gaussian Pacing từ độ dài văn bản.
- [ ] **Task 3.3**: Xây dựng `client/src/event_dispatcher.js` thực hiện chuỗi biến cố `pointerover` $\rightarrow$ `mousemove` $\rightarrow$ `mousedown` $\rightarrow$ `dwell` $\rightarrow$ `mouseup` $\rightarrow$ `click`.
- [ ] **Task 3.4**: Đóng gói Userscript `client/quiz_agent.user.js` sử dụng `GM_xmlhttpRequest` để giao tiếp với `http://127.0.0.1:8000/solve`.

### Giai đoạn 4: Kiểm thử Tích hợp E2E & Tinh chỉnh
- [ ] **Task 4.1**: Chạy kiểm thử toàn trình giữa Local Backend, Tampermonkey Userscript và trang Mock Quiz.
- [ ] **Task 4.2**: Đo lường tỷ lệ chính xác (Accuracy rate) với bộ câu hỏi trích từ văn bản CCHC.
- [ ] **Task 4.3**: Thẩm tra log sự kiện trình duyệt đảm bảo không có bất kỳ cờ bất thường nào từ telemetry.
