import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "docs"))
SYNONYMS_FILE = os.path.join(BASE_DIR, "data", "synonyms.json")

# Server Configs
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8000

# Local LLM Configs (Ollama / llama.cpp)
OLLAMA_API_URL = os.environ.get("OLLAMA_API_URL", "http://127.0.0.1:11434/api/generate")
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen2.5:3b")
LLM_TIMEOUT_SECONDS = float(os.environ.get("LLM_TIMEOUT_SECONDS", "45"))  # 1.1s cũ khiến mọi lần gọi LLM timeout -> luôn rơi vào heuristic
LLM_MODE = os.environ.get("LLM_MODE", "token")  # 'token': 1 token đáp án (nhanh, kiểu Jev); 'json': JSON schema (cũ)
LLM_KEEP_ALIVE = os.environ.get("LLM_KEEP_ALIVE", "30m")  # giữ model trong VRAM, tránh nạp lại
LLM_NUM_CTX = int(os.environ.get("LLM_NUM_CTX", "3072"))  # cố định để Ollama không cấp phát lại KV cache
CONTEXT_TOP_K = int(os.environ.get("CONTEXT_TOP_K", "2"))  # số đoạn ngữ cảnh; prompt <~900 token thì prefill nhanh gấp ~4 lần trên GTX 1650 (đo ngày 2026-10-04)
CONTEXT_CHUNK_CHARS = int(os.environ.get("CONTEXT_CHUNK_CHARS", "1500"))  # số ký tự tối đa mỗi đoạn
CONFIDENCE_THRESHOLD = 0.70

# Human Pacing Constants
PACING_MIN_DELAY_MS = 3000
PACING_MAX_DELAY_MS = 6000
WORDS_PER_SECOND_MEAN = 3.5  # ~ 210 WPM
WORDS_PER_SECOND_STD = 0.4
DECISION_TIME_MEAN_MS = 1200
DECISION_TIME_STD_MS = 200
