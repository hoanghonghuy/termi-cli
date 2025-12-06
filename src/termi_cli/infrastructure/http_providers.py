"""HTTP provider integrations (DeepSeek, Groq, OpenRouter, Ollama).

Tách riêng khỏi `termi_cli.api` để giảm trách nhiệm của api.py và chuẩn bị
cho mở rộng đa provider dễ bảo trì hơn.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod

from rich.console import Console

from termi_cli.json_utils import JsonPayloadParseError, parse_json_payload


logger = logging.getLogger(__name__)
_console = Console()

# Base URL cho Ollama OpenAI-compatible API (local). Có thể override bằng OLLAMA_BASE_URL.
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
# Base URL cho Ollama Cloud REST API.
OLLAMA_CLOUD_BASE_URL = os.getenv("OLLAMA_CLOUD_BASE_URL", "https://ollama.com")


# --- DeepSeek integration (HTTP API, OpenAI-compatible) ---

_deepseek_api_keys: list[str] = []
_current_deepseek_key_index: int = 0
_last_deepseek_call_ts: float | None = None


class DeepseekInsufficientBalance(Exception):
    """Báo hiệu DeepSeek trả về lỗi thiếu credit (HTTP 402 / Insufficient Balance)."""

    pass


# --- Groq integration ---

_groq_api_keys: list[str] = []
_current_groq_key_index: int = 0
_last_groq_call_ts: float | None = None


class GroqInsufficientBalance(Exception):
    """Báo hiệu Groq Cloud trả về lỗi thiếu credit (HTTP 402 / Insufficient)."""

    pass


# --- OpenRouter integration ---

_openrouter_api_keys: list[str] = []
_current_openrouter_key_index: int = 0
_last_openrouter_call_ts: float | None = None


class OpenRouterInsufficientBalance(Exception):
    pass


def _parse_provider_json_response(body: str, provider: str) -> dict:
    """Parse JSON từ HTTP provider với sanitizer để xử lý dấu phẩy dư."""

    try:
        return parse_json_payload(body)
    except JsonPayloadParseError as err:
        snippet = (body or "")[:200].replace("\n", " ")
        _console.print(
            f"[bold red]{provider} trả về JSON không hợp lệ: {err}. Body: {snippet}[/bold red]"
        )
        raise RuntimeError(f"{provider} returned invalid JSON") from err


# ---- DeepSeek helpers -----------------------------------------------------


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
    - Có throttle đơn giản dựa trên _last_deepseek_call_ts.
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
                return _parse_provider_json_response(body, "DeepSeek")

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


# ---- Groq helpers ---------------------------------------------------------


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
    - Có throttle đơn giản dựa trên _last_groq_call_ts.
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
                return _parse_provider_json_response(body, "Groq")

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


# ---- OpenRouter helpers ---------------------------------------------------


def is_openrouter_model(model_name: str) -> bool:
    if not isinstance(model_name, str):
        return False
    if model_name.startswith("models/"):
        return False
    # Loại trừ prefix ollama/ vì đây là provider local riêng, không phải OpenRouter.
    if model_name.startswith("ollama/"):
        return False
    if model_name.startswith("ollama-cloud/"):
        return False
    return "/" in model_name


def is_ollama_cloud_model(model_name: str) -> bool:
    return isinstance(model_name, str) and model_name.startswith("ollama-cloud/")


def initialize_openrouter_api_keys() -> list[str]:
    global _openrouter_api_keys, _current_openrouter_key_index
    _openrouter_api_keys = []
    _current_openrouter_key_index = 0

    primary = os.getenv("OPENROUTER_API_KEY")
    if primary:
        _openrouter_api_keys.append(primary)

    i = 2
    while True:
        key_name = (
            f"OPENROUTER_API_KEY_{i}ND" if i == 2
            else f"OPENROUTER_API_KEY_{i}RD" if i == 3
            else f"OPENROUTER_API_KEY_{i}TH"
        )
        backup = os.getenv(key_name)
        if not backup:
            break
        _openrouter_api_keys.append(backup)
        i += 1

    return _openrouter_api_keys


def switch_to_next_openrouter_key() -> str:
    global _openrouter_api_keys, _current_openrouter_key_index
    if not _openrouter_api_keys:
        initialize_openrouter_api_keys()
        if not _openrouter_api_keys:
            raise RuntimeError("No OpenRouter API key configured (OPENROUTER_API_KEY...).")

    _current_openrouter_key_index = (_current_openrouter_key_index + 1) % len(_openrouter_api_keys)
    return f"OpenRouter key #{_current_openrouter_key_index + 1}"


def _resilient_openrouter_api_call(model_name: str, messages: list[dict]) -> dict:
    global _openrouter_api_keys, _current_openrouter_key_index, _last_openrouter_call_ts

    if not _openrouter_api_keys:
        initialize_openrouter_api_keys()
        if not _openrouter_api_keys:
            raise RuntimeError("No OpenRouter API key configured (OPENROUTER_API_KEY...).")

    initial_index = _current_openrouter_key_index
    url = "https://openrouter.ai/api/v1/chat/completions"

    while True:
        api_key = _openrouter_api_keys[_current_openrouter_key_index]

        now = time.time()
        min_interval = 1.0
        is_pytest = "PYTEST_CURRENT_TEST" in os.environ
        if _last_openrouter_call_ts is not None and not is_pytest:
            elapsed = now - _last_openrouter_call_ts
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

        referer = os.getenv("OPENROUTER_SITE_URL")
        title = os.getenv("OPENROUTER_SITE_NAME")
        if referer:
            headers["HTTP-Referer"] = referer
        if title:
            headers["X-Title"] = title

        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            _last_openrouter_call_ts = time.time()
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = resp.read().decode("utf-8", errors="ignore")
                return _parse_provider_json_response(body, "OpenRouter")

        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            lower = body.lower()

            if e.code == 402 or (
                "insufficient" in lower
                and ("credit" in lower or "balance" in lower or "funds" in lower)
            ):
                raise OpenRouterInsufficientBalance(body) from e

            is_quota_or_rate = (
                e.code == 429
                or "rate limit" in lower
                or "quota" in lower
                or "too many requests" in lower
            )

            if is_quota_or_rate and len(_openrouter_api_keys) > 1:
                _console.print(
                    f"[yellow]⚠️ OpenRouter quota/rate-limit error with key #{_current_openrouter_key_index + 1}. Đang chuyển sang key tiếp theo...[/yellow]"
                )
                msg = switch_to_next_openrouter_key()
                if _current_openrouter_key_index == initial_index:
                    _console.print(
                        "[bold red]❌ Đã thử tất cả OpenRouter API key nhưng đều gặp lỗi quota/rate-limit.[/bold red]"
                    )
                    raise RuntimeError("All OpenRouter API keys exhausted") from e

                _console.print(f"[green]✅ Đã chuyển sang {msg}. Thử lại...[/green]")
                continue

            _console.print(
                f"[bold red]Lỗi HTTP khi gọi OpenRouter (status={e.code}): {body}[/bold red]"
            )
            raise

        except urllib.error.URLError as e:
            _console.print(f"[bold red]Không thể kết nối tới OpenRouter API: {e}[/bold red]")
            raise


# ---- Ollama helpers -------------------------------------------------------


def is_ollama_model(model_name: str) -> bool:
    """Kiểm tra model có thuộc nhóm Ollama local hay không.

    Quy ước: model_name bắt đầu bằng "ollama/", phần sau là tên model thực tế trong Ollama,
    ví dụ: "ollama/qwen3:8b".
    """

    return isinstance(model_name, str) and model_name.startswith("ollama/")


def _ollama_chat_completions(model_name: str, messages: list[dict]) -> dict:
    """Gọi Ollama Chat Completions (OpenAI-compatible) cho các model local.

    - Sử dụng endpoint OpenAI-compatible mặc định: {OLLAMA_BASE_URL}/v1/chat/completions.
    - model_name là tên model trong Ollama (ví dụ: "qwen3:8b").
    - Không có khái niệm quota/InsufficientBalance, chỉ log lỗi HTTP/kết nối.
    """

    base_url = OLLAMA_BASE_URL.rstrip("/")
    url = f"{base_url}/v1/chat/completions"

    payload = {
        "model": model_name,
        "messages": messages,
        "stream": False,
    }
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        # Ollama OpenAI-compatible thường yêu cầu header Authorization, giá trị bất kỳ.
        "Authorization": "Bearer ollama",
    }

    req = urllib.request.Request(url, data=data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            return _parse_provider_json_response(body, "Ollama")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        _console.print(
            f"[bold red]Lỗi HTTP khi gọi Ollama (status={e.code}): {body}[/bold red]"
        )
        raise
    except urllib.error.URLError as e:
        _console.print(f"[bold red]Không thể kết nối tới Ollama API: {e}[/bold red]")
        raise


def _ollama_cloud_chat_completions(model_name: str, messages: list[dict]) -> dict:
    """Gọi Ollama Cloud REST API (https://ollama.com/api/chat).

    Yêu cầu biến môi trường OLLAMA_API_KEY và endpoint `/api/chat`.
    """

    api_key = os.getenv("OLLAMA_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OLLAMA_API_KEY chưa được thiết lập. Hãy tạo API key tại https://ollama.com/settings/keys và export trước khi gọi Ollama Cloud."
        )

    base_url = OLLAMA_CLOUD_BASE_URL.rstrip("/")
    url = f"{base_url}/api/chat"

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
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            return _parse_provider_json_response(body, "Ollama Cloud")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        _console.print(
            f"[bold red]Lỗi HTTP khi gọi Ollama Cloud (status={e.code}): {body}[/bold red]"
        )
        raise
    except urllib.error.URLError as e:
        _console.print(
            f"[bold red]Không thể kết nối tới Ollama Cloud API: {e}[/bold red]"
        )
        raise


# ---- HTTP message helpers -------------------------------------------------


def _build_http_messages(prompt: str, system_instruction: str | None) -> list[dict]:
    """Xây dựng danh sách messages chuẩn cho các provider HTTP (system + user)."""

    messages: list[dict] = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": prompt})
    return messages


def _extract_openai_message_text(response: dict) -> str:
    """Trích xuất nội dung từ response dạng OpenAI Chat Completions.

    Nếu cấu trúc không như mong đợi, fallback sang json.dumps để giúp debug.
    """

    try:
        return response["choices"][0]["message"]["content"]
    except Exception:
        return json.dumps(response, ensure_ascii=False)


# ---- HTTP metrics & cache -------------------------------------------------


_HTTP_CACHE_MAX_ENTRIES = 128
_http_response_cache: dict[tuple[str, str, str | None, str], str] = {}

# Metrics đơn giản cho HTTP providers, dùng cho diagnostics & logging nội bộ.
_HTTP_METRICS: dict[str, object] = {
    "http_calls_total": 0,
    "http_cache_hits_total": 0,
    "http_calls_by_provider": {},  # type: ignore[dict-item]
}


def _http_cache_get(provider_kind: str, model_name: str, prompt: str, system_instruction: str | None) -> str | None:
    key = (provider_kind, model_name, system_instruction, prompt)
    return _http_response_cache.get(key)


def _http_cache_set(provider_kind: str, model_name: str, prompt: str, system_instruction: str | None, value: str) -> None:
    if len(_http_response_cache) >= _HTTP_CACHE_MAX_ENTRIES:
        try:
            _http_response_cache.pop(next(iter(_http_response_cache)))
        except StopIteration:
            pass
    key = (provider_kind, model_name, system_instruction, prompt)
    _http_response_cache[key] = value


def _http_metrics_record_call(provider_kind: str) -> None:
    _HTTP_METRICS["http_calls_total"] = int(_HTTP_METRICS.get("http_calls_total", 0)) + 1
    by_provider = _HTTP_METRICS.get("http_calls_by_provider") or {}
    if not isinstance(by_provider, dict):
        by_provider = {}
    by_provider[provider_kind] = int(by_provider.get(provider_kind, 0)) + 1
    _HTTP_METRICS["http_calls_by_provider"] = by_provider


def _http_metrics_record_cache_hit() -> None:
    _HTTP_METRICS["http_cache_hits_total"] = int(_HTTP_METRICS.get("http_cache_hits_total", 0)) + 1


def get_http_metrics() -> dict:
    """Trả về snapshot metrics HTTP providers để phục vụ diagnostics.

    Giá trị được tính từ lúc process khởi động, chỉ dùng để debug/quan sát.
    """

    return {
        "http_calls_total": int(_HTTP_METRICS.get("http_calls_total", 0)),
        "http_cache_hits_total": int(_HTTP_METRICS.get("http_cache_hits_total", 0)),
        "http_calls_by_provider": dict(_HTTP_METRICS.get("http_calls_by_provider") or {}),
    }


# ---- Provider registry & dispatch -----------------------------------------


def detect_provider_kind(model_name: str) -> str:
    if is_ollama_cloud_model(model_name):
        return "ollama_cloud"
    if is_ollama_model(model_name):
        return "ollama"
    if is_openrouter_model(model_name):
        return "openrouter"
    if isinstance(model_name, str) and model_name.startswith("deepseek-"):
        return "deepseek"
    if isinstance(model_name, str) and model_name.startswith("groq-"):
        return "groq"
    return "gemini"


class BaseProvider(ABC):
    @abstractmethod
    def generate(self, model_name: str, prompt: str, system_instruction: str | None) -> str:  # pragma: no cover - interface
        raise NotImplementedError


class DeepseekProvider(BaseProvider):
    def generate(self, model_name: str, prompt: str, system_instruction: str | None) -> str:
        messages = _build_http_messages(prompt, system_instruction)
        response = _resilient_deepseek_api_call(model_name, messages)
        return _extract_openai_message_text(response)


class GroqProvider(BaseProvider):
    def generate(self, model_name: str, prompt: str, system_instruction: str | None) -> str:
        groq_model = _normalize_groq_model(model_name)
        messages = _build_http_messages(prompt, system_instruction)
        response = _resilient_groq_api_call(groq_model, messages)
        return _extract_openai_message_text(response)


class OpenRouterProvider(BaseProvider):
    def generate(self, model_name: str, prompt: str, system_instruction: str | None) -> str:
        messages = _build_http_messages(prompt, system_instruction)
        response = _resilient_openrouter_api_call(model_name, messages)
        return _extract_openai_message_text(response)


class OllamaProvider(BaseProvider):
    def generate(self, model_name: str, prompt: str, system_instruction: str | None) -> str:
        messages = _build_http_messages(prompt, system_instruction)
        ollama_model = model_name.split("/", 1)[1] if "/" in model_name else model_name
        response = _ollama_chat_completions(ollama_model, messages)
        return _extract_openai_message_text(response)


class OllamaCloudProvider(BaseProvider):
    def generate(self, model_name: str, prompt: str, system_instruction: str | None) -> str:
        messages = _build_http_messages(prompt, system_instruction)
        cloud_model = model_name.split("/", 1)[1] if "/" in model_name else model_name
        response = _ollama_cloud_chat_completions(cloud_model, messages)
        try:
            if "message" in response:
                return response["message"]["content"]
            return _extract_openai_message_text(response)
        except Exception:
            return json.dumps(response, ensure_ascii=False)


_PROVIDER_REGISTRY: dict[str, BaseProvider] = {
    "deepseek": DeepseekProvider(),
    "groq": GroqProvider(),
    "openrouter": OpenRouterProvider(),
    "ollama": OllamaProvider(),
    "ollama_cloud": OllamaCloudProvider(),
}


def http_generate_text(model_name: str, prompt: str, system_instruction: str | None = None) -> str:
    """Sinh text thuần từ một model HTTP provider.

    Bao gồm cache/metering đơn giản và phân phối tới từng provider.
    """

    provider_kind = detect_provider_kind(model_name)
    if provider_kind == "gemini":
        raise RuntimeError("http_generate_text được gọi với model Gemini")

    cached = _http_cache_get(provider_kind, model_name, prompt, system_instruction)
    if cached is not None:
        logger.debug("HTTP generate_text cache hit (provider=%s, model=%s)", provider_kind, model_name)
        _http_metrics_record_cache_hit()
        return cached

    provider = _PROVIDER_REGISTRY.get(provider_kind)
    if provider is None:
        raise RuntimeError(f"Unknown provider kind: {provider_kind}")

    logger.debug("HTTP generate_text call (provider=%s, model=%s)", provider_kind, model_name)
    result = provider.generate(model_name, prompt, system_instruction)
    _http_cache_set(provider_kind, model_name, prompt, system_instruction, result)
    _http_metrics_record_call(provider_kind)
    return result
