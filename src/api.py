"""
Mô-đun này chịu trách nhiệm quản lý tương tác với API của Google Gemini.
"""
import os
import google.generativeai as genai
from rich.table import Table
from rich.console import Console

_current_api_key_index = 0
_api_keys = []

# Import các tool và prompt builder
from .tools import web_search, database, calendar_tool, email_tool
from .tools import instruction_tool
from .tools import code_tool
from .prompts import build_enhanced_instruction

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
}

def configure_api(api_key: str):
    """Cấu hình API key."""
    genai.configure(api_key=api_key)

def get_available_models() -> list[str]:
    """Lấy danh sách các model name hỗ trợ generateContent."""
    models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    return models

def list_models(console: Console):
    """Liệt kê các model có sẵn."""
    table = Table(title="✨ Danh sách Models Gemini Khả Dụng ✨")
    table.add_column("Model Name", style="cyan", no_wrap=True)
    table.add_column("Description", style="magenta")
    console.print("Đang lấy danh sách models...")
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            table.add_row(m.name, m.description)
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

def send_message(chat_session: genai.ChatSession, prompt_parts: list):
    """
    Gửi message và trả về một generator để xử lý streaming.
    """
    response = chat_session.send_message(prompt_parts, stream=True)
    return response

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


def get_model_token_limit(model_name: str) -> int:
    """Lấy token limit của model."""
    try:
        model_info = genai.get_model(model_name)
        if hasattr(model_info, 'input_token_limit'):
            return model_info.input_token_limit
        # Fallback cho các model không có thông tin
        if 'flash' in model_name.lower():
            return 1000000  # Flash models thường có 1M tokens
        elif 'pro' in model_name.lower():
            return 2000000  # Pro models thường có 2M tokens
    except Exception:
        pass
    return 0


def initialize_api_keys():
    """Khởi tạo danh sách API keys từ .env"""
    global _api_keys
    _api_keys = []
    
    primary = os.getenv("GOOGLE_API_KEY")
    if primary:
        _api_keys.append(primary)
    
    # Thêm các key backup
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

def get_current_api_key():
    """Lấy API key hiện tại"""
    global _current_api_key_index, _api_keys
    if _current_api_key_index < len(_api_keys):
        return _api_keys[_current_api_key_index]
    return None

def switch_to_next_api_key():
    """Chuyển sang API key tiếp theo"""
    global _current_api_key_index, _api_keys
    _current_api_key_index += 1
    if _current_api_key_index < len(_api_keys):
        new_key = _api_keys[_current_api_key_index]
        configure_api(new_key)
        return True, f"Key #{_current_api_key_index + 1}"
    return False, "Hết API keys"