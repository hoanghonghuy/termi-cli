# src/utils.py

import os
import re
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
                normalized_path = os.path.normpath(file_path)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        context_str += f"--- START OF FILE: {normalized_path} ---\n\n"
                        context_str += f.read()
                        context_str += f"\n\n--- END OF FILE: {normalized_path} ---\n\n"
                except Exception as e:
                    context_str += f"--- COULD NOT READ FILE: {normalized_path} (Error: {e}) ---\n\n"
    return context_str

def execute_suggested_commands(text: str, console: Console):
    """
    Tìm, hỏi và thực thi các lệnh shell được đề xuất bên trong các khối mã.
    """
    command_blocks = re.findall(r"```(?:bash|shell|sh)\n(.*?)\n```", text, re.DOTALL)
    
    commands_to_run = []
    for block in command_blocks:
        commands_in_block = [
            cmd.strip() for cmd in block.strip().split('\n') 
            if cmd.strip() and not cmd.strip().startswith('#')
        ]
        commands_to_run.extend(commands_in_block)

    if not commands_to_run:
        return

    console.print(f"\n[bold yellow]AI đã đề xuất {len(commands_to_run)} lệnh thực thi:[/bold yellow]")
    for i, command in enumerate(commands_to_run, 1):
        console.print(f"  [cyan]{i}. {command}[/cyan]")
    
    choice = console.input("Thực thi? [y]es/[n]o/[a]ll/[q]uit: ", markup=False).lower().strip()

    if choice in ['n', 'q', '']:
        console.print("[yellow]Đã bỏ qua tất cả các lệnh.[/yellow]")
        return

    execute_all = (choice == 'a')

    for command in commands_to_run:
        do_execute = execute_all
        
        if not execute_all:
            individual_choice = console.input(f"Thực thi lệnh '[cyan]{command}[/cyan]'? [y/n/q]: ", markup=False).lower().strip()
            if individual_choice == 'q':
                console.print("[yellow]Đã dừng thực thi.[/yellow]")
                break
            if individual_choice == 'y':
                do_execute = True
        
        if do_execute:
            try:
                console.print(f"\n[italic green]▶️ Đang thực thi '[cyan]{command}[/cyan]'...[/italic green]")
                process = subprocess.run(
                    command, shell=True, capture_output=True, text=True, encoding='utf-8', check=True
                )
                
                if process.stdout:
                    console.print(f"[dim]{process.stdout.strip()}[/dim]")
                if process.stderr:
                    console.print(f"[dim]STDERR: {process.stderr.strip()}[/dim]")

                console.print(f"[bold green]✅ Thực thi hoàn tất.[/bold green]")

            except subprocess.CalledProcessError as e:
                 console.print(f"[bold red]❌ Lệnh kết thúc với mã lỗi {e.returncode}.[/bold red]")
                 if e.stderr:
                     console.print(f"[bold red]Lỗi:[/bold red] [dim]{e.stderr.strip()}[/dim]")
            except Exception as e:
                console.print(f"[bold red]Lỗi khi thực thi lệnh: {e}[/bold red]")
        else:
            console.print("[yellow]Đã bỏ qua lệnh.[/yellow]")
            
def sanitize_filename(name: str) -> str:
    """Chuyển đổi một chuỗi bất kỳ thành một tên file an toàn."""
    sanitized_name = unidecode(name).lower()
    sanitized_name = re.sub(r'[^\w\s.-]', '', sanitized_name).strip()
    sanitized_name = re.sub(r'[-\s]+', '_', sanitized_name)
    return sanitized_name