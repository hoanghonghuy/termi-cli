import os
import sys
import io
import contextlib
import argparse
import json
from rich.markup import escape
from rich.console import Console
from PIL import Image
from dotenv import load_dotenv

# --- Boilerplate để tắt log không cần thiết ---
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

os.environ.setdefault('GRPC_VERBOSITY', 'ERROR')
os.environ.setdefault('GLOG_minloglevel', '3')
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '3')
os.environ.setdefault('ABSL_CPP_MIN_LOG_LEVEL', '3')

with silence_stderr():
    import google.generativeai as genai
try:
    import logging
    logging.getLogger('google').setLevel(logging.ERROR)
    logging.getLogger('grpc').setLevel(logging.ERROR)
    logging.getLogger('absl').setLevel(logging.ERROR)
    import absl.logging as _absl_logging
    _absl_logging.set_verbosity(_absl_logging.ERROR)
except (ImportError, AttributeError):
    pass
# --- Kết thúc Boilerplate ---

from termi_cli import api, utils, cli, memory
from termi_cli.config import load_config
from termi_cli.handlers import (
    agent_handler,
    chat_handler,
    config_handler,
    core_handler,
    history_handler,
    utility_handler,
)

def main(provided_args=None):
    """Hàm chính điều phối toàn bộ ứng dụng."""
    load_dotenv()
    console = Console()
    config = load_config()
    parser = cli.create_parser()
    
    try:
        args = provided_args or parser.parse_args()
        cli_help_text = parser.format_help()
        args.cli_help_text = cli_help_text 

        # --- Cấu hình ban đầu ---
        args.model = args.model or config.get("default_model")
        args.format = args.format or config.get("default_format", "rich")
        
        keys = api.initialize_api_keys()
        if not keys:
            console.print("[bold red]Lỗi: Vui lòng thiết lập GOOGLE_API_KEY trong file .env[/bold red]"); return
        
        if len(keys) > 1:
            console.print(f"[dim]🔑 Đã tải {len(keys)} API key(s)[/dim]")
        
        api.configure_api(keys[0])

        # --- Xử lý các lệnh tiện ích (thoát ngay sau khi chạy) ---
        if args.list_models: api.list_models(console); return
        if args.set_model: config_handler.model_selection_wizard(console, config); return
        if args.add_persona: config_handler.add_persona(console, config, args.add_persona[0], args.add_persona[1]); return
        if args.list_personas: config_handler.list_personas(console, config); return
        if args.rm_persona: config_handler.remove_persona(console, config, args.rm_persona); return
        if args.add_instruct: config_handler.add_instruction(console, config, args.add_instruct); return
        if args.list_instructs: config_handler.list_instructions(console, config); return
        if args.rm_instruct is not None: config_handler.remove_instruction(console, config, args.rm_instruct); return
        if args.git_commit: utility_handler.generate_git_commit_message(console, args); return
        if args.document: utility_handler.document_code_file(console, args); return
        if args.refactor: utility_handler.refactor_code_file(console, args); return

        # --- Xử lý Agent Mode ---
        if args.agent:
            if not args.prompt:
                console.print("[bold red]Lỗi: Chế độ Agent yêu cầu một mục tiêu (prompt).[/bold red]"); return
            agent_handler.run_master_agent(console, args)
            return

        # --- Xử lý History Browser ---
        history = None
        if args.history and not provided_args:
            selected_file = history_handler.show_history_browser(console)
            if selected_file:
                # Tải lịch sử trước khi hỏi
                try:
                    with open(selected_file, 'r', encoding='utf-8') as f:
                        history = json.load(f).get("history", [])
                except Exception as e:
                    console.print(f"[bold red]Lỗi khi tải file lịch sử: {e}[/bold red]"); return

                action = ''
                while action not in ['c', 's', 'q']:
                    prompt_text = "Bạn muốn [c]hat tiếp, [s]ummarize (tóm tắt), hay [q]uit? "
                    console.print(f"[bold yellow]{escape(prompt_text)}[/bold yellow]", end="")
                    sys.stdout.flush()
                    action = input().lower().strip()
                
                if action == 'q': console.print("[yellow]Đã thoát.[/yellow]"); return
                
                if action == 'c':
                    args.load = selected_file
                    args.chat = True
                    args.print_log = True
                    # Để code tiếp tục chạy xuống khối xử lý chat
                elif action == 's':
                    history_handler.handle_history_summary(console, config, history, cli_help_text)
                    return
            else:
                return
        
        # --- Xử lý các lệnh liên quan đến tải lịch sử (nếu không qua --history) ---
        if not history:
            file_to_load = None
            if args.load: file_to_load = args.load
            elif args.topic: file_to_load = os.path.join(history_handler.HISTORY_DIR, f"chat_{utils.sanitize_filename(args.topic)}.json")

            if file_to_load and os.path.exists(file_to_load):
                # Chỉ tải nếu chưa được tải từ khối --history ở trên
                if not (args.history and args.chat): 
                    try:
                        with open(file_to_load, 'r', encoding='utf-8') as f:
                            history = json.load(f).get("history", [])
                        console.print(f"[green]Đã tải lịch sử từ '{file_to_load}'.[/green]")
                    except Exception as e:
                        console.print(f"[bold red]Lỗi khi tải lịch sử: {e}[/bold red]"); return
        
        if args.summarize:
            if history:
                history_handler.handle_history_summary(console, config, history, cli_help_text)
            else:
                console.print("[yellow]Không có lịch sử để tóm tắt. Hãy dùng --load hoặc --topic.[/yellow]")
            return
        
        if args.print_log and history:
            history_handler.print_formatted_history(console, history)
            if not (args.chat or args.topic):
                return
            
            
        # --- Chế độ Chat ---
        if args.chat or args.topic:
            # Xây dựng system instruction cho chat
            saved_instructions = config.get("saved_instructions", [])
            system_instruction_str = "\n".join(f"- {item}" for item in saved_instructions)
            if args.system_instruction:
                system_instruction_str = args.system_instruction
            elif args.persona and config.get("personas", {}).get(args.persona):
                system_instruction_str = config["personas"][args.persona]

            chat_session = api.start_chat_session(args.model, system_instruction_str, history, cli_help_text=cli_help_text)
            chat_handler.run_chat_mode(chat_session, console, config, args)
            return

        # --- Xử lý prompt đơn (single-turn) ---
        piped_input = None
        if not sys.stdin.isatty():
            try:
                # Thử đọc với encoding của console hệ thống trước
                piped_input = sys.stdin.read().strip()
            except UnicodeDecodeError:
                # Nếu thất bại, thử lại với utf-8 và bỏ qua lỗi
                sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding='utf-8', errors='ignore')
                piped_input = sys.stdin.read().strip()
        
        if not any([args.prompt, piped_input, args.image]):
            if not (history and args.print_log and (args.chat or args.topic)):
                console.print("[bold red]Lỗi: Cần cung cấp prompt hoặc một hành động cụ thể.[/bold red]")
                parser.print_help()
            return

        # Xây dựng prompt
        prompt_parts = []
        prompt_text = ""
        user_intent = args.prompt or ""
        
        if piped_input:
            prompt_text = f"Dựa vào nội dung được cung cấp sau đây:\n{piped_input}\n\n{user_intent}"
        else:
            prompt_text = user_intent

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
                    console.print(f"[bold red]Lỗi: Không tìm thấy file ảnh '{image_path}'[/bold red]"); return
                except Exception as e:
                    console.print(f"[bold red]Lỗi khi mở ảnh '{image_path}': {e}[/bold red]"); return
            console.print(f"[green]Đã tải lên {len(args.image)} ảnh.[/green]")
        
        if prompt_text:
            prompt_parts.append(prompt_text)

        # Xây dựng system instruction cho prompt đơn
        saved_instructions = config.get("saved_instructions", [])
        system_instruction_str = "\n".join(f"- {item}" for item in saved_instructions)
        if args.system_instruction:
            system_instruction_str = args.system_instruction
        elif args.persona and config.get("personas", {}).get(args.persona):
            system_instruction_str = config["personas"][args.persona]

        chat_session = api.start_chat_session(args.model, system_instruction_str, history, cli_help_text=cli_help_text)
        
        console.print(f"\n[dim]🤖 Model: {args.model.replace('models/', '')}[/dim]")
        console.print("\n💡 [bold green]Phản hồi:[/bold green]")
        
        final_response_text, token_usage, token_limit, tool_calls_log = core_handler.handle_conversation_turn(
            chat_session, prompt_parts, console, model_name=args.model, args=args
        )
        
        if user_intent and final_response_text:
            memory.add_memory(user_intent, tool_calls_log, final_response_text)
        
        if token_usage and token_usage['total_tokens'] > 0:
            if token_limit > 0:
                remaining = token_limit - token_usage['total_tokens']
                console.print(f"\n[dim]📊 Token: {token_usage['prompt_tokens']} + {token_usage['completion_tokens']} = {token_usage['total_tokens']:,} / {token_limit:,} ({remaining:,} còn lại)[/dim]")
            else:
                console.print(f"\n[dim]📊 Token: {token_usage['prompt_tokens']} + {token_usage['completion_tokens']} = {token_usage['total_tokens']:,} (total)[/dim]")
        
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(final_response_text)
            console.print(f"\n[bold green]✅ Đã lưu kết quả vào file: [cyan]{args.output}[/cyan][/bold green]")
        
        utils.execute_suggested_commands(final_response_text, console)

    except KeyboardInterrupt:
        console.print("\n[yellow]Đã dừng bởi người dùng.[/yellow]")
    except Exception as e:
        console.print(f"[bold red]Đã xảy ra lỗi khởi động không mong muốn: {e}[/bold red]")

if __name__ == "__main__":
    main()