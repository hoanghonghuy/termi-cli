"""
Module xử lý các tiện ích độc lập như git-commit, document, refactor.
"""
import os
import re
import argparse
import subprocess
from rich.console import Console
from rich.markdown import Markdown

from termi_cli import api, utils, i18n
from termi_cli.config import load_config
from termi_cli.tools import code_tool

def generate_git_commit_message(console: Console, args: argparse.Namespace, short: bool = False):
    # ... (Hàm này đã hoạt động tốt, giữ nguyên) ...
    language = "vi"
    try:
        config = load_config()
        language = config.get("language", "vi")
        git_status = subprocess.check_output(["git", "status", "--porcelain"], text=True, encoding='utf-8').strip()
        if not git_status:
            console.print(i18n.tr(language, "git_no_changes_to_commit"))
            return

        console.print(i18n.tr(language, "git_auto_staging"))
        subprocess.run(["git", "add", "."], check=True, capture_output=True)
        
        staged_diff = subprocess.check_output(["git", "diff", "--staged"], text=True, encoding='utf-8').strip()
        if not staged_diff:
             console.print(i18n.tr(language, "git_no_staged_changes"))
             return

        if short:
            git_commit_system_instruction = (
                "You are an expert at writing Conventional Commits. "
                "Your task is to write ONLY a single-line commit subject (under 50 characters). "
                "The line MUST be a valid Conventional Commit, for example: 'feat: add search'. "
                "Do NOT include any body, bullet points, code blocks, quotes, or surrounding markdown. "
                "Return ONLY the raw subject line."
            )

            prompt_text = (
                "Based on the following `git diff --staged`, write ONLY a single-line Conventional Commit subject, "
                "following the system instructions.\n\n"
                f"```diff\n{staged_diff}\n```"
            )
        else:
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
        
        console.print(i18n.tr(language, "git_request_ai_commit_message"))
        
        model_name = args.model or config.get("default_model")

        model = api.genai.GenerativeModel(model_name, system_instruction=git_commit_system_instruction)

        response = api.resilient_generate_content(model, prompt_text)
        commit_message = (response.text or "").strip()

        if not commit_message:
            console.print(i18n.tr(language, "git_commit_message_empty"))
            return

        if short:
            # Lấy dòng đầu tiên, tránh xuống dòng và ký tự quote gây lỗi shell
            commit_subject = commit_message.splitlines()[0].strip().replace('"', "'")
            commit_command = f'git commit -m "{commit_subject}"'

            console.print(i18n.tr(language, "git_commit_message_short_suggested", message=commit_subject))

            fake_ai_response = f"```shell\n{commit_command}\n```"
            utils.execute_suggested_commands(fake_ai_response, console)
        else:
            commit_file_path = "COMMIT_EDITMSG.tmp"
            try:
                with open(commit_file_path, "w", encoding="utf-8") as f:
                    f.write(commit_message)

                commit_command = f'git commit -F "{commit_file_path}"'
                
                console.print(i18n.tr(language, "git_commit_message_full_suggested", message=commit_message))
                
                fake_ai_response = f"```shell\n{commit_command}\n```"
                utils.execute_suggested_commands(fake_ai_response, console)
            finally:
                if os.path.exists(commit_file_path):
                    os.remove(commit_file_path)

    except subprocess.CalledProcessError as e:
        console.print(i18n.tr(language, "git_error_command", error=e.stderr or e.stdout))
    except Exception as e:
        console.print(i18n.tr(language, "git_unexpected_error", error=e))


def document_code_file(console: Console, args: argparse.Namespace):
    """Tự động viết tài liệu cho một file code."""
    _handle_code_utility(console, file_path=args.document, tool_func=code_tool.document_code, tool_name="viết tài liệu", output_file=args.output)

def refactor_code_file(console: Console, args: argparse.Namespace):
    """Đề xuất các phương án tái cấu trúc cho một file code."""
    _handle_code_utility(console, file_path=args.refactor, tool_func=code_tool.refactor_code, tool_name="tái cấu trúc", output_file=args.output)

def _handle_code_utility(console: Console, file_path: str, tool_func, tool_name: str, output_file: str = None):
    """Hàm chung để xử lý các tiện ích code như document và refactor."""
    language = load_config().get("language", "vi")
    if not os.path.exists(file_path):
        console.print(i18n.tr(language, "code_file_not_found", path=file_path))
        return

    with console.status(i18n.tr(language, "code_running_tool", tool_name=tool_name, path=file_path), spinner="dots"):
        result = tool_func(file_path=file_path)
    
    if result.startswith("Error"):
         console.print(i18n.tr(language, "code_error_result", message=result))
         return

    # KHÔI PHỤC LOGIC XUẤT FILE
    if output_file:
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                code_match = re.search(r"```(?:\w+)?\n(.*)```", result, re.DOTALL)
                content_to_write = code_match.group(1).strip() if code_match else result
                f.write(content_to_write)
            console.print(i18n.tr(language, "file_saved_to", path=output_file))
        except Exception as e:
            console.print(i18n.tr(language, "code_error_saving_file", error=e))
    else:
        console.print(i18n.tr(language, "code_result_title", tool_name=tool_name))
        console.print(Markdown(result))