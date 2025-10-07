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

def get_directory_context() -> str:
    """Đọc tất cả file hợp lệ trong thư mục hiện tại và trả về nội dung."""
    context_str = ""
    for root, dirs, files in os.walk('.'):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
        
        for file in files:
            if any(file.endswith(ext) for ext in ALLOWED_EXTENSIONS):
                file_path = os.path.join(root, file)
                
                # Chuẩn hóa đường dẫn để loại bỏ các './' không nhất quán
                normalized_path = os.path.normpath(file_path)

                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        # Sử dụng đường dẫn đã được chuẩn hóa trong output
                        context_str += f"--- START OF FILE: {normalized_path} ---\n\n"
                        context_str += f.read()
                        context_str += f"\n\n--- END OF FILE: {normalized_path} ---\n\n"
                except Exception as e:
                    context_str += f"--- COULD NOT READ FILE: {normalized_path} (Error: {e}) ---\n\n"
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
    # Thay thế các ký tự không phải chữ, số, gạch dưới bằng gạch dưới, dấu chấm
    sanitized_name = re.sub(r'[^\w\s.-]', '', sanitized_name).strip()
    sanitized_name = re.sub(r'[-\s]+', '_', sanitized_name)
    return sanitized_name