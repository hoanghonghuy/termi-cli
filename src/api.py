"""
Mô-đun này chịu trách nhiệm quản lý tương tác với API của Google Gemini.
"""
import os
import google.generativeai as genai
from rich.table import Table
from rich.console import Console

# Import các tool và prompt builder
from tools import web_search, database, calendar_tool, email_tool
from prompts import build_enhanced_instruction

# Ánh xạ tên tool tới hàm thực thi
AVAILABLE_TOOLS = {
    web_search.search_web.__name__: web_search.search_web,
    database.get_db_schema.__name__: database.get_db_schema,
    database.run_sql_query.__name__: database.run_sql_query,
    calendar_tool.list_events.__name__: calendar_tool.list_events,
    email_tool.search_emails.__name__: email_tool.search_emails,
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
        enhanced_instruction += f"\n\n**ADDITIONAL USER INSTRUCTION:**\n{system_instruction}"

    tools_config = list(AVAILABLE_TOOLS.values())
    
    model = genai.GenerativeModel(
        model_name, 
        system_instruction=enhanced_instruction,
        tools=tools_config
    )
    chat = model.start_chat(history=history or [])
    return chat

def send_message(chat_session: genai.ChatSession, prompt_parts: list):
    """Gửi message và xử lý function calling."""
    response = chat_session.send_message(prompt_parts, stream=False)
    
    while True:
        candidate = response.candidates[0]
        if not candidate.content or not candidate.content.parts:
            break

        function_calls = [part.function_call for part in candidate.content.parts if hasattr(part, 'function_call')]
        
        if not function_calls:
            break
            
        tool_responses = []
        for func_call in function_calls:
            if not func_call.name:
                continue

            tool_name = func_call.name
            tool_args = dict(func_call.args) if func_call.args else {}
            
            if tool_name in AVAILABLE_TOOLS:
                try:
                    tool_function = AVAILABLE_TOOLS[tool_name]
                    result = tool_function(**tool_args)
                except Exception as e:
                    result = f"Error executing tool '{tool_name}': {str(e)}"
            else:
                result = f"Error: Tool '{tool_name}' not found."
                
            tool_responses.append({
                "function_response": { "name": tool_name, "response": {"result": result} }
            })
        
        if not tool_responses:
            break

        response = chat_session.send_message(tool_responses)

    return response

