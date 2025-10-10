"""
Module xử lý các tiện ích độc lập như git-commit, document, refactor.
"""
import os
import re
import argparse
import subprocess
from rich.console import Console
from rich.markdown import Markdown

from termi_cli import api, utils
from termi_cli.config import load_config
from termi_cli.tools import code_tool

def generate_git_commit_message(console: Console, args: argparse.Namespace):
    # ... (Hàm này đã hoạt động tốt, giữ nguyên) ...
    try:
        git_status = subprocess.check_output(["git", "status", "--porcelain"], text=True, encoding='utf-8').strip()
        if not git_status:
            console.print("[yellow]Không có thay đổi nào trong repository để commit.[/yellow]")
            return

        console.print("[yellow]Đang tự động stage tất cả các thay đổi (`git add .`)...[/yellow]")
        subprocess.run(["git", "add", "."], check=True, capture_output=True)
        
        staged_diff = subprocess.check_output(["git", "diff", "--staged"], text=True, encoding='utf-8').strip()
        if not staged_diff:
             console.print("[yellow]Không có thay đổi nào được staged để commit sau khi chạy 'git add'.[/yellow]")
             return

        git_commit_system_instruction = (
            "You are an expert at writing Conventional Commits. "
            "Your task is to write a concise and meaningful commit message. "
            "The message **MUST** follow this structure: "
            "1. A subject line (type, optional scope, and description), under 50 characters. "
            "2. A single blank line. "
            "3. A detailed body explaining the 'why' behind the changes, with lines wrapped at 72 characters. "
            "Respond with ONLY the raw commit message content. Do not include any other text, commands, or markdown formatting."
        )

        prompt_text = (
            "Based on the following `git diff --staged`, write a concise Conventional Commit message following the strict structure provided in the system instructions:\n\n"
            f"```diff\n{staged_diff}\n```"
        )
        
        console.print("\n[dim]🤖 Đang yêu cầu AI viết commit message...[/dim]")
        
        config = load_config()
        model_name = args.model or config.get("default_model")
        model = api.genai.GenerativeModel(model_name, system_instruction=git_commit_system_instruction)

        response = api.resilient_generate_content(model, prompt_text)
        commit_message = response.text.strip()

        if commit_message:
            commit_file_path = "COMMIT_EDITMSG.tmp"
            with open(commit_file_path, "w", encoding="utf-8") as f:
                f.write(commit_message)

            commit_command = f'git commit -F "{commit_file_path}"'
            
            console.print(f"\n[green]AI đã đề xuất commit message sau:[/green]\n[yellow]{commit_message}[/yellow]")
            
            fake_ai_response = f"```shell\n{commit_command}\n```"
            utils.execute_suggested_commands(fake_ai_response, console)

            if os.path.exists(commit_file_path):
                os.remove(commit_file_path)

    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Lỗi khi chạy lệnh git: {e.stderr or e.stdout}[/bold red]")
    except Exception as e:
        console.print(f"[bold red]Đã xảy ra lỗi trong quá trình git-commit: {e}[/bold red]")


def document_code_file(console: Console, args: argparse.Namespace):
    """Tự động viết tài liệu cho một file code."""
    _handle_code_utility(console, file_path=args.document, tool_func=code_tool.document_code, tool_name="viết tài liệu", output_file=args.output)

def refactor_code_file(console: Console, args: argparse.Namespace):
    """Đề xuất các phương án tái cấu trúc cho một file code."""
    _handle_code_utility(console, file_path=args.refactor, tool_func=code_tool.refactor_code, tool_name="tái cấu trúc", output_file=args.output)

def _handle_code_utility(console: Console, file_path: str, tool_func, tool_name: str, output_file: str = None):
    """Hàm chung để xử lý các tiện ích code như document và refactor."""
    if not os.path.exists(file_path):
        console.print(f"[bold red]Lỗi: File '{file_path}' không tồn tại.[/bold red]")
        return

    with console.status(f"[bold green]🤖 Đang {tool_name} cho file [cyan]{file_path}[/cyan]...[/bold green]", spinner="dots"):
        result = tool_func(file_path=file_path)
    
    if result.startswith("Error"):
         console.print(f"[bold red]{result}[/bold red]")
         return

    # KHÔI PHỤC LOGIC XUẤT FILE
    if output_file:
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                code_match = re.search(r"```(?:\w+)?\n(.*)```", result, re.DOTALL)
                content_to_write = code_match.group(1).strip() if code_match else result
                f.write(content_to_write)
            console.print(f"\n[bold green]✅ Đã lưu kết quả vào file: [cyan]{output_file}[/cyan][/bold green]")
        except Exception as e:
            console.print(f"[bold red]Lỗi khi lưu file: {e}[/bold red]")
    else:
        console.print(f"\n[bold green]✨ Kết quả {tool_name}:[/bold green]")
        console.print(Markdown(result))