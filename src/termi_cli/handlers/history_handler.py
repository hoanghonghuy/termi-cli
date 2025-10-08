# src/termi_cli/handlers/history_handler.py

"""
Module xử lý các tác vụ liên quan đến lịch sử trò chuyện,
bao gồm hiển thị, tải, tóm tắt và lưu trữ.
"""
import os
import json
import glob
import argparse
from datetime import datetime

from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

from termi_cli import api
from .core_handler import handle_conversation_turn

# --- CONSTANTS ---
HISTORY_DIR = "chat_logs"

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