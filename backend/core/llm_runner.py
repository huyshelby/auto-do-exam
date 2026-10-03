import json
import random
import re
from typing import Dict, List, Optional, Tuple
import requests

from ..config import (
    OLLAMA_API_URL,
    LLM_MODEL,
    LLM_TIMEOUT_SECONDS,
    CONFIDENCE_THRESHOLD,
    PACING_MIN_DELAY_MS,
    PACING_MAX_DELAY_MS,
    WORDS_PER_SECOND_MEAN,
    WORDS_PER_SECOND_STD,
    DECISION_TIME_MEAN_MS,
    DECISION_TIME_STD_MS
)

SYSTEM_PROMPT = (
    "Bạn là một giám khảo AI chuyên trích xuất và chọn đáp án chính xác cho bài thi trắc nghiệm.\n"
    "CHỈ DỰA VÀO [NGỮ CẢNH ĐƯỢC CẤP] để chọn phương án đúng. Tuyệt đối không tự suy đoán thông tin ngoài ngữ cảnh.\n"
    "BẮT BUỘC trả về DUY NHẤT một chuỗi JSON hợp lệ với định dạng:\n"
    '{"selected_key": "A"|"B"|"C"|"D", "confidence": float, "matched_fact": string}\n'
    "Không giải thích thêm, không dùng khối markdown ```json."
)

class LLMReasoningEngine:
    def __init__(
        self,
        ollama_url: str = OLLAMA_API_URL,
        model: str = LLM_MODEL,
        timeout: float = LLM_TIMEOUT_SECONDS,
        confidence_threshold: float = CONFIDENCE_THRESHOLD
    ):
        self.ollama_url = ollama_url
        self.model = model
        self.timeout = timeout
        self.confidence_threshold = confidence_threshold

    def calculate_gaussian_delay(self, text: str) -> int:
        """
        Tính toán thời gian trễ mô phỏng sinh học theo phân phối Gauss:
        T_delay = Clamp( (N_words / V_read) * 1000 + T_decision + T_jitter, 3000ms, 6000ms )
        """
        words = text.split()
        n_words = max(5, len(words))

        # Tốc độ đọc (từ/giây)
        v_read = max(2.0, random.gauss(WORDS_PER_SECOND_MEAN, WORDS_PER_SECOND_STD))
        t_read_ms = (n_words / v_read) * 1000

        # Thời gian nhận thức ra quyết định
        t_decision_ms = max(500, random.gauss(DECISION_TIME_MEAN_MS, DECISION_TIME_STD_MS))

        # Nhiễu jitter
        t_jitter_ms = random.randint(-200, 350)

        total_delay = int(t_read_ms + t_decision_ms + t_jitter_ms)
        return max(PACING_MIN_DELAY_MS, min(total_delay, PACING_MAX_DELAY_MS))

    def heuristic_fallback(self, question: str, options: List[dict], context_text: str) -> Tuple[str, float, str]:
        """
        Fallback tầng 3: Giải toán thống kê n-gram và so khớp số liệu khi LLM offline hoặc timeout.
        """
        clean_context = context_text.lower()
        best_key = options[0]["key"] if options else "A"
        best_score = -1.0
        best_fact = ""

        # Trích xuất số liệu / tỷ lệ phần trăm trong context
        context_numbers = set(re.findall(r"\b\d+(?:[\.,]\d+)?%?", clean_context))

        for opt in options:
            opt_key = opt.get("key", "A")
            opt_text = opt.get("text", "")
            opt_lower = opt_text.lower()
            
            # 1. So khớp số liệu cụ thể (VD: 80%, 100%, 2026)
            opt_numbers = set(re.findall(r"\b\d+(?:[\.,]\d+)?%?", opt_lower))
            common_numbers = opt_numbers.intersection(context_numbers)

            # 2. So khớp từ vựng
            words = [w for w in re.findall(r"\w+", opt_lower) if len(w) > 2]
            word_matches = sum(1 for w in words if w in clean_context)
            word_ratio = (word_matches / max(1, len(words)))

            # Điểm số kết hợp (ưu tiên rất cao cho số liệu chính xác)
            score = (len(common_numbers) * 3.0) + word_ratio

            if score > best_score:
                best_score = score
                best_key = opt_key
                best_fact = f"Khớp từ vựng ({word_matches}/{len(words)})"
                if common_numbers:
                    best_fact += f", trùng số liệu: {', '.join(common_numbers)}"

        confidence = 0.65 if best_score > 0 else 0.40
        return best_key, confidence, best_fact or "Heuristic fallback match."

    def solve(self, question: str, options: List[dict], context_text: str) -> Tuple[str, float, str]:
        """
        Thực hiện suy luận: Ưu tiên Local LLM -> Nếu thất bại/timeout thì kích hoạt Heuristic Fallback.
        """
        # Xây dựng User Prompt
        prompt_lines = [
            f"NGỮ CẢNH:\n{context_text}\n",
            f"CÂU HỎI: {question}\n",
            "CÁC LỰA CHỌN:"
        ]
        for opt in options:
            prompt_lines.append(f"{opt.get('key')}. {opt.get('text')}")
        user_prompt = "\n".join(prompt_lines)

        try:
            res = requests.post(
                self.ollama_url,
                json={
                    "model": self.model,
                    "system": SYSTEM_PROMPT,
                    "prompt": user_prompt,
                    "format": "json",
                    "stream": False,
                    "options": {
                        "temperature": 0.0,
                        "num_predict": 60,
                        "top_p": 0.1
                    }
                },
                timeout=self.timeout
            )

            if res.status_code == 200:
                body = res.json()
                raw_response = body.get("response", "{}")
                parsed = json.loads(raw_response)
                
                selected_key = str(parsed.get("selected_key", "")).strip().upper()
                confidence = float(parsed.get("confidence", 0.85))
                matched_fact = str(parsed.get("matched_fact", ""))

                # Kiểm tra tính hợp lệ của key
                valid_keys = [o.get("key", "").upper() for o in options]
                if selected_key in valid_keys and confidence >= self.confidence_threshold:
                    return selected_key, confidence, matched_fact

        except Exception as e:
            # LLM offline, timeout hoặc JSON không hợp lệ -> Chuyển sang Fallback
            pass

        # Kích hoạt Heuristic Fallback
        return self.heuristic_fallback(question, options, context_text)
