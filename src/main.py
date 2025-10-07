import os
import sys
import io
import contextlib
import argparse
import re
from rich.markup import escape
from rich.console import Console
from rich.markdown import Markdown
from PIL import Image

from .tools import code_tool 

# Context manager để tắt stderr tạm thời
@contextlib.contextmanager
def silence_stderr():
    """Tạm thời chuyển hướng stderr sang devnull."""
    original_stderr_fd = os.dup(2)
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull_fd, 2)
    os.close(devnull_fd)
    try:
        yield
    finally:
        os.dup2(original_stderr_fd, 2)
        os.close(original_stderr_fd)

# Đặt các biến môi trường
os.environ.setdefault('GRPC_VERBOSITY', 'ERROR')
os.environ.setdefault('GLOG_minloglevel', '3')
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '3')
os.environ.setdefault('ABSL_CPP_MIN_LOG_LEVEL', '3')

# Tắt log C++ khi import
with silence_stderr():
    import google.generativeai as genai
    from google.api_core.exceptions import ResourceExhausted

# Tắt log Python-level
try:
    import logging
    logging.getLogger('google').setLevel(logging.ERROR)
    logging.getLogger('grpc').setLevel(logging.ERROR)
    logging.getLogger('absl').setLevel(logging.ERROR)
    import absl.logging as _absl_logging
    _absl_logging.set_verbosity(_absl_logging.ERROR)
except (ImportError, AttributeError):
    pass

import json
import traceback
import logging as _logging
import subprocess
from dotenv import load_dotenv

from . import api
from . import utils
from . import cli
from . import handlers
from .config import load_config
from . import memory

_logging.basicConfig(level=_logging.ERROR)

def main(provided_args=None):
    """Hàm chính điều phối toàn bộ ứng dụng."""
    load_dotenv()
    console = Console()
    config = load_config()

    parser = cli.create_parser()
    
    try:
        args = provided_args or parser.parse_args()

        # Tự kiểm tra giá trị của --format một cách thủ công
        if args.format and args.format not in ['rich', 'raw']:
            console.print(f"[bold red]Lỗi: Giá trị không hợp lệ cho --format. Phải là 'rich' hoặc 'raw'.[/bold red]")
            return

        cli_help_text = parser.format_help()
        args.cli_help_text = cli_help_text 

        args.model = args.model or config.get("default_model")
        args.format = args.format or config.get("default_format", "rich")
        args.persona = args.persona or None

        keys = api.initialize_api_keys()
        if not keys:
            console.print("[bold red]Lỗi: Vui lòng thiết lập GOOGLE_API_KEY trong file .env[/bold red]")
            return
        
        if len(keys) > 1:
            console.print(f"[dim]🔑 Đã tải {len(keys)} API key(s)[/dim]")
        
        api.configure_api(keys[0])

        # Xử lý các lệnh quản lý
        if args.add_instruct:
            handlers.add_instruction(console, config, args.add_instruct)
            return
        if args.list_instructs:
            handlers.list_instructions(console, config)
            return
        if args.rm_instruct is not None:
            handlers.remove_instruction(console, config, args.rm_instruct)
            return
        if args.add_persona:
            handlers.add_persona(console, config, args.add_persona[0], args.add_persona[1])
            return
        if args.list_personas:
            handlers.list_personas(console, config)
            return
        if args.rm_persona:
            handlers.remove_persona(console, config, args.rm_persona)
            return
        
        if args.list_models:
            api.list_models(console)
            return
        if args.set_model:
            handlers.model_selection_wizard(console, config)
            return
        
        if args.history and not provided_args:
            selected_file = handlers.show_history_browser(console)
            if selected_file:
                action = ''
                while action not in ['c', 's', 'q']:
                    prompt_text = "Bạn muốn [c]hat tiếp, [s]ummarize (tóm tắt), hay [q]uit? "
                    console.print(f"[bold yellow]{escape(prompt_text)}[/bold yellow]", end="")
                    sys.stdout.flush()
                    action = input().lower().strip()
                    if action not in ['c', 's', 'q']:
                        console.print("[bold red]Lựa chọn không hợp lệ.[/bold red]")

                if action == 'q':
                    console.print("[yellow]Đã thoát.[/yellow]")
                    return

                args.load = selected_file
                if action == 'c':
                    args.chat = True
                    args.print_log = True
                elif action == 's':
                    args.summarize = True
            else:
                return
        
        # Xử lý các tool độc lập
        if args.document or args.refactor:
            file_path = args.document or args.refactor
            tool_func = code_tool.document_code if args.document else code_tool.refactor_code
            tool_name = "viết tài liệu" if args.document else "tái cấu trúc"

            if not os.path.exists(file_path):
                console.print(f"[bold red]Lỗi: File '{file_path}' không tồn tại.[/bold red]")
                return

            with console.status(f"[bold green]🤖 Đang {tool_name} cho file [cyan]{file_path}[/cyan]...[/bold green]", spinner="dots"):
                result = tool_func(file_path=file_path)
            
            if result.startswith("Error"):
                 console.print(f"[bold red]{result}[/bold red]")
                 return

            if args.output:
                try:
                    with open(args.output, 'w', encoding='utf-8') as f:
                        code_match = re.search(r"```(?:\w+)?\n(.*)```", result, re.DOTALL)
                        content_to_write = code_match.group(1).strip() if code_match else result
                        f.write(content_to_write)
                    console.print(f"\n[bold green]✅ Đã lưu kết quả vào file: [cyan]{args.output}[/cyan][/bold green]")
                except Exception as e:
                    console.print(f"[bold red]Lỗi khi lưu file: {e}[/bold red]")
            else:
                console.print(f"\n[bold green]✨ Kết quả {tool_name}:[/bold green]")
                console.print(Markdown(result))
            return

        # Xây dựng system instruction
        saved_instructions = config.get("saved_instructions", [])
        system_instruction_str = "\n".join(f"- {item}" for item in saved_instructions)
        if args.system_instruction:
            system_instruction_str = args.system_instruction
        elif args.persona and config.get("personas", {}).get(args.persona):
            system_instruction_str = config["personas"][args.persona]
        
        # Tải lịch sử
        history = None
        if args.load:
            if os.path.exists(args.load):
                try:
                    with open(args.load, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        history = data.get("history", []) if isinstance(data, dict) else data
                    console.print(f"[green]Đã tải lịch sử từ '{args.load}'.[/green]")
                except Exception as e:
                    console.print(f"[bold red]Lỗi khi tải lịch sử: {e}[/bold red]")
                    return
            else:
                console.print(f"[yellow]Cảnh báo: Không tìm thấy file lịch sử '{args.load}'. Bắt đầu phiên mới.[/yellow]")
        
        if history and args.summarize:
            handlers.handle_history_summary(console, config, history, cli_help_text)
            return
        
        if history and args.print_log:
            handlers.print_formatted_history(console, history)
        
        # Chế độ chat
        if args.chat or args.topic:
            chat_session = api.start_chat_session(args.model, system_instruction_str, history, cli_help_text=cli_help_text)
            handlers.run_chat_mode(chat_session, console, config, args)
            return
        
        # Xử lý input từ pipe
        piped_input = None
        if not sys.stdin.isatty():
             sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding='utf-8')
             piped_input = sys.stdin.read().strip()
        
        # Xây dựng prompt
        if not any([args.prompt, piped_input, args.image, args.git_commit]):
             console.print("[bold red]Lỗi: Cần cung cấp prompt hoặc một hành động cụ thể.[/bold red]")
             parser.print_help()
             return

        prompt_parts = []
        prompt_text = ""
        user_intent = ""

        if args.git_commit:
            try:
                staged_diff = subprocess.check_output(["git", "diff", "--staged"], text=True, encoding='utf-8').strip()
                unstaged_diff = subprocess.check_output(["git", "diff"], text=True, encoding='utf-8').strip()
                untracked_files = subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard"], text=True, encoding='utf-8').strip()

                if not staged_diff and not unstaged_diff and not untracked_files:
                    console.print("[yellow]Không có thay đổi nào trong repository để commit.[/yellow]")
                    return
                
                git_context = "Dưới đây là trạng thái hiện tại của repository Git:\n\n"
                if staged_diff:
                    git_context += f"--- CÁC THAY ĐỔI ĐÃ STAGED ---\n```diff\n{staged_diff}\n```\n\n"
                if unstaged_diff:
                    git_context += f"--- CÁC THAY ĐỔI CHƯA STAGED ---\n```diff\n{unstaged_diff}\n```\n\n"
                if untracked_files:
                    git_context += f"--- CÁC FILE MỚI CHƯA ĐƯỢC THEO DÕI ---\n{untracked_files}\n\n"

                user_intent = (
                    f"{git_context}"
                    "**CRITICAL TASK:** Based on all the Git status information above, you MUST generate exactly two separate shell code blocks:\n"
                    "1. A `git add` command to stage ALL changes (modified and new files).\n"
                    "2. A complete `git commit -m \"...\"` command with a well-written Conventional Commit message that summarizes all the changes.\n"
                    "Do not provide any explanation outside of these two code blocks."
                )
                prompt_text = user_intent
            except subprocess.CalledProcessError:
                console.print("[bold red]Lỗi: Không thể chạy lệnh git. Đây có phải là một repository Git không?[/bold red]")
                return
        else:
            user_question = args.prompt or ""
            if piped_input:
                user_intent = f"Dựa vào nội dung sau: '{piped_input}', hãy thực hiện yêu cầu: '{user_question}'"
                prompt_text = f"Dựa vào nội dung được cung cấp sau đây:\n{piped_input}\n\n{user_question}"
            else:
                user_intent = user_question
                prompt_text = user_question

        if user_intent:
            relevant_memory = memory.search_memory(user_intent)
            if relevant_memory:
                console.print("[dim]🧠 Đã tìm thấy trí nhớ liên quan...[/dim]")
                prompt_text = f"{relevant_memory}\n---\n\n{prompt_text}"

        if args.read_dir:
            console.print("[yellow]Đang đọc ngữ cảnh thư mục...[/yellow]")
            context = utils.get_directory_context()
            prompt_text = f"Dựa vào ngữ cảnh các file dưới đây:\n{context}\n\n{prompt_text}"
        
        if args.image:
            for image_path in args.image:
                try:
                    img = Image.open(image_path)
                    prompt_parts.append(img)
                except (FileNotFoundError, IsADirectoryError):
                    console.print(f"[bold red]Lỗi: Không tìm thấy file ảnh '{image_path}'[/bold red]")
                    return
                except Exception as e:
                    console.print(f"[bold red]Lỗi khi mở ảnh '{image_path}': {e}[/bold red]")
                    return
            console.print(f"[green]Đã tải lên {len(args.image)} ảnh.[/green]")
        
        if prompt_text:
            prompt_parts.append(prompt_text)

        # Gửi yêu cầu tới AI
        chat_session = api.start_chat_session(args.model, system_instruction_str, history, cli_help_text=cli_help_text)
        model_display_name = args.model.replace("models/", "")
        console.print(f"\n[dim]🤖 Model: {model_display_name}[/dim]")
        console.print("\n💡 [bold green]Phản hồi:[/bold green]")
        
        try:
            final_response_text, token_usage, token_limit = handlers.handle_conversation_turn(
                chat_session, prompt_parts, console, model_name=args.model, args=args
            )
            
            if user_intent and final_response_text:
                memory.add_memory(user_intent, final_response_text)
            
            if token_usage and token_usage['total_tokens'] > 0:
                if token_limit > 0:
                    remaining = token_limit - token_usage['total_tokens']
                    console.print(f"\n[dim]📊 Token: {token_usage['prompt_tokens']} (prompt) + "
                                 f"{token_usage['completion_tokens']} (completion) = "
                                 f"{token_usage['total_tokens']:,} / {token_limit:,} "
                                 f"({remaining:,} còn lại)[/dim]")
                else:
                    console.print(f"\n[dim]📊 Token: {token_usage['prompt_tokens']} (prompt) + "
                                 f"{token_usage['completion_tokens']} (completion) = "
                                 f"{token_usage['total_tokens']:,} (total)[/dim]")
            
            if args.output and not (args.document or args.refactor):
                with open(args.output, 'w', encoding='utf-8') as f:
                    f.write(final_response_text)
                console.print(f"\n[bold green]✅ Đã lưu kết quả vào file: [cyan]{args.output}[/cyan][/bold green]")
            
            utils.execute_suggested_commands(final_response_text, console)

        except Exception as e:
            console.print(f"[bold red]\nĐã xảy ra lỗi không mong muốn: {e}[/bold red]")

    except KeyboardInterrupt:
        console.print("\n[yellow]Đã dừng bởi người dùng.[/yellow]")
    except Exception as e:
        console.print(f"[bold red]Đã xảy ra lỗi khởi động: {e}[/bold red]")

if __name__ == "__main__":
    main()