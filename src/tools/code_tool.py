# src/tools/code_tool.py
"""
Tool xử lý code: đọc file, tái cấu trúc (refactor), sinh tài liệu (document),
một số helper đơn giản.

Yêu cầu:
- Không import google.generativeai ở top-level (lazy import trong hàm).
- Giữ nguyên các hàm/logic để dễ tích hợp vào hệ thống hiện có.
- Trả về string (kết quả hoặc message lỗi) để CLI/handler in ra.
"""

from __future__ import annotations

import os
import json
import logging
from pathlib import Path
from typing import Optional

# relative import config (chạy từ src/)
from ..config import load_config

logger = logging.getLogger(__name__)


# -------------------------
# Helpers cơ bản
# -------------------------
def _read_file_text(path: str, encoding: str = "utf-8") -> str:
    """Đọc file text an toàn, trả về nội dung hoặc message bắt đầu bằng 'Error:' nếu lỗi."""
    try:
        p = Path(path)
        if not p.exists():
            return f"Error: File '{path}' không tồn tại."
        return p.read_text(encoding=encoding)
    except Exception as e:
        logger.exception("Lỗi đọc file %s: %s", path, e)
        return f"Error: Không đọc được file '{path}': {e}"


def _truncate_for_prompt(s: str, max_chars: int = 12000) -> str:
    """Nếu file quá dài, cắt bớt để tránh vượt giới hạn prompt."""
    if not s:
        return s
    if len(s) <= max_chars:
        return s
    # đơn giản: giữ phần đầu và cuối
    head = s[: max_chars // 2]
    tail = s[- (max_chars // 2) :]
    return head + "\n\n# --- [TRUNCATED] ---\n\n" + tail


def _safe_genai_import():
    """Lazy import google.generativeai, trả về module hoặc raise ImportError."""
    try:
        import google.generativeai as genai  # type: ignore
        return genai
    except Exception as e:
        logger.debug("Không thể import google.generativeai trong code_tool: %s", e, exc_info=True)
        raise ImportError("google.generativeai chưa cài. Vui lòng pip install google-generativeai.") from e


# -------------------------
# Các hàm tool public
# -------------------------
def refactor_code(file_path: str, model_name: Optional[str] = None, extra_instructions: Optional[str] = None) -> str:
    """
    Đọc file tại file_path và gửi prompt yêu cầu refactor code.
    Trả về text do model trả về, hoặc message lỗi nếu không thể thực hiện.

    Args:
        file_path: đường dẫn tới file code.
        model_name: override model (nếu None thì dùng config.default_model).
        extra_instructions: chuỗi thêm vào prompt (ví dụ: coding style).
    """
    # đọc file
    content = _read_file_text(file_path)
    if content.startswith("Error:"):
        return content

    config = load_config()
    model = model_name or config.get("default_model")

    # cắt bớt nội dung nếu quá dài
    code_for_prompt = _truncate_for_prompt(content, max_chars=12000)

    prompt_parts = [
        "Bạn là một lập trình viên chuyên nghiệp. Hãy tái cấu trúc (refactor) đoạn mã sau:",
        f"--- START OF FILE: {file_path} ---",
        "```",
        code_for_prompt,
        "```",
    ]
    if extra_instructions:
        prompt_parts.append("\nThêm yêu cầu: " + extra_instructions)

    try:
        genai = _safe_genai_import()
    except ImportError as ie:
        return f"Lỗi: {ie}"

    try:
        # sử dụng GenerativeModel nếu có
        if hasattr(genai, "GenerativeModel"):
            gm = genai.GenerativeModel(model)
            # tạo prompt đơn giản: kết hợp các phần
            prompt_text = "\n".join(prompt_parts)
            resp = gm.generate_content(prompt_text)
            # resp có thể có .text hoặc dict
            if hasattr(resp, "text"):
                return getattr(resp, "text") or ""
            if isinstance(resp, dict) and "text" in resp:
                return resp["text"] or ""
            return str(resp)
        else:
            # fallback: nếu SDK khác, thử gọi chat API
            if hasattr(genai, "chat"):
                chat_resp = genai.chat(model=model, prompt="\n".join(prompt_parts))
                # standardize
                if isinstance(chat_resp, dict):
                    return chat_resp.get("text") or chat_resp.get("message") or str(chat_resp)
                return str(chat_resp)
            return "Error: SDK không hỗ trợ phương thức để refactor code."
    except Exception as e:
        logger.exception("Lỗi khi gọi model refactor: %s", e)
        return f"Error khi gọi model refactor: {e}"


def document_code(file_path: str, model_name: Optional[str] = None, extra_instructions: Optional[str] = None) -> str:
    """
    Sinh tài liệu (documentation) cho file code tại file_path.
    Trả về string chứa doc hoặc message lỗi.
    """
    content = _read_file_text(file_path)
    if content.startswith("Error:"):
        return content

    config = load_config()
    model = model_name or config.get("default_model")
    code_for_prompt = _truncate_for_prompt(content, max_chars=12000)

    prompt_parts = [
        "Bạn là một lập trình viên kinh nghiệm và chuyên viết tài liệu code.",
        "Viết tài liệu ngắn gọn cho đoạn mã sau, bao gồm: mô tả chức năng, input, output, complexity nếu có, và ví dụ sử dụng ngắn:",
        f"--- START OF FILE: {file_path} ---",
        "```",
        code_for_prompt,
        "```",
    ]
    if extra_instructions:
        prompt_parts.append("\nThêm yêu cầu: " + extra_instructions)

    try:
        genai = _safe_genai_import()
    except ImportError as ie:
        return f"Lỗi: {ie}"

    try:
        if hasattr(genai, "GenerativeModel"):
            gm = genai.GenerativeModel(model)
            resp = gm.generate_content("\n".join(prompt_parts))
            if hasattr(resp, "text"):
                return getattr(resp, "text") or ""
            if isinstance(resp, dict) and "text" in resp:
                return resp["text"] or ""
            return str(resp)
        else:
            if hasattr(genai, "chat"):
                chat_resp = genai.chat(model=model, prompt="\n".join(prompt_parts))
                if isinstance(chat_resp, dict):
                    return chat_resp.get("text") or chat_resp.get("message") or str(chat_resp)
                return str(chat_resp)
            return "Error: SDK không hỗ trợ phương thức để document code."
    except Exception as e:
        logger.exception("Lỗi khi gọi model document: %s", e)
        return f"Error khi gọi model document: {e}"


# -------------------------
# Các hàm bổ trợ (nếu project cũ có dùng)
# -------------------------
def run_refactor_on_folder(folder_path: str, pattern: str = ".py", output_json: bool = False) -> str:
    """
    Duyệt folder, refactor từng file khớp pattern (mặc định .py).
    Trả về báo cáo JSON (string) nếu output_json True, hoặc text ngắn.
    LƯU Ý: hàm này có thể tốn thời gian, nên dùng thận trọng.
    """
    p = Path(folder_path)
    if not p.exists() or not p.is_dir():
        return f"Error: Folder '{folder_path}' không tồn tại."

    report = []
    for f in p.rglob(f"*{pattern}"):
        try:
            res = refactor_code(str(f))
            report.append({"file": str(f), "result_preview": (res[:200] + "...") if len(res) > 200 else res})
        except Exception as e:
            logger.exception("Lỗi refactor file %s: %s", f, e)
            report.append({"file": str(f), "error": str(e)})

    if output_json:
        try:
            return json.dumps(report, ensure_ascii=False, indent=2)
        except Exception:
            return str(report)
    else:
        lines = [f"Refactor report: {len(report)} files processed"]
        for r in report:
            if "error" in r:
                lines.append(f"- {r['file']}: ERROR {r['error']}")
            else:
                lines.append(f"- {r['file']}: OK (preview: {r['result_preview']})")
        return "\n".join(lines)


# Kết thúc file src/tools/code_tool.py
