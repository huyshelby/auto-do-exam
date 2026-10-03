import os
import sys
import json
import requests

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

SERVER_URL = "http://127.0.0.1:8000/solve"

QUESTIONS = [
    {
        "id": "q1",
        "question": "Theo Quyết định số 1963/QĐ-UBND ngày 06/5/2026 của UBND thành phố Đà Nẵng, ai là người ký thay Chủ tịch (KT. Chủ tịch)?",
        "expected": "A",
        "options": [
            {"key": "A", "text": "Phó Chủ tịch Hồ Quang Bửu"},
            {"key": "B", "text": "Giám đốc Sở Nội vụ thành phố"},
            {"key": "C", "text": "Chánh Văn phòng UBND thành phố"},
            {"key": "D", "text": "Chủ tịch Hội đồng nhân dân thành phố"}
        ]
    },
    {
        "id": "q2",
        "question": "Theo Kế hoạch số 1963/QĐ-UBND, công tác thông tin, tuyên truyền CCHC năm 2026 phải quán triệt nguyên tắc lấy đối tượng nào làm 'trung tâm, chủ thể, mục tiêu và động lực của CCHC'?",
        "expected": "B",
        "options": [
            {"key": "A", "text": "Doanh nghiệp nhà nước và cơ quan báo chí địa phương"},
            {"key": "B", "text": "Người dân, doanh nghiệp"},
            {"key": "C", "text": "Đội ngũ cán bộ quản lý cấp thành phố"},
            {"key": "D", "text": "Các tổ chức tài chính và nhà đầu tư nước ngoài"}
        ]
    },
    {
        "id": "q3",
        "question": "Theo Kế hoạch số 244/KH-UBND ngày 07/8/2026 của UBND xã Đại Lộc, công tác tuyên truyền CCHC được đưa vào hoạt động thường xuyên trên kênh thông tin nào?",
        "expected": "A",
        "options": [
            {"key": "A", "text": "Trang Thông tin Đại Lộc"},
            {"key": "B", "text": "Kênh truyền hình VTV1 Quốc gia"},
            {"key": "C", "text": "Tạp chí Nghiên cứu Lập pháp"},
            {"key": "D", "text": "Bản tin nội bộ của Bộ Nội vụ"}
        ]
    },
    {
        "id": "q4",
        "question": "Theo Kế hoạch kèm Quyết định số 1963/QĐ-UBND, yêu cầu đối với các cơ quan, đơn vị về việc sản xuất video clip tuyên truyền CCHC trong năm là gì?",
        "expected": "A",
        "options": [
            {"key": "A", "text": "100% các đơn vị thực hiện ít nhất 01 video clip truyền tải thông điệp về CCHC trong năm"},
            {"key": "B", "text": "Mỗi quý phát hành ít nhất 05 video phóng sự chuyên sâu"},
            {"key": "C", "text": "Chỉ có Đài Phát thanh - Truyền hình Đà Nẵng chịu trách nhiệm làm video clip"},
            {"key": "D", "text": "Không bắt buộc sản xuất video clip, chỉ đăng bài viết trên mạng xã hội"}
        ]
    },
    {
        "id": "q5",
        "question": "Mục tiêu chung của Kế hoạch số 244/KH-UBND ngày 07/8/2026 trên địa bàn xã Đại Lộc nhằm nâng cao nhận thức và sự đồng thuận của ai?",
        "expected": "A",
        "options": [
            {"key": "A", "text": "Cán bộ quản lý, cán bộ, công chức, viên chức xã và người dân, tổ chức, xã hội"},
            {"key": "B", "text": "Cắt giảm 50% số lượng cán bộ cấp xã trong năm 2026"},
            {"key": "C", "text": "Dừng toàn bộ việc tiếp nhận và xử lý thủ tục hành chính trực tiếp"},
            {"key": "D", "text": "Xóa bỏ hoàn toàn hệ thống loa truyền thanh cơ sở"}
        ]
    }
]

def run_multi_eval():
    print("=== ĐÁNH GIÁ ĐỘ CHÍNH XÁC PIPELINE TRÊN BỘ ĐỀ 5 CÂU HỎI ===")
    correct = 0
    for idx, item in enumerate(QUESTIONS, 1):
        payload = {
            "question": item["question"],
            "options": item["options"]
        }
        res = requests.post(SERVER_URL, json=payload, timeout=5)
        data = res.json()

        is_match = data["selected_key"] == item["expected"]
        if is_match:
            correct += 1

        print(f"\n[Câu {idx}] {item['question'][:65]}...")
        print(f" -> Dự đoán: [{data['selected_key']}] | Kỳ vọng: [{item['expected']}] | Khớp: {'✅ ĐÚNG' if is_match else '❌ SAI'}")
        print(f" -> Tin cậy: {data['confidence']} | Delay: {data['suggested_delay_ms']}ms | Cache: {data.get('from_cache', False)}")
        print(f" -> Ngữ cảnh trích xuất: {data['matched_chunk'][:100]}...")

    score_pct = (correct / len(QUESTIONS)) * 100
    print(f"\n==================================================")
    print(f"TỔNG KẾT: {correct}/{len(QUESTIONS)} câu đúng ({score_pct:.1f}%)")
    print(f"==================================================")

if __name__ == "__main__":
    run_multi_eval()
