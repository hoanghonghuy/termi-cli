import os
import sys
import io
import contextlib
import argparse
import json
import logging

from rich.markup import escape
from rich.console import Console
from rich.markdown import Markdown
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
    """Tạm thởi chuyển hướng stderr sang devnull."""
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


def _setup_logging():
    """Cấu hình logging cho toàn bộ ứng dụng (console + file log)."""
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


def _run_single_turn(console: Console, config: dict, language: str, parser, args, cli_help_text: str, history):
    """Xử lý luồng prompt đơn (single-turn) tách riêng khỏi main cho dễ đọc/test."""
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
    model_name = args.model or config.get("default_model")

    # Nếu là HTTP provider (DeepSeek/Groq) thì không dùng tool-calls Gemini, gọi trực tiếp generate_text
    if isinstance(model_name, str) and (
        model_name.startswith("deepseek-") or model_name.startswith("groq-")
    ):
        if not prompt_text:
            return

        console.print(f"\n[dim]🤖 Model: {model_name}[/dim]")
        console.print("\n💡 [bold green]Phản hồi:[/bold green]")

        try:
            response_text = api.generate_text(
                model_name,
                prompt_text,
                system_instruction=system_instruction_str,
            )
        except (api.DeepseekInsufficientBalance, api.GroqInsufficientBalance) as e:
            provider = "DeepSeek" if isinstance(e, api.DeepseekInsufficientBalance) else "Groq"
            console.print(
                f"[bold red]{provider} báo lỗi Insufficient Balance. Không thể dùng {provider} cho lượt hỏi này.[/bold red]"
            )
            fallback_model = config.get("default_model")
            console.print(
                f"[yellow]Đang chuyển tạm sang model Gemini '[cyan]{fallback_model}[/cyan]' cho lượt hỏi này.[/yellow]"
            )

            response_text = api.generate_text(
                fallback_model,
                prompt_text,
                system_instruction=system_instruction_str,
            )
        except Exception as e:
            console.print(i18n.tr(language, "chat_generic_error", error=e))
            return

        final_response_text = (response_text or "").strip()
        if not final_response_text:
            return

        if args.format == "rich":
            console.print(Markdown(final_response_text))
        else:
            console.print(final_response_text)

        if user_intent and final_response_text:
            # Không có tool-calls trong nhánh HTTP provider
            if memory.add_memory(user_intent, [], final_response_text):
                console.print("[dim]💾 Đã lưu 1 lượt tương tác vào trí nhớ dài hạn.[/dim]")

        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(final_response_text)
            console.print(i18n.tr(language, "file_saved_to", path=args.output))

        utils.execute_suggested_commands(final_response_text, console)
        return

    # Nhánh mặc định: dùng Gemini với tool-calls như trước
    chat_session = api.start_chat_session(model_name, system_instruction_str, history, cli_help_text=cli_help_text)

    console.print(f"\n[dim]🤖 Model: {model_name.replace('models/', '')}[/dim]")
    console.print("\n💡 [bold green]Phản hồi:[/bold green]")

    final_response_text, _, _, tool_calls_log = core_handler.handle_conversation_turn(
        chat_session, prompt_parts, console, model_name=model_name, args=args
    )

    if user_intent and final_response_text:
        if memory.add_memory(user_intent, tool_calls_log, final_response_text):
            console.print("[dim]💾 Đã lưu 1 lượt tương tác vào trí nhớ dài hạn.[/dim]")

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(final_response_text)
        console.print(i18n.tr(language, "file_saved_to", path=args.output))

    utils.execute_suggested_commands(final_response_text, console)


def _handle_history_flow(console: Console, config: dict, language: str, args, cli_help_text: str, provided_args):
    history = None

    # --- Xử lý History Browser ---
    if args.history and not provided_args:
        selected_file = history_handler.show_history_browser(console)
        if selected_file:
            # Tải lịch sử trước khi hỏi
            try:
                with open(selected_file, 'r', encoding='utf-8') as f:
                    history = json.load(f).get("history", [])
            except Exception as e:
                console.print(f"[bold red]Lỗi khi tải file lịch sử: {e}[/bold red]")
                return None, True
            action = ''
            while action not in ['c', 's', 'r', 'd', 'q']:
                prompt_text = i18n.tr(language, "history_action_prompt")
                console.print(f"[bold yellow]{escape(prompt_text)}[/bold yellow]", end="")
                sys.stdout.flush()
                action = input().lower().strip()

            if action == 'q':
                console.print(i18n.tr(language, "action_quit"))
                return None, True

            if action == 'c':
                args.load = selected_file
                args.chat = True
                args.print_log = True
            elif action == 's':
                history_handler.handle_history_summary(console, config, history, cli_help_text)
                return None, True
            elif action == 'r':
                # Đổi tên lịch sử: cập nhật title trong JSON và đổi tên file
                try:
                    with open(selected_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                except Exception:
                    data = {}

                old_title = data.get("title", os.path.basename(selected_file))
                new_title = console.input(
                    i18n.tr(language, "history_rename_prompt"), markup=False
                ).strip()

                if not new_title:
                    return None, True

                data["title"] = new_title

                from termi_cli import utils as _utils
                from termi_cli.handlers.history_handler import HISTORY_DIR as _HIST_DIR

                new_filename = f"chat_{_utils.sanitize_filename(new_title)}.json"
                new_path = os.path.join(_HIST_DIR, new_filename)

                # Tránh ghi đè file khác nếu trùng tên
                if os.path.abspath(new_path) != os.path.abspath(selected_file) and os.path.exists(new_path):
                    console.print(i18n.tr(language, "history_invalid_choice"))
                    return None, True

                try:
                    # Đổi tên file trên đĩa
                    if os.path.abspath(new_path) != os.path.abspath(selected_file):
                        os.rename(selected_file, new_path)

                    with open(new_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)

                    console.print(
                        i18n.tr(language, "history_rename_success", title=new_title)
                    )
                except Exception as e:
                    console.print(i18n.tr(language, "chat_cannot_save_history_error", error=e))
                return None, True
            elif action == 'd':
                # Xóa file lịch sử
                try:
                    title = None
                    try:
                        with open(selected_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            title = data.get("title", os.path.basename(selected_file))
                    except Exception:
                        title = os.path.basename(selected_file)

                    confirm = console.input(
                        i18n.tr(language, "history_delete_confirm", title=title),
                        markup=False,
                    ).strip().lower()

                    if confirm == 'y':
                        os.remove(selected_file)
                        console.print(
                            i18n.tr(language, "history_delete_success", title=title)
                        )
                except Exception as e:
                    console.print(i18n.tr(language, "chat_cannot_save_history_error", error=e))
                return None, True
        else:
            return None, True

    # --- Xử lý các lệnh liên quan đến tải lịch sử (nếu không qua --history) ---
    if not history:
        file_to_load = None
        if args.load:
            file_to_load = args.load
        elif args.topic:
            file_to_load = os.path.join(history_handler.HISTORY_DIR, f"chat_{utils.sanitize_filename(args.topic)}.json")

        if file_to_load and os.path.exists(file_to_load):
            if not (args.history and args.chat):
                try:
                    with open(file_to_load, 'r', encoding='utf-8') as f:
                        history = json.load(f).get("history", [])
                    console.print(i18n.tr(language, "history_loaded_from_file", path=file_to_load))
                except Exception as e:
                    console.print(f"[bold red]Lỗi khi tải lịch sử: {e}[/bold red]")
                    return None, True

    if args.summarize:
        if history:
            history_handler.handle_history_summary(console, config, history, cli_help_text)
        else:
            console.print(i18n.tr(language, "no_history_to_summarize"))
        return history, True

    if args.print_log and history:
        history_handler.print_formatted_history(console, history)
        if not (args.chat or args.topic):
            return history, True

    return history, False


def main(provided_args=None):
    """Hàm chính điều phối toàn bộ ứng dụng."""
    load_dotenv()
    _setup_logging()

    console = Console()
    config = load_config()
    language = config.get("language", "vi")

    parser = cli.create_parser()

    try:
        args = provided_args or parser.parse_args()
        cli_help_text = parser.format_help()
        args.cli_help_text = cli_help_text

        # Cho phép override ngôn ngữ tạm thời qua --lang/--language
        if getattr(args, "language", None):
            language = args.language
            config["language"] = language

        # Điều chỉnh mức logging console theo --verbose/--quiet
        root_logger = logging.getLogger()

        if getattr(args, "verbose", False):
            for handler in root_logger.handlers:
                if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
                    handler.setLevel(logging.INFO)
        elif getattr(args, "quiet", False):
            for handler in root_logger.handlers:
                if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
                    handler.setLevel(logging.ERROR)

        # Áp dụng profile cấu hình nhanh (nếu có) trước khi set model mặc định
        if getattr(args, "profile", None):
            config_handler.apply_profile(console, config, args.profile)
            language = config.get("language", language)

        # --- Cấu hình ban đầu ---
        args.model = args.model or config.get("default_model")
        args.format = args.format or config.get("default_format", "rich")

        # Lệnh chẩn đoán cấu hình không cần API key
        if getattr(args, "diagnostics", False):
            config_handler.show_diagnostics(console, config)
            return

        # Cho phép xoá database trí nhớ dài hạn bằng một lệnh riêng
        if getattr(args, "reset_memory", False):
            if memory.reset_memory_db():
                console.print("[green]Đã xoá xong database trí nhớ dài hạn (memory_db).[/green]")
            else:
                console.print("[red]Không thể xoá database trí nhớ dài hạn. Xem thêm chi tiết trong logs/termi.log.[/red]")
            return

        # Tìm kiếm trong trí nhớ dài hạn (không cần API ngoài)
        if getattr(args, "memory_search", None):
            result = memory.search_memory(args.memory_search)
            if not result:
                console.print(i18n.tr(language, "memory_search_no_results"))
            else:
                console.print(Markdown(result))
            return

        # Các thao tác history non-interactive
        if getattr(args, "rm_history", None):
            history_handler.delete_history_entry(console, args.rm_history)
            return

        if getattr(args, "rename_history", None):
            old, new = args.rename_history
            history_handler.rename_history_entry(console, old, new)
            return

        # Quản lý profile cấu hình nhanh
        if getattr(args, "save_profile", None):
            config_handler.save_profile(console, config, args.save_profile)
            return

        if getattr(args, "list_profiles", False):
            config_handler.list_profiles(console, config)
            return

        if getattr(args, "rm_profile", None):
            config_handler.remove_profile(console, config, args.rm_profile)
            return

        keys = api.initialize_api_keys()

        if not keys:
            console.print(i18n.tr(language, "error_no_api_key"))
            return

        if len(keys) > 1:
            console.print(i18n.tr(language, "api_keys_loaded", count=len(keys)))

        api.configure_api(keys[0])

        # --- Xử lý các lệnh tiện ích (thoát ngay sau khi chạy) ---
        if args.list_models:
            api.list_models(console)
            return
        if getattr(args, "list_tools", False):
            api.list_tools(console)
            return

        if args.set_model:
            config_handler.model_selection_wizard(console, config)
            return
        if args.add_persona:
            config_handler.add_persona(console, config, args.add_persona[0], args.add_persona[1])
            return
        if args.list_personas:
            config_handler.list_personas(console, config)
            return
        if args.rm_persona:
            config_handler.remove_persona(console, config, args.rm_persona)
            return
        if args.add_instruct:
            config_handler.add_instruction(console, config, args.add_instruct)
            return
        if args.list_instructs:
            config_handler.list_instructions(console, config)
            return
        if args.rm_instruct is not None:
            config_handler.remove_instruction(console, config, args.rm_instruct)
            return
        if args.git_commit or getattr(args, "git_commit_short", False):
            utility_handler.generate_git_commit_message(
                console,
                args,
                short=getattr(args, "git_commit_short", False),
            )
            return
        if args.document:
            utility_handler.document_code_file(console, args)
            return
        if args.refactor:
            utility_handler.refactor_code_file(console, args)
            return

        # --- Xử lý Agent Mode ---
        if args.agent:
            if not args.prompt:
                console.print(i18n.tr(language, "agent_requires_prompt"))
                return
            agent_handler.run_master_agent(console, args)
            return

        history, should_exit = _handle_history_flow(
            console, config, language, args, cli_help_text, provided_args
        )
        if should_exit:
            return

        # --- Chế độ Chat ---
        if args.chat or args.topic:
            # Xây dựng system instruction cho chat
            system_instruction_str = core_handler.build_system_instruction(config, args)

            model_name = args.model or config.get("default_model")

            # Nếu model là HTTP provider (DeepSeek/Groq), dùng luồng chat riêng qua HTTP API.
            if isinstance(model_name, str) and (
                model_name.startswith("deepseek-")
                or model_name.startswith("groq-")
            ):
                chat_handler.run_chat_mode_deepseek(console, config, args, system_instruction_str)
            else:
                chat_session = api.start_chat_session(
                    model_name, system_instruction_str, history, cli_help_text=cli_help_text
                )
                chat_handler.run_chat_mode(chat_session, console, config, args)
            return

        _run_single_turn(console, config, language, parser, args, cli_help_text, history)

    except KeyboardInterrupt:
        console.print(i18n.tr(language, "interrupted_by_user"))
    except Exception as e:
        console.print(i18n.tr(language, "unexpected_startup_error", error=e))

if __name__ == "__main__":
    main()