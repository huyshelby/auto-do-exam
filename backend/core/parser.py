import os
import re
from typing import Dict, List, Optional
from pydantic import BaseModel

class DocumentChunk(BaseModel):
    chunk_id: str
    doc_name: str
    breadcrumb: str
    raw_content: str
    enriched_text: str
    metadata: Dict[str, str] = {}

class LegalDocumentParser:
    """
    Parser chuyên biệt cho văn bản hành chính/quy phạm Việt Nam:
    - Bóc tách theo cây phả hệ: Tiêu đề -> Chương/Phần (I, II) -> Mục/Điều (1, 2, Điều 1) -> Khoản (a, b, 1) -> Điểm
    - Gắn Context-prepending vào từng chunk để giữ trọn vẹn ngữ cảnh.
    """

    # Regex nhận diện các cấp bậc
    RE_LEVEL_1 = re.compile(r"^(?:#+\s+)?(?:[I|V|X|L|C|D|M]+\.|\bChương\s+[IVXLCDM\d]+|\bPhần\s+[IVXLCDM\d]+)\s*(.*)", re.IGNORECASE)
    RE_LEVEL_2 = re.compile(r"^(?:#+\s+)?(?:Điều\s+\d+\.?|\b[0-9]+\.\s+[A-ZÀ-Ỹ])\s*(.*)")
    RE_LEVEL_3 = re.compile(r"^(?:[a-zđ]\)\s+|[0-9]+\.\s+|[0-9]+\)\s+)\s*(.*)")
    RE_BULLET  = re.compile(r"^(?:[\-\+\*•]\s+)(.*)")

    RE_SIGNATURE = re.compile(r"(?:KT\.|TM\.|Nơi nhận)", re.IGNORECASE)

    def __init__(self, max_chunk_chars: int = 600, min_chunk_chars: int = 80):
        self.max_chunk_chars = max_chunk_chars
        self.min_chunk_chars = min_chunk_chars

    def parse_file(self, file_path: str) -> List[DocumentChunk]:
        doc_name = os.path.basename(file_path)
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        return self.parse_text(content, doc_name)

    def parse_text(self, content: str, doc_name: str) -> List[DocumentChunk]:
        lines = content.splitlines()
        chunks: List[DocumentChunk] = []

        curr_l1 = ""
        curr_l2 = ""
        curr_l3 = ""
        
        buffer_lines: List[str] = []
        chunk_idx = 0

        def flush_buffer():
            nonlocal chunk_idx, buffer_lines
            if not buffer_lines:
                return

            text_block = "\n".join(buffer_lines).strip()
            # Xóa các dòng table format markdown đơn thuần nếu trống rỗng
            clean_block = re.sub(r"\|[-\s|]+\|", "", text_block).strip()
            if not clean_block or len(clean_block) < self.min_chunk_chars:
                buffer_lines = []
                return

            # Xây dựng breadcrumb
            parts = [f"[{doc_name}]"]
            if curr_l1:
                parts.append(f"[{curr_l1}]")
            if curr_l2:
                parts.append(f"[{curr_l2}]")
            if curr_l3:
                parts.append(f"[{curr_l3}]")

            breadcrumb = " > ".join(parts)
            enriched_text = f"{breadcrumb}\n{clean_block}"

            chunk_id = f"{doc_name}_c{chunk_idx:04d}"
            chunks.append(DocumentChunk(
                chunk_id=chunk_id,
                doc_name=doc_name,
                breadcrumb=breadcrumb,
                raw_content=clean_block,
                enriched_text=enriched_text,
                metadata={
                    "level_1": curr_l1,
                    "level_2": curr_l2,
                    "level_3": curr_l3,
                }
            ))
            chunk_idx += 1
            buffer_lines = []

        for line in lines:
            line_str = line.strip()
            if not line_str or line_str.startswith("|---"):
                continue

            # Khối chữ ký / nơi nhận -> chunk riêng để truy xuất "ai ký, ký thay ai"
            if line_str.startswith("|") and self.RE_SIGNATURE.search(line_str):
                flush_buffer()
                sig_text = re.sub(r"<br\s*/?>", "; ", line_str).replace("|", " ").replace("*", "")
                sig_text = re.sub(r"\s+", " ", sig_text).strip()
                sig_breadcrumb = f"[{doc_name}] > [Chữ ký, người ký, ký thay (KT.), thừa lệnh, nơi nhận]"
                chunks.append(DocumentChunk(
                    chunk_id=f"{doc_name}_sig{chunk_idx:04d}",
                    doc_name=doc_name,
                    breadcrumb=sig_breadcrumb,
                    raw_content=sig_text,
                    enriched_text=sig_breadcrumb + "\n" + sig_text,
                    metadata={"kind": "signature"}
                ))
                chunk_idx += 1
                continue

            # Kiểm tra Cấp 1 (Chương/Phần)
            m1 = self.RE_LEVEL_1.match(line_str)
            if m1:
                flush_buffer()
                curr_l1 = line_str.lstrip("#").strip()
                curr_l2 = ""
                curr_l3 = ""
                continue

            # Kiểm tra Cấp 2 (Điều / Mục số lớn)
            m2 = self.RE_LEVEL_2.match(line_str)
            if m2:
                flush_buffer()
                curr_l2 = line_str.lstrip("#").strip()
                curr_l3 = ""
                continue

            # Kiểm tra Cấp 3 (Khoản / a), b), 1.)
            m3 = self.RE_LEVEL_3.match(line_str)
            if m3 and len(buffer_lines) > 0 and sum(len(x) for x in buffer_lines) > self.min_chunk_chars:
                flush_buffer()
                curr_l3 = line_str
                buffer_lines.append(line_str)
                continue

            # Nội dung thông thường
            buffer_lines.append(line_str)
            current_len = sum(len(x) for x in buffer_lines)
            if current_len >= self.max_chunk_chars:
                flush_buffer()

        flush_buffer()

        header = self._build_header_chunk(lines, doc_name)
        if header:
            chunks.insert(0, header)
        return chunks

    def _build_header_chunk(self, lines: List[str], doc_name: str) -> Optional[DocumentChunk]:
        """Chunk thông tin văn bản: số hiệu, ngày ban hành, cơ quan, tiêu đề (trước phần 'Căn cứ')."""
        head: List[str] = []
        for line in lines:
            t = line.strip()
            if not t or t.startswith("|---") or t.startswith("| | |"):
                continue
            if re.match(r"^\**\s*Căn cứ", t.lstrip("*_ ")) or t.startswith("*Căn cứ") or t.startswith("##") or len(head) >= 12:
                break
            head.append(re.sub(r"<br\s*/?>", "; ", t).replace("|", " ").replace("*", "").lstrip("# "))
        text = re.sub(r"\s+", " ", " ".join(head)).strip()
        if not text:
            return None
        breadcrumb = f"[{doc_name}] > [Thông tin văn bản: số hiệu, ngày ban hành, cơ quan ban hành, tiêu đề]"
        return DocumentChunk(
            chunk_id=f"{doc_name}_head",
            doc_name=doc_name,
            breadcrumb=breadcrumb,
            raw_content=text,
            enriched_text=breadcrumb + "\n" + text,
            metadata={"kind": "header"}
        )
