# src/utils.py

import os
import re
import time
import subprocess
from rich.console import Console
from rich.markdown import Markdown
from unidecode import unidecode

ALLOWED_EXTENSIONS = {'.py', '.js', '.ts', '.html', '.css', '.scss', '.json', '.yaml', '.yml', 
                      '.md', '.java', '.cs', '.cpp', '.c', '.h', '.hpp', '.go', '.rs', '.php',
                      '.rb', '.sql', '.sh', '.txt'}
IGNORED_DIRS = {'.venv', '.git', '__pycache__', 'node_modules', 'bin', 'obj'}

# --- BẮT ĐẦU THÊM MỚI ---
def print_streamed_markdown(console: Console, text: str, speed: float = 0.005):
    """
    In một chuỗi Markdown ra console với hiệu ứng streaming từng từ.
    Hàm này giúp cải thiện trải nghiệm người dùng mà không cần thay đổi logic API.
    """
    if not text.strip():
        return

    buffer = ""
    # In từng ký tự để có hiệu ứng mượt mà
    for char in text:
        buffer += char
        # Chỉ render lại Markdown sau khi gặp khoảng trắng hoặc dòng mới để tối ưu hiệu suất
        if char.isspace() or char in ['.', ',', '!', '?', ':', ';']:
            console.print(Markdown(buffer), end="")
            # Dùng \r để đưa con trỏ về đầu dòng, chuẩn bị ghi đè
            # Tuy nhiên, Rich xử lý việc này tốt hơn, ta chỉ cần in chồng lên
            # Vì vậy, chúng ta sẽ xóa dòng hiện tại trước khi in buffer mới
            # Rich không có cách trực tiếp để "xóa và vẽ lại", 
            # việc in liên tục với end="" là cách tiếp cận tốt nhất của nó.
            # Trong trường hợp này, chúng ta sẽ để Rich tự quản lý việc render.
            # Với Rich, cách tốt nhất là build buffer và in ra một lần.
            # Để tạo hiệu ứng, chúng ta sẽ dùng cách thủ công hơn.
            
    # In phần còn lại của buffer
    console.print(Markdown(buffer))

    # Cách tiếp cận thứ hai, đơn giản hơn và hiệu quả với Rich
    # rendered_text = ""
    # for word in text.split(' '):
    #     rendered_text += word + " "
    #     console.clear() # Có thể gây nhấp nháy
    #     console.print(Markdown(rendered_text))
    #     time.sleep(speed)
# --- KẾT THÚC THÊM MỚI ---


def get_directory_context() -> str:
    """Đọc tất cả file hợp lệ trong thư mục hiện tại và trả về nội dung."""
    context_str = ""
    for root, dirs, files in os.walk('.'):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
        
        for file in files:
            if any(file.endswith(ext) for ext in ALLOWED_EXTENSIONS):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        context_str += f"--- START OF FILE: {file_path} ---\n\n"
                        context_str += f.read()
                        context_str += f"\n\n--- END OF FILE: {file_path} ---\n\n"
                except Exception as e:
                    context_str += f"--- COULD NOT READ FILE: {file_path} (Error: {e}) ---\n\n"
    return context_str

def execute_suggested_commands(text: str, console: Console):
    """Tìm, hỏi và thực thi các lệnh shell được đề xuất một cách linh hoạt."""
    command_blocks = re.findall(r"```(bash|shell|sh)\n(.*?)\n```", text, re.DOTALL)
    
    if not command_blocks:
        return

    execute_all = False
    for _, command in command_blocks:
        command = command.strip()
        
        if not execute_all:
            console.print(f"\n[bold yellow]AI đã đề xuất một lệnh:[/bold yellow]")
            console.print(f"[cyan on default]{command}[/cyan on default]")
            choice = console.input("Thực thi? [y]es/[n]o/[a]ll/[q]uit: ").lower()

            if choice == 'q':
                console.print("[yellow]Đã hủy thực thi cho tất cả các lệnh còn lại.[/yellow]")
                break
            elif choice == 'a':
                execute_all = True
            elif choice != 'y':
                console.print("[yellow]Đã bỏ qua lệnh.[/yellow]")
                continue
        
        try:
            console.print(f"[italic green]Đang thực thi...[/italic green]")
            process = subprocess.Popen(
                command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8'
            )
            for line in process.stdout:
                console.print(f"[dim]{line.strip()}[/dim]")
            for line in process.stderr:
                console.print(f"[bold red]Lỗi:[/bold red] [dim]{line.strip()}[/dim]")
            process.wait()
            console.print(f"[bold green]✅ Thực thi hoàn tất.[/bold green]")
        except Exception as e:
            console.print(f"[bold red]Lỗi khi thực thi lệnh: {e}[/bold red]")
            
def sanitize_filename(name: str) -> str:
    """Chuyển đổi một chuỗi bất kỳ thành một tên file an toàn."""
    # Chuyển thành chữ thường, bỏ dấu
    sanitized_name = unidecode(name).lower()
    # Thay thế các ký tự không phải chữ, số, gạch dưới bằng gạch dưới
    sanitized_name = re.sub(r'[^\w\s-]', '', sanitized_name).strip()
    sanitized_name = re.sub(r'[-\s]+', '_', sanitized_name)
    return sanitized_name