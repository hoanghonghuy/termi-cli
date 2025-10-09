"""
Công cụ dành cho AI để tương tác với các file code,
như đọc, tái cấu trúc, hoặc viết tài liệu.
"""
import google.generativeai as genai
from termi_cli.config import load_config
from termi_cli import api

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
    print(f"--- TOOL: Đang đọc file để tái cấu trúc: {file_path} ---")
    code_content = _get_code_from_file(file_path)
    if code_content.startswith("Error"):
        return code_content

    config = load_config()
    model = genai.GenerativeModel(config.get("default_model"))
    
    prompt = (
        "Với vai trò là một kiến trúc sư phần mềm chuyên nghiệp, hãy tái cấu trúc (refactor) đoạn code dưới đây để nó sạch hơn, hiệu quả hơn và dễ bảo trì hơn.\n"
        "Chỉ trả về phần code đã được cập nhật trong một khối mã duy nhất, không giải thích gì thêm.\n\n"
        f"```python\n{code_content}\n```"
    )
    
    print("--- TOOL: Đang gửi yêu cầu tái cấu trúc tới AI ---")
    # <-- SỬ DỤNG HÀM AN TOÀN -->
    response = api.safe_generate_content(model, prompt)
    return response.text

def document_code(file_path: str) -> str:
    """
    Tự động viết tài liệu (docstrings, comments) cho code trong một file.
    Args:
        file_path (str): Đường dẫn đến file code cần viết tài liệu.
    Returns:
        str: Đoạn code đã được bổ sung tài liệu.
    """
    print(f"--- TOOL: Đang đọc file để viết tài liệu: {file_path} ---")
    code_content = _get_code_from_file(file_path)
    if code_content.startswith("Error"):
        return code_content

    config = load_config()
    model = genai.GenerativeModel(config.get("default_model"))
    
    prompt = (
        "Với vai trò là một lập trình viên kinh nghiệm, hãy viết tài liệu (docstrings cho hàm/class và comment cho các logic phức tạp) cho đoạn code dưới đây.\n"
        "Hãy tuân thủ các chuẩn viết docstring phổ biến (ví dụ: Google Style hoặc reStructuredText cho Python).\n"
        "Chỉ trả về phần code đã được cập nhật trong một khối mã duy nhất, không giải thích gì thêm.\n\n"
        f"```python\n{code_content}\n```"
    )

    print("--- TOOL: Đang gửi yêu cầu viết tài liệu tới AI ---")
    response = api.safe_generate_content(model, prompt)
    return response.text