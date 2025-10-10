"""
Mô-đun này chịu trách nhiệm quản lý tương tác với API của Google Gemini,
bao gồm cả cơ chế xử lý lỗi Quota mạnh mẽ.
"""
import os
import time
import re
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted
from rich.table import Table
from rich.console import Console

# Import các module con một cách an toàn
from termi_cli.tools import web_search, database, calendar_tool, email_tool, file_system_tool, shell_tool
from termi_cli.tools import instruction_tool
from termi_cli.tools import code_tool
from termi_cli.prompts import build_enhanced_instruction

_current_api_key_index = 0
_api_keys = []
_console = Console() # Console riêng cho module này

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

def configure_api(api_key: str):
    """Cấu hình API key ban đầu."""
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

def _switch_to_next_api_key():
    """Hàm nội bộ để chuyển sang API key tiếp theo và quay vòng."""
    global _current_api_key_index, _api_keys
    _current_api_key_index = (_current_api_key_index + 1) % len(_api_keys)
    new_key = _api_keys[_current_api_key_index]
    genai.configure(api_key=new_key)
    return f"Key #{_current_api_key_index + 1}"

def _resilient_api_call(api_function, *args, **kwargs):
    """
    Hàm bọc "bất tử" cho mọi lệnh gọi API, tự động xử lý lỗi Quota.
    """
    initial_key_index = _current_api_key_index
    max_rpm_retries = 3 # Số lần thử lại tối đa cho lỗi RPM với CÙNG MỘT KEY
    
    while True:
        rpm_retry_count = 0
        try:
            while rpm_retry_count < max_rpm_retries:
                try:
                    return api_function(*args, **kwargs)
                except ResourceExhausted as e:
                    error_message = str(e)
                    if (match := re.search(r"Please retry in (\d+\.\d+)s", error_message)):
                        rpm_retry_count += 1
                        wait_time = float(match.group(1)) + 1
                        with _console.status(f"[yellow]⏳ Lỗi tốc độ (RPM). Chờ {wait_time:.1f}s (thử lại {rpm_retry_count}/{max_rpm_retries})...[/yellow]", spinner="clock"):
                            time.sleep(wait_time)
                    else:
                        raise e # Ném ra ngoài nếu không phải lỗi RPM
            
            # Nếu hết số lần thử lại RPM, ném lỗi ra để chuyển key
            raise ResourceExhausted("Hết số lần thử lại cho lỗi RPM. Đang chuyển key.")

        except ResourceExhausted as e:
            _console.print(f"[yellow]⚠️ Gặp lỗi Quota với Key #{_current_api_key_index + 1}. Đang chuyển sang key tiếp theo...[/yellow]")
            msg = _switch_to_next_api_key()

            if _current_api_key_index == initial_key_index:
                _console.print("[bold red]❌ Đã thử tất cả các API key nhưng đều gặp lỗi Quota.[/bold red]")
                raise e
            
            _console.print(f"[green]✅ Đã chuyển sang {msg}. Thử lại...[/green]")
            # Ném một exception đặc biệt để báo cho logic cấp cao hơn biết cần phải tái tạo session
            raise RPDQuotaExhausted("API key changed.")

        except Exception as e:
            _console.print(f"[bold red]Lỗi không mong muốn khi gọi API: {e}[/bold red]")
            raise e

# Định nghĩa một exception tùy chỉnh
class RPDQuotaExhausted(Exception):
    pass

# Các hàm public để gọi từ bên ngoài
def resilient_generate_content(model: genai.GenerativeModel, prompt: str):
    return _resilient_api_call(model.generate_content, prompt)

def resilient_send_message(chat_session: genai.ChatSession, prompt):
    return _resilient_api_call(chat_session.send_message, prompt)