# src/termi_cli/handlers/core_handler.py

"""
Module chứa logic cốt lõi để xử lý một lượt hội thoại với AI,
bao gồm gọi tool, xử lý lỗi quota, và retry cho chế độ chat thông thường.
"""
import os
import json
import re
import argparse
from collections import namedtuple

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from google.api_core.exceptions import ResourceExhausted, PermissionDenied, InvalidArgument

from termi_cli import api
from termi_cli.config import load_config


def get_response_text_from_history(history_entry):
    """Trích xuất text từ một entry trong đối tượng history."""
    try:
        parts_to_check = []
        if isinstance(history_entry, list):
             parts_to_check = history_entry
        elif hasattr(history_entry, 'parts'):
             parts_to_check = history_entry.parts

        text_parts = [
            part.text
            for part in parts_to_check
            if hasattr(part, "text") and part.text
        ]
        return "".join(text_parts)
    except Exception:
        return ""


def accumulate_response_stream(response_stream):
    """
    Tích lũy text và function calls từ stream, có khả năng phân tích JSON tool call.
    """
    full_text = ""
    function_calls = []
    
    MockFunctionCall = namedtuple('MockFunctionCall', ['name', 'args'])

    try:
        for chunk in response_stream:
            if chunk.candidates:
                for part in chunk.candidates[0].content.parts:
                    if hasattr(part, 'function_call') and part.function_call:
                        function_calls.append(part.function_call)
                    
                    elif part.text:
                        cleaned_text = part.text.strip()
                        try:
                            if cleaned_text.startswith('{') and cleaned_text.endswith('}') and '"tool_name"' in cleaned_text:
                                json_match = re.search(r'\{.*\}', cleaned_text, re.DOTALL)
                                if json_match:
                                    json_str = json_match.group(0)
                                    data = json.loads(json_str)
                                    tool_name = data.get("tool_name", "").split(':')[-1]
                                    tool_args = data.get("tool_args", {})
                                    
                                    if tool_name:
                                        mock_call = MockFunctionCall(name=tool_name, args=tool_args)
                                        function_calls.append(mock_call)
                                    else:
                                        full_text += part.text
                                else:
                                    full_text += part.text
                            else:
                                full_text += part.text
                        except json.JSONDecodeError:
                            full_text += part.text
    except Exception as e:
        print(f"\n[bold red]Lỗi khi xử lý stream: {e}[/bold red]")
    return full_text, function_calls


def get_session_recreation_args(chat_session, args):
    """Hàm trợ giúp để lấy các tham số cần thiết để tạo lại session."""
    history_for_new_session = [c for c in chat_session.history if c.role != 'system']
    cli_help_text = args.cli_help_text if args and hasattr(args, 'cli_help_text') else ""
    
    config = load_config()
    saved_instructions = config.get("saved_instructions", [])
    system_instruction_str = "\n".join(f"- {item}" for item in saved_instructions)
    if args.system_instruction:
        system_instruction_str = args.system_instruction
    elif args.persona and config.get("personas", {}).get(args.persona):
        system_instruction_str = config["personas"][args.persona]
        
    return system_instruction_str, history_for_new_session, cli_help_text


def handle_conversation_turn(chat_session, prompt_parts, console: Console, model_name: str = None, args: argparse.Namespace = None):
    """
    Xử lý một lượt hội thoại với logic retry mạnh mẽ cho chế độ chat.
    """
    max_attempts = len(api._api_keys)
    attempt_count = 0

    while attempt_count < max_attempts:
        try:
            final_text_response = ""
            total_tokens = {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}
            tool_calls_log = []
            
            with console.status("[bold green]AI đang suy nghĩ...[/bold green]", spinner="dots") as status:
                # Gọi hàm send_message gốc (có stream)
                response_stream = api.send_message(chat_session, prompt_parts)
                text_chunk, function_calls = accumulate_response_stream(response_stream)
                
                try:
                    response_stream.resolve()
                    usage = api.get_token_usage(response_stream)
                    if usage:
                        for key in total_tokens:
                            total_tokens[key] += usage.get(key, 0)
                except Exception:
                    pass
                
                if text_chunk:
                    final_text_response += text_chunk

                while function_calls:
                    tool_responses = []
                    for func_call in function_calls:
                        tool_name = func_call.name
                        tool_args = dict(func_call.args) if func_call.args else {}
                        
                        status.update(f"[bold green]⚙️ Đang chạy tool [cyan]{tool_name}[/cyan]...[/bold green]")
                        
                        result = ""
                        if tool_name in api.AVAILABLE_TOOLS:
                            try:
                                tool_function = api.AVAILABLE_TOOLS[tool_name]
                                result = tool_function(**tool_args)
                            except Exception as e:
                                result = f"Error executing tool '{tool_name}': {str(e)}"
                        else:
                            result = f"Error: Tool '{tool_name}' not found."
                        
                        if isinstance(result, str) and result.startswith("USER_CONFIRMATION_REQUIRED:WRITE_FILE:"):
                            status.stop()
                            file_path_to_write = result.split(":", 2)[2]
                            
                            console.print(f"[bold yellow]⚠️ AI muốn ghi vào file '{file_path_to_write}'. Nội dung sẽ được ghi đè nếu file tồn tại.[/bold yellow]")
                            choice = console.input("Bạn có đồng ý không? [y/n]: ", markup=False).lower()

                            if choice == 'y':
                                try:
                                    content_to_write = tool_args.get('content', '')
                                    parent_dir = os.path.dirname(file_path_to_write)
                                    if parent_dir:
                                        os.makedirs(parent_dir, exist_ok=True)
                                    with open(file_path_to_write, 'w', encoding='utf-8') as f:
                                        f.write(content_to_write)
                                    result = f"Đã ghi thành công vào file '{file_path_to_write}'."
                                except Exception as e:
                                    result = f"Lỗi khi ghi file: {e}"
                            else:
                                result = "Người dùng đã từ chối hành động ghi file."
                            
                            status.start()
                            
                        tool_calls_log.append({
                            "name": tool_name,
                            "args": tool_args,
                            "result": str(result)
                        })
                        
                        tool_responses.append({
                            "function_response": {
                                "name": tool_name,
                                "response": {"result": result}
                            }
                        })

                    status.update("[bold green]AI đang xử lý kết quả từ tool...[/bold green]")
                    response_stream = api.send_message(chat_session, tool_responses)
                    text_chunk, function_calls = accumulate_response_stream(response_stream)
                    
                    try:
                        response_stream.resolve()
                        usage = api.get_token_usage(response_stream)
                        if usage:
                            for key in total_tokens:
                                total_tokens[key] += usage.get(key, 0)
                    except Exception:
                        pass
                    
                    if text_chunk:
                        final_text_response += "\n" + text_chunk

            output_format = args.format if args else 'rich'
            display_text = final_text_response.strip()

            if output_format == 'rich':
                console.print(Markdown(display_text))
            else:
                console.print(display_text)

            token_limit = api.get_model_token_limit(model_name)
            
            return final_text_response.strip(), total_tokens, token_limit, tool_calls_log
        
        except ResourceExhausted as e:
            attempt_count += 1
            console.print(f"\n[yellow]⚠️ Gặp lỗi Quota. Đang thử chuyển sang key tiếp theo... ({attempt_count}/{max_attempts})[/yellow]")
            success, msg = api.switch_to_next_api_key()
            if success:
                console.print(f"[green]✅ Đã chuyển sang {msg}. Đang tạo lại session...[/green]")
                chat_session = api.start_chat_session(
                    model_name, 
                    *get_session_recreation_args(chat_session, args)
                )
                continue
            else:
                console.print(f"[bold red]❌ {msg}. Đã hết API keys.[/bold red]")
                break
        except Exception as e:
            raise

    return "", {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}, 0, []