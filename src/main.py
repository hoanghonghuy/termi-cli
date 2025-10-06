import os
import sys
import json
import traceback
from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from PIL import Image
from google.api_core.exceptions import ResourceExhausted

# --- Import các module đã được tách ra ---
import api
import utils
import cli
import handlers
from config import load_config

def main(provided_args=None):
    """Hàm chính điều phối toàn bộ ứng dụng."""
    # --- Giai đoạn 1: Thiết lập ban đầu ---
    os.environ['GRPC_ENABLE_FORK_SUPPORT'] = '0'
    os.environ['GRPC_POLL_STRATEGY'] = 'poll'
    load_dotenv()
    console = Console()
    config = load_config()

    # --- Giai đoạn 2: Phân tích cú pháp lệnh ---
    parser = cli.create_parser()
    args = provided_args or parser.parse_args()

    cli_help_text = parser.format_help()
    args.cli_help_text = cli_help_text 

    # Ghi đè config mặc định từ các tham số người dùng
    args.model = args.model or config.get("default_model")
    args.format = args.format or config.get("default_format")
    args.persona = args.persona or None

    # --- Giai đoạn 3: Cấu hình API và điều phối ---
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        console.print("[bold red]Lỗi: Vui lòng thiết lập GOOGLE_API_KEY trong file .env[/bold red]")
        return
    
    try:
        api.configure_api(api_key)

        # Điều phối các lệnh không cần prompt
        if args.list_models:
            api.list_models(console)
            return
        if args.set_model:
            handlers.model_selection_wizard(console, config)
            return
        if args.history and not provided_args:
            selected_file = handlers.show_history_browser(console)
            if selected_file:
                new_args = parser.parse_args([]) 
                new_args.load = selected_file
                new_args.chat = True
                new_args.print_log = True
                main(new_args)
            return
        if args.document or args.refactor:
            handlers.handle_code_helper(args, config, console, cli_help_text)
            return

        # --- Giai đoạn 4: Chuẩn bị và thực thi ---
        system_instruction = args.system_instruction or \
                             (config.get("personas", {}).get(args.persona) if args.persona else None)
        
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
        
        if history and args.print_log:
            handlers.print_formatted_history(console, history)
            if not args.chat:
                return

        models_to_try = [args.model] if args.model and args.model != config.get("default_model") else config.get("model_fallback_order", [config.get("default_model")])
        
        if args.chat:
            chat_session = api.start_chat_session(models_to_try[0], system_instruction, history, cli_help_text=cli_help_text)
            handlers.run_chat_mode(chat_session, console, config, args)
            return
        
        # Logic xử lý prompt đơn lẻ
        piped_input = None
        if not sys.stdin.isatty():
             piped_input = sys.stdin.read().strip()
        
        if not args.prompt and not piped_input and not args.image and not args.git_commit:
             console.print("[bold red]Lỗi: Cần cung cấp prompt hoặc một hành động như --git-commit.[/bold red]")
             parser.print_help()
             return

        prompt_parts = []
        user_question = args.prompt or ""
        if args.image:
            try:
                img = Image.open(args.image)
                prompt_parts.append(img)
            except (FileNotFoundError, IsADirectoryError):
                console.print(f"[bold red]Lỗi: Không tìm thấy file ảnh '{args.image}'[/bold red]")
                return
            except Exception as e:
                console.print(f"[bold red]Lỗi khi mở ảnh: {e}[/bold red]")
                return
        
        prompt_text = ""
        if piped_input:
            prompt_text += f"Dựa vào nội dung được cung cấp sau đây:\n{piped_input}\n\n{user_question}"
        else:
            prompt_text += user_question

        if args.read_dir:
            console.print("[yellow]Đang đọc ngữ cảnh thư mục...[/yellow]")
            context = utils.get_directory_context()
            prompt_text = f"Dựa vào ngữ cảnh các file dưới đây:\n{context}\n\n{prompt_text}"
        
        if prompt_text:
            prompt_parts.append(prompt_text)

        response = None
        for model in models_to_try:
            try:
                if len(models_to_try) > 1:
                    console.print(f"[dim]Đang thử với model: {model}...[/dim]")
                chat_session = api.start_chat_session(model, system_instruction, history, cli_help_text=cli_help_text)
                if args.git_commit:
                    handlers.handle_git_commit(chat_session, console, args.format)
                    return
                with console.status(f"[bold green]AI (model: {model}) đang suy nghĩ...[/bold green]"):
                    response = api.send_message(chat_session, prompt_parts)
                break
            except ResourceExhausted:
                console.print(f"[bold yellow]⚠️ Model '{model}' đã hết hạn ngạch.[/bold yellow]")
                if model == models_to_try[-1]:
                    console.print("[bold red]❌ Đã thử hết các model dự phòng nhưng đều thất bại.[/bold red]")
                else:
                    console.print("[cyan]Đang tự động chuyển sang model tiếp theo...[/cyan]")
                continue
            except Exception as e:
                console.print(f"[bold red]Đã xảy ra lỗi không mong muốn với model {model}: {e}[/bold red]")
                break
        
        if response:
            console.print("\n💡 [bold green]Phản hồi:[/bold green]")
            response_text = handlers.get_response_text(response)
            if args.output:
                try:
                    with open(args.output, 'w', encoding='utf-8') as f:
                        f.write(response_text)
                    console.print(f"[bold green]✅ Đã lưu kết quả vào file: [cyan]{args.output}[/cyan][/bold green]")
                except Exception as e:
                     console.print(f"\n[bold red]Lỗi khi lưu file: {e}[/bold red]")
            elif args.format == 'rich':
                console.print(Markdown(response_text))
            else:
                console.print(response_text)
                
            if response.usage_metadata:
                tokens = response.usage_metadata.total_token_count
                console.print(f"\n[dim]Token usage: {tokens}[/dim]")
            utils.execute_suggested_commands(response_text, console)

    except KeyboardInterrupt:
        console.print("\n[yellow]Đã dừng bởi người dùng.[/yellow]")
    except Exception as e:
        console.print(f"[bold red]Đã xảy ra lỗi không mong muốn: {e}[/bold red]")
        console.print(f"[dim]{traceback.format_exc()}[/dim]")

if __name__ == "__main__":
    main()