import os
import re
import subprocess
import sys
from rich.console import Console
from rich.markdown import Markdown
from unidecode import unidecode
from termi_cli.tools import shell_tool
from termi_cli import i18n
from termi_cli.config import load_config

ALLOWED_EXTENSIONS = {'.py', '.js', '.ts', '.html', '.css', '.scss', '.json', '.yaml', '.yml', 
                      '.md', '.java', '.cs', '.cpp', '.c', '.h', '.hpp', '.go', '.rs', '.php',
                      '.rb', '.sql', '.sh', '.txt'}
IGNORED_DIRS = {'.venv', '.git', '__pycache__', 'node_modules', 'bin', 'obj'}

MAX_CONTEXT_FILES = 50
MAX_CONTEXT_CHARS = 200_000

def get_directory_context() -> str:
    """Đọc tất cả file hợp lệ trong thư mục hiện tại và trả về nội dung."""
    context_str = ""
    files_processed = 0
    for root, dirs, files in os.walk('.'):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
        
        for file in files:
            if any(file.endswith(ext) for ext in ALLOWED_EXTENSIONS):
                # Giới hạn số file và kích thước context để tránh quá tải
                if files_processed >= MAX_CONTEXT_FILES or len(context_str) >= MAX_CONTEXT_CHARS:
                    context_str += "\n--- CONTEXT TRUNCATED DUE TO SIZE LIMIT ---\n"
                    return context_str

                file_path = os.path.join(root, file)
                normalized_path = os.path.normpath(file_path)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        context_str += f"--- START OF FILE: {normalized_path} ---\n\n"
                        context_str += f.read()
                        context_str += f"\n\n--- END OF FILE: {normalized_path} ---\n\n"
                        files_processed += 1
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

    language = load_config().get("language", "vi")

    console.print(i18n.tr(language, "utils_ai_suggested_commands", count=len(commands_to_run)))
    
    for i, command in enumerate(commands_to_run, 1):
        console.print(f"  [cyan]{i}. {command}[/cyan]")
    
    choice = console.input(i18n.tr(language, "utils_execute_all_prompt"), markup=False).lower().strip()

    if choice in ['n', 'q', '']:
        console.print(i18n.tr(language, "utils_skip_all_commands"))
        return

    execute_all = (choice == 'a')

    for command in commands_to_run:
        do_execute = execute_all
        
        if not execute_all:
            # Tách print và input để vừa có màu, vừa không lỗi parsing
            prompt_text = i18n.tr(language, "utils_execute_each_prompt", command=command)
            console.print(prompt_text, end="")
            sys.stdout.flush()
            individual_choice = input().lower().strip()

            if individual_choice == 'q':
                console.print(i18n.tr(language, "utils_stopped_execution"))
                break

            if individual_choice == 'y':
                do_execute = True
        
        if do_execute:
            try:
                console.print(i18n.tr(language, "utils_executing_command", command=command))
                output = shell_tool.execute_command(command, skip_confirm=True)
                if output:
                    console.print(f"[dim]{output.strip()}[/dim]")
                console.print(i18n.tr(language, "utils_execute_done"))
            except Exception as e:
                console.print(i18n.tr(language, "utils_execute_error", error=e))

        else:
            console.print(i18n.tr(language, "utils_command_skipped"))
            
def sanitize_filename(name: str) -> str:
    """Chuyển đổi một chuỗi bất kỳ thành một tên file an toàn."""
    sanitized_name = unidecode(name).lower()
    sanitized_name = re.sub(r'[^\w\s.-]', '', sanitized_name).strip()
    sanitized_name = re.sub(r'[-\s]+', '_', sanitized_name)
    return sanitized_name