import os
import google.generativeai as genai
from rich.table import Table
from rich.console import Console
from datetime import datetime

# Import các tool
from tools import web_search, database, calendar_tool, email_tool

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
    models = []
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            models.append(m.name)
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


def start_chat_session(model_name: str, system_instruction: str = None, history: list = None):
    """Khởi tạo chat session với system instruction cải tiến, có nhận thức về bối cảnh."""
    
    current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    enhanced_instruction = f"""
You are a powerful AI assistant integrated into a command-line interface (CLI). Your goal is to be as helpful as possible to the user, a developer.
**CURRENT CONTEXT:**
- The current date and time is: {current_datetime}. Use this for any time-related questions.
**YOUR CAPABILITIES:**
You have two types of capabilities: Internal Tools (which you can call yourself) and External CLI Flags (which you must instruct the user on how to use).
**1. Internal Tools (Function Calling):**
- You can now see images directly if they are provided. Analyze them when the user asks.
- `search_web(query: str)`: Use this to find real-time, up-to-date information like news, stock prices, or weather.
- `get_db_schema()`: Inspects a local database to see its tables and columns.
- `run_sql_query(query: str)`: Executes a SELECT query on the database.
- `list_events(max_results: int)`: Lists upcoming events from the user's Google Calendar.
- `search_emails(query: str, max_results: int)`: Searches the user's Gmail.
**2. External CLI Flags (You CANNOT call these, but you MUST guide the user):**
If the user asks about a capability that matches one of these flags, you must instruct them on how to use the correct flag.
- To read and analyze code in the current directory, instruct the user to use the `--read-dir` flag.
- To automatically generate a Git commit message, instruct the user to use the `--git-commit` flag.
- To see chat history, instruct the user to use the `--history` flag.

**RESPONSE GUIDELINES:**
- Be proactive. If a tool fails (e.g., web search returns no results), try again with a different query.
- Be direct. Answer the user's question by synthesizing information.
- Be aware of your own limitations and guide the user on how to use the CLI's features to help you.
"""

    tools_config = [
        web_search.search_web,
        database.get_db_schema,
        database.run_sql_query,
        calendar_tool.list_events,
        email_tool.search_emails
    ]
    
    model = genai.GenerativeModel(
        model_name, 
        system_instruction=enhanced_instruction,
        tools=tools_config
    )
    chat = model.start_chat(history=history or [])
    return chat

def send_message(chat_session: genai.ChatSession, prompt_parts: list):
    """Gửi message và xử lý function calling (hỗ trợ nhiều tool song song)."""
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
            # Bỏ qua các yêu cầu tool không có tên
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
                "function_response": {
                    "name": tool_name,
                    "response": {"result": result}
                }
            })
        
        # Nếu không có tool response hợp lệ nào để gửi, hãy thoát vòng lặp
        if not tool_responses:
            break

        response = chat_session.send_message(tool_responses)

    return response