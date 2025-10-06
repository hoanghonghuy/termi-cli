# src/handlers.py
import os
import sys
import json
import glob
import re
import argparse
from datetime import datetime
import subprocess
import logging

from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

# NOTE: lazy import google.generativeai (don't import at top-level to avoid native logs)
# ✅ PATCH: thay vì `import google.generativeai as genai` ở top-level, dùng _get_genai() để lazy import
# (một số chỗ trong file trước đó dùng genai; mình giữ logic đó nhưng import khi cần)
# from google.api_core.exceptions import ResourceExhausted
from google.api_core.exceptions import ResourceExhausted

import api
import utils
from config import save_config, load_config

logger = logging.getLogger(__name__)

# --- CONSTANTS ---
HISTORY_DIR = "chat_logs"


# ---------------------------
# Utility: lazy import genai
# ---------------------------
def _get_genai():
    """
    Lazy import google.generativeai. Nếu không import được, raise ImportError.
    Giữ nguyên interface như trước khi code gốc dùng genai.
    """
    try:
        import google.generativeai as genai  # type: ignore
        return genai
    except Exception as e:
        logger.debug("Không thể import google.generativeai: %s", e, exc_info=True)
        raise ImportError("Module 'google.generativeai' chưa cài hoặc không thể import.") from e


# ---------------------------
# HELPER FUNCTIONS
# ---------------------------
def get_response_text_from_history(history_entry):
    """Trích xuất text từ một entry trong đối tượng history."""
    try:
        text_parts = [
            part.text
            for part in history_entry.parts
            if hasattr(part, "text") and part.text
        ]
        return "".join(text_parts)
    except Exception:
        return ""


def _sanitize_chunk_text(text: str) -> str:
    """
    Loại bỏ ký tự rác, CR, collapse nhiều newline để tránh render xấu.
    ✅ PATCH: chuẩn hoá text streaming để tránh chuyện 'chữ cách chữ' hoặc nhiều dòng trống.
    """
    if not text:
        return ""
    # loại bỏ null bytes và CR
    s = text.replace("\x00", "")
    s = s.replace("\r", "")
    # collapse >3 newline thành 2 newline
    while "\n\n\n\n" in s:
        s = s.replace("\n\n\n\n", "\n\n")
    while "\n\n\n" in s:
        s = s.replace("\n\n\n", "\n\n")
    # trim trailing spaces on each line
    s = "\n".join(line.rstrip() for line in s.splitlines())
    return s


def process_response_stream(response_stream, console: Console, output_format: str = "rich"):
    """
    Xử lý luồng phản hồi từ AI với format tùy chọn.

    Giữ nguyên logic gốc (duyệt chunk, lấy part.text, function_call detection),
    nhưng sanitize phần text trước khi in để UI ổn hơn.
    """
    full_text = ""
    function_calls = []

    try:
        for chunk in response_stream:
            # chunk có cấu trúc khác nhau tuỳ SDK. Gốc dùng chunk.candidates[0].content.parts
            # Chúng ta cố gắng tương thích nhiều dạng:
            parts = []
            try:
                # SDK gốc (có candidates)
                if hasattr(chunk, "candidates") and chunk.candidates:
                    cand0 = chunk.candidates[0]
                    # trong nội dung candidate có `content.parts`
                    content = getattr(cand0, "content", None)
                    if content and hasattr(content, "parts"):
                        parts = list(content.parts)
                # fallback: chunk có attribute .text hoặc dict-like
                if not parts:
                    if hasattr(chunk, "text"):
                        # tạo pseudo-part
                        class _P:
                            def __init__(self, text): self.text = text
                        parts = [_P(getattr(chunk, "text"))]
                    elif isinstance(chunk, dict):
                        # dict có thể chứa 'text' hoặc 'candidates'
                        if "text" in chunk and chunk["text"]:
                            class _P:
                                def __init__(self, text): self.text = text
                            parts = [_P(chunk["text"])]
                        elif "candidates" in chunk and chunk["candidates"]:
                            try:
                                cand0 = chunk["candidates"][0]
                                cont = cand0.get("content", {})
                                for p in cont.get("parts", []):
                                    class _P2:
                                        def __init__(self, text): self.text = text
                                    parts.append(_P2(p.get("text")))
                            except Exception:
                                pass
            except Exception:
                # fallback tổng quát: convert chunk -> str
                try:
                    txt = str(chunk)
                    class _P3:
                        def __init__(self, text): self.text = text
                    parts = [_P3(txt)]
                except Exception:
                    parts = []

            # process parts
            for part in parts:
                try:
                    part_text = getattr(part, "text", None)
                    if not part_text:
                        # nếu có function_call trên part
                        if hasattr(part, "function_call") and part.function_call:
                            function_calls.append(part.function_call)
                        continue
                    sanitized = _sanitize_chunk_text(part_text)
                    full_text += sanitized

                    # Render theo format (giữ hành vi real-time nhưng sanitized)
                    if output_format == "rich":
                        # ✅ PATCH: in từng chunk đã sanitize bằng Markdown (giúp render code block)
                        try:
                            console.print(Markdown(sanitized), end="")
                        except Exception:
                            console.print(sanitized, end="")
                    else:
                        # Raw text: in liên tục
                        console.print(sanitized, end="")

                    # detect function_call attribute on part (SDK-specific)
                    if hasattr(part, 'function_call') and part.function_call:
                        function_calls.append(part.function_call)

                except Exception as ex_part:
                    logger.exception("Lỗi xử lý part trong stream: %s", ex_part)

        # cuối cùng in 1 dòng xuống để ngắt dòng nếu cần
        try:
            console.print()
        except Exception:
            pass

    except Exception as e:
        console.print(f"\n[bold red]Lỗi khi xử lý stream: {e}[/bold red]")
        logger.exception("process_response_stream error: %s", e)

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
        content_dict = {"role": getattr(content, "role", None) or content.role if hasattr(content, "role") else content.get("role", "unknown"), "parts": []}
        # support both attr-based and dict-based content
        parts_iter = getattr(content, "parts", None) or content.get("parts", []) if isinstance(content, dict) else getattr(content, "parts", [])
        for part in parts_iter:
            part_dict = {}
            # part may be object or dict
            if hasattr(part, "text") and part.text is not None:
                part_dict["text"] = part.text
            elif isinstance(part, dict) and part.get("text") is not None:
                part_dict["text"] = part.get("text")
            elif hasattr(part, "function_call") and part.function_call is not None:
                try:
                    part_dict["function_call"] = {
                        "name": part.function_call.name,
                        "args": dict(part.function_call.args) if part.function_call.args else {},
                    }
                except Exception:
                    part_dict["function_call"] = {"name": getattr(part.function_call, "name", None)}
            elif (
                hasattr(part, "function_response")
                and part.function_response is not None
            ):
                try:
                    part_dict["function_response"] = {
                        "name": part.function_response.name,
                        "response": dict(part.function_response.response) if getattr(part.function_response, "response", None) else {},
                    }
                except Exception:
                    part_dict["function_response"] = {"name": getattr(part.function_response, "name", None)}
            if part_dict:
                content_dict["parts"].append(part_dict)
        if content_dict["parts"]:
            serializable.append(content_dict)
    return serializable


def handle_conversation_turn(chat_session, prompt_parts, console: Console, model_name: str = None, output_format: str = "rich"):
    """
    Xử lý một lượt hội thoại với auto-retry khi hết quota.
    Tự động chuyển sang API key backup nếu key hiện tại hết quota.
    """
    from google.api_core.exceptions import ResourceExhausted

    max_retries = len(api._api_keys) if getattr(api, "_api_keys", None) else 1

    for attempt in range(max_retries):
        try:
            final_text_response = ""
            total_tokens = {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}

            # gọi API - ở api.send_message bạn đã implement stream / non-stream return
            response_stream = api.send_message(chat_session, prompt_parts)
            text_chunk, function_calls = process_response_stream(response_stream, console, output_format)

            # Lấy token usage (gốc có dùng response_stream.resolve() -> nếu SDK có)
            try:
                # ✅ PATCH: bọc try/except để tránh exception nếu response_stream không hỗ trợ resolve()
                if hasattr(response_stream, "resolve"):
                    try:
                        response_stream.resolve()
                    except Exception:
                        pass
                usage = {}
                try:
                    usage = api.get_token_usage(response_stream)
                except Exception:
                    usage = {}
                if usage:
                    for key in total_tokens:
                        if key in usage and usage[key]:
                            total_tokens[key] += usage[key]
            except Exception:
                # ignore usage errors
                pass

            if text_chunk:
                final_text_response += text_chunk + "\n"

            # Xử lý function calls (giữ nguyên logic gốc)
            while function_calls:
                tool_responses = []
                for func_call in function_calls:
                    tool_name = func_call.name
                    tool_args = dict(func_call.args) if func_call.args else {}

                    console.print(f"[yellow]⚙ Lệnh gọi tool: [bold]{tool_name}[/bold]({tool_args})[/yellow]")

                    if tool_name in api.AVAILABLE_TOOLS:
                        try:
                            tool_function = api.AVAILABLE_TOOLS[tool_name]
                            result = tool_function(**tool_args)

                            if tool_name in ['refactor_code', 'document_code']:
                                console.print(f"\n[bold cyan]📄 Kết quả từ {tool_name}:[/bold cyan]")
                                console.print(Markdown(result))
                                console.print()

                        except Exception as e:
                            result = f"Error executing tool '{tool_name}': {str(e)}"
                    else:
                        result = f"Error: Tool '{tool_name}' not found."

                    tool_responses.append({
                        "function_response": {"name": tool_name, "response": {"result": result}}
                    })

                # Gửi lại tool responses như conversation-turn cho model
                response_stream = api.send_message(chat_session, tool_responses)
                text_chunk, function_calls = process_response_stream(response_stream, console, output_format)

                try:
                    if hasattr(response_stream, "resolve"):
                        try:
                            response_stream.resolve()
                        except Exception:
                            pass
                    usage = {}
                    try:
                        usage = api.get_token_usage(response_stream)
                    except Exception:
                        usage = {}
                    if usage:
                        for key in total_tokens:
                            if key in usage and usage[key]:
                                total_tokens[key] += usage[key]
                except Exception:
                    pass

                if text_chunk:
                    final_text_response += text_chunk + "\n"

            # Lấy token limit
            token_limit = 0
            if model_name:
                token_limit = api.get_model_token_limit(model_name)

            return final_text_response.strip(), total_tokens, token_limit

        except ResourceExhausted as e:
            # Hết quota, thử chuyển sang key khác
            if attempt < max_retries - 1:
                success, msg = api.switch_to_next_api_key()
                if success:
                    console.print(f"\n[yellow]⚠ Hết quota! Đã chuyển sang API {msg}. Đang thử lại...[/yellow]")
                    continue
                else:
                    console.print(f"\n[bold red]❌ {msg}. Không thể tiếp tục.[/bold red]")
                    raise
            else:
                console.print(f"\n[bold red]❌ Đã thử hết {max_retries} API key(s). Tất cả đều hết quota.[/bold red]")
                raise
        except Exception as e:
            # Lỗi khác, không retry
            logger.exception("Lỗi khi xử lý conversation turn: %s", e)
            raise

    # Không bao giờ đến đây, nhưng để an toàn
    return "", {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}, 0


def model_selection_wizard(console: Console, config: dict):
    # This function remains unchanged from your original implementation
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
            choice_str = console.input("Nhập số thứ tự của model bạn muốn chọn: ")
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
    """Chạy chế độ chat tương tác với logic lưu trữ thông minh."""
    console.print("[bold green]Đã vào chế độ trò chuyện. Gõ 'exit' hoặc 'quit' để thoát.[/bold green]")
    initial_save_path = None
    if getattr(args, "topic", None):
        initial_save_path = os.path.join(HISTORY_DIR, f"chat_{utils.sanitize_filename(args.topic)}.json")
    elif getattr(args, "load", None):
        initial_save_path = args.load

    try:
        while True:
            prompt = console.input("\n[bold cyan]You:[/bold cyan] ")
            if prompt.lower().strip() in ["exit", "quit", "q"]:
                break
            if not prompt.strip():
                continue

            console.print("\n[bold magenta]AI:[/bold magenta]")
            try:
                response_text, token_usage, token_limit = handle_conversation_turn(
                    chat_session, [prompt], console,
                    model_name=config.get("default_model"),
                    output_format=getattr(args, "format", None) or config.get("default_format", "rich")
                )

                # Hiển thị token usage (nếu có)
                if token_usage and isinstance(token_usage, dict) and token_usage.get('total_tokens', 0) > 0:
                    if token_limit and token_limit > 0:
                        console.print(f"[dim]📊 {token_usage['total_tokens']:,} / {token_limit:,} tokens[/dim]")
                    else:
                        console.print(f"[dim]📊 {token_usage['total_tokens']:,} tokens[/dim]")
            except Exception as e:
                console.print(f"[bold red]Lỗi: {e}[/bold red]")
                logger.exception("Lỗi khi chạy vòng chat: %s", e)
                continue

            # preserve original behavior: execute suggested commands if any
            utils.execute_suggested_commands(response_text, console)
    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]Đã dừng bởi người dùng.[/yellow]")
    finally:
        # Saving logic (giữ nguyên luồng gốc, chỉ thêm kiểm tra an toàn)
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
                title = getattr(args, "topic", None) or os.path.splitext(os.path.basename(save_path))[0].replace("chat_", "")
        else:
            try:
                # THÊM XỬ LÝ EXCEPTION KHI TRUY CẬP HISTORY
                try:
                    history_len = len(getattr(chat_session, "history", []))
                except Exception:
                    # Nếu không thể truy cập history (vì stream chưa hoàn thành), bỏ qua việc lưu
                    console.print("\n[yellow]Không thể lưu lịch sử do phiên chat chưa hoàn tất.[/yellow]")
                    return

                initial_len = 0
                if getattr(args, "load", None) or getattr(args, "topic", None):
                    initial_len = len(load_config().get("history", [])) or 0

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
                    # get_response_text_from_history expects a history entry object; guard
                    first_history_item = None
                    try:
                        first_history_item = getattr(chat_session, "history", [None])[0]
                    except Exception:
                        first_history_item = None

                    first_user_prompt = ""
                    if first_history_item:
                        try:
                            first_user_prompt = get_response_text_from_history(first_history_item)
                        except Exception:
                            try:
                                # fallback if history stored as dicts
                                hist = getattr(chat_session, "history", []) or []
                                if hist and isinstance(hist[0], dict):
                                    first_user_prompt = "".join(p.get("text","") for p in hist[0].get("parts", []))
                            except Exception:
                                first_user_prompt = ""

                    prompt_for_title = f"Dựa trên câu hỏi đầu tiên này: '{first_user_prompt}', hãy tạo một tiêu đề ngắn gọn (dưới 7 từ) cho cuộc trò chuyện. Chỉ trả về tiêu đề."

                    try:
                        # ✅ PATCH: dùng lazy import genai để tránh import native libs sớm
                        genai = _get_genai()
                        title_chat = genai.GenerativeModel(
                            config.get("default_model")
                        ).start_chat()
                        response = title_chat.send_message(prompt_for_title)
                        # response có thể là object hoặc dict
                        title = getattr(response, "text", None) or (response.get("text") if isinstance(response, dict) else str(response))
                        title = str(title).strip().replace('"', "")
                    except Exception as e:
                        logger.exception("Không thể tạo tiêu đề tự động: %s", e)
                        title = "untitled_chat_" + datetime.now().strftime("%Y%m%d_%H%M%S")

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
                    "history": serialize_history(getattr(chat_session, "history", [])),
                }
                with open(save_path, "w", encoding="utf-8") as f:
                    json.dump(history_data, f, indent=2, ensure_ascii=False)
                console.print(
                    f"\n[bold yellow]Lịch sử trò chuyện đã được lưu vào '{save_path}'.[/bold yellow]"
                )
            except Exception as e:
                console.print(f"\n[yellow]Không thể lưu lịch sử: {e}[/yellow]")


def show_history_browser(console: Console):
    # This function remains unchanged (kept original behavior)
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
        try:
            mod_time_str = datetime.fromisoformat(meta["last_modified"]).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        except Exception:
            mod_time_str = meta["last_modified"]
        table.add_row(str(i + 1), meta["title"], mod_time_str)
    console.print(table)
    try:
        choice_str = console.input(
            "Nhập số để tiếp tục cuộc trò chuyện (nhấn Enter để thoát): "
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
    # This function remains unchanged in behavior
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

        console.print("\n[bold green]📝 Tóm Tắt Cuộc Trò Chuyện:[/bold green] ", end="")
        handle_conversation_turn(chat_session, [prompt], console)

    except Exception as e:
        console.print(f"[bold red]Lỗi khi tóm tắt lịch sử: {e}[/bold red]")


# --- Handlers for custom instructions ---
def add_instruction(console: Console, config: dict, instruction: str):
    """Thêm một chỉ dẫn mới vào config."""
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
    """Liệt kê các chỉ dẫn đã lưu."""
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
    """Xóa một chỉ dẫn theo index (bắt đầu từ 1)."""
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
