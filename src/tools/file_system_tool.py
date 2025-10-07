# src/tools/file_system_tool.py
import os
import glob
from rich.console import Console

# Tạo một console riêng cho tool để tránh xung đột với spinner
tool_console = Console()

def list_files(directory: str = ".", pattern: str = "*", recursive: bool = False) -> str:
    """
    Liệt kê các file và thư mục, trả về dưới dạng danh sách Markdown.
    """
    print(f"--- TOOL: Liệt kê file trong '{directory}' với mẫu '{pattern}' ---")
    try:
        search_path = os.path.join(directory, pattern)
        if recursive:
            search_path = os.path.join(directory, '**', pattern)
        
        files = glob.glob(search_path, recursive=recursive)
        
        if not files:
            return f"Không tìm thấy file nào khớp với mẫu '{pattern}' trong '{directory}'."
        
        # --- BẮT ĐẦU SỬA LỖI HIỂN THỊ ---
        # Định dạng output thành danh sách Markdown
        markdown_list = "\n".join(f"- `{os.path.normpath(f)}`" for f in files)
        return f"Các file và thư mục tìm thấy:\n{markdown_list}"
        # --- KẾT THÚC SỬA LỖI HIỂN THỊ ---
    except Exception as e:
        return f"Lỗi khi liệt kê file: {e}"

def read_file(path: str) -> str:
    """
    Đọc và trả về toàn bộ nội dung của một file văn bản.
    """
    print(f"--- TOOL: Đọc file '{path}' ---")
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        return content
    except FileNotFoundError:
        return f"Lỗi: Không tìm thấy file tại '{path}'."
    except Exception as e:
        return f"Lỗi khi đọc file: {e}"

def write_file(path: str, content: str) -> str:
    """
    Ghi nội dung vào một file. Sẽ hỏi người dùng xác nhận trước khi thực hiện.
    """
    print(f"--- TOOL: Yêu cầu ghi file '{path}' ---")
    try:
        # --- BẮT ĐẦU SỬA LỖI TREO ---
        # Không cần in ra đây nữa vì spinner đã dừng
        # tool_console.print(f"[bold yellow]⚠️ AI muốn ghi vào file '{path}'. Nội dung sẽ được ghi đè nếu file tồn tại.[/bold yellow]")
        
        # Trả về một chuỗi đặc biệt để báo cho handler biết cần hỏi người dùng
        return f"USER_CONFIRMATION_REQUIRED:WRITE_FILE:{path}"
        # --- KẾT THÚC SỬA LỖI TREO ---
    except Exception as e:
        return f"Lỗi khi chuẩn bị ghi file: {e}"