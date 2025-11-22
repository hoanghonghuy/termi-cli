import argparse

def create_parser():
    """Tạo và cấu hình parser cho các tham số dòng lệnh."""
    parser = argparse.ArgumentParser(
        description=(
            "Termi – AI CLI đa provider (Gemini, DeepSeek, Groq).\n\n"
            "Ví dụ nhanh:\n"
            "  termi \"Giải thích đoạn code này\"\n"
            "  termi --chat\n"
            "  termi --agent \"Xây API CRUD cho User\""
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    
    # --- Chế độ hoạt động ---
    mode_group = parser.add_argument_group("Chế độ hoạt động")
    mode_group.add_argument(
        "--chat",
        action="store_true",
        help=(
            "Bật chế độ chat tương tác (hội thoại nhiều lượt).\n"
            "Gõ 'exit' hoặc 'quit' để thoát."
        ),
    )
    mode_group.add_argument(
        "--agent",
        action="store_true",
        help=(
            "Bật chế độ Agent tự trị để xử lý nhiệm vụ nhiều bước\n"
            "(lập kế hoạch project hoặc tác vụ ReAct đơn giản).\n"
            "Cần kèm prompt mô tả mục tiêu, ví dụ: --agent \"Xây CLI quản lý task\"."
        ),
    )

    mode_group.add_argument(
        "--agent-dry-run",
        action="store_true",
        help=(
            "Chạy Agent ở chế độ dry-run: chỉ lập kế hoạch và mô phỏng tool,\n"
            "không thực thi lệnh shell, ghi file hay lệnh nguy hiểm thật."
        ),
    )
    mode_group.add_argument(
        "--agent-max-steps",
        type=int,
        metavar="N",
        help=(
            "Giới hạn số bước tối đa cho Agent trong phiên này.\n"
            "Nếu bỏ trống, Agent dùng giá trị mặc định nội bộ."
        ),
    )
    
    # --- Cấu hình Model & AI ---
    model_group = parser.add_argument_group("Cấu hình Model & AI")

    model_group.add_argument("--list-models", action="store_true", help="Liệt kê các model khả dụng.")
    model_group.add_argument("--set-model", action="store_true", help="Chạy giao diện để chọn model mặc định.")
    
    model_group.add_argument("-m", "--model", type=str, help="Chọn model cho phiên này (ghi đè tạm thời).")
    
    model_group.add_argument("-p", "--persona", type=str, help="Chọn một persona (tính cách) đã định nghĩa trong config.")
    model_group.add_argument("-si", "--system-instruction", type=str, help="Ghi đè chỉ dẫn hệ thống cho phiên này.")
    model_group.add_argument(
        "--lang",
        "--language",
        dest="language",
        type=str,
        choices=["vi", "en"],
        help="Chọn ngôn ngữ giao diện cho phiên này (override tạm thời config.language).",
    )
    model_group.add_argument(
        "--verbose",
        action="store_true",
        help="Hiển thị thêm thông tin chi tiết (debug) khi chạy CLI.",
    )
    model_group.add_argument(
        "--quiet",
        action="store_true",
        help="Giảm bớt các log/thông báo, chỉ giữ lại kết quả chính và lỗi.",
    )
    model_group.add_argument(
        "--diagnostics",
        "--whoami",
        dest="diagnostics",
        action="store_true",
        help="Hiển thị thông tin cấu hình hiện tại (models, provider, v.v.).",
    )
    model_group.add_argument(
        "--profile",
        type=str,
        help="Áp dụng một profile cấu hình nhanh cho phiên này.",
    )
    model_group.add_argument(
        "--save-profile",
        type=str,
        metavar="NAME",
        help="Lưu cấu hình model hiện tại thành một profile tên NAME.",
    )
    model_group.add_argument(
        "--list-profiles",
        action="store_true",
        help="Liệt kê các profile cấu hình nhanh đã lưu.",
    )
    model_group.add_argument(
        "--rm-profile",
        type=str,
        metavar="NAME",
        help="Xóa một profile cấu hình nhanh theo tên.",
    )
    
    # --- Quản lý Persona ---
    persona_group = parser.add_argument_group("Quản lý Persona")

    persona_group.add_argument("--add-persona", nargs=2, metavar=('NAME', 'INSTRUCTION'), help="Thêm một persona mới. \nVí dụ: --add-persona python_dev \"Bạn là chuyên gia Python...\"")
    persona_group.add_argument("--list-personas", action="store_true", help="Liệt kê tất cả các persona đã lưu.")
    persona_group.add_argument("--rm-persona", metavar="NAME", type=str, help="Xóa một persona đã lưu theo tên.")

    # --- Quản lý Chỉ Dẫn Tùy Chỉnh ---
    instruct_group = parser.add_argument_group("Quản lý Chỉ Dẫn Tùy Chỉnh (Custom Instructions)")

    instruct_group.add_argument("--add-instruct", metavar="INSTRUCTION", type=str, help="Thêm một chỉ dẫn lâu dài cho AI.")
    instruct_group.add_argument("--list-instructs", action="store_true", help="Liệt kê tất cả các chỉ dẫn đã lưu.")
    instruct_group.add_argument("--rm-instruct", metavar="INDEX", type=int, help="Xóa một chỉ dẫn đã lưu theo số thứ tự.")

    # --- Quản lý Lịch sử ---
    history_group = parser.add_argument_group("Quản lý Lịch sử")

    history_group.add_argument("--history", action="store_true", help="Hiển thị trình duyệt lịch sử chat.")
    history_group.add_argument("--load", type=str, help="Tải lịch sử chat từ một file cụ thể.")
    history_group.add_argument("--topic", type=str, help="Tải hoặc tạo một cuộc trò chuyện theo chủ đề.")
    history_group.add_argument("--print-log", action="store_true", help="In nội dung của file lịch sử đã tải ra màn hình.")
    history_group.add_argument("--summarize", action="store_true", help="Tóm tắt lịch sử chat đã tải (dùng chung với --load hoặc --topic).")
    history_group.add_argument(
        "--rm-history",
        type=str,
        help="Xóa một lịch sử chat theo đường dẫn file hoặc topic (non-interactive).",
    )
    history_group.add_argument(
        "--rename-history",
        nargs=2,
        metavar=("OLD", "NEW"),
        help="Đổi tên lịch sử chat theo đường dẫn file hoặc topic (non-interactive).",
    )

    # --- Trí nhớ dài hạn ---
    memory_group = parser.add_argument_group("Trí nhớ dài hạn")
    memory_group.add_argument(
        "--reset-memory",
        action="store_true",
        help=(
            "Xóa toàn bộ database trí nhớ dài hạn (memory_db).\n"
            "Dùng khi memory_db bị lỗi hoặc bạn muốn reset sạch."
        ),
    )
    memory_group.add_argument(
        "--memory-search",
        type=str,
        metavar="QUERY",
        help="Tìm kiếm trong trí nhớ dài hạn và in các tương tác liên quan.",
    )

    # --- Tích hợp & Tiện ích Code ---
    code_group = parser.add_argument_group("Tích hợp & Tiện ích Code")
    code_group.add_argument(
        "--git-commit",
        action="store_true",
        help=(
            "Sinh commit message ĐẦY ĐỦ cho các thay đổi đã staged\n"
            "và thực thi git commit -F <file_tạm>."
        ),
    )
    code_group.add_argument(
        "--git-commit-short",
        action="store_true",
        help=(
            "Sinh commit message NGẮN một dòng (subject) cho các thay đổi đã staged\n"
            "và thực thi git commit -m <message>."
        ),
    )

    code_group.add_argument("--document", type=str, metavar="FILE_PATH", help="Tự động viết tài liệu (docstrings) cho code trong file.")
    code_group.add_argument("--refactor", type=str, metavar="FILE_PATH", help="Đề xuất các phương án tái cấu trúc code trong file.")
    code_group.add_argument("--list-tools", action="store_true", help="Liệt kê tất cả tools khả dụng (bao gồm plugin).")
    
    # --- Input & Output ---
    io_group = parser.add_argument_group("Input & Output")

    io_group.add_argument("-i", "--image", nargs='+', type=str, help="Đường dẫn tới một hoặc nhiều file ảnh để phân tích.")
    io_group.add_argument("-rd", "--read-dir", action="store_true", help="Đọc ngữ cảnh của toàn bộ thư mục hiện tại.")
    io_group.add_argument("-f", "--format", type=str, help="Định dạng output (mặc định: rich).")
    io_group.add_argument("-o", "--output", type=str, metavar="FILE_PATH", help="Lưu kết quả đầu ra vào một file thay vì in ra console.")

    parser.add_argument(
        "prompt",
        nargs="?",
        default=None,
        help=(
            "Câu lệnh hỏi AI cho chế độ single-turn.\n"
            "Bỏ trống nếu bạn dùng --chat hoặc --agent."
        ),
    )
    
    return parser