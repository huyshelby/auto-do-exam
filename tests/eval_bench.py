import json
import os
import sys
import time
import requests

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_multi_questions import QUESTIONS as BASE_QUESTIONS

BASE_URL = os.environ.get("RAG_URL", "http://127.0.0.1:8000")

def load_questions():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "eval_set.json")
    with open(path, encoding="utf-8") as f:
        extra = json.load(f)
    return list(BASE_QUESTIONS) + extra

def main():
    # Xóa cache để mỗi lần đo đều đi qua toàn pipeline
    requests.post(f"{BASE_URL}/reload-docs", timeout=30)
    model = requests.get(f"{BASE_URL}/health", timeout=5).json().get("llm_model")
    questions = load_questions()
    correct, total_t, misses = 0, 0.0, []
    for q in questions:
        t0 = time.time()
        data = requests.post(f"{BASE_URL}/solve", json={"question": q["question"], "options": q["options"]}, timeout=180).json()
        dt = time.time() - t0
        total_t += dt
        ok = data["selected_key"] == q["expected"]
        correct += ok
        if not ok:
            misses.append((q, data, dt))
    print(f"MODEL={model}  ĐÚNG {correct}/{len(questions)} ({100*correct/len(questions):.1f}%)  TB {total_t/len(questions):.1f}s/câu")
    for q, d, dt in misses:
        print(f"  ✗ {q['id']}: dự đoán {d['selected_key']} (tin cậy {d['confidence']}) kỳ vọng {q['expected']} | {q['question'][:80]}")

if __name__ == "__main__":
    main()
