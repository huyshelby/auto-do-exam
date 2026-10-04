"""Sinh tests/mock_assessment_page.html từ mẫu giao diện + bộ 30 câu hỏi.

Chạy: python tests/build_mock_page.py
Nguồn câu hỏi: QUESTIONS trong test_multi_questions.py (5 câu đầu) + tests/eval_set.json (25 câu).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from test_multi_questions import QUESTIONS  # noqa: E402


def load_quiz():
    with open(os.path.join(HERE, "eval_set.json"), encoding="utf-8") as f:
        extra = json.load(f)
    quiz = []
    for q in list(QUESTIONS) + extra:
        doc = q.get("doc") or ("244" if "244/KH" in q["question"] else "1963")
        quiz.append({
            "id": q["id"],
            "doc": doc,
            "question": q["question"],
            "options": q["options"],
            "expected": q["expected"],
        })
    return quiz


def main():
    with open(os.path.join(HERE, "mock_assessment_page.template.html"), encoding="utf-8") as f:
        template = f.read()
    quiz = load_quiz()
    html = template.replace("__QUIZ_JSON__", json.dumps(quiz, ensure_ascii=False, indent=2))
    out = os.path.join(HERE, "mock_assessment_page.html")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    print(f"Đã ghi {out} với {len(quiz)} câu hỏi.")


if __name__ == "__main__":
    main()
