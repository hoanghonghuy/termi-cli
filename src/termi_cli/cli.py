import argparse

def create_parser():
    """Tạo và cấu hình parser cho các tham số dòng lệnh."""
    parser = argparse.ArgumentParser(
        description="AI Agent CLI mạnh mẽ với Gemini.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    # --- Các đối số chính ---
    parser.add_argument("--chat", action="store_true", help="Bật chế độ chat tương tác.")
    parser.add_argument("--agent", action="store_true", help="Bật chế độ Agent tự trị để thực hiện các nhiệm vụ phức tạp.")
    parser.add_argument(
        "--agent-dry-run",
        action="store_true",
        help="Chạy Agent ở chế độ dry-run (chỉ lập kế hoạch và mô phỏng tool, không thực thi lệnh thật).",
    )
    
    # --- Cấu hình Model & AI ---
    model_group = parser.add_argument_group('Cấu hình Model & AI')
    model_group.add_argument("--list-models", action="store_true", help="Liệt kê các model khả dụng.")
    model_group.add_argument("--set-model", action="store_true", help="Chạy giao diện để chọn model mặc định.")
    model_group.add_argument("-m", "--model", type=str, help="Chọn model cho phiên này (ghi đè tạm thởi).")
    model_group.add_argument("-p", "--persona", type=str, help="Chọn một persona (tính cách) đã định nghĩa trong config.")
    model_group.add_argument("-si", "--system-instruction", type=str, help="Ghi đè chỉ dẫn hệ thống cho phiên này.")
    model_group.add_argument(
        "--lang",
        "--language",
        dest="language",
        type=str,
        choices=["vi", "en"],
        help="Chọn ngôn ngữ giao diện cho phiên này (override tạm thởi config.language).",
    )
    
    # --- Quản lý Persona ---
    persona_group = parser.add_argument_group('Quản lý Persona')
    persona_group.add_argument("--add-persona", nargs=2, metavar=('NAME', 'INSTRUCTION'), help="Thêm một persona mới. \nVí dụ: --add-persona python_dev \"Bạn là chuyên gia Python...\"")
    persona_group.add_argument("--list-personas", action="store_true", help="Liệt kê tất cả các persona đã lưu.")
    persona_group.add_argument("--rm-persona", metavar="NAME", type=str, help="Xóa một persona đã lưu theo tên.")

    # --- Quản lý Chỉ Dẫn Tùy Chỉnh ---
    instruct_group = parser.add_argument_group('Quản lý Chỉ Dẫn Tùy Chỉnh (Custom Instructions)')
    instruct_group.add_argument("--add-instruct", metavar="INSTRUCTION", type=str, help="Thêm một chỉ dẫn lâu dài cho AI.")
    instruct_group.add_argument("--list-instructs", action="store_true", help="Liệt kê tất cả các chỉ dẫn đã lưu.")
    instruct_group.add_argument("--rm-instruct", metavar="INDEX", type=int, help="Xóa một chỉ dẫn đã lưu theo số thứ tự.")

    # --- Quản lý Lịch sử ---
    history_group = parser.add_argument_group('Quản lý Lịch sử')
    history_group.add_argument("--history", action="store_true", help="Hiển thị trình duyệt lịch sử chat.")
    history_group.add_argument("--load", type=str, help="Tải lịch sử chat từ một file cụ thể.")
    history_group.add_argument("--topic", type=str, help="Tải hoặc tạo một cuộc trò chuyện theo chủ đề.")
    history_group.add_argument("--print-log", action="store_true", help="In nội dung của file lịch sử đã tải ra màn hình.")
    history_group.add_argument("--summarize", action="store_true", help="Tóm tắt lịch sử chat đã tải (dùng chung với --load hoặc --topic).")

    # --- Tích hợp & Tiện ích Code ---
    code_group = parser.add_argument_group('Tích hợp & Tiện ích Code')
    code_group.add_argument("--git-commit", action="store_true", help="Tự động tạo commit message cho các thay đổi đã staged.")
    code_group.add_argument("--document", type=str, metavar="FILE_PATH", help="Tự động viết tài liệu (docstrings) cho code trong file.")
    code_group.add_argument("--refactor", type=str, metavar="FILE_PATH", help="Đề xuất các phương án tái cấu trúc code trong file.")
    
    # --- Input & Output ---
    io_group = parser.add_argument_group('Input & Output')
    io_group.add_argument("-i", "--image", nargs='+', type=str, help="Đường dẫn tới một hoặc nhiều file ảnh để phân tích.")
    io_group.add_argument("-rd", "--read-dir", action="store_true", help="Đọc ngữ cảnh của toàn bộ thư mục hiện tại.")
    io_group.add_argument("-f", "--format", type=str, help="Định dạng output (mặc định: rich).")
    io_group.add_argument("-o", "--output", type=str, metavar="FILE_PATH", help="Lưu kết quả đầu ra vào một file thay vì in ra console.")

    parser.add_argument("prompt", nargs='?', default=None, help="Câu lệnh hỏi AI (nên đặt ở cuối).")
    
    return parser