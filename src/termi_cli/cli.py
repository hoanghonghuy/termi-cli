import argparse

def create_parser(language: str = "vi"):
    """Tạo và cấu hình parser cho các tham số dòng lệnh.

    Help/description sẽ được hiển thị theo ngôn ngữ (`vi` hoặc `en`).
    """
    if language not in ("vi", "en"):
        language = "vi"

    if language == "en":
        description = (
            "Termi – multi-provider AI CLI (Gemini, DeepSeek, Groq, OpenRouter, Ollama).\n\n"
            "Quick examples:\n"
            "  termi \"Explain this code\"\n"
            "  termi --chat        (or: termi chat)\n"
            "  termi --agent \"Build a CRUD API for User\"  (or: termi agent \"Build a CRUD API for User\")"
        )
        mode_group_title = "Modes"
        model_group_title = "Model & AI"
        persona_group_title = "Personas"
        instruct_group_title = "Custom instructions"
        history_group_title = "History"
        memory_group_title = "Long-term memory"
        code_group_title = "Code tools"
        io_group_title = "Input & output"
    else:
        description = (
            "Termi – AI CLI đa provider (Gemini, DeepSeek, Groq, OpenRouter, Ollama).\n\n"
            "Ví dụ nhanh:\n"
            "  termi \"Giải thích đoạn code này\"\n"
            "  termi --chat        (hoặc: termi chat)\n"
            "  termi --agent \"Xây API CRUD cho User\"  (hoặc: termi agent \"Xây API CRUD cho User\")"
        )
        mode_group_title = "Chế độ hoạt động"
        model_group_title = "Cấu hình Model & AI"
        persona_group_title = "Quản lý Persona"
        instruct_group_title = "Quản lý Chỉ Dẫn Tùy Chỉnh"
        history_group_title = "Quản lý Lịch sử"
        memory_group_title = "Trí nhớ dài hạn"
        code_group_title = "Tích hợp & Tiện ích Code"
        io_group_title = "Input & Output"

    parser = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.RawTextHelpFormatter,
    )

    # --- Chế độ hoạt động ---
    mode_group = parser.add_argument_group(mode_group_title)
    mode_group.add_argument(
        "--chat",
        action="store_true",
        help=(
            "Multi-turn chat mode.\n"
            "Type 'exit' or 'quit' to leave."
            if language == "en"
            else
            "Chế độ chat nhiều lượt.\n"
            "Gõ 'exit' hoặc 'quit' để thoát."
        ),
    )
    mode_group.add_argument(
        "--agent",
        action="store_true",
        help=(
            "Autonomous agent for multi-step tasks (project planning, simple ReAct-style tasks).\n"
            "Requires a goal prompt, e.g. --agent \"Build a task management CLI\"."
            if language == "en"
            else
            "Agent tự động cho nhiệm vụ nhiều bước (lập kế hoạch project, tác vụ ReAct đơn giản).\n"
            "Cần kèm prompt mục tiêu, ví dụ: --agent \"Xây CLI quản lý task\"."
        ),
    )
    mode_group.add_argument(
        "--agent-dry-run",
        action="store_true",
        help=(
            "Agent dry-run: only plan and simulate tool calls,\n"
            "without actually running shell commands or writing files."
            if language == "en"
            else
            "Agent dry-run: chỉ lập kế hoạch và mô phỏng tool,\n"
            "không thực thi lệnh shell hay ghi file thật."
        ),
    )
    mode_group.add_argument(
        "--agent-max-steps",
        type=int,
        metavar="N",
        help=(
            "Limit the maximum number of Agent steps in this session."
            if language == "en"
            else
            "Giới hạn số bước tối đa cho Agent trong phiên này."
        ),
    )

    # --- Cấu hình Model & AI ---
    model_group = parser.add_argument_group(model_group_title)
    model_group.add_argument(
        "--list-models",
        action="store_true",
        help=(
            "List available models."
            if language == "en"
            else
            "Liệt kê các model khả dụng."
        ),
    )
    model_group.add_argument(
        "--set-model",
        action="store_true",
        help=(
            "Run a wizard to choose the default model."
            if language == "en"
            else
            "Chạy wizard để chọn model mặc định."
        ),
    )
    model_group.add_argument(
        "-m",
        "--model",
        type=str,
        help=(
            "Model for this session (temporary override)."
            if language == "en"
            else
            "Chọn model cho phiên này (ghi đè tạm thời)."
        ),
    )
    model_group.add_argument(
        "-p",
        "--persona",
        type=str,
        help=(
            "Persona defined in config."
            if language == "en"
            else
            "Chọn một persona đã định nghĩa trong config."
        ),
    )
    model_group.add_argument(
        "-si",
        "--system-instruction",
        type=str,
        help=(
            "Override system instruction for this session."
            if language == "en"
            else
            "Ghi đè system instruction cho phiên này."
        ),
    )
    model_group.add_argument(
        "--lang",
        "--language",
        dest="language",
        type=str,
        choices=["vi", "en"],
        help=(
            "Choose UI language for this session (temporary override of config.language)."
            if language == "en"
            else
            "Chọn ngôn ngữ giao diện cho phiên này (ghi đè tạm thời config.language)."
        ),
    )
    model_group.add_argument(
        "--set-lang",
        dest="set_lang",
        type=str,
        choices=["vi", "en"],
        help=(
            "Persist default UI language as 'vi' or 'en' in config.json."
            if language == "en"
            else
            "Đặt vĩnh viễn ngôn ngữ giao diện mặc định ('vi' hoặc 'en') trong config.json."
        ),
    )
    model_group.add_argument(
        "--verbose",
        action="store_true",
        help=(
            "Show detailed logs (debug)."
            if language == "en"
            else
            "Hiển thị thêm log chi tiết (debug) khi chạy CLI."
        ),
    )
    model_group.add_argument(
        "--quiet",
        action="store_true",
        help=(
            "Reduce logs; only main results and errors."
            if language == "en"
            else
            "Giảm bớt log/thông báo, chỉ giữ lại kết quả chính và lỗi."
        ),
    )
    model_group.add_argument(
        "--diagnostics",
        "--whoami",
        dest="diagnostics",
        action="store_true",
        help=(
            "Show current config (models, provider, keys present/missing)."
            if language == "en"
            else
            "Hiển thị thông tin cấu hình hiện tại (models, provider, keys có/không)."
        ),
    )
    model_group.add_argument(
        "--doctor",
        action="store_true",
        help=(
            "Check environment (Python, Gemini, API keys, config)."
            if language == "en"
            else
            "Kiểm tra nhanh môi trường (Python, Gemini, API keys, config)."
        ),
    )
    model_group.add_argument(
        "--init-config",
        "--init",
        dest="init_config",
        action="store_true",
        help=(
            "Create default config.json at TERMI_CLI_HOME if missing (does not overwrite existing config)."
            if language == "en"
            else
            "Khởi tạo file config.json mặc định tại TERMI_CLI_HOME nếu chưa tồn tại (không ghi đè cấu hình hiện có)."
        ),
    )
    model_group.add_argument(
        "--profile",
        type=str,
        help=(
            "Apply a saved profile for this session."
            if language == "en"
            else
            "Áp dụng một profile cấu hình nhanh cho phiên này."
        ),
    )
    model_group.add_argument(
        "--save-profile",
        type=str,
        metavar="NAME",
        help=(
            "Save current model config as profile NAME."
            if language == "en"
            else
            "Lưu cấu hình model hiện tại thành một profile tên NAME."
        ),
    )
    model_group.add_argument(
        "--list-profiles",
        action="store_true",
        help=(
            "List saved profiles."
            if language == "en"
            else
            "Liệt kê các profile cấu hình nhanh đã lưu."
        ),
    )
    model_group.add_argument(
        "--rm-profile",
        type=str,
        metavar="NAME",
        help=(
            "Delete profile by name."
            if language == "en"
            else
            "Xóa một profile cấu hình nhanh theo tên."
        ),
    )
    model_group.add_argument(
        "--reset-config",
        action="store_true",
        help=(
            "Delete current config and restore defaults (config.json in TERMI_CLI_HOME or current dir)."
            if language == "en"
            else
            "Xóa file config hiện tại và khôi phục cấu hình mặc định "
            "(config.json trong TERMI_CLI_HOME hoặc thư mục hiện tại)."
        ),
    )

    # --- Quản lý Persona ---
    persona_group = parser.add_argument_group(persona_group_title)
    persona_group.add_argument(
        "--add-persona",
        nargs=2,
        metavar=("NAME", "INSTRUCTION"),
        help=(
            "Add a new persona.\nExample: --add-persona python_dev \"You are a Python expert...\""
            if language == "en"
            else
            "Thêm một persona mới.\nVí dụ: --add-persona python_dev \"Bạn là chuyên gia Python...\""
        ),
    )
    persona_group.add_argument(
        "--list-personas",
        action="store_true",
        help=(
            "List all saved personas."
            if language == "en"
            else
            "Liệt kê tất cả các persona đã lưu."
        ),
    )
    persona_group.add_argument(
        "--rm-persona",
        metavar="NAME",
        type=str,
        help=(
            "Delete a persona by name."
            if language == "en"
            else
            "Xóa một persona đã lưu theo tên."
        ),
    )

    # --- Quản lý Chỉ Dẫn Tùy Chỉnh ---
    instruct_group = parser.add_argument_group(instruct_group_title)
    instruct_group.add_argument(
        "--add-instruct",
        metavar="INSTRUCTION",
        type=str,
        help=(
            "Add a persistent custom instruction for the AI."
            if language == "en"
            else
            "Thêm một chỉ dẫn lâu dài cho AI."
        ),
    )
    instruct_group.add_argument(
        "--list-instructs",
        action="store_true",
        help=(
            "List all saved custom instructions."
            if language == "en"
            else
            "Liệt kê tất cả các chỉ dẫn đã lưu."
        ),
    )
    instruct_group.add_argument(
        "--rm-instruct",
        metavar="INDEX",
        type=int,
        help=(
            "Delete a custom instruction by index."
            if language == "en"
            else
            "Xóa một chỉ dẫn đã lưu theo số thứ tự."
        ),
    )

    # --- Quản lý Lịch sử ---
    history_group = parser.add_argument_group(history_group_title)
    history_group.add_argument(
        "--history",
        action="store_true",
        help=(
            "Open interactive chat history browser."
            if language == "en"
            else
            "Hiển thị trình duyệt lịch sử chat."
        ),
    )
    history_group.add_argument(
        "--load",
        type=str,
        help=(
            "Load chat history from a specific file."
            if language == "en"
            else
            "Tải lịch sử chat từ một file cụ thể."
        ),
    )
    history_group.add_argument(
        "--topic",
        type=str,
        help=(
            "Load or create a conversation by topic."
            if language == "en"
            else
            "Tải hoặc tạo một cuộc trò chuyện theo chủ đề."
        ),
    )
    history_group.add_argument(
        "--print-log",
        action="store_true",
        help=(
            "Print the contents of the loaded history file."
            if language == "en"
            else
            "In nội dung của file lịch sử đã tải ra màn hình."
        ),
    )
    history_group.add_argument(
        "--summarize",
        action="store_true",
        help=(
            "Summarize the loaded chat history (use with --load or --topic)."
            if language == "en"
            else
            "Tóm tắt lịch sử chat đã tải (dùng chung với --load hoặc --topic)."
        ),
    )
    history_group.add_argument(
        "--rm-history",
        type=str,
        help=(
            "Delete a chat history by file path or topic (non-interactive)."
            if language == "en"
            else
            "Xóa một lịch sử chat theo đường dẫn file hoặc topic (non-interactive)."
        ),
    )
    history_group.add_argument(
        "--rename-history",
        nargs=2,
        metavar=("OLD", "NEW"),
        help=(
            "Rename a chat history by file path or topic (non-interactive)."
            if language == "en"
            else
            "Đổi tên lịch sử chat theo đường dẫn file hoặc topic (non-interactive)."
        ),
    )
    history_group.add_argument(
        "--history-filter",
        type=str,
        metavar="QUERY",
        help=(
            "Filter history list in --history browser by keyword in title."
            if language == "en"
            else
            "Lọc danh sách lịch sử khi hiển thị với --history theo từ khoá trong tiêu đề."
        ),
    )

    # --- Trí nhớ dài hạn ---
    memory_group = parser.add_argument_group(memory_group_title)
    memory_group.add_argument(
        "--reset-memory",
        action="store_true",
        help=(
            "Delete the entire long-term memory database (memory_db).\n"
            "Use when memory_db is corrupted or you want a clean reset."
            if language == "en"
            else
            "Xóa toàn bộ database trí nhớ dài hạn (memory_db).\n"
            "Dùng khi memory_db bị lỗi hoặc bạn muốn reset sạch."
        ),
    )
    memory_group.add_argument(
        "--memory-search",
        type=str,
        metavar="QUERY",
        help=(
            "Search long-term memory and print related interactions."
            if language == "en"
            else
            "Tìm kiếm trong trí nhớ dài hạn và in các tương tác liên quan."
        ),
    )

    # --- Tích hợp & Tiện ích Code ---
    code_group = parser.add_argument_group(code_group_title)
    code_group.add_argument(
        "--git-commit",
        action="store_true",
        help=(
            "Generate a FULL commit message for staged changes and run 'git commit -F <temp_file>'."
            if language == "en"
            else
            "Sinh commit message ĐẦY ĐỦ cho các thay đổi đã staged và chạy git commit -F <file_tạm>."
        ),
    )
    code_group.add_argument(
        "--git-commit-short",
        action="store_true",
        help=(
            "Generate a SHORT (one-line) commit message for staged changes and run 'git commit -m <message>'."
            if language == "en"
            else
            "Sinh commit message NGẮN (một dòng) cho các thay đổi đã staged và chạy git commit -m <message>."
        ),
    )
    code_group.add_argument(
        "--document",
        type=str,
        metavar="FILE_PATH",
        help=(
            "Automatically write documentation (docstrings) for code in the file."
            if language == "en"
            else
            "Tự động viết tài liệu (docstrings) cho code trong file."
        ),
    )
    code_group.add_argument(
        "--refactor",
        type=str,
        metavar="FILE_PATH",
        help=(
            "Suggest refactorings for the code in the file."
            if language == "en"
            else
            "Đề xuất các phương án tái cấu trúc code trong file."
        ),
    )
    code_group.add_argument(
        "--list-tools",
        action="store_true",
        help=(
            "List all available tools (including plugins)."
            if language == "en"
            else
            "Liệt kê tất cả tools khả dụng (bao gồm plugin)."
        ),
    )

    # --- Input & Output ---
    io_group = parser.add_argument_group(io_group_title)
    io_group.add_argument(
        "-i",
        "--image",
        nargs="+",
        type=str,
        help=(
            "Path to one or more image files to analyze."
            if language == "en"
            else
            "Đường dẫn tới một hoặc nhiều file ảnh để phân tích."
        ),
    )
    io_group.add_argument(
        "-rd",
        "--read-dir",
        action="store_true",
        help=(
            "Read context from the entire current directory."
            if language == "en"
            else
            "Đọc ngữ cảnh của toàn bộ thư mục hiện tại."
        ),
    )
    io_group.add_argument(
        "-f",
        "--format",
        type=str,
        help=(
            "Output format (default: rich)."
            if language == "en"
            else
            "Định dạng output (mặc định: rich)."
        ),
    )
    io_group.add_argument(
        "-o",
        "--output",
        type=str,
        metavar="FILE_PATH",
        help=(
            "Save output to a file instead of printing to console."
            if language == "en"
            else
            "Lưu kết quả đầu ra vào một file thay vì in ra console."
        ),
    )

    parser.add_argument(
        "prompt",
        nargs="?",
        default=None,
        help=(
            "Prompt for single-turn mode (leave empty when using --chat or --agent)."
            if language == "en"
            else
            "Câu lệnh hỏi AI cho chế độ single-turn (bỏ trống nếu dùng --chat hoặc --agent)."
        ),
    )

    return parser