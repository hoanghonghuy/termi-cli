"""
Module xử lý chế độ chat tương tác, bao gồm vòng lặp đọc input,
gọi AI, hiển thị output và lưu lịch sử khi kết thúc.
"""
import os
import json
import argparse
from datetime import datetime

import google.generativeai as genai
from rich.console import Console

from termi_cli import utils, api
from .core_handler import handle_conversation_turn, get_response_text_from_history
from .history_handler import serialize_history, HISTORY_DIR

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
                response_text, token_usage, token_limit, _ = handle_conversation_turn(
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

                    title_model = genai.GenerativeModel(config.get("default_model"))
                    response = api.resilient_generate_content(title_model, prompt_for_title)
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