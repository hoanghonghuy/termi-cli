import argparse

def create_parser():
    """Tạo và cấu hình parser cho các tham số dòng lệnh."""
    parser = argparse.ArgumentParser(
        description="AI Agent CLI mạnh mẽ với Gemini.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    # --- Các đối số chính ---
    parser.add_argument("prompt", nargs='?', default=None, help="Câu lệnh hỏi AI.")
    parser.add_argument("--chat", action="store_true", help="Bật chế độ chat tương tác.")
    
    # --- Cấu hình Model & AI ---
    parser.add_argument("--list-models", action="store_true", help="Liệt kê các model khả dụng.")
    parser.add_argument("--set-model", action="store_true", help="Chạy giao diện để chọn model mặc định.")
    parser.add_argument("-m", "--model", type=str, help="Chọn model cho phiên này (ghi đè tạm thời).")
    parser.add_argument("-p", "--persona", type=str, help="Chọn một persona (tính cách) đã định nghĩa trong config.")
    parser.add_argument("-si", "--system-instruction", type=str, help="Ghi đè chỉ dẫn hệ thống cho phiên này.")

    # --- Quản lý Lịch sử ---
    parser.add_argument("--history", action="store_true", help="Hiển thị trình duyệt lịch sử chat.")
    parser.add_argument("--load", type=str, help="Tải lịch sử chat từ một file cụ thể.")
    parser.add_argument("--topic", type=str, help="Tải hoặc tạo một cuộc trò chuyện theo chủ đề.")
    parser.add_argument("--print-log", action="store_true", help="In nội dung của file lịch sử đã tải ra màn hình.")

    # --- Tích hợp & Tiện ích Code ---
    parser.add_argument("--git-commit", action="store_true", help="Tự động tạo commit message cho các thay đổi đã staged.")
    parser.add_argument("--document", type=str, metavar="FILE_PATH", help="Tự động viết tài liệu (docstrings) cho code trong file.")
    parser.add_argument("--refactor", type=str, metavar="FILE_PATH", help="Đề xuất các phương án tái cấu trúc code trong file.")
    
    # --- Input & Output ---
    parser.add_argument("-i", "--image", type=str, help="Đường dẫn tới file ảnh để phân tích.")
    parser.add_argument("-rd", "--read-dir", action="store_true", help="Đọc ngữ cảnh của toàn bộ thư mục hiện tại.")
    parser.add_argument("-f", "--format", type=str, choices=['rich', 'raw'], help="Định dạng output (mặc định: rich).")
    parser.add_argument("-o", "--output", type=str, metavar="FILE_PATH", help="Lưu kết quả đầu ra vào một file thay vì in ra console.")

    return parser