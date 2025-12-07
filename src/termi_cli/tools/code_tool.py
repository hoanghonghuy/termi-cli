"""
Công cụ dành cho AI để tương tác với các file code,
như đọc, tái cấu trúc, hoặc viết tài liệu.
"""
import logging

from termi_cli.config import load_config
from termi_cli import api

logger = logging.getLogger(__name__)

def _get_code_from_file(file_path: str) -> str | None:
    """Hàm trợ giúp để đọc nội dung file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return f"Error: File not found at '{file_path}'"
    except Exception as e:
        return f"Error reading file: {str(e)}"

def refactor_code(file_path: str) -> str:
    """
    Phân tích và đề xuất các phương án tái cấu trúc (refactor) cho code trong một file.
    Args:
        file_path (str): Đường dẫn đến file code cần tái cấu trúc.
    Returns:
        str: Đoạn code đã được tái cấu trúc hoặc các đề xuất.
    """
    logger.info("--- TOOL: Đang đọc file để tái cấu trúc: %s ---", file_path)

    code_content = _get_code_from_file(file_path)
    if code_content.startswith("Error"):
        return code_content

    config = load_config()
    model_name = config.get("code_model") or config.get("default_model")
    
    prompt = (
        "You are a senior software architect. Refactor the following code so that it is cleaner, "
        "more efficient, and easier to maintain.\n"
        "Return ONLY the updated code inside a single code block and do not include any explanation.\n\n"
        f"```python\n{code_content}\n```"
    )
    
    logger.info("--- TOOL: Đang gửi yêu cầu tái cấu trúc tới AI ---")

    try:
        return api.generate_text(model_name, prompt)
    except (api.DeepseekInsufficientBalance, api.GroqInsufficientBalance):
        fallback_model = config.get("default_model")
        if fallback_model and fallback_model != model_name:
            logger.warning(
                "DeepSeek/Groq Insufficient Balance cho model '%s', fallback sang '%s' cho refactor_code.",
                model_name,
                fallback_model,
            )
            return api.generate_text(fallback_model, prompt)
        raise

def document_code(file_path: str) -> str:
    """
    Tự động viết tài liệu (docstrings, comments) cho code trong một file.
    Args:
        file_path (str): Đường dẫn đến file code cần viết tài liệu.
    Returns:
        str: Đoạn code đã được bổ sung tài liệu.
    """
    logger.info("--- TOOL: Đang đọc file để viết tài liệu: %s ---", file_path)

    code_content = _get_code_from_file(file_path)
    if code_content.startswith("Error"):
        return code_content

    config = load_config()
    model_name = config.get("code_model") or config.get("default_model")
    
    prompt = (
        "You are an experienced software engineer. Add documentation to the following code: "
        "docstrings for functions/classes and comments for complex logic.\n"
        "Follow common Python docstring conventions (for example Google style or reStructuredText for Python).\n"
        "Return ONLY the updated code inside a single code block and do not include any explanation.\n\n"
        f"```python\n{code_content}\n```"
    )

    logger.info("--- TOOL: Đang gửi yêu cầu viết tài liệu tới AI ---")

    try:
        return api.generate_text(model_name, prompt)
    except (api.DeepseekInsufficientBalance, api.GroqInsufficientBalance):
        fallback_model = config.get("default_model")
        if fallback_model and fallback_model != model_name:
            logger.warning(
                "DeepSeek/Groq Insufficient Balance cho model '%s', fallback sang '%s' cho document_code.",
                model_name,
                fallback_model,
            )
            return api.generate_text(fallback_model, prompt)
        raise