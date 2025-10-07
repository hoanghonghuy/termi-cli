import os
import sys
import json
import glob
import re
import argparse
from datetime import datetime
import subprocess
from collections import namedtuple

from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted, PermissionDenied, InvalidArgument
from rich.panel import Panel
from rich.markup import escape

from . import api
from . import utils
from .config import save_config, load_config
from .prompts import build_agent_instruction
from .tools import file_system_tool

# --- CONSTANTS ---
HISTORY_DIR = "chat_logs"


# --- HELPER FUNCTIONS ---
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


def print_formatted_history(console: Console, history: list):
    """In lịch sử trò chuyện đã tải ra màn hình."""
    console.print("\n--- [bold yellow]LỊCH SỬ TRÒ CHUYỆN[/bold yellow] ---")
    for item in history:
        role = item.get("role", "unknown")
        text_parts = [p.get("text", "") for p in item.get("parts", []) if p.get("text")]
        text = "".join(text_parts).strip()
        if not text:
            continue
        if role == "user":
            console.print(f"\n[bold cyan]You:[/bold cyan] {text}")
        elif role == "model":
            console.print(f"\n[bold magenta]AI:[/bold magenta]")
            console.print(Markdown(text))
    console.print("\n--- [bold yellow]KẾT THÚC LỊCH SỬ[/bold yellow] ---\n")


def serialize_history(history):
    """Chuyển đổi history thành format JSON có thể serialize một cách an toàn."""
    serializable = []
    for content in history:
        content_dict = {"role": content.role, "parts": []}
        for part in content.parts:
            part_dict = {}
            if hasattr(part, "text") and part.text is not None:
                part_dict["text"] = part.text
            elif hasattr(part, "function_call") and part.function_call is not None:
                part_dict["function_call"] = {
                    "name": part.function_call.name,
                    "args": dict(part.function_call.args),
                }
            elif (
                hasattr(part, "function_response")
                and part.function_response is not None
            ):
                part_dict["function_response"] = {
                    "name": part.function_response.name,
                    "response": dict(part.function_response.response),
                }
            if part_dict:
                content_dict["parts"].append(part_dict)
        if content_dict["parts"]:
            serializable.append(content_dict)
    return serializable


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
    Xử lý một lượt hội thoại với logic retry mạnh mẽ, ưu tiên xử lý lỗi model trước lỗi quota.
    """
    FALLBACK_MODEL = "models/gemini-flash-latest"
    
    current_model_name = model_name
    attempt_count = 0
    max_attempts = len(api._api_keys)
    tool_calls_log = []

    while attempt_count < max_attempts:
        try:
            final_text_response = ""
            total_tokens = {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}
            
            with console.status("[bold green]AI đang suy nghĩ...[/bold green]", spinner="dots") as status:
                response_stream = api.send_message(chat_session, prompt_parts)
                text_chunk, function_calls = accumulate_response_stream(response_stream)
                
                try:
                    response_stream.resolve()
                    usage = api.get_token_usage(response_stream)
                    if usage:
                        for key in total_tokens:
                            total_tokens[key] += usage[key]
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
                            "result": str(result) # Chuyển kết quả thành chuỗi để đảm bảo an toàn
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
                                total_tokens[key] += usage[key]
                    except Exception:
                        pass
                    
                    if text_chunk:
                        final_text_response += "\n" + text_chunk

            output_format = args.format if args else 'rich'
            persona = args.persona if args else None
            display_text = final_text_response.strip()

            if persona == 'python_dev' and display_text and not display_text.startswith('```'):
                display_text = f"```python\n{display_text}\n```"

            if output_format == 'rich':
                console.print(Markdown(display_text))
            else:
                console.print(display_text)

            token_limit = api.get_model_token_limit(current_model_name)
            
            return final_text_response.strip(), total_tokens, token_limit, tool_calls_log
        
        except (ResourceExhausted, PermissionDenied, InvalidArgument) as e:
            is_preview_model = "preview" in current_model_name or "exp" in current_model_name
            
            if isinstance(e, PermissionDenied) or (is_preview_model and isinstance(e, (ResourceExhausted, InvalidArgument))):
                if current_model_name == FALLBACK_MODEL:
                    console.print(f"[bold red]❌ Lỗi nghiêm trọng:[/bold red] Ngay cả model dự phòng [cyan]'{FALLBACK_MODEL}'[/cyan] cũng không thể truy cập. Vui lòng kiểm tra lại API key.")
                    break

                console.print(f"[bold yellow]⚠️ Cảnh báo:[/bold yellow] Không có quyền truy cập model [cyan]'{current_model_name}'[/cyan].")
                console.print(f"[green]🔄 Tự động chuyển sang model ổn định [cyan]'{FALLBACK_MODEL}'[/cyan] và thử lại...[/green]")
                
                current_model_name = FALLBACK_MODEL
                args.model = FALLBACK_MODEL
                
                chat_session = api.start_chat_session(
                    current_model_name, 
                    *get_session_recreation_args(chat_session, args)
                )
                continue
            
            elif isinstance(e, ResourceExhausted):
                attempt_count += 1
                if attempt_count < max_attempts:
                    success, msg = api.switch_to_next_api_key()
                    if success:
                        console.print(f"\n[yellow]⚠ Hết quota! Đã chuyển sang API {msg}. Đang thử lại...[/yellow]")
                        chat_session = api.start_chat_session(
                            current_model_name, 
                            *get_session_recreation_args(chat_session, args)
                        )
                        continue
                
            elif "API key not valid" in str(e):
                 console.print(f"[bold red]❌ Lỗi API Key:[/bold red] Key đang sử dụng không hợp lệ hoặc đã hết hạn.")
                 break
            
            else:
                raise e
        except Exception as e:
            raise

    if attempt_count >= max_attempts:
        console.print(f"\n[bold red]❌ Đã thử hết {max_attempts} API key(s). Tất cả đều hết quota.[/bold red]")
    
    return "", {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}, 0, []


def model_selection_wizard(console: Console, config: dict):
    console.print("[bold green]Đang lấy danh sách các model khả dụng...[/bold green]")
    try:
        models = api.get_available_models()
        if not models:
            console.print("[bold red]Không tìm thấy model nào khả dụng.[/bold red]")
            return
    except Exception as e:
        console.print(f"[bold red]Lỗi khi lấy danh sách model: {e}[/bold red]")
        return

    table = Table(title="Chọn một model để làm mặc định")
    table.add_column("#", style="cyan")
    table.add_column("Model Name", style="magenta")
    stable_models = sorted([m for m in models if "preview" not in m and "exp" not in m])
    preview_models = sorted([m for m in models if "preview" in m or "exp" in m])
    sorted_models = stable_models + preview_models
    for i, model_name in enumerate(sorted_models):
        table.add_row(str(i + 1), model_name)
    console.print(table)

    while True:
        try:
            choice_str = console.input("Nhập số thứ tự của model bạn muốn chọn: ", markup=False)
            choice = int(choice_str) - 1
            if 0 <= choice < len(sorted_models):
                selected_model = sorted_models[choice]
                config["default_model"] = selected_model
                fallback_list = [selected_model]
                for m in stable_models:
                    if m != selected_model and m not in fallback_list:
                        fallback_list.append(m)
                config["model_fallback_order"] = fallback_list
                save_config(config)
                console.print(
                    f"\n[bold green]✅ Đã đặt model mặc định là: [cyan]{selected_model}[/cyan][/bold green]"
                )
                console.print(
                    f"[yellow]Thứ tự model dự phòng đã được cập nhật.[/yellow]"
                )
                break
            else:
                console.print(
                    "[bold red]Lựa chọn không hợp lệ, vui lòng thử lại.[/bold red]"
                )
        except ValueError:
            console.print("[bold red]Vui lòng nhập một con số.[/bold red]")
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Đã hủy lựa chọn.[/yellow]")
            break


def run_chat_mode(chat_session, console: Console, config: dict, args: argparse.Namespace):
    console.print("[bold green]Đã vào chế độ trò chuyện. Gõ 'exit' hoặc 'quit' để thoát.[/bold green]")
    initial_save_path = None
    if args.topic:
        initial_save_path = os.path.join(HISTORY_DIR, f"chat_{utils.sanitize_filename(args.topic)}.json")
    elif args.load:
        initial_save_path = args.load
        
    try:
        while True:
            prompt = console.input("\n[bold cyan]You:[/bold cyan] ")
            if prompt.lower().strip() in ["exit", "quit", "q"]: break
            if not prompt.strip(): continue

            console.print("\n[bold magenta]AI:[/bold magenta]")
            try:
                response_text, token_usage, token_limit = handle_conversation_turn(
                    chat_session, [prompt], console, 
                    model_name=args.model or config.get("default_model"),
                    args=args
                )
                
                if token_usage and token_usage['total_tokens'] > 0:
                    if token_limit > 0:
                        console.print(f"[dim]📊 {token_usage['total_tokens']:,} / {token_limit:,} tokens[/dim]")
                    else:
                        console.print(f"[dim]📊 {token_usage['total_tokens']:,} tokens[/dim]")
            except Exception as e:
                console.print(f"[bold red]Lỗi: {e}[/bold red]")
                continue
            
            utils.execute_suggested_commands(response_text, console)
    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]Đã dừng bởi người dùng.[/yellow]")
    finally:
        if not os.path.exists(HISTORY_DIR):
            os.makedirs(HISTORY_DIR)
        save_path = initial_save_path
        title = ""
        if save_path:
            try:
                with open(save_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    title = data.get("title", os.path.basename(save_path))
            except (FileNotFoundError, json.JSONDecodeError):
                title = args.topic or os.path.splitext(os.path.basename(save_path))[
                    0
                ].replace("chat_", "")
        else:
            try:
                try:
                    history_len = len(chat_session.history)
                except Exception:
                    console.print("\n[yellow]Không thể lưu lịch sử do phiên chat chưa hoàn tất.[/yellow]")
                    return
                
                initial_len = 0
                if args.load or args.topic:
                    try:
                        with open(args.load or initial_save_path, 'r', encoding='utf-8') as f:
                            initial_data = json.load(f)
                            initial_len = len(initial_data.get("history", []))
                    except (FileNotFoundError, TypeError, json.JSONDecodeError):
                        initial_len = 0

                if history_len <= initial_len:
                    console.print("\n[yellow]Không có nội dung mới để lưu.[/yellow]")
                    return

                user_title = console.input(
                    "\n[bold yellow]Lưu cuộc trò chuyện với tên (bỏ trống để AI tự đặt tên): [/bold yellow]"
                ).strip()
                if user_title:
                    title = user_title
                else:
                    console.print(
                        "[cyan]AI đang nghĩ tên cho cuộc trò chuyện...[/cyan]"
                    )
                    
                    conversation_summary = ""
                    for content in chat_session.history:
                        if content.role == 'user':
                            conversation_summary += f"User: {get_response_text_from_history(content)}\n"
                        elif content.role == 'model':
                            conversation_summary += f"AI: {get_response_text_from_history(content)}\n"

                    prompt_for_title = (
                        "Based on the following full conversation transcript, create a very short, "
                        "descriptive title (under 7 words) that captures the main topic. "
                        "Return only the title itself, with no quotes.\n\n"
                        f"--- CONVERSATION ---\n{conversation_summary}"
                    )

                    title_chat = genai.GenerativeModel(
                        config.get("default_model")
                    ).start_chat()
                    response = title_chat.send_message(prompt_for_title)
                    title = response.text.strip().replace('"', "")

                filename = f"chat_{utils.sanitize_filename(title)}.json"
                save_path = os.path.join(HISTORY_DIR, filename)
            except (KeyboardInterrupt, EOFError):
                console.print("\n[yellow]Không lưu cuộc trò chuyện.[/yellow]")
                return
        if save_path and title:
            try:
                history_data = {
                    "title": title,
                    "last_modified": datetime.now().isoformat(),
                    "history": serialize_history(chat_session.history),
                }
                with open(save_path, "w", encoding="utf-8") as f:
                    json.dump(history_data, f, indent=2, ensure_ascii=False)
                console.print(
                    f"\n[bold yellow]Lịch sử trò chuyện đã được lưu vào '{save_path}'.[/bold yellow]"
                )
            except Exception as e:
                console.print(f"\n[yellow]Không thể lưu lịch sử: {e}[/yellow]")

def show_history_browser(console: Console):
    console.print(
        f"[bold green]Đang quét các file lịch sử trong `{HISTORY_DIR}/`...[/bold green]"
    )
    if not os.path.exists(HISTORY_DIR):
        console.print(
            f"[yellow]Thư mục '{HISTORY_DIR}' không tồn tại. Chưa có lịch sử nào được lưu.[/yellow]"
        )
        return None
    history_files = glob.glob(os.path.join(HISTORY_DIR, "*.json"))
    if not history_files:
        console.print("[yellow]Không tìm thấy file lịch sử nào.[/yellow]")
        return None
    history_metadata = []
    for file_path in history_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                title = data.get("title", os.path.basename(file_path))
                last_modified_iso = data.get(
                    "last_modified",
                    datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat(),
                )
                history_metadata.append(
                    {
                        "title": title,
                        "last_modified": last_modified_iso,
                        "file_path": file_path,
                    }
                )
        except Exception:
            continue
    history_metadata.sort(key=lambda x: x["last_modified"], reverse=True)
    table = Table(title="📚 Lịch sử Trò chuyện")
    table.add_column("#", style="cyan")
    table.add_column("Chủ Đề Trò Chuyện", style="magenta")
    table.add_column("Lần Cập Nhật Cuối", style="green")
    for i, meta in enumerate(history_metadata):
        mod_time_str = datetime.fromisoformat(meta["last_modified"]).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        table.add_row(str(i + 1), meta["title"], mod_time_str)
    console.print(table)
    try:
        choice_str = console.input(
            "Nhập số để tiếp tục cuộc trò chuyện (nhấn Enter để thoát): ",
            markup=False
        )
        if not choice_str:
            console.print("[yellow]Đã thoát trình duyệt lịch sử.[/yellow]")
            return None
        choice = int(choice_str)
        if 1 <= choice <= len(history_metadata):
            selected_file = history_metadata[choice - 1]["file_path"]
            console.print(
                f"\n[green]Đang tải lại cuộc trò chuyện: '{history_metadata[choice - 1]['title']}'...[/green]"
            )
            return selected_file
        else:
            console.print("[yellow]Lựa chọn không hợp lệ.[/yellow]")
    except (ValueError, KeyboardInterrupt, EOFError):
        console.print("\n[yellow]Đã thoát trình duyệt lịch sử.[/yellow]")
    return None


def handle_history_summary(
    console: Console, config: dict, history: list, cli_help_text: str
):
    console.print(
        "\n[bold yellow]Đang yêu cầu AI tóm tắt cuộc trò chuyện...[/bold yellow]"
    )
    history_text = ""
    for item in history:
        role = "User" if item.get("role") == "user" else "AI"
        text = "".join(
            p.get("text", "") for p in item.get("parts", []) if p.get("text")
        ).strip()
        if text:
            history_text += f"{role}: {text}\n"

    if not history_text:
        console.print("[yellow]Lịch sử trống, không có gì để tóm tắt.[/yellow]")
        return

    prompt = (
        "Dưới đây là một cuộc trò chuyện đã được lưu. "
        "Hãy đọc và tóm tắt lại nội dung chính của nó trong vài gạch đầu dòng ngắn gọn.\n\n"
        f"--- NỘI DUNG CUỘC TRÒ CHUYỆN ---\n{history_text}---\n\n"
        "Tóm tắt của bạn:"
    )

    try:
        model_name = config.get("default_model")
        chat_session = api.start_chat_session(
            model_name,
            "You are a helpful summarizer.",
            history=[],
            cli_help_text=cli_help_text,
        )

        console.print("\n[bold green]📝 Tóm Tắt Cuộc Trò Chuyện:[/bold green] ")
        handle_conversation_turn(chat_session, [prompt], console, args=argparse.Namespace(persona=None, format='rich', cli_help_text=cli_help_text))

    except Exception as e:
        console.print(f"[bold red]Lỗi khi tóm tắt lịch sử: {e}[/bold red]")


# --- Handlers for custom instructions ---
def add_instruction(console: Console, config: dict, instruction: str):
    if "saved_instructions" not in config:
        config["saved_instructions"] = []
    if instruction not in config["saved_instructions"]:
        config["saved_instructions"].append(instruction)
        save_config(config)
        console.print(
            f"[bold green]✅ Đã thêm chỉ dẫn mới:[/bold green] '{instruction}'"
        )
    else:
        console.print(f"[yellow]Chỉ dẫn đã tồn tại.[/yellow]")


def list_instructions(console: Console, config: dict):
    instructions = config.get("saved_instructions", [])
    if not instructions:
        console.print("[yellow]Không có chỉ dẫn tùy chỉnh nào được lưu.[/yellow]")
        return

    table = Table(title="📝 Các Chỉ Dẫn Tùy Chỉnh Đã Lưu")
    table.add_column("#", style="cyan")
    table.add_column("Chỉ Dẫn", style="magenta")
    for i, instruction in enumerate(instructions):
        table.add_row(str(i + 1), instruction)
    console.print(table)


def remove_instruction(console: Console, config: dict, index: int):
    instructions = config.get("saved_instructions", [])
    if not 1 <= index <= len(instructions):
        console.print(
            f"[bold red]Lỗi: Index không hợp lệ. Vui lòng chọn số từ 1 đến {len(instructions)}.[/bold red]"
        )
        return

    removed_instruction = instructions.pop(index - 1)
    config["saved_instructions"] = instructions
    save_config(config)
    console.print(
        f"[bold green]✅ Đã xóa chỉ dẫn:[/bold green] '{removed_instruction}'"
    )

# --- Handlers for persona ---
def add_persona(console: Console, config: dict, name: str, instruction: str):
    """Thêm một persona mới vào config."""
    if "personas" not in config:
        config["personas"] = {}
    
    config["personas"][name] = instruction
    save_config(config)
    console.print(f"[bold green]✅ Đã lưu persona [cyan]'{name}'[/cyan].[/bold green]")

def list_personas(console: Console, config: dict):
    """Liệt kê các persona đã lưu."""
    personas = config.get("personas", {})
    if not personas:
        console.print("[yellow]Không có persona nào được lưu.[/yellow]")
        return

    table = Table(title="🎭 Các Persona Đã Lưu")
    table.add_column("Tên Persona", style="cyan")
    table.add_column("Chỉ Dẫn Hệ Thống", style="magenta")
    for name, instruction in personas.items():
        table.add_row(name, instruction)
    console.print(table)

def remove_persona(console: Console, config: dict, name: str):
    """Xóa một persona theo tên."""
    personas = config.get("personas", {})
    if name not in personas:
        console.print(f"[bold red]Lỗi: Không tìm thấy persona có tên '{name}'.[/bold red]")
        return

    removed_instruction = personas.pop(name)
    config["personas"] = personas
    save_config(config)
    console.print(f"[bold green]✅ Đã xóa persona [cyan]'{name}'[/cyan].[/bold green]")
    
def run_agent_mode(console: Console, args: argparse.Namespace):
    """
    Chạy chế độ Agent tự trị, quản lý vòng lặp ReAct và xử lý lỗi một cách độc lập.
    """
    console.print(Panel(f"[bold green]🤖 Chế Độ Agent Đã Kích Hoạt 🤖[/bold green]\n[yellow]Mục tiêu:[/yellow] {args.prompt}", border_style="blue"))

    agent_instruction = build_agent_instruction()
    chat_session = api.start_chat_session(
        model_name=args.model,
        system_instruction=agent_instruction
    )

    current_prompt_parts = [{"text": args.prompt}]
    max_steps = 10
    
    for step in range(max_steps):
        console.print(f"\n[bold]--- Vòng {step + 1}/{max_steps} ---[/bold]")
        
        response_text = ""
        for _ in range(2):
            try:
                with console.status("[magenta]🧠 Agent đang suy nghĩ...[/magenta]"):
                    response_stream = api.send_message(chat_session, current_prompt_parts)
                    response_text = ""
                    for chunk in response_stream:
                        if chunk.candidates:
                            for part in chunk.candidates[0].content.parts:
                                if part.text:
                                    response_text += part.text
                if response_text.strip():
                    break
                console.print("[yellow]Cảnh báo: AI trả về phản hồi trống, đang thử lại...[/yellow]")
            except Exception as e:
                console.print(f"[bold red]Lỗi khi giao tiếp với AI: {e}[/bold red]")
                return

        if not response_text.strip():
            console.print("[bold red]Lỗi: AI liên tục trả về phản hồi trống. Đang dừng Agent.[/bold red]")
            return

        try:
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL)
            if not json_match:
                json_match = re.search(r'(\{.*?\})', response_text, re.DOTALL)
            
            if not json_match:
                console.print("[bold red]Lỗi: AI không trả về định dạng JSON hợp lệ. Đang dừng Agent.[/bold red]")
                console.print(f"Phản hồi thô:\n{response_text}")
                break

            json_str = json_match.group(1)
            
            def escape_newlines(match):
                return match.group(0).replace('\n', '\\n')
            json_str_fixed = re.sub(r'"[^"]*"', escape_newlines, json_str)

            plan = json.loads(json_str_fixed)
            thought = plan.get("thought")
            action = plan.get("action")
            
            if not thought or not action:
                raise ValueError("Phản hồi JSON thiếu 'thought' hoặc 'action'.")

            console.print(Panel(f"[cyan]🤔 Suy nghĩ:[/cyan] {thought}", title="[bold magenta]Kế Hoạch Của Agent[/bold magenta]", border_style="magenta"))

            tool_name_raw = action.get("tool_name", "")
            tool_name = tool_name_raw.split(':')[-1]
            
            tool_args = action.get("tool_args", {})

            if tool_name == "finish":
                final_answer = tool_args.get("answer", "Nhiệm vụ đã hoàn thành.")
                console.print(Panel(Markdown(final_answer), title="[bold green]✅ Nhiệm Vụ Hoàn Thành[/bold green]", border_style="green"))
                break

            if tool_name in api.AVAILABLE_TOOLS:
                console.print(f"[yellow]🎬 Hành động:[/yellow] Gọi tool [bold cyan]{tool_name}[/bold cyan] với tham số {tool_args}")
                tool_function = api.AVAILABLE_TOOLS[tool_name]
                
                observation = ""
                if tool_name == 'write_file':
                    confirm_choice = console.input(f"  [bold yellow]⚠️ AI muốn ghi vào file '{tool_args.get('path')}'. Đồng ý? [y/n]: [/bold yellow]", markup=True).lower()
                    if confirm_choice != 'y':
                        observation = "User denied the file write operation."
                    else:
                        try:
                            content_to_write = tool_args.get('content', '')
                            path_to_write = tool_args.get('path')
                            parent_dir = os.path.dirname(path_to_write)
                            if parent_dir: os.makedirs(parent_dir, exist_ok=True)
                            with open(path_to_write, 'w', encoding='utf-8') as f: f.write(content_to_write)
                            observation = f"Successfully wrote to file '{path_to_write}'."
                        except Exception as e:
                            observation = f"Error writing to file: {e}"
                else:
                    with console.status(f"[green]Đang chạy tool {tool_name}...[/green]"):
                        observation = tool_function(**tool_args)
                
                display_observation = observation
                lines = observation.splitlines()
                if len(lines) > 20:
                    display_observation = "\n".join(lines[:20]) + "\n\n[dim]... (nội dung quá dài, đã được rút gọn) ...[/dim]"
                
                safe_display = escape(display_observation)
                console.print(Panel(f"[bold blue]👀 Quan sát:[/bold blue]\n{safe_display}", title="[bold blue]Kết Quả Tool[/bold blue]", border_style="blue", expand=False))
                
                current_prompt_parts = [{"text": f"This was the result of your last action:\n\n{observation}\n\nBased on this, what is your next thought and action to achieve the original objective: '{args.prompt}'?"}]
            else:
                console.print(f"[bold red]Lỗi: AI cố gắng gọi một tool không tồn tại: {tool_name_raw}[/bold red]")
                break

        except (json.JSONDecodeError, ValueError) as e:
            console.print(f"[bold red]Lỗi khi phân tích phản hồi của Agent: {e}[/bold red]")
            console.print(f"Phản hồi thô:\n{response_text}")
            break
        except Exception as e:
            console.print(f"[bold red]Đã xảy ra lỗi không mong muốn trong vòng lặp Agent: {e}[/bold red]")
            break
    else:
        console.print(f"[bold yellow]⚠️ Agent đã đạt đến giới hạn {max_steps} bước và sẽ tự động dừng lại.[/bold yellow]")