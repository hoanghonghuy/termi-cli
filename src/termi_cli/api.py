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
import json
import urllib.request
import urllib.error

import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted
from rich.table import Table
from rich.console import Console

# Import các module con một cách an toàn
from termi_cli.tools import web_search, database, calendar_tool, email_tool, file_system_tool, shell_tool
from termi_cli.tools import instruction_tool
from termi_cli.tools import code_tool
from termi_cli.prompts import build_enhanced_instruction
from termi_cli.config import APP_DIR

_current_api_key_index = 0
_api_keys = []
_console = Console()
_last_free_tier_call_ts: float | None = None
logger = logging.getLogger(__name__)

# --- DeepSeek integration (HTTP API, OpenAI-compatible) ---

_deepseek_api_keys: list[str] = []
_current_deepseek_key_index: int = 0
_last_deepseek_call_ts: float | None = None


class DeepseekInsufficientBalance(Exception):
    """Báo hiệu DeepSeek trả về lỗi thiếu credit (HTTP 402 / Insufficient Balance)."""
    pass


# --- Groq Cloud integration (HTTP OpenAI-compatible) ---

_groq_api_keys: list[str] = []
_current_groq_key_index: int = 0
_last_groq_call_ts: float | None = None


class GroqInsufficientBalance(Exception):
    """Báo hiệu Groq Cloud trả về lỗi thiếu credit (HTTP 402 / Insufficient)."""
    pass


def initialize_deepseek_api_keys() -> list[str]:
    """Khởi tạo danh sách DeepSeek API keys từ biến môi trường.

    Quy ước:
    - DEEPSEEK_API_KEY
    - DEEPSEEK_API_KEY_2ND, DEEPSEEK_API_KEY_3RD, ...
    """
    global _deepseek_api_keys, _current_deepseek_key_index
    _deepseek_api_keys = []
    _current_deepseek_key_index = 0

    primary = os.getenv("DEEPSEEK_API_KEY")
    if primary:
        _deepseek_api_keys.append(primary)

    i = 2
    while True:
        key_name = (
            f"DEEPSEEK_API_KEY_{i}ND" if i == 2
            else f"DEEPSEEK_API_KEY_{i}RD" if i == 3
            else f"DEEPSEEK_API_KEY_{i}TH"
        )
        backup = os.getenv(key_name)
        if not backup:
            break
        _deepseek_api_keys.append(backup)
        i += 1

    return _deepseek_api_keys


def switch_to_next_deepseek_key() -> str:
    """Chuyển sang DeepSeek API key tiếp theo và quay vòng giống logic Gemini."""
    global _deepseek_api_keys, _current_deepseek_key_index
    if not _deepseek_api_keys:
        initialize_deepseek_api_keys()
        if not _deepseek_api_keys:
            raise RuntimeError("No DeepSeek API key configured (DEEPSEEK_API_KEY...).")

    _current_deepseek_key_index = (_current_deepseek_key_index + 1) % len(_deepseek_api_keys)
    return f"DeepSeek key #{_current_deepseek_key_index + 1}"


def _resilient_deepseek_api_call(model_name: str, messages: list[dict]) -> dict:
    """Gọi DeepSeek Chat Completions với cơ chế retry + xoay API key khi hết quota.

    - Sử dụng HTTP API OpenAI-compatible: https://api.deepseek.com/chat/completions
    - Khi gặp lỗi 429 hoặc thông báo chứa "rate limit"/"quota":
        * Nếu có nhiều key: xoay sang key kế tiếp, thử lại.
        * Nếu quay lại key ban đầu: coi như hết toàn bộ key, raise exception.
    - Có throttle đơn giản dựa trên _last_deepseek_call_ts (tương tự Gemini).
    """
    global _deepseek_api_keys, _current_deepseek_key_index, _last_deepseek_call_ts

    if not _deepseek_api_keys:
        initialize_deepseek_api_keys()
        if not _deepseek_api_keys:
            raise RuntimeError("No DeepSeek API key configured (DEEPSEEK_API_KEY...).")

    initial_index = _current_deepseek_key_index
    url = "https://api.deepseek.com/chat/completions"

    while True:
        api_key = _deepseek_api_keys[_current_deepseek_key_index]

        # Throttle đơn giản giữa các request DeepSeek
        now = time.time()
        min_interval = 2.0
        is_pytest = "PYTEST_CURRENT_TEST" in os.environ
        if _last_deepseek_call_ts is not None and not is_pytest:
            elapsed = now - _last_deepseek_call_ts
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)

        payload = {
            "model": model_name,
            "messages": messages,
            "stream": False,
        }
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            _last_deepseek_call_ts = time.time()
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = resp.read().decode("utf-8", errors="ignore")
                return json.loads(body)

        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            lower = body.lower()

            # Trường hợp hết tiền / thiếu credit: raise exception riêng để layer trên có thể fallback provider.
            if e.code == 402 or "insufficient balance" in lower:
                raise DeepseekInsufficientBalance(body) from e

            is_quota_or_rate = (
                e.code == 429
                or "rate limit" in lower
                or "quota" in lower
            )

            if is_quota_or_rate and len(_deepseek_api_keys) > 1:
                _console.print(
                    f"[yellow]⚠️ DeepSeek quota/rate-limit error with key #{_current_deepseek_key_index + 1}. "
                    "Đang chuyển sang key tiếp theo...[/yellow]"
                )
                msg = switch_to_next_deepseek_key()
                if _current_deepseek_key_index == initial_index:
                    _console.print(
                        "[bold red]❌ Đã thử tất cả DeepSeek API key nhưng đều gặp lỗi quota/rate-limit.[/bold red]"
                    )
                    raise RuntimeError("All DeepSeek API keys exhausted") from e

                _console.print(f"[green]✅ Đã chuyển sang {msg}. Thử lại...[/green]")
                continue

            # Các lỗi HTTP khác: log ra console và re-raise để caller xử lý
            _console.print(
                f"[bold red]Lỗi HTTP khi gọi DeepSeek (status={e.code}): {body}[/bold red]"
            )
            raise

        except urllib.error.URLError as e:  # bao gồm lỗi kết nối, timeout ở tầng socket
            _console.print(f"[bold red]Không thể kết nối tới DeepSeek API: {e}[/bold red]")
            raise


def initialize_groq_api_keys() -> list[str]:
    """Khởi tạo danh sách Groq API keys từ biến môi trường.

    Quy ước:
    - GROQ_API_KEY
    - GROQ_API_KEY_2ND, GROQ_API_KEY_3RD, ...
    """
    global _groq_api_keys, _current_groq_key_index
    _groq_api_keys = []
    _current_groq_key_index = 0

    primary = os.getenv("GROQ_API_KEY")
    if primary:
        _groq_api_keys.append(primary)

    i = 2
    while True:
        key_name = (
            f"GROQ_API_KEY_{i}ND" if i == 2
            else f"GROQ_API_KEY_{i}RD" if i == 3
            else f"GROQ_API_KEY_{i}TH"
        )
        backup = os.getenv(key_name)
        if not backup:
            break
        _groq_api_keys.append(backup)
        i += 1

    return _groq_api_keys


def switch_to_next_groq_key() -> str:
    """Chuyển sang Groq API key tiếp theo."""
    global _groq_api_keys, _current_groq_key_index
    if not _groq_api_keys:
        initialize_groq_api_keys()
        if not _groq_api_keys:
            raise RuntimeError("No Groq API key configured (GROQ_API_KEY...).")

    _current_groq_key_index = (_current_groq_key_index + 1) % len(_groq_api_keys)
    return f"Groq key #{_current_groq_key_index + 1}"


def _resilient_groq_api_call(model_name: str, messages: list[dict]) -> dict:
    """Gọi Groq Chat Completions với cơ chế retry + xoay API key khi hết quota.

    - Sử dụng HTTP API OpenAI-compatible: https://api.groq.com/openai/v1/chat/completions
    - Khi gặp lỗi 429 hoặc thông báo chứa "rate limit"/"quota":
        * Nếu có nhiều key: xoay sang key kế tiếp, thử lại.
        * Nếu quay lại key ban đầu: coi như hết toàn bộ key, raise exception.
    - Có throttle đơn giản dựa trên _last_groq_call_ts (tương tự DeepSeek).
    """
    global _groq_api_keys, _current_groq_key_index, _last_groq_call_ts

    if not _groq_api_keys:
        initialize_groq_api_keys()
        if not _groq_api_keys:
            raise RuntimeError("No Groq API key configured (GROQ_API_KEY...).")

    initial_index = _current_groq_key_index
    url = "https://api.groq.com/openai/v1/chat/completions"

    while True:
        api_key = _groq_api_keys[_current_groq_key_index]

        now = time.time()
        min_interval = 1.0
        is_pytest = "PYTEST_CURRENT_TEST" in os.environ
        if _last_groq_call_ts is not None and not is_pytest:
            elapsed = now - _last_groq_call_ts
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)

        payload = {
            "model": model_name,
            "messages": messages,
            "stream": False,
        }
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            _last_groq_call_ts = time.time()
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = resp.read().decode("utf-8", errors="ignore")
                return json.loads(body)

        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            lower = body.lower()

            if e.code == 402 or ("insufficient" in lower and ("credit" in lower or "balance" in lower or "quota" in lower)):
                raise GroqInsufficientBalance(body) from e

            is_quota_or_rate = (
                e.code == 429
                or "rate limit" in lower
                or "quota" in lower
            )

            if is_quota_or_rate and len(_groq_api_keys) > 1:
                _console.print(
                    f"[yellow]⚠️ Groq quota/rate-limit error with key #{_current_groq_key_index + 1}. Đang chuyển sang key tiếp theo...[/yellow]"
                )
                msg = switch_to_next_groq_key()
                if _current_groq_key_index == initial_index:
                    _console.print(
                        "[bold red]❌ Đã thử tất cả Groq API key nhưng đều gặp lỗi quota/rate-limit.[/bold red]"
                    )
                    raise RuntimeError("All Groq API keys exhausted") from e

                _console.print(f"[green]✅ Đã chuyển sang {msg}. Thử lại...[/green]")
                continue

            _console.print(
                f"[bold red]Lỗi HTTP khi gọi Groq (status={e.code}): {body}[/bold red]"
            )
            raise

        except urllib.error.URLError as e:
            _console.print(f"[bold red]Không thể kết nối tới Groq API: {e}[/bold red]")
            raise


def _normalize_groq_model(model_name: str) -> str:
    """Chuẩn hoá tên model Groq khi người dùng dùng alias tiện nhớ.

    - Đầu vào thường có dạng "groq-<alias-hoặc-model-thật>".
    - Nếu là alias ngắn (ví dụ: "groq-chat"), map sang model Groq khuyến nghị.
    - Nếu đã là tên model Groq đầy đủ (ví dụ: "groq-llama-3.1-70b-versatile"), giữ nguyên.
    """

    raw = model_name
    if model_name.startswith("groq-"):
        raw = model_name[len("groq-"):] or model_name

    alias_map = {
        # Alias thân thiện cho chat tổng quát (dùng model Groq khuyến nghị mới)
        "chat": "llama-3.3-70b-versatile",
        # Một số alias rút gọn thường gặp
        "llama-3.1-70b": "llama-3.3-70b-versatile",
        "llama3-70b": "llama-3.3-70b-versatile",
        "llama3-8b": "llama3-8b-8192",
    }

    return alias_map.get(raw, raw)


def generate_text(model_name: str, prompt: str, system_instruction: str | None = None) -> str:
    """Sinh text thuần từ một model, bọc qua resilient_generate_content + get_response_text.

    Dùng helper này thay vì khởi tạo genai.GenerativeModel trực tiếp ở các module khác,
    để sau này có thể hoán đổi provider (ví dụ DeepSeek, Groq) chỉ bằng cách sửa api.py.

    - Nhánh ``deepseek-*``: gọi DeepSeek Chat Completions qua HTTP API với cơ chế
      retry + xoay API key riêng (DEEPSEEK_API_KEY, DEEPSEEK_API_KEY_2ND, ...).
    - Nhánh ``groq-*``: gọi Groq Chat Completions (OpenAI-compatible) với bộ
      Groq API key riêng (GROQ_API_KEY, GROQ_API_KEY_2ND, ...).
    - Các model còn lại: dùng Gemini như trước đây.
    """
    if model_name.startswith("deepseek-"):
        messages: list[dict] = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        response = _resilient_deepseek_api_call(model_name, messages)
        try:
            # OpenAI-compatible schema: choices[0].message.content
            return response["choices"][0]["message"]["content"]
        except Exception:
            # Nếu format không như mong đợi, trả body thô để debug
            return json.dumps(response, ensure_ascii=False)

    if model_name.startswith("groq-"):
        groq_model = _normalize_groq_model(model_name)
        messages: list[dict] = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        response = _resilient_groq_api_call(groq_model, messages)
        try:
            return response["choices"][0]["message"]["content"]
        except Exception:
            return json.dumps(response, ensure_ascii=False)

    # Nhánh mặc định: dùng Gemini thông qua google.generativeai
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
}

# Hợp nhất plugin tools (nếu có), ưu tiên giữ nguyên core tools khi trùng tên
_PLUGIN_TOOLS = _load_plugin_tools()
for _name, _func in _PLUGIN_TOOLS.items():
    if _name not in AVAILABLE_TOOLS:
        AVAILABLE_TOOLS[_name] = _func


def configure_api(api_key: str):
    """Cấu hình API key ban đầu."""
    genai.configure(api_key=api_key)


def get_available_models() -> list[str]:
    """Lấy danh sách các model name hỗ trợ generateContent."""
    models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    return models


def list_models(console: Console):
    """Liệt kê các model có sẵn."""
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


def start_chat_session(model_name: str, system_instruction: str = None, history: list = None, cli_help_text: str = ""):
    """Khởi tạo chat session."""
    enhanced_instruction = build_enhanced_instruction(cli_help_text)
    if system_instruction:
        enhanced_instruction = f"**PRIMARY DIRECTIVE (User-defined rules):**\n{system_instruction}\n\n---\n\n{enhanced_instruction}"

    tools_config = list(AVAILABLE_TOOLS.values())

    model = genai.GenerativeModel(
        model_name,
        system_instruction=enhanced_instruction,
        tools=tools_config
    )

    chat = model.start_chat(history=history or [])
    return chat


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