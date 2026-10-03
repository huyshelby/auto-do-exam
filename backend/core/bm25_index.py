from collections import OrderedDict
import hashlib
import math
from typing import Any, Dict, List, Optional, Tuple
from .normalizer import TextNormalizer
from .parser import DocumentChunk

class LRUMemoCache:
    """Bộ nhớ đệm LRU O(1) lưu kết quả phân tích theo SHA-256."""
    def __init__(self, capacity: int = 2000):
        self.capacity = capacity
        self.cache: OrderedDict[str, Any] = OrderedDict()

    @staticmethod
    def generate_key(question: str, options: List[dict]) -> str:
        norm_q = question.strip().lower()
        opts_str = "".join(f"{o.get('key','')}:{o.get('text','').strip().lower()}" for o in sorted(options, key=lambda x: x.get('key','')))
        combined = f"{norm_q}||{opts_str}"
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        if key not in self.cache:
            return None
        self.cache.move_to_end(key)
        return self.cache[key]

    def set(self, key: str, value: Any):
        if key in self.cache:
            self.cache.move_to_end(key)
        self.cache[key] = value
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)

    def clear(self):
        self.cache.clear()

class InMemBM25:
    """
    Thuật toán In-memory Okapi BM25 độ trễ cực thấp (< 3ms)
    Tối ưu hóa bằng Inverted Index dạng Dictionary.
    """
    def __init__(self, k1: float = 1.5, b: float = 0.75, normalizer: Optional[TextNormalizer] = None):
        self.k1 = k1
        self.b = b
        self.normalizer = normalizer or TextNormalizer()
        
        self.chunks: List[DocumentChunk] = []
        self.doc_len: List[int] = []
        self.avg_doc_len: float = 0.0
        self.n_docs: int = 0
        
        # Inverted index: term -> list of (doc_index, term_frequency)
        self.inverted_index: Dict[str, List[Tuple[int, int]]] = {}
        # Document frequency: term -> number of docs containing term
        self.df: Dict[str, int] = {}
        # IDF table: term -> idf value
        self.idf: Dict[str, float] = {}

    def fit(self, chunks: List[DocumentChunk]):
        """Lập chỉ mục toàn bộ danh sách chunks."""
        self.chunks = chunks
        self.n_docs = len(chunks)
        self.doc_len = []
        self.inverted_index.clear()
        self.df.clear()
        self.idf.clear()

        if self.n_docs == 0:
            self.avg_doc_len = 0.0
            return

        total_length = 0

        for idx, chunk in enumerate(chunks):
            # Mở rộng từ viết tắt và token hóa nội dung enriched
            expanded = self.normalizer.expand_acronyms(chunk.enriched_text)
            tokens = self.normalizer.tokenize(expanded)
            doc_l = len(tokens)
            self.doc_len.append(doc_l)
            total_length += doc_l

            # Đếm tần suất từ trong tài liệu (TF)
            counts: Dict[str, int] = {}
            for t in tokens:
                counts[t] = counts.get(t, 0) + 1

            for t, count in counts.items():
                if t not in self.inverted_index:
                    self.inverted_index[t] = []
                self.inverted_index[t].append((idx, count))
                self.df[t] = self.df.get(t, 0) + 1

        self.avg_doc_len = total_length / self.n_docs

        # Tính toán trước giá trị IDF
        for t, freq in self.df.items():
            self.idf[t] = math.log((self.n_docs - freq + 0.5) / (freq + 0.5) + 1.0)

    def search(self, query: str, top_k: int = 3) -> List[Tuple[DocumentChunk, float]]:
        """Truy xuất top_k chunks có điểm BM25 cao nhất."""
        if self.n_docs == 0:
            return []

        # Chuẩn hóa & mở rộng từ viết tắt câu hỏi
        expanded_query = self.normalizer.expand_acronyms(query)
        query_tokens = self.normalizer.tokenize(expanded_query)

        if not query_tokens:
            return []

        # Mảng cộng dồn điểm số của từng document
        scores: Dict[int, float] = {}

        for q in query_tokens:
            if q not in self.inverted_index:
                continue
            
            idf_val = self.idf.get(q, 0.0)
            if idf_val <= 0:
                continue

            postings = self.inverted_index[q]
            for doc_idx, tf in postings:
                dl = self.doc_len[doc_idx]
                denom = tf + self.k1 * (1.0 - self.b + self.b * (dl / self.avg_doc_len))
                term_score = idf_val * ((tf * (self.k1 + 1.0)) / denom)
                scores[doc_idx] = scores.get(doc_idx, 0.0) + term_score

        if not scores:
            return []

        # Lấy top_k tài liệu có điểm số cao nhất
        sorted_docs = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:top_k]
        return [(self.chunks[doc_idx], score) for doc_idx, score in sorted_docs]
