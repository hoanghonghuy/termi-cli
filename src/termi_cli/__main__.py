import os
import sys
import io
import contextlib
import argparse
import json
import logging

# Workaround tương thích Python 3.14: buộc protobuf dùng implementation Python thuần
# thay vì extension C (_upb/_message), tránh lỗi "Metaclasses with custom tp_new".
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

from rich.markup import escape
from rich.console import Console
from rich.markdown import Markdown
try:
    from PIL import Image
except Exception:
    Image = None
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
    try:
        import google.generativeai as genai  # noqa: F401
    except Exception:
        genai = None
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
from termi_cli.config import load_config, APP_DIR, CONFIG_PATH

from termi_cli.handlers import (
    agent_handler,
    chat_handler,
    config_handler,
    core_handler,
    history_handler,
    utility_handler,
    mini_agent,
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


def _get_gemini_fallback_model(config: dict) -> str:
    """Chọn model Gemini an toàn để fallback khi HTTP provider hết quota/balance."""
    model = config.get("default_model")
    if isinstance(model, str) and (model.startswith("models/") or "gemini" in model.lower()):
        return model
    for candidate in config.get("model_fallback_order", []):
        if isinstance(candidate, str) and (candidate.startswith("models/") or "gemini" in candidate.lower()):
            return candidate
    return "models/gemini-flash-latest"


def _is_http_model_name(model_name: str) -> bool:
    """Kiểm tra xem model thuộc nhóm HTTP provider (DeepSeek/Groq/OpenRouter/Ollama) hay không."""
    if not isinstance(model_name, str):
        return False
    if model_name.startswith("deepseek-"):
        return True
    if model_name.startswith("groq-"):
        return True
    if api.is_openrouter_model(model_name):
        return True
    if api.is_ollama_model(model_name):
        return True
    if api.is_ollama_cloud_model(model_name):
        return True
    return False


def _requires_gemini_for_command(config: dict, args) -> bool:
    """Quyết định xem lệnh hiện tại có thực sự cần GOOGLE_API_KEY/Gemini không.

    - Agent và summarize history luôn dùng Gemini.
    - list-models/set-model yêu cầu gọi trực tiếp Gemini API.
    - Chat/single-turn/git-commit/document/refactor chỉ cần Gemini nếu model không phải HTTP provider.
    """

    # Agent: nếu không bật agent_allow_http hoặc agent_model không phải HTTP provider
    # thì vẫn yêu cầu Gemini như cũ. Nếu agent_allow_http=True và agent_model là HTTP
    # (DeepSeek/Groq/OpenRouter) thì không cần Gemini. Riêng model local Ollama luôn
    # được phép chạy Agent mà không cần Gemini.
    if getattr(args, "agent", False):
        agent_model = config.get("agent_model") or config.get("default_model")
        allow_http_for_agent = config.get("agent_allow_http", False)

        if isinstance(agent_model, str) and api.is_ollama_model(agent_model):
            return False

        if allow_http_for_agent and _is_http_model_name(agent_model):
            return False
        return True

    # Tóm tắt history: chỉ yêu cầu Gemini nếu default_model KHÔNG phải HTTP provider.
    if getattr(args, "summarize", False):
        model_name = config.get("default_model")
        return not _is_http_model_name(model_name)

    # Làm việc trực tiếp với danh sách model Gemini
    if getattr(args, "list_models", False) or getattr(args, "set_model", False):
        # Nếu Gemini SDK khả dụng thì coi như cần Gemini; nếu không, cho phép chạy
        # để api.list_models tự xử lý degrade (gợi ý HTTP models).
        return getattr(api, "GEMINI_AVAILABLE", True)

    # Chat tương tác: chỉ cần Gemini nếu model không phải HTTP provider
    if getattr(args, "chat", False) or getattr(args, "topic", None):
        model_name = getattr(args, "model", None) or config.get("default_model")
        return not _is_http_model_name(model_name)

    # git-commit (full/short): ưu tiên commit_model/code_model/default_model
    if getattr(args, "git_commit", False) or getattr(args, "git_commit_short", False):
        model_name = (
            getattr(args, "model", None)
            or config.get("commit_model")
            or config.get("code_model")
            or config.get("default_model")
        )
        return not _is_http_model_name(model_name)

    # document/refactor: dựa vào code_model/default_model
    if getattr(args, "document", None) or getattr(args, "refactor", None):
        model_name = config.get("code_model") or config.get("default_model")
        return not _is_http_model_name(model_name)

    # Single-turn: có prompt/image/read-dir mà không bật chat/agent
    has_single_turn_intent = bool(
        getattr(args, "prompt", None)
        or getattr(args, "image", None)
        or getattr(args, "read_dir", False)
    )
    if has_single_turn_intent:
        model_name = getattr(args, "model", None) or config.get("default_model")
        return not _is_http_model_name(model_name)

    # Các lệnh còn lại không yêu cầu Gemini.
    return False


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
        if Image is None:
            console.print(i18n.tr(language, "image_support_not_available"))
            return
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

    # Nếu là HTTP provider (DeepSeek/Groq/OpenRouter/Ollama) thì không dùng tool-calls Gemini, gọi trực tiếp generate_text
    if _is_http_model_name(model_name):
        if not prompt_text:
            return

        console.print(f"\n[dim]🤖 Model: {model_name}[/dim]")
        console.print("\n💡 [bold green]Phản hồi:[/bold green]")

        try:
            # Mini-agent pattern-based được tách riêng ra handler để dễ test & mở rộng.
            response_text = None
            if not getattr(args, "mini_agent_off", False):
                response_text = mini_agent.run_http_mini_agent(
                    prompt_text=prompt_text,
                    user_intent=user_intent,
                    config=config,
                )

            if not response_text:
                response_text = api.generate_text(
                    model_name,
                    prompt_text,
                    system_instruction=system_instruction_str,
                )
        except (
            api.DeepseekInsufficientBalance,
            api.GroqInsufficientBalance,
            api.OpenRouterInsufficientBalance,
        ) as e:
            if isinstance(e, api.DeepseekInsufficientBalance):
                provider = "DeepSeek"
            elif isinstance(e, api.GroqInsufficientBalance):
                provider = "Groq"
            else:
                provider = "OpenRouter"

            console.print(
                i18n.tr(
                    language,
                    "http_insufficient_balance_single_turn",
                    provider=provider,
                )
            )
            fallback_model = _get_gemini_fallback_model(config)
            console.print(
                i18n.tr(
                    language,
                    "http_switch_to_gemini_single_turn",
                    fallback_model=fallback_model,
                )
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
            console.print("[dim] Đã lưu 1 lượt tương tác vào trí nhớ dài hạn.[/dim]")

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(final_response_text)
        console.print(i18n.tr(language, "file_saved_to", path=args.output))

    utils.execute_suggested_commands(final_response_text, console)


def _handle_history_flow(console: Console, config: dict, language: str, args, cli_help_text: str, provided_args):
    """Xử lý các luồng liên quan đến history (load, summarize, print_log).

    Trả về (history, should_exit):
    - history: danh sách entry history đã load (hoặc None).
    - should_exit: True nếu đã hoàn thành tác vụ history và không cần tiếp tục main flow.
    """
    history = None

    if getattr(args, "history", False):
        filter_query = getattr(args, "history_filter", None)
        selected_file = history_handler.show_history_browser(console, filter_query)
        if not selected_file:
            return None, True
        try:
            with open(selected_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                history = data.get("history", [])
            history_handler.print_formatted_history(console, history)
        except Exception as e:
            console.print(f"[bold red]Lỗi khi tải lịch sử: {e}[/bold red]")
        return None, True

    # Tải history từ --load hoặc --topic nếu có
    file_to_load = None
    if getattr(args, "load", None):
        file_to_load = args.load
    elif getattr(args, "topic", None):
        file_to_load = os.path.join(
            history_handler.HISTORY_DIR,
            f"chat_{utils.sanitize_filename(args.topic)}.json",
        )

    if file_to_load and os.path.exists(file_to_load):
        try:
            with open(file_to_load, 'r', encoding='utf-8') as f:
                history = json.load(f).get("history", [])
            console.print(i18n.tr(language, "history_loaded_from_file", path=file_to_load))
        except Exception as e:
            console.print(f"[bold red]Lỗi khi tải lịch sử: {e}[/bold red]")
            return None, True

    # Tóm tắt history nếu được yêu cầu
    if getattr(args, "summarize", False):
        if history:
            history_handler.handle_history_summary(console, config, history, cli_help_text)
        else:
            console.print(i18n.tr(language, "no_history_to_summarize"))
        return history, True

    # In log history nếu được yêu cầu
    if getattr(args, "print_log", False) and history:
        history_handler.print_formatted_history(console, history)
        if not (getattr(args, "chat", False) or getattr(args, "topic", None)):
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

        # Cho phép override ngôn ngữ tạm thởi qua --lang/--language
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

        # Khởi tạo config.json mặc định nếu chưa tồn tại (nhẹ nhàng hơn reset-config).
        if getattr(args, "init_config", False):
            cfg = load_config()
            console.print(
                i18n.tr(
                    language,
                    "config_init_success",
                    path=str(CONFIG_PATH),
                )
            )
            return

        # Cho phép reset toàn bộ config về mặc định (xoá file config.json hiện tại)
        if getattr(args, "reset_config", False):
            # Debug thêm khi chạy dưới pytest để kiểm tra đường dẫn
            if "PYTEST_CURRENT_TEST" in os.environ:
                console.print(f"[DEBUG] TERMI_CLI_HOME={os.getenv('TERMI_CLI_HOME')}")
                console.print(f"[DEBUG] APP_DIR={APP_DIR}")
                console.print(f"[DEBUG] CONFIG_PATH={CONFIG_PATH}")
                console.print(f"[DEBUG] CONFIG_PATH.exists(before)={CONFIG_PATH.exists()}")

            # Chỉ hỏi confirm nếu đang chạy trong TTY; nếu không (script/test) thì bỏ qua confirm
            if sys.stdin.isatty() and "PYTEST_CURRENT_TEST" not in os.environ:
                answer = console.input(i18n.tr(language, "config_reset_confirm"), markup=False).strip().lower()
                if answer not in ("y", "yes"):
                    console.print(i18n.tr(language, "config_reset_cancelled"))
                    return

            try:
                if CONFIG_PATH.exists():
                    CONFIG_PATH.unlink()

                load_config()

                if "PYTEST_CURRENT_TEST" in os.environ:
                    console.print(f"[DEBUG] CONFIG_PATH.exists(after)={CONFIG_PATH.exists()}")
                    if CONFIG_PATH.exists():
                        try:
                            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                                console.print(f"[DEBUG] CONFIG_CONTENT(after)={f.read()}")
                        except Exception:
                            pass

                console.print(i18n.tr(language, "config_reset_success", path=str(CONFIG_PATH)))
            except Exception as e:
                console.print(i18n.tr(language, "config_reset_error", error=e))
            return

        # Cho phép xoá database trí nhớ dài hạn bằng một lệnh riêng
        if getattr(args, "reset_memory", False):
            # Debug thêm khi chạy dưới pytest để kiểm tra đường dẫn
            if "PYTEST_CURRENT_TEST" in os.environ:
                console.print(f"[DEBUG] TERMI_CLI_HOME={os.getenv('TERMI_CLI_HOME')}")
                console.print(f"[DEBUG] APP_DIR={APP_DIR}")
                console.print(f"[DEBUG] DB_PATH={memory.DB_PATH}")
                console.print(f"[DEBUG] DB_PATH.exists(before)={os.path.exists(memory.DB_PATH)}")

            # Chỉ hỏi confirm nếu đang chạy trong TTY; nếu không (script/test) thì bỏ qua confirm
            if sys.stdin.isatty() and "PYTEST_CURRENT_TEST" not in os.environ:
                answer = console.input(i18n.tr(language, "memory_reset_confirm"), markup=False).strip().lower()
                if answer not in ("y", "yes"):
                    console.print(i18n.tr(language, "memory_reset_cancelled"))
                    return

            if memory.reset_memory_db():
                if "PYTEST_CURRENT_TEST" in os.environ:
                    console.print(f"[DEBUG] DB_PATH.exists(after)={os.path.exists(memory.DB_PATH)}")
                console.print(i18n.tr(language, "memory_reset_success"))
            else:
                console.print(i18n.tr(language, "memory_reset_error"))
            return

        # Lệnh doctor: kiểm tra môi trường (Python, Gemini, API keys) + diagnostics cấu hình.
        if getattr(args, "doctor", False):
            console.print(f"[bold]Termi Doctor[/bold] - Python: {sys.version.splitlines()[0]}")

            if getattr(api, "GEMINI_AVAILABLE", True):
                console.print("[green]Gemini SDK: available in this environment.[/green]")
            else:
                console.print(
                    "[yellow]Gemini SDK: unavailable in this Python environment. "
                    "Bạn vẫn có thể dùng các provider HTTP (DeepSeek/Groq/OpenRouter/Ollama), "
                    "hoặc chạy Termi trên Python 3.10–3.12 để dùng Gemini đầy đủ.[/yellow]"
                )

            config_handler.show_diagnostics(console, config)
            return

        # Lệnh chẩn đoán cấu hình không cần API key
        if getattr(args, "diagnostics", False):
            config_handler.show_diagnostics(console, config)
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

        # Cho phép liệt kê tools mà không cần GOOGLE_API_KEY
        if getattr(args, "list_tools", False):
            api.list_tools(console)
            return

        requires_gemini = _requires_gemini_for_command(config, args)

        # Nếu lệnh yêu cầu Gemini nhưng SDK không khả dụng (ví dụ Python 3.14),
        # dừng sớm với thông báo rõ ràng.
        if requires_gemini and not getattr(api, "GEMINI_AVAILABLE", True):
            console.print(
                "[bold red]Lệnh này yêu cầu Gemini, nhưng Gemini SDK hiện không hoạt động trên phiên bản Python này "
                "(có thể do Python 3.14). Hãy dùng model HTTP (deepseek-/groq-/OpenRouter) hoặc chạy Termi trên Python 3.11/3.12.[/bold red]"
            )
            return

        keys = api.initialize_api_keys()

        if not keys and requires_gemini:
            console.print(i18n.tr(language, "error_no_api_key"))
            return

        # Chỉ cấu hình Gemini và in log khi lệnh hiện tại thực sự cần Gemini.
        if keys and getattr(api, "GEMINI_AVAILABLE", True) and requires_gemini:
            if len(keys) > 1:
                console.print(i18n.tr(language, "api_keys_loaded", count=len(keys)))

            api.configure_api(keys[0])

        # --- Xử lý các lệnh tiện ích (thoát ngay sau khi chạy) ---
        if args.list_models:
            api.list_models(console)
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

            # Nếu model là HTTP provider (DeepSeek/Groq/OpenRouter/Ollama), dùng luồng chat riêng qua HTTP API.
            if _is_http_model_name(model_name):
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