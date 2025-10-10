# src/termi_cli/handlers/utility_handler.py

"""
Module xử lý các tiện ích độc lập như git-commit, document, refactor.
"""
import argparse
import os
import subprocess
from rich.console import Console

from termi_cli import api, utils
from termi_cli.config import load_config

def generate_git_commit_message(console: Console, args: argparse.Namespace):
    """
    Tự động tạo commit message cho các thay đổi đã staged.
    """
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
        # Sử dụng model mặc định hoặc model được chỉ định, không cần model agent mạnh
        model_name = args.model or config.get("default_model")
        model = api.genai.GenerativeModel(model_name, system_instruction=git_commit_system_instruction)

        # SỬA LỖI: Gọi hàm API "bất tử" mới
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