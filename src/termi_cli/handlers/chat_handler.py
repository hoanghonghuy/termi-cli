"""
Module xử lý chế độ chat tương tác, bao gồm vòng lặp đọc input,
gọi AI, hiển thị output và lưu lịch sử khi kết thúc.
"""
import os
import json
import argparse
from datetime import datetime

import argparse
from datetime import datetime

from rich.console import Console

from termi_cli import utils, api, i18n

from .core_handler import handle_conversation_turn, get_response_text_from_history
from .history_handler import serialize_history, HISTORY_DIR

def run_chat_mode(chat_session, console: Console, config: dict, args: argparse.Namespace):
    language = config.get("language", "vi")
    console.print(i18n.tr(language, "chat_mode_intro"))

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
                response_text, _, _, _ = handle_conversation_turn(
                    chat_session, [prompt], console, 
                    model_name=args.model or config.get("default_model"),
                    args=args
                )
            except Exception as e:
                console.print(i18n.tr(language, "chat_generic_error", error=e))

                continue
            
            utils.execute_suggested_commands(response_text, console)
    except (KeyboardInterrupt, EOFError):
        console.print(i18n.tr(language, "interrupted_by_user"))

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
                    console.print(i18n.tr(language, "chat_cannot_save_history_incomplete"))
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
                    console.print(i18n.tr(language, "chat_no_new_content_to_save"))
                    return

                user_title = console.input(
                    i18n.tr(language, "chat_save_name_prompt")
                ).strip()

                if user_title:
                    title = user_title
                else:
                    console.print(
                        i18n.tr(language, "chat_ai_thinking_title")
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

                    title_text = api.generate_text(config.get("default_model"), prompt_for_title)
                    title = title_text.strip().replace('"', "")

                filename = f"chat_{utils.sanitize_filename(title)}.json"
                save_path = os.path.join(HISTORY_DIR, filename)
            except (KeyboardInterrupt, EOFError):
                console.print(i18n.tr(language, "chat_no_save_conversation"))
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
                    i18n.tr(language, "chat_history_saved_to", path=save_path)
                )
            except Exception as e:
                console.print(i18n.tr(language, "chat_cannot_save_history_error", error=e))


def run_chat_mode_deepseek(console: Console, config: dict, args: argparse.Namespace, system_instruction: str):
    """Chế độ chat đơn giản dùng DeepSeek (không dùng tool-calls Gemini)."""
    language = config.get("language", "vi")
    console.print(i18n.tr(language, "chat_mode_intro"))

    model_name = args.model or config.get("default_model")
    dialogue: list[tuple[str, str]] = []  # (role, text) với role in {"user", "assistant"}

    try:
        while True:
            prompt = console.input("\n[bold cyan]You:[/bold cyan] ")
            if prompt.lower().strip() in ["exit", "quit", "q"]:
                break
            if not prompt.strip():
                continue

            console.print("\n[bold magenta]AI:[/bold magenta]")

            dialogue.append(("user", prompt))

            # Xây dựng ngữ cảnh hội thoại dạng text để gửi cho DeepSeek
            conversation_text_lines: list[str] = []
            for role, text in dialogue:
                label = "User" if role == "user" else "AI"
                conversation_text_lines.append(f"{label}: {text}")
            conversation_text = "\n".join(conversation_text_lines)

            composite_prompt = (
                "You are a helpful assistant in a multi-turn conversation. "
                "Continue the conversation by replying to the last user message, "
                "taking into account the entire dialogue so far.\n\n"
                f"--- CONVERSATION SO FAR ---\n{conversation_text}\n---\n\n"
                "Your reply (do not repeat previous messages):"
            )

            try:
                response_text = api.generate_text(
                    model_name,
                    composite_prompt,
                    system_instruction=system_instruction,
                )
            except (api.DeepseekInsufficientBalance, api.GroqInsufficientBalance) as e:
                provider = "DeepSeek" if isinstance(e, api.DeepseekInsufficientBalance) else "Groq"
                console.print(
                    f"[bold red]{provider} báo lỗi Insufficient Balance. Không thể tiếp tục dùng {provider} cho phiên chat này.[/bold red]"
                )
                fallback_model = config.get("default_model")
                console.print(
                    f"[yellow]Đang chuyển tạm sang model Gemini '[cyan]{fallback_model}[/cyan]' cho phần còn lại của phiên chat.[/yellow]"
                )

                from termi_cli.handlers.core_handler import build_system_instruction  # tránh import vòng
                from termi_cli import api as _api

                system_instruction_gemini = build_system_instruction(config, args)
                chat_session = _api.start_chat_session(
                    fallback_model,
                    system_instruction_gemini,
                    history=None,
                    cli_help_text=getattr(args, "cli_help_text", ""),
                )

                run_chat_mode(chat_session, console, config, args)
                return
            except Exception as e:
                console.print(i18n.tr(language, "chat_generic_error", error=e))
                continue

            response_text = (response_text or "").strip()
            if not response_text:
                continue

            dialogue.append(("assistant", response_text))
            console.print(response_text)

            # Vẫn cho phép AI đề xuất lệnh shell nếu có
            utils.execute_suggested_commands(response_text, console)

    except (KeyboardInterrupt, EOFError):
        console.print(i18n.tr(language, "interrupted_by_user"))

    # Lưu history đơn giản cho session DeepSeek
    if not os.path.exists(HISTORY_DIR):
        os.makedirs(HISTORY_DIR)

    title = ""
    try:
        user_title = console.input(i18n.tr(language, "chat_save_name_prompt")).strip()
        if user_title:
            title = user_title
        else:
            console.print(i18n.tr(language, "chat_ai_thinking_title"))

            conversation_summary = ""
            for role, text in dialogue:
                if role == "user":
                    conversation_summary += f"User: {text}\n"
                elif role == "assistant":
                    conversation_summary += f"AI: {text}\n"

            prompt_for_title = (
                "Based on the following full conversation transcript, create a very short, "
                "descriptive title (under 7 words) that captures the main topic. "
                "Return only the title itself, with no quotes.\n\n"
                f"--- CONVERSATION ---\n{conversation_summary}"
            )

            title_text = api.generate_text(config.get("default_model"), prompt_for_title)
            title = (title_text or "").strip().replace('"', "")

        if not title:
            console.print(i18n.tr(language, "chat_no_save_conversation"))
            return

        filename = f"chat_{utils.sanitize_filename(title)}.json"
        save_path = os.path.join(HISTORY_DIR, filename)

        history_payload = []
        for role, text in dialogue:
            entry = {
                "role": "user" if role == "user" else "model",
                "parts": [{"text": text}],
            }
            history_payload.append(entry)

        history_data = {
            "title": title,
            "last_modified": datetime.now().isoformat(),
            "history": history_payload,
        }

        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(history_data, f, indent=2, ensure_ascii=False)

        console.print(i18n.tr(language, "chat_history_saved_to", path=save_path))

    except (KeyboardInterrupt, EOFError):
        console.print(i18n.tr(language, "chat_no_save_conversation"))
    except Exception as e:
        console.print(i18n.tr(language, "chat_cannot_save_history_error", error=e))