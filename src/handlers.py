import os
import sys
import json
import glob
import re
import argparse
from datetime import datetime
import subprocess

from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted

import api
import utils
from config import save_config

# --- CONSTANTS ---
HISTORY_DIR = "chat_logs"

# --- HELPER FUNCTIONS ---
def get_response_text(response: genai.types.GenerateContentResponse) -> str:
    """Trích xuất tất cả nội dung text từ một response một cách an toàn."""
    try:
        return response.text
    except Exception:
        text_parts = [part.text for part in response.parts if hasattr(part, 'text') and part.text]
        return "".join(text_parts)

def print_formatted_history(console: Console, history: list):
    """In lịch sử trò chuyện đã tải ra màn hình."""
    console.print("\n--- [bold yellow]LỊCH SỬ TRÒ CHUYỆN[/bold yellow] ---")
    for item in history:
        role = item.get('role', 'unknown')
        text_parts = [p.get('text', '') for p in item.get('parts', []) if p.get('text')]
        text = "".join(text_parts).strip()
        if not text: continue
        if role == 'user':
            console.print(f"\n[bold cyan]You:[/bold cyan] {text}")
        elif role == 'model':
            console.print(f"\n[bold magenta]AI:[/bold magenta]")
            console.print(Markdown(text))
    console.print("\n--- [bold yellow]KẾT THÚC LỊCH SỬ[/bold yellow] ---\n")

def serialize_history(history):
    """
    Chuyển đổi history thành format JSON có thể serialize một cách an toàn.
    Sửa lỗi "to_dict" và lỗi lưu object bằng cách xây dựng thủ công.
    """
    serializable = []
    for content in history:
        content_dict = {'role': content.role, 'parts': []}
        for part in content.parts:
            part_dict = {}
            if hasattr(part, 'text') and part.text is not None:
                part_dict['text'] = part.text
            elif hasattr(part, 'function_call') and part.function_call is not None:
                part_dict['function_call'] = {
                    'name': part.function_call.name,
                    'args': dict(part.function_call.args)
                }
            elif hasattr(part, 'function_response') and part.function_response is not None:
                part_dict['function_response'] = {
                    'name': part.function_response.name,
                    'response': dict(part.function_response.response)
                }
            
            if part_dict:
                content_dict['parts'].append(part_dict)
        
        if content_dict['parts']:
            serializable.append(content_dict)
            
    return serializable

# --- COMMAND HANDLERS ---
def model_selection_wizard(console: Console, config: dict):
    """Giao diện hướng dẫn người dùng chọn model mặc định."""
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
    stable_models = sorted([m for m in models if 'preview' not in m and 'exp' not in m])
    preview_models = sorted([m for m in models if 'preview' in m or 'exp' in m])
    sorted_models = stable_models + preview_models
    for i, model_name in enumerate(sorted_models):
        table.add_row(str(i + 1), model_name)
    console.print(table)
    while True:
        try:
            choice_str = console.input("Nhập số thứ tự của model bạn muốn chọn: ")
            choice = int(choice_str) - 1
            if 0 <= choice < len(sorted_models):
                selected_model = sorted_models[choice]
                config['default_model'] = selected_model
                fallback_list = [selected_model]
                for m in stable_models:
                    if m != selected_model and m not in fallback_list:
                        fallback_list.append(m)
                config['model_fallback_order'] = fallback_list
                save_config(config)
                console.print(f"\n[bold green]✅ Đã đặt model mặc định là: [cyan]{selected_model}[/cyan][/bold green]")
                console.print(f"[yellow]Thứ tự model dự phòng đã được cập nhật.[/yellow]")
                break
            else:
                console.print("[bold red]Lựa chọn không hợp lệ, vui lòng thử lại.[/bold red]")
        except ValueError:
            console.print("[bold red]Vui lòng nhập một con số.[/bold red]")
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Đã hủy lựa chọn.[/yellow]")
            break

def run_chat_mode(chat_session, console: Console, config: dict, args: argparse.Namespace):
    """Chạy chế độ chat tương tác với logic lưu trữ thông minh."""
    console.print("[bold green]Đã vào chế độ trò chuyện. Gõ 'exit' hoặc 'quit' để thoát.[/bold green]")
    fallback_models = config.get("model_fallback_order", [])
    current_model_name = chat_session.model.model_name
    current_model_index = fallback_models.index(current_model_name) if current_model_name in fallback_models else -1
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
            with console.status("[bold green]AI đang suy nghĩ...[/bold green]"):
                try:
                    response = api.send_message(chat_session, [prompt])
                except ResourceExhausted:
                    console.print(f"[bold yellow]⚠️ Model '{chat_session.model.model_name}' đã hết hạn ngạch.[/bold yellow]")
                    if current_model_index != -1: current_model_index += 1
                    if current_model_index != -1 and current_model_index < len(fallback_models):
                        new_model = fallback_models[current_model_index]
                        console.print(f"[cyan]Đang tự động chuyển sang model: '{new_model}'...[/cyan]")
                        history = chat_session.history
                        system_instruction = chat_session.model.system_instruction
                        chat_session = api.start_chat_session(new_model, system_instruction, history, cli_help_text=args.cli_help_text)
                        try:
                             response = api.send_message(chat_session, [prompt])
                        except Exception as e:
                            console.print(f"[bold red]Lỗi ngay cả với model dự phòng: {e}[/bold red]")
                            continue
                    else:
                        console.print("[bold red]❌ Đã thử hết các model dự phòng nhưng đều thất bại.[/bold red]")
                        continue
                except Exception as e:
                    console.print(f"[bold red]Lỗi: {e}[/bold red]")
                    continue
            console.print("\n[bold magenta]AI:[/bold magenta]")
            response_text = get_response_text(response)
            if args.format == 'rich': console.print(Markdown(response_text))
            else: console.print(response_text)
            if response.usage_metadata:
                tokens = response.usage_metadata.total_token_count
                console.print(f"\n[dim]Token usage: {tokens}[/dim]")
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
                with open(save_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    title = data.get("title", os.path.basename(save_path))
             except (FileNotFoundError, json.JSONDecodeError):
                title = args.topic or os.path.splitext(os.path.basename(save_path))[0].replace('chat_', '')
        else:
            try:
                if not chat_session.history:
                    console.print("\n[yellow]Không có nội dung để lưu.[/yellow]")
                    return
                user_title = console.input("\n[bold yellow]Lưu cuộc trò chuyện với tên (bỏ trống để AI tự đặt tên): [/bold yellow]").strip()
                if user_title:
                    title = user_title
                else:
                    console.print("[cyan]AI đang nghĩ tên cho cuộc trò chuyện...[/cyan]")
                    first_user_prompt = chat_session.history[0].parts[0].text
                    prompt_for_title = f"Dựa trên câu hỏi đầu tiên này: '{first_user_prompt}', hãy tạo một tiêu đề ngắn gọn (dưới 7 từ) cho cuộc trò chuyện. Chỉ trả về tiêu đề."
                    title_chat = api.start_chat_session(config.get("default_model"), cli_help_text=args.cli_help_text)
                    title_response = api.send_message(title_chat, [prompt_for_title])
                    title = get_response_text(title_response).strip().replace('"', '')
                filename = f"chat_{utils.sanitize_filename(title)}.json"
                save_path = os.path.join(HISTORY_DIR, filename)
            except (KeyboardInterrupt, EOFError):
                console.print("\n[yellow]Không lưu cuộc trò chuyện.[/yellow]")
                return
        if save_path and title:
            history_data = {"title": title, "last_modified": datetime.now().isoformat(), "history": serialize_history(chat_session.history)}
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(history_data, f, indent=2, ensure_ascii=False)
            console.print(f"\n[bold yellow]Lịch sử trò chuyện đã được lưu vào '{save_path}'.[/bold yellow]")

def show_history_browser(console: Console):
    """Trình duyệt lịch sử, trả về file path được chọn để main xử lý."""
    console.print(f"[bold green]Đang quét các file lịch sử trong `{HISTORY_DIR}/`...[/bold green]")
    if not os.path.exists(HISTORY_DIR):
        console.print(f"[yellow]Thư mục '{HISTORY_DIR}' không tồn tại. Chưa có lịch sử nào được lưu.[/yellow]")
        return None
    history_files = glob.glob(os.path.join(HISTORY_DIR, "*.json"))
    if not history_files:
        console.print("[yellow]Không tìm thấy file lịch sử nào.[/yellow]")
        return None
    history_metadata = []
    for file_path in history_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    title = os.path.basename(file_path)
                    last_modified_iso = datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat()
                else:
                    title = data.get("title", os.path.basename(file_path))
                    last_modified_iso = data.get("last_modified", datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat())
                history_metadata.append({"title": title, "last_modified": last_modified_iso, "file_path": file_path})
        except Exception:
            continue
    history_metadata.sort(key=lambda x: x["last_modified"], reverse=True)
    table = Table(title="📚 Lịch sử Trò chuyện")
    table.add_column("#", style="cyan")
    table.add_column("Chủ Đề Trò Chuyện", style="magenta")
    table.add_column("Lần Cập Nhật Cuối", style="green")
    for i, meta in enumerate(history_metadata):
        mod_time_str = datetime.fromisoformat(meta["last_modified"]).strftime('%Y-%m-%d %H:%M:%S')
        table.add_row(str(i + 1), meta["title"], mod_time_str)
    console.print(table)
    try:
        choice_str = console.input("Nhập số để tiếp tục cuộc trò chuyện (nhấn Enter để thoát): ")
        if not choice_str:
             console.print("[yellow]Đã thoát trình duyệt lịch sử.[/yellow]")
             return None
        choice = int(choice_str)
        if 1 <= choice <= len(history_metadata):
            selected_file = history_metadata[choice - 1]["file_path"]
            console.print(f"\n[green]Đang tải lại cuộc trò chuyện: '{history_metadata[choice - 1]['title']}'...[/green]")
            return selected_file
        else:
            console.print("[yellow]Lựa chọn không hợp lệ.[/yellow]")
    except (ValueError, KeyboardInterrupt, EOFError):
        console.print("\n[yellow]Đã thoát trình duyệt lịch sử.[/yellow]")
    return None

def handle_git_commit(chat_session, console: Console, format_type: str):
    try:
        diff = subprocess.check_output(["git", "diff", "--staged"], text=True, encoding='utf-8')
        if not diff:
            console.print("[yellow]Không có thay đổi nào được staged. Hãy dùng 'git add' trước.[/yellow]")
            return
        prompt = ("Dựa trên nội dung 'git diff' dưới đây, hãy viết một commit message súc tích và ý nghĩa "
                  "theo chuẩn Conventional Commits. Chỉ trả về message, không giải thích gì thêm.\n\n"
                  f"```diff\n{diff}\n```")
        with console.status("[bold green]AI đang tạo commit message...[/bold green]"):
            response = api.send_message(chat_session, [prompt])
        console.print("\n💡 [bold green]Commit message được đề xuất:[/bold green]")
        clean_text = get_response_text(response).strip().replace("```", "")
        if format_type == 'rich': console.print(Markdown(clean_text))
        else: console.print(clean_text)
    except FileNotFoundError:
        console.print("[bold red]Lỗi: Lệnh 'git' không tồn tại. Bạn đã cài Git chưa?[/bold red]")
    except subprocess.CalledProcessError:
        console.print("[bold red]Lỗi: Đây không phải là một Git repository hoặc có lỗi khi chạy 'git diff'.[/bold red]")

def handle_code_helper(args, config, console: Console, cli_help_text: str):
    file_path = args.document or args.refactor
    task = "viết tài liệu (docstrings, comments)" if args.document else "phân tích và đề xuất các phương án tái cấu trúc (refactor)"
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            code_content = f.read()
    except FileNotFoundError:
        console.print(f"[bold red]Lỗi: Không tìm thấy file '{file_path}'[/bold red]")
        return
    except Exception as e:
        console.print(f"[bold red]Lỗi khi đọc file: {e}[/bold red]")
        return
        
    system_instruction = "You are an expert software architect specializing in code quality."
    model_name = config.get("default_model") 
    chat_session = api.start_chat_session(model_name, system_instruction, cli_help_text=cli_help_text)
    
    prompt = (f"Với vai trò là một kiến trúc sư phần mềm, hãy {task} cho đoạn mã trong file `{file_path}` dưới đây.\n"
              "Trình bày câu trả lời rõ ràng, chuyên nghiệp và chỉ trả về phần mã đã được cập nhật trong một khối mã markdown duy nhất.\n\n"
              f"```python\n{code_content}\n```")
              
    console.print(f"🤖 [bold cyan]Đang {task} cho file '{file_path}'...[/bold cyan]")
    with console.status("[bold green]AI đang phân tích...[/bold green]"):
        try:
            response = api.send_message(chat_session, [prompt])
        except Exception as e:
            console.print(f"[bold red]Lỗi: {e}[/bold red]")
            return
            
    response_text = get_response_text(response)
    
    clean_code = None
    code_match = re.search(r"```(?:python|py)?\n(.*?)```", response_text, re.DOTALL)
    if code_match:
        clean_code = code_match.group(1).strip()
        console.print(Markdown(f"```python\n{clean_code}\n```"))
    else:
        console.print(Markdown(response_text))
    if response.usage_metadata:
        tokens = response.usage_metadata.total_token_count
        console.print(f"\n[dim]Token usage: {tokens}[/dim]")

