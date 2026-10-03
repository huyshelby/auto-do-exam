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
        best_score = -999.0
        best_fact = ""

        # Trích xuất riêng phần trăm và số thông thường
        context_percentages = set(re.findall(r"\b\d+(?:[\.,]\d+)?%", clean_context))
        context_numbers = set(re.findall(r"\b\d+\b", clean_context)) - {"2024", "2025", "2026", "2030"} # Loại trừ năm phổ biến

        for opt in options:
            opt_key = opt.get("key", "A")
            opt_text = opt.get("text", "")
            opt_lower = opt_text.lower()
            
            # Phân tích số liệu trong option
            opt_percentages = set(re.findall(r"\b\d+(?:[\.,]\d+)?%", opt_lower))
            common_pct = opt_percentages.intersection(context_percentages)
            missing_pct = opt_percentages - context_percentages

            opt_numbers = set(re.findall(r"\b\d+\b", opt_lower)) - {"2024", "2025", "2026", "2030"}
            common_nums = opt_numbers.intersection(context_numbers)

            # Đếm số từ đơn trùng khớp (tối thiểu 2 ký tự: hồ, xã, sở, bộ...)
            words = [w for w in re.findall(r"\w+", opt_lower) if len(w) >= 2]
            word_matches = sum(1 for w in words if w in clean_context)
            word_ratio = word_matches / max(1, len(words))

            # Tính điểm cụm từ liên tiếp (2-grams và 3-grams)
            opt_words = opt_lower.split()
            bi_grams = [" ".join(opt_words[i:i+2]) for i in range(len(opt_words)-1)]
            tri_grams = [" ".join(opt_words[i:i+3]) for i in range(len(opt_words)-2)]

            bi_matches = sum(1 for bg in bi_grams if bg in clean_context)
            tri_matches = sum(1 for tg in tri_grams if tg in clean_context)

            # 4. Proximity & Anchor Window Matching:
            q_anchors = re.findall(r"\((.*?)\)", question.lower()) + re.findall(r"['\"](.*?)['\"]", question.lower())
            is_who_question = any(q_word in question.lower() for q_word in ["ai là", "người ký", "ai có", "chữ ký"])
            if is_who_question:
                q_anchors.extend(["kt. chủ tịch", "kt chủ tịch", "ký thay", "chữ ký"])

            anchor_bonus = 0.0
            for anchor in q_anchors:
                anchor_idx = clean_context.find(anchor)
                if anchor_idx != -1:
                    # Lấy cửa sổ văn bản 160 ký tự quanh anchor
                    start_w = max(0, anchor_idx - 40)
                    end_w = min(len(clean_context), anchor_idx + 180)
                    window_text = clean_context[start_w:end_w]
                    
                    # Tỷ lệ từ của option nằm ngay trong cửa sổ anchor
                    w_matches = sum(1 for w in words if w in window_text)
                    w_ratio = w_matches / max(1, len(words))
                    if w_ratio > 0.4:
                        anchor_bonus = max(anchor_bonus, w_ratio * 30.0)

            # Tính điểm trọng số tổng hợp
            score = (
                (tri_matches * 4.0) +
                (bi_matches * 2.0) +
                (word_matches * 1.0) +
                (word_ratio * 3.0) +
                (len(common_pct) * 6.0) +
                (len(common_nums) * 3.0) +
                anchor_bonus -
                (len(missing_pct) * 8.0)
            )

            if score > best_score:
                best_score = score
                best_key = opt_key
                best_fact = f"Khớp {tri_matches} cụm-3, {bi_matches} cụm-2, {word_matches}/{len(words)} từ ({word_ratio:.0%})"
                if anchor_bonus > 0:
                    best_fact += f" [Anchor Proximity Bonus: {anchor_bonus:.1f}]"
                if common_pct:
                    best_fact += f", khớp tỷ lệ: {', '.join(common_pct)}"

        confidence = 0.80 if best_score > 5.0 else (0.60 if best_score > 0 else 0.40)
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
