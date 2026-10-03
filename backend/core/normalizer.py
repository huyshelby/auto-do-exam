import json
import os
import re
from typing import Dict, List

DEFAULT_SYNONYMS = {
    "tthc": "thủ tục hành chính",
    "cchc": "cải cách hành chính",
    "ubnd": "ủy ban nhân dân",
    "hđnd": "hội đồng nhân dân",
    "hdnd": "hội đồng nhân dân",
    "dvctt": "dịch vụ công trực tuyến",
    "csdl": "cơ sở dữ liệu",
    "cbccvc": "cán bộ công chức viên chức",
    "cbcc": "cán bộ công chức",
    "cntt": "công nghệ thông tin",
    "kh-ubnd": "kế hoạch ủy ban nhân dân",
    "qd-ubnd": "quyết định ủy ban nhân dân",
    "nq-cp": "nghị quyết chính phủ"
}

class TextNormalizer:
    def __init__(self, synonyms_path: str = None):
        self.synonyms: Dict[str, str] = dict(DEFAULT_SYNONYMS)
        if synonyms_path and os.path.exists(synonyms_path):
            try:
                with open(synonyms_path, "r", encoding="utf-8") as f:
                    custom = json.load(f)
                    self.synonyms.update({k.lower(): v.lower() for k, v in custom.items()})
            except Exception as e:
                print(f"[Warning] Không thể nạp synonyms_path {synonyms_path}: {e}")

        # Biên dịch regex thay thế từ viết tắt
        # Bắt các từ đứng độc lập (word boundaries hoặc dấu gạch nối)
        escaped_keys = [re.escape(k) for k in sorted(self.synonyms.keys(), key=len, reverse=True)]
        self.acronym_regex = re.compile(r"(?<!\w)(" + "|".join(escaped_keys) + r")(?!\w)", re.IGNORECASE)

    def expand_acronyms(self, text: str) -> str:
        """Thay thế và bổ sung từ đồng nghĩa/viết tắt để tăng recall."""
        def repl(match):
            key = match.group(0).lower()
            expanded = self.synonyms.get(key, key)
            # Giữ cả từ gốc và từ mở rộng để tối ưu tìm kiếm
            return f"{match.group(0)} {expanded}"
        return self.acronym_regex.sub(repl, text)

    def clean_text(self, text: str) -> str:
        """Chuẩn hóa khoảng trắng và dấu câu."""
        text = re.sub(r"[\r\t]+", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def tokenize(self, text: str) -> List[str]:
        """Tách từ giữ nguyên số, phần trăm và ký tự tiếng Việt."""
        text = text.lower()
        # Giữ lại chữ cái Unicode, chữ số, ký hiệu %
        tokens = re.findall(r"[\w]+%?", text)
        return [t for t in tokens if len(t) > 1 or t.isdigit()]
