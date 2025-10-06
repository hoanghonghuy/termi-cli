# src/api.py
"""
Wrapper an toàn cho Google Generative AI SDK (google.generativeai).
Mục tiêu:
- Giữ nguyên các hàm thường dùng trong project: configure_api, start_chat_session, send_message, list_models, get_model_token_limit.
- Thực hiện lazy-import google.generativeai để tránh load native libs (gRPC/absl) ở thời điểm import module.
- Cung cấp fallback rõ ràng (error messages) khi SDK không có hoặc gọi API lỗi.
- Không thay đổi giao diện hàm (signature) để dễ tích hợp với code hiện có.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Iterable, Generator, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Không import google.generativeai ở top-level để tránh load gRPC/absl sớm
def _import_genai():
    """
    Lazy import google.generativeai. Ném ImportError nếu không có.
    """
    try:
        import google.generativeai as genai  # type: ignore
        return genai
    except Exception as e:
        # Ghi log chi tiết cho debug, nhưng không raise nguyên vẹn để phần gọi xử lý được.
        logger.debug("Không thể import google.generativeai: %s", e, exc_info=True)
        raise ImportError("google.generativeai chưa được cài hoặc không thể import. "
                          "Vui lòng cài package chính chủ (pip install google-generativeai) "
                          "và đảm bảo môi trường đã được cấu hình.") from e


# -------------------------
# Public API functions
# -------------------------
def configure_api(api_key: str, **kwargs) -> None:
    """
    Cấu hình API key cho google.generativeai.
    Gọi hàm này trước khi tạo session / gọi model.

    Args:
        api_key: API key (string)
        **kwargs: additional options (ignored but accepted for compatibility)
    Raises:
        ImportError nếu SDK không có.
        Exception nếu configure lỗi.
    """
    genai = _import_genai()
    try:
        # Một số SDK dùng genai.configure, tuỳ SDK phiên bản
        if hasattr(genai, "configure"):
            genai.configure(api_key=api_key)
        else:
            # Một số bản mới có thể dùng khác - bảo toàn call
            # Ví dụ: genai.Client(...) -> not standardized; để logger thông báo
            logger.debug("SDK không có hàm configure; tiếp tục mà không gọi configure().")
    except Exception as e:
        logger.exception("Lỗi khi cấu hình google.generativeai: %s", e)
        raise


def start_chat_session(model_name: str,
                       system_instruction: Optional[str] = None,
                       history: Optional[List[Dict[str, str]]] = None,
                       cli_help_text: Optional[str] = None,
                       **kwargs) -> Any:
    """
    Khởi tạo chat session (wrapper) dùng model của google.generativeai.
    Trả về đối tượng session (SDK-specific) có method send_message.

    Args:
        model_name: Tên model (ví dụ "gemini-2.0-flash-exp")
        system_instruction: system prompt (nếu có)
        history: danh sách history theo định dạng [{'role': 'user'|'assistant'|'system', 'content': '...'}, ...]
        cli_help_text: text hỗ trợ / help để gộp vào system instruction nếu cần
        **kwargs: reserved for compatibility

    Returns:
        chat_session object (SDK provided)
    Raises:
        ImportError nếu SDK không cài, Exception nếu tạo session lỗi.
    """
    genai = _import_genai()

    combined_system = None
    if system_instruction and cli_help_text:
        combined_system = f"{system_instruction}\n\n{cli_help_text}"
    elif system_instruction:
        combined_system = system_instruction
    elif cli_help_text:
        combined_system = cli_help_text

    history = history or []

    try:
        # Cố gắng khởi tạo theo API phổ biến: GenerativeModel(...).start_chat(history=...)
        if hasattr(genai, "GenerativeModel"):
            model = genai.GenerativeModel(model_name, system_instruction=combined_system)
            chat = model.start_chat(history=history)
            return chat
        else:
            # Fallback nếu SDK khác phiên bản: thử genai.start_chat hoặc genai.chat
            if hasattr(genai, "start_chat"):
                return genai.start_chat(model=model_name, system_instruction=combined_system, history=history)
            elif hasattr(genai, "chat"):
                return genai.chat(model=model_name, system_instruction=combined_system, history=history)
            else:
                raise RuntimeError("Không tìm thấy API phù hợp trong google.generativeai để tạo chat session.")
    except Exception as e:
        logger.exception("Lỗi khi tạo chat session cho model %s: %s", model_name, e)
        raise


def send_message(chat_session: Any, prompt_parts: Iterable[str], stream: bool = True, timeout: Optional[int] = None) -> Generator[Any, None, None]:
    """
    Gửi message tới chat_session. Trả về generator các chunk nếu stream=True,
    nếu SDK không hỗ trợ stream thì trả về generator có một chunk chứa toàn bộ text.

    Args:
        chat_session: đối tượng session trả về từ start_chat_session
        prompt_parts: iterable các phần string (thường chỉ 1 phần user input)
        stream: nếu True, cố gắng stream (SDK có hỗ trợ)
        timeout: reserved (không bắt buộc)

    Yields:
        chunk objects (mỗi chunk mong chứa attribute .text hoặc key 'text')
    """
    # Gọi send_message trên chat_session; nhiều SDK hỗ trợ stream=True
    try:
        # Một số SDK expect list -> send_message(list, stream=True)
        result = chat_session.send_message(prompt_parts, stream=stream, timeout=timeout)  # type: ignore
        # Nếu result là generator -> return as-is
        if hasattr(result, "__iter__") and not isinstance(result, (str, bytes, dict)):
            # generator hoặc iterable
            for chunk in result:
                yield chunk
            return
        # Nếu result là object trả về 1 giá trị -> wrap thành generator
        # Có thể là dict hoặc object với .text
        class _SingleGen:
            def __init__(self, value):
                self.value = value
            def __iter__(self):
                yield self.value
        for chunk in _SingleGen(result):
            yield chunk
        return
    except TypeError as te:
        # Một số SDK không chấp nhận stream kwarg -> thử không stream
        logger.debug("send_message TypeError (try fallback non-stream): %s", te)
        try:
            resp = chat_session.send_message(prompt_parts, stream=False)  # type: ignore
            # Normalize response to chunk-like object
            text = None
            if isinstance(resp, dict):
                text = resp.get("text") or resp.get("message") or str(resp)
                yield {"text": text}
            else:
                text = getattr(resp, "text", None)
                if text is None:
                    text = str(resp)
                class Chunk:
                    def __init__(self, t): self.text = t
                yield Chunk(text)
            return
        except Exception as e:
            logger.exception("Fallback non-stream send_message failed: %s", e)
            raise
    except Exception as e:
        logger.exception("Lỗi khi gọi chat_session.send_message: %s", e)
        # Thay vì trực tiếp raise, yield một chunk chứa thông báo lỗi để phần gọi xử lý hiển thị
        try:
            yield {"text": f"[ERROR] Lỗi khi gửi tới model: {e}"}
        except Exception:
            # cuối cùng raise nếu không thể yield
            raise


def list_models() -> List[Dict[str, Any]]:
    """
    Trả về danh sách models có thể dùng. Mỗi entry là dict chứa ít nhất 'name' và optional 'description'.
    Nếu SDK không có hỗ trợ, trả về list rỗng.
    """
    try:
        genai = _import_genai()
    except ImportError:
        return []

    models = []
    try:
        # Ưu tiên genai.list_models() nếu có
        if hasattr(genai, "list_models"):
            for m in genai.list_models():
                # m có thể là object hoặc dict
                name = getattr(m, "name", None) or (m.get("name") if isinstance(m, dict) else None)
                desc = getattr(m, "description", None) or (m.get("description") if isinstance(m, dict) else "")
                models.append({"name": name, "description": desc})
        else:
            # fallback: không có list_models
            logger.debug("SDK không hỗ trợ list_models().")
    except Exception as e:
        logger.exception("Lỗi khi lấy danh sách models: %s", e)
    return models


def get_model_token_limit(model_name: str) -> int:
    """
    Trả về giới hạn token đầu vào (input token limit) của model nếu SDK cung cấp,
    nếu không biết thì sử dụng heuristic dựa trên tên model.
    """
    # Try SDK
    try:
        genai = _import_genai()
        if hasattr(genai, "get_model"):
            try:
                m = genai.get_model(model_name)
                # try attribute
                if hasattr(m, "input_token_limit") and getattr(m, "input_token_limit"):
                    return int(getattr(m, "input_token_limit"))
                # try dict-like
                if isinstance(m, dict) and "input_token_limit" in m:
                    return int(m["input_token_limit"])
            except Exception:
                # ignore and fallback to heuristics
                logger.debug("Không thể lấy model info từ SDK cho %s", model_name, exc_info=True)
    except ImportError:
        # SDK không cài -> fallback
        pass
    # Heuristic dựa trên tên
    name = (model_name or "").lower()
    if "flash" in name:
        return 1_000_000
    if "pro" in name:
        return 2_000_000
    if "gemini" in name:
        return 1_048_576
    # default
    return 1_048_576


# -------------------------
# Utility functions (optional helpers)
# -------------------------
def extract_text_from_chunk(chunk: Any) -> str:
    """
    Chuẩn hoá một chunk thành string:
    - Nếu chunk là dict và có 'text' key -> trả về value
    - Nếu chunk có attribute .text -> trả về
    - Nếu chunk có attribute .delta hoặc .message thì cũng thử
    - Ngược lại trả string(chunk)
    """
    if chunk is None:
        return ""
    try:
        if isinstance(chunk, dict):
            if "text" in chunk and chunk["text"] is not None:
                return str(chunk["text"])
            # một số SDK trả {'delta': {'content': '...'}}
            if "delta" in chunk:
                d = chunk["delta"]
                if isinstance(d, dict) and "content" in d:
                    return str(d["content"] or "")
            if "message" in chunk and chunk["message"] is not None:
                return str(chunk["message"])
            # fallback
            return str(chunk)
        # object-like
        if hasattr(chunk, "text"):
            return str(getattr(chunk, "text") or "")
        if hasattr(chunk, "content"):
            return str(getattr(chunk, "content") or "")
        if hasattr(chunk, "delta"):
            d = getattr(chunk, "delta")
            if isinstance(d, dict) and "content" in d:
                return str(d["content"] or "")
        # fallback generic
        return str(chunk)
    except Exception:
        # bảo toàn: trả string repr để không crash
        try:
            return str(chunk)
        except Exception:
            return ""


# End of src/api.py
