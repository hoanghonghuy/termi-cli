"""
Module này chịu trách nhiệm quản lý tương tác với API của Google Gemini,
bao gồm cả cơ chế xử lý lỗi Quota mạnh mẽ, và đăng ký danh sách tools (bao gồm plugin).
"""
import os
import time
import re
import importlib.util
from pathlib import Path
import logging

try:
    import google.generativeai as genai
    from google.api_core.exceptions import ResourceExhausted
    GEMINI_AVAILABLE = True
except Exception:
    # Trong môi trường không cài được Gemini SDK (ví dụ Python 3.14), ta
    # vẫn cần một đối tượng genai có thuộc tính GenerativeModel để các unit
    # test có thể patch. Khi chạy dưới pytest (PYTEST_CURRENT_TEST tồn tại),
    # ta cho phép GEMINI_AVAILABLE=True để dùng stub + patch trong test;
    # còn khi chạy CLI bình thường thì GEMINI_AVAILABLE=False để tránh gọi
    # Gemini thật.

    class _DummyGenerativeModel:
        def __init__(self, *args, **kwargs) -> None:  # pragma: no cover - stub cho test
            pass

    class _DummyGenaiModule:
        GenerativeModel = _DummyGenerativeModel

    genai = _DummyGenaiModule()  # type: ignore[assignment]

    class ResourceExhausted(Exception):  # type: ignore[no-redef]
        """Fallback khi không import được google.api_core.exceptions (ví dụ Python 3.14)."""

        pass

    GEMINI_AVAILABLE = "PYTEST_CURRENT_TEST" in os.environ

from rich.table import Table
from rich.console import Console

# Import các module con một cách an toàn
from termi_cli.tools import web_search, database, calendar_tool, email_tool, file_system_tool, shell_tool, system_time_tool, system_status_tool

# Import các module con một cách an toàn
from termi_cli.tools import instruction_tool
from termi_cli.tools import code_tool
from termi_cli.tools import git_advanced_tool
from termi_cli.prompts import build_enhanced_instruction
from termi_cli.config import APP_DIR
from termi_cli.infrastructure import http_providers

_current_api_key_index = 0
_api_keys = []
_console = Console()
_last_free_tier_call_ts: float | None = None
logger = logging.getLogger(__name__)

# Re-export HTTP provider exceptions và helpers để giữ nguyên public API
DeepseekInsufficientBalance = http_providers.DeepseekInsufficientBalance
GroqInsufficientBalance = http_providers.GroqInsufficientBalance
OpenRouterInsufficientBalance = http_providers.OpenRouterInsufficientBalance

initialize_deepseek_api_keys = http_providers.initialize_deepseek_api_keys
initialize_groq_api_keys = http_providers.initialize_groq_api_keys
initialize_openrouter_api_keys = http_providers.initialize_openrouter_api_keys

is_openrouter_model = http_providers.is_openrouter_model
is_ollama_model = http_providers.is_ollama_model
is_ollama_cloud_model = http_providers.is_ollama_cloud_model
is_generic_openai_model = http_providers.is_generic_openai_model

get_http_metrics = http_providers.get_http_metrics


def generate_text(model_name: str, prompt: str, system_instruction: str | None = None) -> str:
    """Sinh text thuần từ một model, bọc qua resilient_generate_content + get_response_text.

    Dùng helper này thay vì khởi tạo genai.GenerativeModel trực tiếp ở các module khác,
    để sau này có thể hoán đổi provider (ví dụ DeepSeek, Groq) chỉ bằng cách sửa api.py.

    - Nhánh ``deepseek-*``: gọi DeepSeek Chat Completions qua HTTP API với cơ chế
      retry + xoay API key riêng (DEEPSEEK_API_KEY, DEEPSEEK_API_KEY_2ND, ...).
    - Nhánh ``groq-*``: gọi Groq Chat Completions (OpenAI-compatible) với bộ
      Groq API key riêng (GROQ_API_KEY, GROQ_API_KEY_2ND, ...).
    - Nhánh OpenRouter: model_name dạng ``provider/model`` (không phải ``models/*``),
      dùng OpenRouter Chat Completions (OpenAI-compatible) với bộ OpenRouter API key riêng
      (OPENROUTER_API_KEY, OPENROUTER_API_KEY_2ND, ...).
    - Nhánh Ollama local: model_name dạng ``ollama/<model-tag>`` (ví dụ ``ollama/qwen3:8b``),
      gọi Ollama Chat Completions trên localhost qua HTTP API.
    - Nhánh Ollama Cloud: model_name dạng ``ollama-cloud/<model-tag>`` (ví dụ ``ollama-cloud/qwen3-coder:480b-cloud``),
      gọi Ollama Cloud REST API với OLLAMA_API_KEY.
    - Các model còn lại: dùng Gemini như trước đây.
    """

    provider_kind = http_providers.detect_provider_kind(model_name)

    # Nhánh HTTP provider (DeepSeek/Groq/OpenRouter/Ollama) được uỷ quyền hoàn toàn
    # cho infrastructure.http_providers để giữ api.py mỏng và dễ bảo trì.
    if provider_kind != "gemini":
        return http_providers.http_generate_text(
            model_name,
            prompt,
            system_instruction=system_instruction,
        )

    if not GEMINI_AVAILABLE:
        _console.print(
            "[bold red]Gemini SDK không khả dụng trên phiên bản Python hiện tại (có thể do Python 3.14). "
            "Hãy sử dụng model HTTP (deepseek-/groq-/OpenRouter) hoặc chạy Termi trên Python 3.11/3.12 để dùng Gemini.[/bold red]"
        )
        raise RuntimeError("Gemini SDK unavailable in this Python environment")

    model_kwargs = {}
    if system_instruction is not None:
        model_kwargs["system_instruction"] = system_instruction

    model = genai.GenerativeModel(model_name, **model_kwargs)
    response = resilient_generate_content(model, prompt)
    return get_response_text(response)


def _load_plugin_tools() -> dict[str, callable]:  # type: ignore[name-defined]
    """Tải thêm tools từ thư mục plugin `APP_DIR/plugins`.

    Mỗi file `.py` (không bắt đầu bằng `_`) có thể định nghĩa biến
    `PLUGIN_TOOLS` là một dict: tên_tool (str) -> callable.
    Các key trùng với core tools sẽ bị bỏ qua để tránh override ngầm.
    """

    plugin_tools: dict[str, callable] = {}
    plugins_dir = Path(APP_DIR) / "plugins"
    if not plugins_dir.exists() or not plugins_dir.is_dir():
        return plugin_tools

    for path in plugins_dir.glob("*.py"):
        if path.name.startswith("_"):
            continue

        module_name = f"termi_cli_plugins.{path.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                logger.warning("Không thể tạo spec cho plugin '%s'", path)
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)  # type: ignore[assignment]

            tools_dict = getattr(module, "PLUGIN_TOOLS", None)
            if not isinstance(tools_dict, dict):
                logger.warning("Plugin '%s' không có dict PLUGIN_TOOLS hợp lệ", path)
                continue
            for name, func in tools_dict.items():
                if not callable(func):
                    logger.warning("Tool '%s' trong plugin '%s' không callable, bỏ qua", name, path)
                    continue
                # Không override core tools
                if name in plugin_tools:
                    logger.warning("Trùng tên tool plugin '%s' trong '%s', bỏ qua", name, path)
                    continue
                plugin_tools[name] = func
                logger.info("Đã đăng ký plugin tool '%s' từ '%s'", name, path)
        except Exception:
            # Plugin lỗi sẽ bị bỏ qua, không làm hỏng toàn bộ CLI
            logger.exception("Lỗi khi load plugin '%s'", path)
            continue

    return plugin_tools


# Ánh xạ tên tool tới hàm thực thi
_PLUGIN_TOOLS = _load_plugin_tools()
AVAILABLE_TOOLS = {
    web_search.search_web.__name__: web_search.search_web,
    database.get_db_schema.__name__: database.get_db_schema,
    database.run_sql_query.__name__: database.run_sql_query,
    calendar_tool.list_events.__name__: calendar_tool.list_events,
    email_tool.search_emails.__name__: email_tool.search_emails,
    instruction_tool.save_instruction.__name__: instruction_tool.save_instruction,
    code_tool.refactor_code.__name__: code_tool.refactor_code,
    code_tool.document_code.__name__: code_tool.document_code,
    file_system_tool.list_files.__name__: file_system_tool.list_files,
    file_system_tool.read_file.__name__: file_system_tool.read_file,
    file_system_tool.write_file.__name__: file_system_tool.write_file,
    file_system_tool.create_directory.__name__: file_system_tool.create_directory,
    shell_tool.execute_command.__name__: shell_tool.execute_command,
    system_time_tool.get_current_time.__name__: system_time_tool.get_current_time,
    system_status_tool.get_cli_uptime.__name__: system_status_tool.get_cli_uptime,
    # Advanced Git tools
    git_advanced_tool.get_merge_conflicts.__name__: git_advanced_tool.get_merge_conflicts,
    git_advanced_tool.get_conflict_content.__name__: git_advanced_tool.get_conflict_content,
    git_advanced_tool.resolve_conflict_in_file.__name__: git_advanced_tool.resolve_conflict_in_file,
    git_advanced_tool.generate_changelog.__name__: git_advanced_tool.generate_changelog,
    git_advanced_tool.get_pr_diff.__name__: git_advanced_tool.get_pr_diff,
    git_advanced_tool.get_branch_info.__name__: git_advanced_tool.get_branch_info,
}

# Hợp nhất plugin tools (nếu có), ưu tiên giữ nguyên core tools khi trùng tên
_PLUGIN_TOOLS = _load_plugin_tools()
for _name, _func in _PLUGIN_TOOLS.items():
    if _name not in AVAILABLE_TOOLS:
        AVAILABLE_TOOLS[_name] = _func


def configure_api(api_key: str):
    """Cấu hình API key ban đầu."""
    if not GEMINI_AVAILABLE:
        raise RuntimeError(
            "Gemini SDK không khả dụng trong môi trường hiện tại. "
            "Hãy dùng model HTTP (deepseek-/groq-/OpenRouter) hoặc chuyển sang Python 3.11/3.12."
        )
    genai.configure(api_key=api_key)


def get_available_models() -> list[str]:
    """Lấy danh sách các model name hỗ trợ generateContent."""
    if not GEMINI_AVAILABLE:
        return []
    models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    return models


def list_models(console: Console):
    """Liệt kê các model có sẵn."""
    if not GEMINI_AVAILABLE:
        console.print(
            "[bold red]Gemini SDK không khả dụng trên phiên bản Python hiện tại (có thể do Python 3.14). "
            "Không thể gọi trực tiếp danh sách model Gemini.[/bold red]"
        )

        # Hiển thị một bảng gợi ý các model HTTP phổ biến để người dùng tham khảo nhanh.
        table = Table(title="✨ Một số models HTTP gợi ý (DeepSeek/Groq/OpenRouter) ✨")
        table.add_column("Provider", style="green", no_wrap=True)
        table.add_column("Model Name", style="cyan", no_wrap=True)
        table.add_column("Description", style="magenta")

        recommendations = [
            ("🟣 DeepSeek", "deepseek-chat", "Chat tổng quát, tốc độ tốt."),
            ("🟣 DeepSeek", "deepseek-reasoner", "Model reasoning mạnh, phù hợp phân tích chuyên sâu."),
            ("🟠 Groq", "groq-chat", "Alias chat nhanh dựa trên LLaMA 3.x."),
            ("🟠 Groq", "groq-llama3-8b-8192", "Model 8B nhanh, phù hợp coding & trợ lý nhẹ."),
            ("🔵 OpenRouter", "openai/gpt-4o-mini", "Model đa năng, phù hợp chat & coding nhẹ."),
            ("🔵 OpenRouter", "google/gemma-2-27b-it", "Model mạnh, free-tier tốt cho coding & phân tích."),
            ("🔵 OpenRouter", "meta-llama/llama-3.1-70b-instruct", "Model 70B mạnh cho reasoning & coding."),
        ]

        for provider_label, name, desc in recommendations:
            table.add_row(provider_label, name, desc)

        console.print(table)
        return

    table = Table(title="✨ Danh sách Models Khả Dụng ✨")
    table.add_column("Provider", style="green", no_wrap=True)
    table.add_column("Model Name", style="cyan", no_wrap=True)
    table.add_column("Description", style="magenta")
    console.print("Đang lấy danh sách models...")
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            provider_label = "🟢 Gemini"
            table.add_row(provider_label, m.name, m.description)
    console.print(table)


def list_tools(console: Console):
    table = Table(title="🔧 Danh sách Tools (core + plugin)")
    table.add_column("Tên tool", style="cyan", no_wrap=True)
    table.add_column("Nguồn", style="magenta", no_wrap=True)
    table.add_column("Mô tả", style="green")

    for name in sorted(AVAILABLE_TOOLS.keys()):
        func = AVAILABLE_TOOLS[name]
        source = "plugin" if name in _PLUGIN_TOOLS else "core"
        doc = ""
        if getattr(func, "__doc__", None):
            doc = func.__doc__.strip().splitlines()[0]
        table.add_row(name, source, doc)

    console.print(table)


class GeminiChatBackend:
    """Backend nhẹ cho chat/tool-calls dùng Gemini.

    Hiện tại chỉ wrap GenAI GenerativeModel/ChatSession để chuẩn bị cho kiềm soát đa provider sau này.
    """

    def __init__(
        self,
        model_name: str,
        system_instruction: str | None = None,
        history: list | None = None,
        cli_help_text: str = "",
    ) -> None:
        if not GEMINI_AVAILABLE:
            raise RuntimeError(
                "Gemini SDK không khả dụng trong môi trường hiện tại. "
                "Hãy dùng model HTTP (deepseek-/groq-/OpenRouter) hoặc chạy Termi trên Python 3.11/3.12."
            )

        enhanced_instruction = build_enhanced_instruction(cli_help_text)
        if system_instruction:
            enhanced_instruction = (
                "**PRIMARY DIRECTIVE (User-defined rules):**\n"  # giữ đúng format cũ
                f"{system_instruction}\n\n---\n\n{enhanced_instruction}"
            )

        tools_config = list(AVAILABLE_TOOLS.values())

        self.model = genai.GenerativeModel(
            model_name,
            system_instruction=enhanced_instruction,
            tools=tools_config,
        )
        self.chat = self.model.start_chat(history=history or [])

    def start_session(self):
        return self.chat

    def send_stream(self, message):
        return self.chat.send_message(message, stream=True)

    def send_resilient(self, message):
        return _resilient_api_call(self.chat.send_message, message)


def start_chat_session(model_name: str, system_instruction: str = None, history: list = None, cli_help_text: str = ""):
    """Khởi tạo chat session."""
    if not GEMINI_AVAILABLE:
        raise RuntimeError(
            "Gemini SDK không khả dụng trong môi trường hiện tại. "
            "Hãy dùng model HTTP (deepseek-/groq-/OpenRouter) hoặc chạy Termi trên Python 3.11/3.12."
        )

    backend = GeminiChatBackend(
        model_name=model_name,
        system_instruction=system_instruction,
        history=history,
        cli_help_text=cli_help_text,
    )
    return backend.start_session()


def get_token_usage(response):
    """Trích xuất thông tin token usage từ response."""
    try:
        if hasattr(response, 'usage_metadata'):
            usage = response.usage_metadata
            return {
                'prompt_tokens': getattr(usage, 'prompt_token_count', 0),
                'completion_tokens': getattr(usage, 'candidates_token_count', 0),
                'total_tokens': getattr(usage, 'total_token_count', 0)
            }
    except Exception:
        pass
    return None


def get_response_text(response) -> str:
    """Trích xuất text từ một response Gemini, an toàn cho cả multi-part.

    - Ưu tiên đọc qua `candidates[].content.parts` (cách chính thức).
    - Fallback sang thuộc tính `.text` cho các đối tượng giả lập trong test.
    """
    if response is None:
        return ""

    # Thử lấy từ cấu trúc candidates/parts trước (multi-part, function_call, ...)
    try:
        if hasattr(response, "candidates") and response.candidates:
            parts_text = []
            for cand in response.candidates:
                content = getattr(cand, "content", None)
                if content is None:
                    continue
                for part in getattr(content, "parts", []) or []:
                    if hasattr(part, "text") and part.text:
                        parts_text.append(part.text)
            if parts_text:
                return "".join(parts_text)
    except Exception:
        # Nếu có lỗi, fallback xuống dưới
        pass

    # Fallback: dùng .text cho các response đơn giản hoặc object giả trong test
    try:
        text_attr = response.text  # type: ignore[attr-defined]
    except Exception:
        text_attr = None

    if isinstance(text_attr, str):
        return text_attr

    return ""


def get_model_token_limit(model_name: str) -> int:
    """Lấy token limit của model."""
    if not GEMINI_AVAILABLE:
        return 0
    try:
        model_info = genai.get_model(model_name)
        if hasattr(model_info, 'input_token_limit'):
            return model_info.input_token_limit
        if 'flash' in model_name.lower():
            return 1000000
        elif 'pro' in model_name.lower():
            return 2000000
    except Exception:
        pass
    return 0


def initialize_api_keys():
    """Khởi tạo danh sách API keys từ .env và reset trạng thái."""
    global _api_keys, _current_api_key_index
    _api_keys = []
    _current_api_key_index = 0
    
    primary = os.getenv("GOOGLE_API_KEY")
    if primary:
        _api_keys.append(primary)
    
    i = 2
    while True:
        key_name = f"GOOGLE_API_KEY_{i}ND" if i == 2 else f"GOOGLE_API_KEY_{i}RD" if i == 3 else f"GOOGLE_API_KEY_{i}TH"
        backup_key = os.getenv(key_name)
        if backup_key:
            _api_keys.append(backup_key)
            i += 1
        else:
            break
    
    return _api_keys


def switch_to_next_api_key():
    """Hàm nội bộ để chuyển sang API key tiếp theo và quay vòng."""
    global _current_api_key_index, _api_keys
    if not GEMINI_AVAILABLE:
        raise RuntimeError(
            "Gemini SDK không khả dụng trong môi trường hiện tại, không thể xoay GOOGLE_API_KEY."
        )
    _current_api_key_index = (_current_api_key_index + 1) % len(_api_keys)
    new_key = _api_keys[_current_api_key_index]
    genai.configure(api_key=new_key)
    return f"Key #{_current_api_key_index + 1}"


class RPDQuotaExhausted(Exception):
    """Exception tùy chỉnh để báo hiệu cần tái tạo session."""
    pass

def _resilient_api_call(api_function, *args, **kwargs):

    """
    Hàm bọc "bất tử" cho mọi lệnh gọi API, tự động xử lý lỗi Quota.
    """
    initial_key_index = _current_api_key_index
    max_rpm_retries = 3
    
    while True:
        rpm_retry_count = 0
        try:
            while rpm_retry_count < max_rpm_retries:
                try:
                    # Throttle client-side: luôn cách nhau tối thiểu ~10 giây giữa các request
                    global _last_free_tier_call_ts
                    now = time.time()
                    min_interval = 10.0

                    # Khi chạy test (pytest), bỏ qua sleep để test không chậm
                    is_pytest = "PYTEST_CURRENT_TEST" in os.environ

                    if _last_free_tier_call_ts is not None and not is_pytest:
                        elapsed = now - _last_free_tier_call_ts
                        if elapsed < min_interval:
                            wait_time = min_interval - elapsed
                            with _console.status(
                                f"[yellow]⏳ Throttle: chờ {wait_time:.1f}s trước khi gọi Gemini...[/yellow]",
                                spinner="clock",
                            ):
                                time.sleep(wait_time)

                    _last_free_tier_call_ts = time.time()

                    return api_function(*args, **kwargs)

                except ResourceExhausted as e:
                    error_message = str(e)

                    # Nếu thông báo cho biết đã hết quota free tier/ngày, không nên retry tiếp
                    if "free_tier_requests" in error_message or "daily" in error_message:
                        raise e

                    match = re.search(r"Please retry in (\d+\.\d+)s", error_message)
                    if match:
                        rpm_retry_count += 1
                        wait_time = float(match.group(1)) + 1
                        with _console.status(
                            f"[yellow]⏳ Lỗi tốc độ (RPM). Chờ {wait_time:.1f}s (thử lại {rpm_retry_count}/{max_rpm_retries})...[/yellow]",
                            spinner="clock",
                        ):
                            time.sleep(wait_time)
                    else:
                        raise e
            
            raise ResourceExhausted("Hết số lần thử lại cho lỗi RPM. Đang chuyển key.")

        except ResourceExhausted as e:
            error_message = str(e)
            # Nếu đã hết quota free tier trong ngày / tổng, không xoay key nữa.
            if "free_tier_requests" in error_message or "daily" in error_message:
                _console.print("[bold red]❌ Đã hết quota free tier (Requests Per Day / free_tier_requests). Hãy thử lại sau khi quota được reset.[/bold red]")
                raise e

            _console.print(f"[yellow]⚠️ Gặp lỗi Quota với Key #{_current_api_key_index + 1}. Đang chuyển sang key tiếp theo...[/yellow]")
            msg = switch_to_next_api_key()

            if _current_api_key_index == initial_key_index:
                _console.print("[bold red]❌ Đã thử tất cả các API key nhưng đều gặp lỗi Quota.[/bold red]")
                raise e
            
            _console.print(f"[green]✅ Đã chuyển sang {msg}. Thử lại...[/green]")
            raise RPDQuotaExhausted("API key changed.")

        except Exception as e:
            _console.print(f"[bold red]Lỗi không mong muốn khi gọi API: {e}[/bold red]")
            raise e

def resilient_generate_content(model: genai.GenerativeModel, prompt: str):
    """Hàm gọi generate_content với cơ chế retry, dùng cho Agent và các tool."""
    return _resilient_api_call(model.generate_content, prompt)

def resilient_send_message(chat_session: genai.ChatSession, prompt):
    """Hàm gọi send_message với cơ chế retry, dùng cho Agent."""
    try:
        return _resilient_api_call(chat_session.send_message, prompt)
    except RPDQuotaExhausted:
        raise

def send_message(chat_session: genai.ChatSession, prompt_parts: list):
    """Hàm send_message gốc cho chế độ chat thông thường (có streaming)."""
    return chat_session.send_message(prompt_parts, stream=True)