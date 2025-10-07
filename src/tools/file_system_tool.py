import os
import glob
from rich.console import Console

# Tạo một console riêng cho tool để tránh xung đột với spinner
tool_console = Console()

IGNORE_PATTERNS = [
    '__pycache__',
    '*.pyc',
    '*.egg-info',
    '.venv',
    '.git',
    'node_modules',
    'bin',
    'obj',
    'memory_db',
]

def list_files(directory: str = ".", pattern: str = "*", recursive: bool = False, read_content: bool = False) -> str:
    """
    Liệt kê các file và thư mục. Nếu read_content=True, sẽ đọc và trả về nội dung của các file tìm thấy.
    Args:
        directory (str): Thư mục cần liệt kê.
        pattern (str): Mẫu để lọc file (ví dụ: '*.py').
        recursive (bool): Nếu True, sẽ tìm kiếm trong các thư mục con.
        read_content (bool): Nếu True, sẽ đọc nội dung của các file tìm thấy.
    """
    print(f"--- TOOL: Liệt kê file trong '{directory}' với mẫu '{pattern}' (Read: {read_content}) ---")
    try:
        search_path = os.path.join(directory, pattern)
        if recursive:
            search_path = os.path.join(directory, '**', pattern)
        
        all_paths = glob.glob(search_path, recursive=recursive)
        
        # Lọc ra các đường dẫn không mong muốn
        filtered_paths = []
        for path in all_paths:
            # Kiểm tra xem bất kỳ phần nào của đường dẫn có khớp với mẫu bỏ qua không
            if not any(ignore_part in path.split(os.sep) for ignore_part in IGNORE_PATTERNS):
                filtered_paths.append(path)

        if not filtered_paths:
            return f"Không tìm thấy file nào (sau khi lọc) khớp với mẫu '{pattern}' trong '{directory}'."
        
        files_only = [f for f in filtered_paths if os.path.isfile(f)]

        if read_content:
            content_str = ""
            for file_path in files_only:
                normalized_path = os.path.normpath(file_path)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    content_str += f"--- START OF FILE: {normalized_path} ---\n\n"
                    content_str += content
                    content_str += f"\n\n--- END OF FILE: {normalized_path} ---\n\n"
                except Exception as e:
                    content_str += f"--- COULD NOT READ FILE: {normalized_path} (Error: {e}) ---\n\n"
            return content_str if content_str else "Không tìm thấy file nào có thể đọc được."
        else:
            normalized_files = [os.path.normpath(f) for f in filtered_paths]
            markdown_list = "\n".join(f"- `{f}`" for f in normalized_files)
            return f"Các file và thư mục tìm thấy:\n{markdown_list}"
            
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
        # Không cần in ra đây nữa vì spinner đã dừng
        # tool_console.print(f"[bold yellow]⚠️ AI muốn ghi vào file '{path}'. Nội dung sẽ được ghi đè nếu file tồn tại.[/bold yellow]")
        
        # Trả về một chuỗi đặc biệt để báo cho handler biết cần hỏi người dùng
        return f"USER_CONFIRMATION_REQUIRED:WRITE_FILE:{path}"
        # --- KẾT THÚC SỬA LỖI TREO ---
    except Exception as e:
        return f"Lỗi khi chuẩn bị ghi file: {e}"