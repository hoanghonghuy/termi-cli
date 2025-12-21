import os
import sys
import io
import contextlib
import logging
import argparse

# Workaround tương thích Python 3.14: buộc protobuf dùng implementation Python thuần
# thay vì extension C (_upb/_message), tránh lỗi "Metaclasses with custom tp_new".
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

from rich.console import Console
from rich.markdown import Markdown

try:
    from PIL import Image
except Exception:
    Image = None
from dotenv import load_dotenv

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

# ruff: noqa: E402 - các import bên dưới phụ thuộc vào phần bootstrap phía trên
from termi_cli import api, utils, cli, memory, i18n
from termi_cli.presentation import cli_app

from termi_cli.config import load_config, APP_DIR

from termi_cli.handlers import (
    core_handler,
    history_handler,
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
    if api.is_generic_openai_model(model_name):
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
    
    if not any([args.prompt, piped_input, args.image, getattr(args, "file", None)]):
        if not (history and args.print_log and (args.chat or args.topic)):
            console.print(i18n.tr(language, "error_need_prompt_or_action"))
            parser.print_help()
        return

    # Xây dựng prompt
    prompt_parts = []
    prompt_text = ""
    user_intent = args.prompt or ""
    
    if piped_input:
        prompt_text = (
            "Using the following piped input as additional context:\n"
            f"{piped_input}\n\n"
            f"{user_intent}"
        )
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
        prompt_text = (
            "Using the following directory context as additional input:\n"
            f"{context}\n\n{prompt_text}"
        )

    # RAG context injection when --rag flag is used
    if getattr(args, "rag", False) and user_intent:
        from termi_cli.rag import codebase_query
        index_name = getattr(args, "rag_index", "default")
        if codebase_query.is_index_available(index_name):
            rag_context = codebase_query.get_codebase_context(user_intent, index_name)
            if rag_context:
                console.print(i18n.tr(language, "rag_context_found"))
                prompt_text = f"{rag_context}\n---\n\n{prompt_text}"
            else:
                console.print(i18n.tr(language, "rag_no_context"))
        else:
            console.print(i18n.tr(language, "rag_index_not_available"))
    
    if args.image:
        if Image is None:
            console.print(i18n.tr(language, "image_support_not_available"))
            return
        for image_path in args.image:
            try:
                img = Image.open(image_path)
                prompt_parts.append(img)
            except (FileNotFoundError, IsADirectoryError):
                console.print(i18n.tr(language, "error_image_not_found", path=image_path))
                return
            except Exception as e:
                console.print(i18n.tr(language, "error_opening_image", path=image_path, error=e))
                return
        console.print(i18n.tr(language, "images_loaded_count", count=len(args.image)))

    if getattr(args, "file", None):
        for file_path in args.file:
            if os.path.exists(file_path):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        prompt_text += f"\n\n--- File: {file_path} ---\n{content}\n---"
                except Exception as e:
                    console.print(i18n.tr(language, "chat_file_read_failed", path=file_path, error=e))
                    return
            else:
                console.print(i18n.tr(language, "code_file_not_found", path=file_path))
                return
    
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
                # Prepare prompt for HTTP providers (Text or List[dict])
                final_prompt: str | list[dict] = prompt_text
                
                # If images are present, construct OpenAI-compatible message list
                # Note: HTTP providers use args.image paths directly via encode helper
                if args.image:
                    from termi_cli.infrastructure import http_providers
                    content_list = []
                    if prompt_text:
                        content_list.append({"type": "text", "text": prompt_text})
                    
                    for img_path in args.image:
                        if os.path.exists(img_path):
                            b64 = http_providers.encode_image_to_base64(img_path)
                            if b64:
                                content_list.append({"type": "image_url", "image_url": {"url": b64}})
                            else:
                                console.print(f"[bold red]Failed to encode image: {img_path}[/bold red]")
                                return
                    
                    final_prompt = [{"role": "user", "content": content_list}]

                response_text = api.generate_text(
                    model_name,
                    final_prompt,
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
            data = history_handler.load_history_file(selected_file)
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
            data = history_handler.load_history_file(file_to_load)
            history = data.get("history", [])
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


def _preprocess_subcommands(argv):
    """Hỗ trợ cú pháp dạng `termi chat` / `termi agent` mà không phá vỡ flags cũ."""

    if not argv:
        return argv

    first = argv[0]
    if first == "chat":
        return ["--chat", *argv[1:]]
    if first == "agent":
        return ["--agent", *argv[1:]]
    if first == "set-model":
        return ["--set-model", *argv[1:]]

    return argv


def _extract_language_from_argv(argv, default_language: str) -> str:
    """Rút trích language override (--lang/--language) từ argv trước khi tạo parser."""
    language = default_language
    for i, token in enumerate(argv):
        value = None
        if token.startswith("--lang="):
            value = token.split("=", 1)[1]
        elif token.startswith("--language="):
            value = token.split("=", 1)[1]
        elif token in ("--lang", "--language"):
            if i + 1 < len(argv):
                value = argv[i + 1]
        if value in ("vi", "en"):
            language = value
            break
    return language


def main(provided_args=None):
    """Hàm chính điều phối toàn bộ ứng dụng."""
    load_dotenv()
    _setup_logging()

    console = Console()
    config = load_config()
    language = config.get("language", "vi")

    # Inject Generic OpenAI config to env vars for http_providers.py to pick up
    if "openai_compatible" in config:
        oa_conf = config["openai_compatible"]
        if oa_conf.get("base_url"):
            os.environ["OPENAI_COMPATIBLE_BASE_URL"] = oa_conf["base_url"]
        if oa_conf.get("api_key"):
            os.environ["OPENAI_COMPATIBLE_API_KEY"] = oa_conf["api_key"]

    try:
        # Nếu tests truyền sẵn một argparse.Namespace thì dùng trực tiếp
        # để không phá vỡ hành vi cũ.
        if isinstance(provided_args, argparse.Namespace):
            ns_language = getattr(provided_args, "language", None)
            if ns_language in ("vi", "en"):
                language = ns_language
            parser = cli.create_parser(language=language)
            args = provided_args
        else:
            raw_args = provided_args if provided_args is not None else sys.argv[1:]
            # Hỗ trợ cú pháp ngắn `termi chat` / `termi agent` cho người dùng cuối.
            raw_args = _preprocess_subcommands(list(raw_args))
            language = _extract_language_from_argv(raw_args, language)
            parser = cli.create_parser(language=language)
            args = parser.parse_args(raw_args)
        cli_help_text = parser.format_help()
        args.cli_help_text = cli_help_text

        cli_app.run_cli(
            console=console,
            config=config,
            language=language,
            parser=parser,
            args=args,
            cli_help_text=cli_help_text,
            provided_args=provided_args,
            run_single_turn=_run_single_turn,
            handle_history_flow=_handle_history_flow,
            requires_gemini_for_command=_requires_gemini_for_command,
        )

    except KeyboardInterrupt:
        console.print(i18n.tr(language, "interrupted_by_user"))
    except Exception as e:
        console.print(i18n.tr(language, "unexpected_startup_error", error=e))


if __name__ == "__main__":
    main()