import os
import sys
import json
import glob
import argparse
import datetime
import subprocess
import traceback
from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table
from PIL import Image
from google.api_core.exceptions import ResourceExhausted
import google.generativeai as genai

import api
import utils
from config import load_config, save_config

def get_response_text(response: genai.types.GenerateContentResponse) -> str:
    """Trích xuất tất cả nội dung text từ một response một cách an toàn."""
    try:
        # Thử cách nhanh nhất trước
        return response.text
    except Exception:
        # Nếu thất bại, ghép các phần text lại với nhau
        text_parts = []
        for part in response.parts:
            if hasattr(part, 'text') and part.text:
                text_parts.append(part.text)
        return "".join(text_parts)

def serialize_history(history):
    serializable = []
    for content in history:
        parts_data = []
        for part in content.parts:
            if not hasattr(part, 'text') and not hasattr(part, 'function_call') and not hasattr(part, 'function_response'):
                continue
            if hasattr(part, 'text') and part.text:
                parts_data.append({"text": part.text})
            elif hasattr(part, 'function_call') and part.function_call:
                parts_data.append({"function_call": {"name": part.function_call.name, "args": dict(part.function_call.args)}})
            elif hasattr(part, 'function_response') and part.function_response:
                response_content = part.function_response.response
                if not isinstance(response_content, dict):
                     response_content = {'result': str(response_content)}
                parts_data.append({"function_response": {"name": part.function_response.name, "response": response_content}})
        if parts_data:
            serializable.append({"role": content.role, "parts": parts_data})
    return serializable

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

def run_chat_mode(chat_session, console: Console, config: dict, format_type: str, save_path: str = None):
    console.print("[bold green]Đã vào chế độ trò chuyện. Gõ 'exit' hoặc 'quit' để thoát.[/bold green]")
    fallback_models = config.get("model_fallback_order", [])
    current_model_name = chat_session.model.model_name
    current_model_index = fallback_models.index(current_model_name) if current_model_name in fallback_models else -1
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
                        chat_session = api.start_chat_session(new_model, system_instruction, history)
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
            if format_type == 'rich': console.print(Markdown(response_text))
            else: console.print(response_text)
            if response.usage_metadata:
                tokens = response.usage_metadata.total_token_count
                console.print(f"\n[dim]Token usage: {tokens}[/dim]")
            utils.execute_suggested_commands(response_text, console)
    except KeyboardInterrupt:
        console.print("\n[yellow]Đã dừng bởi người dùng.[/yellow]")
    finally:
        if not save_path:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = f"chat_history_{timestamp}.json"
        try:
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(serialize_history(chat_session.history), f, indent=2, ensure_ascii=False)
            console.print(f"\n[bold yellow]Lịch sử trò chuyện đã được lưu vào '{save_path}'.[/bold yellow]")
        except Exception as e:
            console.print(f"[bold red]Lỗi khi lưu lịch sử: {e}[/bold red]")

def show_history_browser(console: Console):
    console.print("[bold green]Đang tìm kiếm các file lịch sử trò chuyện...[/bold green]")
    history_files = glob.glob("chat_history_*.json")
    if not history_files:
        console.print("[yellow]Không tìm thấy file lịch sử nào.[/yellow]")
        return
    table = Table(title="📚 Lịch sử Trò chuyện")
    table.add_column("#", style="cyan")
    table.add_column("File Name", style="magenta")
    table.add_column("Last Modified", style="green")
    history_files.sort(key=os.path.getmtime, reverse=True)
    for i, file_path in enumerate(history_files):
        mod_time = datetime.datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y-%m-%d %H:%M:%S')
        table.add_row(str(i + 1), file_path, mod_time)
    console.print(table)
    try:
        choice_str = console.input("Nhập số để chọn lịch sử muốn tiếp tục (nhấn Enter để thoát): ")
        if not choice_str:
             console.print("[yellow]Đã thoát trình duyệt lịch sử.[/yellow]")
             return
        choice = int(choice_str)
        if 1 <= choice <= len(history_files):
            selected_file = history_files[choice - 1]
            console.print("\nĐể tiếp tục cuộc trò chuyện này, hãy chạy lệnh sau:")
            console.print(f'[bold cyan]python src/main.py --chat --load "{selected_file}"[/bold cyan]')
        else:
            console.print("[yellow]Lựa chọn không hợp lệ.[/yellow]")
    except (ValueError, KeyboardInterrupt):
        console.print("[yellow]Đã thoát trình duyệt lịch sử.[/yellow]")

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

def handle_code_helper(args, config, console: Console):
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
    chat_session = api.start_chat_session(model_name, system_instruction)
    prompt = (f"Với vai trò là một kiến trúc sư phần mềm, hãy {task} cho đoạn mã trong file `{file_path}` dưới đây.\n"
              "Trình bày câu trả lời rõ ràng, chuyên nghiệp.\n\n"
              f"```\n{code_content}\n```")
    console.print(f"🤖 [bold cyan]Đang {task} cho file '{file_path}'...[/bold cyan]")
    with console.status("[bold green]AI đang phân tích...[/bold green]"):
        try:
            response = api.send_message(chat_session, [prompt])
        except Exception as e:
            console.print(f"[bold red]Lỗi: {e}[/bold red]")
            return
    console.print("\n💡 [bold green]Phân tích & Đề xuất:[/bold green]")
    response_text = get_response_text(response)
    console.print(Markdown(response_text))
    if response.usage_metadata:
        tokens = response.usage_metadata.total_token_count
        console.print(f"\n[dim]Token usage: {tokens}[/dim]")

def main():
    os.environ['GRPC_ENABLE_FORK_SUPPORT'] = '0'
    os.environ['GRPC_POLL_STRATEGY'] = 'poll'
    
    load_dotenv()
    console = Console()
    config = load_config()
    
    parser = argparse.ArgumentParser(description="AI Agent CLI mạnh mẽ với Gemini.", formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("prompt", nargs='?', default=None, help="Câu lệnh hỏi AI.")
    parser.add_argument("--list-models", action="store_true", help="Liệt kê models.")
    parser.add_argument("--set-model", action="store_true", help="Chạy giao diện để chọn model mặc định.")
    parser.add_argument("--chat", action="store_true", help="Bật chế độ chat.")
    parser.add_argument("-m", "--model", type=str, default=config.get("default_model"), help="Chọn model (ghi đè tạm thời).")
    parser.add_argument("-f", "--format", type=str, choices=['rich', 'raw'], default=config.get("default_format"), help="Định dạng output.")
    parser.add_argument("-rd", "--read-dir", action="store_true", help="Đọc ngữ cảnh thư mục.")
    parser.add_argument("-p", "--persona", type=str, choices=list(config.get("personas", {}).keys()), help="Chọn persona.")
    parser.add_argument("-si", "--system-instruction", type=str, default=None, help="Ghi đè chỉ dẫn hệ thống.")
    parser.add_argument("--load", type=str, help="Tải lịch sử chat.")
    parser.add_argument("--save", type=str, help="Lưu lịch sử chat vào file cụ thể.")
    parser.add_argument("-i", "--image", type=str, help="Đường dẫn tới file ảnh để phân tích.")
    parser.add_argument("--history", action="store_true", help="Hiển thị trình duyệt lịch sử chat.")
    parser.add_argument("--git-commit", action="store_true", help="Tự động tạo commit message.")
    parser.add_argument("--document", type=str, metavar="FILE_PATH", help="Tự động viết tài liệu cho code trong file.")
    parser.add_argument("--refactor", type=str, metavar="FILE_PATH", help="Đề xuất cách tái cấu trúc code trong file.")

    args = parser.parse_args()
    api_key = os.getenv("GOOGLE_API_KEY")

    if not api_key:
        console.print("[bold red]Lỗi: Vui lòng thiết lập GOOGLE_API_KEY trong file .env[/bold red]")
        return
    
    try:
        api.configure_api(api_key)
        if args.list_models:
            api.list_models(console)
            return
        if args.set_model:
            model_selection_wizard(console, config)
            return
        if args.history:
            show_history_browser(console)
            return
        if args.document or args.refactor:
            handle_code_helper(args, config, console)
            return
        system_instruction = args.system_instruction or \
                             (config.get("personas", {}).get(args.persona) if args.persona else None) or \
                             config.get("default_system_instruction")
        history = None
        if args.load:
            try:
                with open(args.load, 'r', encoding='utf-8') as f:
                    history = json.load(f)
                console.print(f"[green]Đã tải lịch sử từ '{args.load}'.[/green]")
            except Exception as e:
                console.print(f"[bold red]Lỗi khi tải lịch sử: {e}[/bold red]")
                return
        if args.model != config.get("default_model"):
            models_to_try = [args.model]
        else:
            models_to_try = config.get("model_fallback_order", [config.get("default_model")])
        response = None
        if args.chat:
            chat_session = api.start_chat_session(models_to_try[0], system_instruction, history)
            run_chat_mode(chat_session, console, config, args.format, args.save)
            return
        piped_input = None
        if not sys.stdin.isatty():
             piped_input = sys.stdin.read().strip()
        if not args.prompt and not piped_input and not args.image and not args.git_commit:
             console.print("[bold red]Lỗi: Cần cung cấp prompt hoặc một hành động như --git-commit, --chat, etc.[/bold red]")
             parser.print_help()
             return
        prompt_parts = []
        user_question = args.prompt or ""
        if args.image:
            try:
                img = Image.open(args.image)
                prompt_parts.append(img)
            except FileNotFoundError:
                console.print(f"[bold red]Lỗi: Không tìm thấy file ảnh '{args.image}'[/bold red]")
                return
            except Exception as e:
                console.print(f"[bold red]Lỗi khi mở ảnh: {e}[/bold red]")
                return
        prompt_text = ""
        if piped_input:
            prompt_text += f"Dựa vào nội dung được cung cấp sau đây:\n{piped_input}\n\n"
        if args.read_dir:
            console.print("[yellow]Đang đọc ngữ cảnh thư mục...[/yellow]")
            context = utils.get_directory_context()
            prompt_text += f"Dựa vào ngữ cảnh các file dưới đây:\n{context}\n\n"
        if args.image:
             prompt_text += user_question if user_question else "Phân tích ảnh này."
        else:
             prompt_text += user_question
        if prompt_text:
            prompt_parts.append(prompt_text)
        for model in models_to_try:
            try:
                if len(models_to_try) > 1:
                    console.print(f"[dim]Đang thử với model: {model}...[/dim]")
                chat_session = api.start_chat_session(model, system_instruction, history)
                if args.git_commit:
                    handle_git_commit(chat_session, console, args.format)
                    return
                with console.status(f"[bold green]AI (model: {model}) đang suy nghĩ...[/bold green]"):
                    response = api.send_message(chat_session, prompt_parts)
                break
            except ResourceExhausted:
                console.print(f"[bold yellow]⚠️ Model '{model}' đã hết hạn ngạch.[/bold yellow]")
                if model == models_to_try[-1]:
                    console.print("[bold red]❌ Đã thử hết các model dự phòng nhưng đều thất bại.[/bold red]")
                else:
                    console.print("[cyan]Đang tự động chuyển sang model tiếp theo...[/cyan]")
                continue
            except Exception as e:
                console.print(f"[bold red]Đã xảy ra lỗi không mong muốn với model {model}: {e}[/bold red]")
                break
        if response:
            console.print("\n💡 [bold green]Phản hồi:[/bold green]")
            response_text = get_response_text(response)
            if args.format == 'rich':
                console.print(Markdown(response_text))
            else:
                console.print(response_text)
            if response.usage_metadata:
                tokens = response.usage_metadata.total_token_count
                console.print(f"\n[dim]Token usage: {tokens}[/dim]")
            utils.execute_suggested_commands(response_text, console)
    except KeyboardInterrupt:
        console.print("\n[yellow]Đã dừng bởi người dùng.[/yellow]")
    except Exception as e:
        console.print(f"[bold red]Đã xảy ra lỗi không mong muốn: {e}[/bold red]")
        console.print(f"[dim]{traceback.format_exc()}[/dim]")

if __name__ == "__main__":
    main()