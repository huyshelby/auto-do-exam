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
CONFIDENCE_THRESHOLD = 0.70

# Human Pacing Constants
PACING_MIN_DELAY_MS = 3000
PACING_MAX_DELAY_MS = 6000
WORDS_PER_SECOND_MEAN = 3.5  # ~ 210 WPM
WORDS_PER_SECOND_STD = 0.4
DECISION_TIME_MEAN_MS = 1200
DECISION_TIME_STD_MS = 200
