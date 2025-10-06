import os
import sys

# --- Giảm log native ---
os.environ.setdefault('GRPC_VERBOSITY', 'ERROR')
os.environ.setdefault('GLOG_minloglevel', '3')
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '3')
os.environ.setdefault('GRPC_ENABLE_FORK_SUPPORT', '0')
os.environ.setdefault('GRPC_POLL_STRATEGY', 'poll')
os.environ.setdefault('ABSL_CPP_MIN_LOG_LEVEL', '3')

# --- Kiểm soát việc tắt stderr ---
SILENCE_NATIVE_STDERR = os.getenv("SILENCE_NATIVE_STDERR", "1") == "1"

# ✅ Chỉ redirect stderr thực sự nếu chạy trên Linux/macOS
if SILENCE_NATIVE_STDERR and os.name != "nt":  # tránh Windows
    try:
        devnull_fd = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull_fd, 2)
        sys.stderr = open(os.devnull, 'w')
    except Exception:
        pass
else:
    # Trên Windows chỉ tắt log ở Python-level
    import logging
    logging.getLogger('google').setLevel(logging.ERROR)
    logging.getLogger('grpc').setLevel(logging.ERROR)
    logging.getLogger('absl').setLevel(logging.ERROR)
    try:
        import absl.logging as _absl_logging
        _absl_logging.set_verbosity(_absl_logging.ERROR)
    except Exception:
        pass

# --- Import phần còn lại ---
import json
import traceback
import logging as _logging
import subprocess
from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from PIL import Image
from google.api_core.exceptions import ResourceExhausted

import api
import utils
import cli
import handlers
from config import load_config

_logging.basicConfig(level=_logging.ERROR)

def main(provided_args=None):
    """Hàm chính điều phối toàn bộ ứng dụng."""
    load_dotenv()
    console = Console()
    config = load_config()

    parser = cli.create_parser()
    args = provided_args or parser.parse_args()

    cli_help_text = parser.format_help()
    args.cli_help_text = cli_help_text 

    args.model = args.model or config.get("default_model")
    args.format = args.format or config.get("default_format", "rich")
    args.persona = args.persona or None

    # Khởi tạo API keys từ .env
    keys = api.initialize_api_keys()
    if not keys:
        console.print("[bold red]Lỗi: Vui lòng thiết lập GOOGLE_API_KEY trong file .env[/bold red]")
        return
    
    if len(keys) > 1:
        console.print(f"[dim]🔑 Đã tải {len(keys)} API key(s)[/dim]")
    
    try:
        # Configure với key đầu tiên
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
        
        if args.list_models:
            api.list_models(console)
            return
        if args.set_model:
            handlers.model_selection_wizard(console, config)
            return
        if args.history and not provided_args:
            selected_file = handlers.show_history_browser(console)
            if selected_file:
                prompt_text = "Bạn muốn [c]hat tiếp, [s]ummarize (tóm tắt), hay [q]uit? "
                action = input(prompt_text).lower()
                if action == 'c':
                    new_args = parser.parse_args(['--load', selected_file, '--chat', '--print-log'])
                    main(new_args)
                elif action == 's':
                    new_args = parser.parse_args(['--load', selected_file, '--summarize'])
                    main(new_args)
            return

        # Xử lý system instruction
        saved_instructions = config.get("saved_instructions", [])
        system_instruction_str = "\n".join(f"- {item}" for item in saved_instructions)
        if args.system_instruction:
            system_instruction_str = args.system_instruction
        elif args.persona and config.get("personas", {}).get(args.persona):
            system_instruction_str = config["personas"][args.persona]
        
        # Tải lịch sử nếu có
        history = None
        load_path = None
        if args.topic:
            sanitized_topic = utils.sanitize_filename(args.topic)
            load_path = os.path.join(handlers.HISTORY_DIR, f"chat_{sanitized_topic}.json")
        elif args.load:
            load_path = args.load

        if load_path and os.path.exists(load_path):
            try:
                with open(load_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    history = data.get("history", []) if isinstance(data, dict) else data
                console.print(f"[green]Đã tải lịch sử từ '{load_path}'.[/green]")
            except Exception as e:
                console.print(f"[bold red]Lỗi khi tải lịch sử: {e}[/bold red]")
                return
        
        # Xử lý summarize
        if history and args.summarize:
            handlers.handle_history_summary(console, config, history, cli_help_text)
            return
        
        # In lịch sử nếu có
        if history and args.print_log:
            handlers.print_formatted_history(console, history)
            if not args.chat and not args.topic:
                 return

        # Khởi tạo chat session
        chat_session = api.start_chat_session(args.model, system_instruction_str, history, cli_help_text=cli_help_text)
        
        # Chế độ chat
        if args.chat or args.topic:
            handlers.run_chat_mode(chat_session, console, config, args)
            return
        
        # Đọc input từ pipe
        piped_input = None
        if not sys.stdin.isatty():
             piped_input = sys.stdin.read().strip()
        
        # Kiểm tra có prompt hay không
        if not any([args.prompt, piped_input, args.image, args.git_commit, args.document, args.refactor]):
             console.print("[bold red]Lỗi: Cần cung cấp prompt hoặc một hành động cụ thể.[/bold red]")
             parser.print_help()
             return

        # Xây dựng prompt
        prompt_parts = []
        user_question = args.prompt or ""

        # Xử lý ảnh
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
        
        # Xây dựng prompt text
        prompt_text = ""
        if piped_input:
            prompt_text += f"Dựa vào nội dung được cung cấp sau đây:\n{piped_input}\n\n{user_question}"
        else:
            prompt_text += user_question

        # Đọc context thư mục
        if args.read_dir:
            console.print("[yellow]Đang đọc ngữ cảnh thư mục...[/yellow]")
            context = utils.get_directory_context()
            prompt_text = f"Dựa vào ngữ cảnh các file dưới đây:\n{context}\n\n{prompt_text}"
        
        # Xử lý các chức năng đặc biệt
        if args.git_commit:
             diff = subprocess.check_output(["git", "diff", "--staged"], text=True, encoding='utf-8')
             prompt_text = (
                 "Hãy viết một commit message theo chuẩn Conventional Commits dựa trên git diff sau:\n"
                 f"```diff\n{diff}\n```"
             )
        elif args.document:
            console.print(f"🤖 [bold cyan]Đang yêu cầu AI viết tài liệu cho file '{args.document}'...[/bold cyan]")
            prompt_text = f"Sử dụng tool 'document_code' để viết tài liệu cho file '{args.document}'."
        elif args.refactor:
            console.print(f"🤖 [bold cyan]Đang yêu cầu AI tái cấu trúc file '{args.refactor}'...[/bold cyan]")
            prompt_text = f"Sử dụng tool 'refactor_code' để tái cấu trúc code trong file '{args.refactor}'."

        if prompt_text:
            prompt_parts.append(prompt_text)

        # Hiển thị model đang sử dụng
        model_display_name = args.model.replace("models/", "")
        console.print(f"\n[dim]🤖 Model: {model_display_name}[/dim]")
        console.print("\n💡 [bold green]Phản hồi:[/bold green]")
        
        try:
            final_response_text, token_usage, token_limit = handlers.handle_conversation_turn(
                chat_session, prompt_parts, console, model_name=args.model, output_format=args.format
            )
            
            # Hiển thị token usage
            if token_usage and token_usage['total_tokens'] > 0:
                if token_limit > 0:
                    remaining = token_limit - token_usage['total_tokens']
                    console.print(f"\n[dim] Token: {token_usage['prompt_tokens']} (prompt) + "
                                 f"{token_usage['completion_tokens']} (completion) = "
                                 f"{token_usage['total_tokens']:,} / {token_limit:,} "
                                 f"({remaining:,} còn lại)[/dim]")
                else:
                    console.print(f"\n[dim]📊 Token: {token_usage['prompt_tokens']} (prompt) + "
                                 f"{token_usage['completion_tokens']} (completion) = "
                                 f"{token_usage['total_tokens']:,} (total)[/dim]")
            
            # Lưu output nếu có
            if args.output:
                with open(args.output, 'w', encoding='utf-8') as f:
                    f.write(final_response_text)
                console.print(f"\n[bold green]✅ Đã lưu kết quả vào file: [cyan]{args.output}[/cyan][/bold green]")
            
            # Thực thi lệnh được đề xuất
            utils.execute_suggested_commands(final_response_text, console)

        except ResourceExhausted:
            console.print("[bold red]❌ Tất cả API keys đều đã hết quota.[/bold red]")
        except Exception as e:
            console.print(f"[bold red]\nĐã xảy ra lỗi không mong muốn: {e}[/bold red]")
            console.print(f"[dim]{traceback.format_exc()}[/dim]")

    except KeyboardInterrupt:
        console.print("\n[yellow]Đã dừng bởi người dùng.[/yellow]")
    except Exception as e:
        console.print(f"[bold red]Đã xảy ra lỗi không mong muốn: {e}[/bold red]")
        console.print(f"[dim]{traceback.format_exc()}[/dim]")

if __name__ == "__main__":
    main()