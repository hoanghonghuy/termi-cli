import os
import sys
import io
import contextlib
import argparse
import json
import logging

from rich.markup import escape
from rich.console import Console
from PIL import Image
from dotenv import load_dotenv

# Chuẩn hoá biến môi trường LANGUAGE càng sớm càng tốt để tránh lỗi
lang_env = os.environ.get("LANGUAGE")
if lang_env:
    primary = lang_env.replace(" ", "").split(",")[0].split(":")[0]
    if primary in ("vi", "en"):
        os.environ["LANGUAGE"] = primary

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

from termi_cli import api, utils, cli, memory, i18n
from termi_cli.config import load_config, APP_DIR
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
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    # Ghi log chi tiết ra file ngoài console (trong thư mục ứng dụng cố định),
    # đồng thởi giảm độ ồn trên console chỉ còn WARNING trở lên.
    log_dir = os.path.join(APP_DIR, "logs")
    try:
        os.makedirs(log_dir, exist_ok=True)
        root_logger = logging.getLogger()

        # Thêm file handler ở mức DEBUG để lưu toàn bộ log vào file
        file_handler = logging.FileHandler(os.path.join(log_dir, "termi.log"), encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s")
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

        # Hạ level cho các StreamHandler (console) xuống WARNING để ẩn bớt log INFO
        for handler in root_logger.handlers:
            if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
                handler.setLevel(logging.WARNING)
    except Exception:
        # Không được để lỗi logging làm hỏng trải nghiệm CLI
        pass

    console = Console()
    config = load_config()
    language = config.get("language", "vi")

    parser = cli.create_parser()
    
    try:
        args = provided_args or parser.parse_args()
        cli_help_text = parser.format_help()
        args.cli_help_text = cli_help_text 

        # Cho phép override ngôn ngữ tạm thởi qua --lang/--language
        if getattr(args, "language", None):
            language = args.language
            config["language"] = language

        # --- Cấu hình ban đầu ---
        args.model = args.model or config.get("default_model")
        args.format = args.format or config.get("default_format", "rich")

        # Cho phép xoá database trí nhớ dài hạn bằng một lệnh riêng
        if getattr(args, "reset_memory", False):
            if memory.reset_memory_db():
                console.print("[green]✅ Đã xoá xong database trí nhớ dài hạn (memory_db).[/green]")
            else:
                console.print("[red]❌ Không thể xoá database trí nhớ dài hạn. Xem thêm chi tiết trong logs/termi.log.[/red]")
            return

        keys = api.initialize_api_keys()
        if not keys:
            console.print(i18n.tr(language, "error_no_api_key")); return
        
        if len(keys) > 1:
            console.print(i18n.tr(language, "api_keys_loaded", count=len(keys)))
        
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
        if args.git_commit or getattr(args, "git_commit_short", False):
            utility_handler.generate_git_commit_message(
                console,
                args,
                short=getattr(args, "git_commit_short", False),
            ); return
        if args.document: utility_handler.document_code_file(console, args); return
        if args.refactor: utility_handler.refactor_code_file(console, args); return

        # --- Xử lý Agent Mode ---
        if args.agent:
            if not args.prompt:
                console.print(i18n.tr(language, "agent_requires_prompt")); return
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
                    prompt_text = i18n.tr(language, "history_action_prompt")
                    console.print(f"[bold yellow]{escape(prompt_text)}[/bold yellow]", end="")
                    sys.stdout.flush()
                    action = input().lower().strip()
                
                if action == 'q': console.print(i18n.tr(language, "action_quit")); return
                
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
                        console.print(i18n.tr(language, "history_loaded_from_file", path=file_to_load))
                    except Exception as e:
                        console.print(f"[bold red]Lỗi khi tải lịch sử: {e}[/bold red]"); return
        
        if args.summarize:
            if history:
                history_handler.handle_history_summary(console, config, history, cli_help_text)
            else:
                console.print(i18n.tr(language, "no_history_to_summarize"))
            return
        
        if args.print_log and history:
            history_handler.print_formatted_history(console, history)
            if not (args.chat or args.topic):
                return
            
            
        # --- Chế độ Chat ---
        if args.chat or args.topic:
            # Xây dựng system instruction cho chat
            system_instruction_str = core_handler.build_system_instruction(config, args)

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
                console.print(i18n.tr(language, "error_need_prompt_or_action"))
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
                console.print(i18n.tr(language, "memory_found_relevant"))
                prompt_text = f"{relevant_memory}\n---\n\n{prompt_text}"

        if args.read_dir:
            console.print(i18n.tr(language, "reading_directory_context"))
            context = utils.get_directory_context()
            prompt_text = f"Dựa vào ngữ cảnh các file dưới đây:\n{context}\n\n{prompt_text}"
        
        if args.image:
            for image_path in args.image:
                try:
                    img = Image.open(image_path)
                    prompt_parts.append(img)
                except (FileNotFoundError, IsADirectoryError):
                    console.print(i18n.tr(language, "error_image_not_found", path=image_path)); return
                except Exception as e:
                    console.print(i18n.tr(language, "error_opening_image", path=image_path, error=e)); return
            console.print(i18n.tr(language, "images_loaded_count", count=len(args.image)))
        
        if prompt_text:
            prompt_parts.append(prompt_text)

        # Xây dựng system instruction cho prompt đơn
        system_instruction_str = core_handler.build_system_instruction(config, args)

        chat_session = api.start_chat_session(args.model, system_instruction_str, history, cli_help_text=cli_help_text)
        
        console.print(f"\n[dim]🤖 Model: {args.model.replace('models/', '')}[/dim]")
        console.print("\n💡 [bold green]Phản hồi:[/bold green]")
        
        final_response_text, _, _, tool_calls_log = core_handler.handle_conversation_turn(
            chat_session, prompt_parts, console, model_name=args.model, args=args
        )
        
        if user_intent and final_response_text:
            if memory.add_memory(user_intent, tool_calls_log, final_response_text):
                console.print("[dim]💾 Đã lưu 1 lượt tương tác vào trí nhớ dài hạn.[/dim]")
        
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(final_response_text)
            console.print(i18n.tr(language, "file_saved_to", path=args.output))

        utils.execute_suggested_commands(final_response_text, console)

    except KeyboardInterrupt:
        console.print(i18n.tr(language, "interrupted_by_user"))
    except Exception as e:
        console.print(i18n.tr(language, "unexpected_startup_error", error=e))

if __name__ == "__main__":
    main()