"""Application-level service cho logic chế độ chat.

Tách khỏi chat_handler để handler chỉ còn vai trò I/O với Console và CLI.
"""

from __future__ import annotations

import os
import json
import argparse
import re
from dataclasses import dataclass
from datetime import datetime

from rich.console import Console

from termi_cli import api, i18n, utils
from termi_cli.handlers import mini_agent
from termi_cli.json_utils import JsonPayloadParseError, parse_json_payload
from termi_cli.handlers.core_handler import (
    handle_conversation_turn,
    get_response_text_from_history,
    confirm_and_write_file,
)
from termi_cli.application.history_service import HistoryService, HISTORY_DIR
from termi_cli.infrastructure import http_providers


@dataclass
class ChatLoopOptions:
    """DTO gom các tuỳ chọn chính cho vòng lặp chat Gemini."""

    language: str
    model_name: str
    topic: str | None
    load_path: str | None

    @classmethod
    def from_args(cls, config: dict, args: argparse.Namespace) -> "ChatLoopOptions":
        language = config.get("language", "vi")
        model_name = args.model or config.get("default_model")
        topic = getattr(args, "topic", None)
        load_path = getattr(args, "load", None)
        return cls(
            language=language,
            model_name=model_name,
            topic=topic,
            load_path=load_path,
        )


@dataclass
class HttpChatOptions:
    """DTO gom các tuỳ chọn chính cho chat HTTP providers."""

    language: str
    model_name: str
    mini_agent_off: bool

    @classmethod
    def from_args(cls, config: dict, args: argparse.Namespace) -> "HttpChatOptions":
        language = config.get("language", "vi")
        model_name = args.model or config.get("default_model")
        mini_agent_off = getattr(args, "mini_agent_off", False)
        return cls(
            language=language,
            model_name=model_name,
            mini_agent_off=mini_agent_off,
        )


class ChatService:
    @staticmethod
    def get_gemini_fallback_model(config: dict) -> str:
        """Chọn một model Gemini an toàn để fallback khi HTTP provider hết quota/balance."""

        model = config.get("default_model")
        if isinstance(model, str) and (
            model.startswith("models/") or "gemini" in model.lower()
        ):
            return model
        for candidate in config.get("model_fallback_order", []):
            if isinstance(candidate, str) and (
                candidate.startswith("models/")
                or "gemini" in candidate.lower()
            ):
                return candidate
        return "models/gemini-flash-latest"

    def run_chat_mode(
        self,
        chat_session,
        console: Console,
        config: dict,
        args: argparse.Namespace,
    ) -> None:
        """Logic chính cho chế độ chat Gemini (đa lượt)."""

        opts = ChatLoopOptions.from_args(config, args)
        language = opts.language
        console.print(i18n.tr(language, "chat_mode_intro"))

        history_service = HistoryService()

        initial_save_path = None
        if opts.topic:
            initial_save_path = os.path.join(
                HISTORY_DIR, f"chat_{utils.sanitize_filename(opts.topic)}.json"
            )
        elif opts.load_path:
            initial_save_path = opts.load_path

        try:
            user_label = i18n.tr(language, "history_user_label")
            ai_label = i18n.tr(language, "history_ai_label")
            while True:
                prompt = console.input(f"\n{user_label} ")
                if prompt.lower().strip() in ["exit", "quit", "q"]:
                    break
                if not prompt.strip():
                    continue

                console.print(f"\n{ai_label}")

                try:
                    response_text, _, _, _ = handle_conversation_turn(
                        chat_session,
                        [prompt],
                        console,
                        model_name=opts.model_name,
                        args=args,
                    )
                except Exception as e:  # noqa: BLE001
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
            skip_save = False

            if save_path:
                try:
                    data = history_service.load_history_file(save_path)
                    title = data.get("title", os.path.basename(save_path))
                except (FileNotFoundError, ValueError, OSError):
                    title = (
                        args.topic
                        or os.path.splitext(os.path.basename(save_path))[0].replace(
                            "chat_", ""
                        )
                    )
            else:
                try:
                    try:
                        history_len = len(chat_session.history)
                    except Exception:  # noqa: BLE001
                        console.print(
                            i18n.tr(
                                language,
                                "chat_cannot_save_history_incomplete",
                            )
                        )
                        skip_save = True

                    if not skip_save:
                        initial_len = 0
                        if args.load or args.topic:
                            try:
                                initial_source = args.load or initial_save_path
                                if initial_source:
                                    initial_data = history_service.load_history_file(
                                        initial_source
                                    )
                                    initial_len = len(
                                        initial_data.get("history", [])
                                    )
                            except (
                                FileNotFoundError,
                                TypeError,
                                ValueError,
                                OSError,
                            ):
                                initial_len = 0

                        if history_len <= initial_len:
                            console.print(
                                i18n.tr(language, "chat_no_new_content_to_save")
                            )
                            skip_save = True

                    if not skip_save:
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
                                if content.role == "user":
                                    conversation_summary += (
                                        "User: "
                                        f"{get_response_text_from_history(content)}\n"
                                    )
                                elif content.role == "model":
                                    conversation_summary += (
                                        "AI: "
                                        f"{get_response_text_from_history(content)}\n"
                                    )

                            prompt_for_title = (
                                "Based on the following full conversation transcript, create a very short, "
                                "descriptive title (under 7 words) that captures the main topic. "
                                "Return only the title itself, with no quotes.\n\n"
                                f"--- CONVERSATION ---\n{conversation_summary}"
                            )

                            title_text = api.generate_text(
                                config.get("default_model"),
                                prompt_for_title,
                            )
                            title = title_text.strip().replace("\"", "")

                        filename = f"chat_{utils.sanitize_filename(title)}.json"
                        save_path = os.path.join(HISTORY_DIR, filename)
                except (KeyboardInterrupt, EOFError):
                    console.print(i18n.tr(language, "chat_no_save_conversation"))
                    skip_save = True

            if save_path and title and not skip_save:
                try:
                    history_data = {
                        "title": title,
                        "last_modified": datetime.now().isoformat(),
                        "history": history_service.serialize_history(
                            chat_session.history
                        ),
                    }
                    with open(save_path, "w", encoding="utf-8") as f:
                        json.dump(history_data, f, indent=2, ensure_ascii=False)
                    console.print(
                        i18n.tr(language, "chat_history_saved_to", path=save_path)
                    )
                except Exception as e:  # noqa: BLE001
                    console.print(
                        i18n.tr(
                            language,
                            "chat_cannot_save_history_error",
                            error=e,
                        )
                    )

    def run_chat_mode_deepseek(
        self,
        console: Console,
        config: dict,
        args: argparse.Namespace,
        system_instruction: str,
    ) -> None:
        """Chế độ chat dùng HTTP providers (DeepSeek/Groq/OpenRouter) với Multi-modal support."""

        opts = HttpChatOptions.from_args(config, args)
        language = opts.language
        console.print(i18n.tr(language, "chat_mode_intro"))

        model_name = opts.model_name
        # Messages list chuẩn OpenAI: [{"role": "user", "content": ...}]
        messages: list[dict] = []

        tool_names = ", ".join(sorted(api.AVAILABLE_TOOLS.keys()))
        tool_usage_hint = (
            "If you need to run a tool (shell/files/web/etc.), return exactly one JSON object like "
            '{"tool_name": "<name>", "tool_args": { ... }} without Markdown fences. '
            f"Valid tool_name values: {tool_names}. If no tool is needed, answer normally."
        )
        
        # Buffer cho attachment (ảnh/file) chờ gửi ở lượt tiếp theo
        pending_images: list[str] = []
        pending_files_content: list[str] = []

        # Xử lý startup arguments (--image, --file)
        if getattr(args, "image", None):
            for img_path in args.image:
                if os.path.exists(img_path):
                    b64_img = http_providers.encode_image_to_base64(img_path)
                    if b64_img:
                        pending_images.append(b64_img)
                        console.print(i18n.tr(language, "chat_image_added", path=img_path))
                    else:
                        console.print(i18n.tr(language, "chat_image_load_failed", path=img_path, error="Encoding failed"))
                else:
                    console.print(i18n.tr(language, "error_image_not_found", path=img_path))

        if getattr(args, "file", None):
            for file_path in args.file:
                if os.path.exists(file_path):
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            content = f.read()
                            formatted_content = f"\n\n--- File: {file_path} ---\n{content}\n---"
                            pending_files_content.append(formatted_content)
                            console.print(i18n.tr(language, "chat_file_added", path=file_path))
                    except Exception as e:
                        console.print(i18n.tr(language, "chat_file_read_failed", path=file_path, error=e))
                else:
                    console.print(i18n.tr(language, "code_file_not_found", path=file_path))

        initial_prompt = getattr(args, "prompt", None)  # Handles: termi chat "prompt" ...

        try:
            user_label = i18n.tr(language, "history_user_label")
            ai_label = i18n.tr(language, "history_ai_label")
            
            while True:
                # Hiển thị chỉ báo nếu có pending attachment
                if pending_images or pending_files_content:
                    console.print(f"[dim](Pending: {len(pending_images)} images, {len(pending_files_content)} files)[/dim]")

                if initial_prompt:
                    prompt = initial_prompt
                    initial_prompt = None
                    console.print(f"\n{user_label} {prompt}")
                else:
                    prompt = console.input(f"\n{user_label} ")
                
                # Xử lý lệnh slash command
                if prompt.startswith("/image "):
                    image_path = prompt[7:].strip().strip('"').strip("'")
                    if os.path.exists(image_path):
                        b64_img = http_providers.encode_image_to_base64(image_path)
                        if b64_img:
                            pending_images.append(b64_img)
                            console.print(i18n.tr(language, "chat_image_added", path=image_path))
                        else:
                            console.print(i18n.tr(language, "chat_image_load_failed", path=image_path, error="Encoding failed"))
                    else:
                        console.print(i18n.tr(language, "error_image_not_found", path=image_path))
                    continue
                
                if prompt.startswith("/file "):
                    file_path = prompt[6:].strip().strip('"').strip("'")
                    if os.path.exists(file_path):
                        try:
                            with open(file_path, "r", encoding="utf-8") as f:
                                content = f.read()
                                formatted_content = f"\n\n--- File: {file_path} ---\n{content}\n---"
                                pending_files_content.append(formatted_content)
                                console.print(i18n.tr(language, "chat_file_added", path=file_path))
                        except Exception as e:
                            console.print(i18n.tr(language, "chat_file_read_failed", path=file_path, error=e))
                    else:
                        console.print(i18n.tr(language, "code_file_not_found", path=file_path))
                    continue

                # Toggle RAG mode during chat
                if prompt.strip().lower() == "/rag":
                    current_rag = getattr(args, "rag", False)
                    args.rag = not current_rag
                    status = "ON" if args.rag else "OFF"
                    console.print(f"[green]RAG mode: {status}[/green]")
                    continue

                # Show available tools
                if prompt.strip().lower() == "/tools":
                    console.print(f"[dim]Available tools: {tool_names}[/dim]")
                    continue

                if prompt.lower().strip() in ["exit", "quit", "q"]:
                    break
                
                # Nếu prompt rỗng nhưng có pending data thì vẫn gửi
                if not prompt.strip() and not pending_images and not pending_files_content:
                    continue

                console.print(f"\n{ai_label}")

                # Xây dựng nội dung tin nhắn User
                user_text_part = prompt
                if pending_files_content:
                    user_text_part += "\n".join(pending_files_content)
                
                user_content: str | list[dict] = user_text_part
                
                # Nếu có ảnh, phải chuyển sang dạng list[dict] (OpenAI Vision format)
                if pending_images:
                    content_list = []
                    if user_text_part:
                        content_list.append({"type": "text", "text": user_text_part})
                    for img_b64 in pending_images:
                        content_list.append({
                            "type": "image_url",
                            "image_url": {
                                "url": img_b64
                            }
                        })
                    user_content = content_list
                
                # Reset pending buffers
                pending_images = []
                pending_files_content = []

                # RAG context injection when --rag flag is enabled
                if getattr(args, "rag", False) and user_text_part:
                    from termi_cli.rag import codebase_query
                    index_name = getattr(args, "rag_index", "default")
                    if codebase_query.is_index_available(index_name):
                        rag_context = codebase_query.get_codebase_context(user_text_part, index_name)
                        if rag_context:
                            console.print(i18n.tr(language, "rag_context_found"))
                            # Inject RAG context into user text
                            if isinstance(user_content, str):
                                user_content = f"{rag_context}\n---\n\nUser question: {user_content}"
                            elif isinstance(user_content, list):
                                # Multi-modal: prepend to first text part
                                for item in user_content:
                                    if item.get("type") == "text":
                                        item["text"] = f"{rag_context}\n---\n\nUser question: {item['text']}"
                                        break
                        else:
                            console.print(i18n.tr(language, "rag_no_context"))

                # Add to history
                messages.append({"role": "user", "content": user_content})

                mini_agent_response = None
                if not opts.mini_agent_off:
                    # Mini agent chỉ chạy với text thuần túy
                    mini_agent_response = mini_agent.run_http_mini_agent(
                        prompt_text=user_text_part,
                        user_intent=user_text_part,
                        config=config,
                    )

                if mini_agent_response:
                    console.print(mini_agent_response)
                    messages.append({"role": "assistant", "content": mini_agent_response})
                    utils.execute_suggested_commands(mini_agent_response, console)
                    continue

                max_tool_loops = 3
                tool_loop_count = 0

                while True:
                    # Inject System Instruction & Tool Hint vào context
                    # Vì http_providers._build_http_messages sẽ tự thêm system instruction nếu chưa có
                    # nhưng ở đây ta quản lý messages stateful, nên ta sẽ truyền messages list trực tiếp.
                    # Tuy nhiên, ta cần inject tool_usage_hint vào system instruction hoặc user message cuối.
                    # Cách tốt nhất: Inject vào system instruction tạm thời cho lần gọi này? 
                    # Hoặc append vào user text cuối cùng?
                    # Để đơn giản, ta append tool hint vào message cuối nếu nó là user text.
                    # Nhưng ta không muốn lưu hint vào lịch sử hiển thị.
                    
                    # Clone messages để gửi API
                    messages_for_api = messages[:]
                    
                    # Thêm tool hint vào system instruction
                    effective_system = system_instruction if system_instruction else ""
                    effective_system += f"\n\n{tool_usage_hint}"

                    try:
                        response_text = api.generate_text(
                            model_name,
                            messages_for_api,  # Truyền list messages
                            system_instruction=effective_system,
                        )
                    except (
                        api.DeepseekInsufficientBalance,
                        api.GroqInsufficientBalance,
                        api.OpenRouterInsufficientBalance,
                    ) as e:  # noqa: BLE001
                        if isinstance(e, api.DeepseekInsufficientBalance):
                            provider = "DeepSeek"
                        elif isinstance(e, api.GroqInsufficientBalance):
                            provider = "Groq"
                        else:
                            provider = "OpenRouter"

                        console.print(
                            i18n.tr(
                                language,
                                "http_insufficient_balance_chat",
                                provider=provider,
                            )
                        )

                        fallback_model = self.get_gemini_fallback_model(config)
                        offer_prompt = i18n.tr(
                            language,
                            "http_chat_offer_switch_to_gemini",
                            fallback_model=fallback_model,
                        )
                        choice = (
                            console.input(offer_prompt, markup=False)
                            .strip()
                            .lower()
                        )
                        if choice not in ("y", "yes"):
                            return
                        
                        # Fallback logic cũ (giữ nguyên)
                        console.print(
                            i18n.tr(
                                language,
                                "http_switch_to_gemini_chat",
                                fallback_model=fallback_model,
                            )
                        )
                        from termi_cli.handlers.core_handler import (  # avoid circular
                            build_system_instruction,
                        )
                        from termi_cli import api as _api

                        system_instruction_gemini = build_system_instruction(
                            config, args
                        )
                        chat_session = _api.start_chat_session(
                            fallback_model,
                            system_instruction_gemini,
                            history=None,
                            cli_help_text=getattr(args, "cli_help_text", ""),
                        )

                        self.run_chat_mode(chat_session, console, config, args)
                        return
                    except Exception as e:  # noqa: BLE001
                        console.print(
                            i18n.tr(language, "chat_generic_error", error=e)
                        )
                        break

                    response_text = (response_text or "").strip()
                    if not response_text:
                        break

                    tool_name = None
                    tool_args: dict | None = {}

                    try:
                        cleaned = response_text.strip()
                        if (
                            cleaned.startswith("{")
                            and cleaned.endswith("}")
                            and "\"tool_name\"" in cleaned
                        ):
                            json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
                            if json_match:
                                data = parse_json_payload(json_match.group(0))
                                tool_name = data.get("tool_name")
                                tool_args = data.get("tool_args") or {}
                    except JsonPayloadParseError:
                        tool_name = None
                        tool_args = {}
                    except Exception:
                        tool_name = None
                        tool_args = {}

                    if tool_name and tool_loop_count < max_tool_loops:
                        tool_loop_count += 1
                        if tool_name not in api.AVAILABLE_TOOLS:
                            console.print(
                                f"[yellow]Tool '{tool_name}' không tồn tại trong AVAILABLE_TOOLS.[/yellow]"
                            )
                            # Add assistant response w/ invalid tool
                            messages.append({"role": "assistant", "content": response_text})
                            console.print(response_text)
                            utils.execute_suggested_commands(
                                response_text, console
                            )
                            break

                        try:
                            tool_function = api.AVAILABLE_TOOLS[tool_name]
                            kwargs = tool_args or {}
                            result = tool_function(**kwargs)
                            if isinstance(result, str) and result.startswith(
                                "USER_CONFIRMATION_REQUIRED:WRITE_FILE:"
                            ):
                                file_path_to_write = result.split(":", 2)[2]
                                content_to_write = (kwargs or {}).get(
                                    "content", ""
                                )
                                result = confirm_and_write_file(
                                    console,
                                    file_path_to_write,
                                    content_to_write,
                                )
                        except Exception as e:  # noqa: BLE001
                            result = f"Error executing tool '{tool_name}': {e}"

                        observation = str(result)
                        if getattr(args, "verbose", False):
                            console.print(
                                f"[bold cyan]Tool '{tool_name}' result:[/bold cyan] {observation}"
                            )
                        else:
                            console.print(f"[dim]⚙️  Used tool '{tool_name}'...[/dim]")
                        
                        # Append tool result as tool role or user role depending on provider support.
                        # For simplicity in "deepseek" mode (often generic OpenAI), we append as 'user' role saying "Tool output: ..." 
                        # OR if the model supports 'tool' role. Generic OpenAI usually supports 'tool' role if function calling is used, 
                        # but here we are doing "implied" tool use via JSON. 
                        # Best approach for generic chat models: Append as User message containing the observation.
                        messages.append(
                            {
                                "role": "user",
                                "content": f"--- Tool '{tool_name}' Output ---\n{observation}\n---"
                            }
                        )
                        continue

                    # Normal response handling
                    messages.append({"role": "assistant", "content": response_text})
                    console.print(response_text)
                    utils.execute_suggested_commands(response_text, console)
                    break

        except (KeyboardInterrupt, EOFError):
            console.print(i18n.tr(language, "interrupted_by_user"))

        if not messages:
            return

        if not os.path.exists(HISTORY_DIR):
            os.makedirs(HISTORY_DIR)

        title = ""
        try:
            user_title = console.input(
                i18n.tr(language, "chat_save_name_prompt")
            ).strip()
            if user_title:
                title = user_title
            else:
                console.print(i18n.tr(language, "chat_ai_thinking_title"))

                conversation_summary = ""
                for msg in messages:
                    role = msg.get("role", "unknown")
                    content = msg.get("content", "")
                    text_content = ""
                    if isinstance(content, str):
                        text_content = content
                    elif isinstance(content, list):
                        for part in content:
                            if isinstance(part, dict):
                                if part.get("type") == "text":
                                    text_content += part.get("text", "") + "\n"
                                elif part.get("type") == "image_url":
                                    text_content += "[Image Attachment]\n"
                    
                    if role == "user":
                        conversation_summary += f"User: {text_content}\n"
                    elif role == "assistant":
                        conversation_summary += f"AI: {text_content}\n"

                prompt_for_title = (
                    "Based on the following full conversation transcript, create a very short, "
                    "descriptive title (under 7 words) that captures the main topic. "
                    "Return only the title itself, with no quotes.\n\n"
                    f"--- CONVERSATION ---\n{conversation_summary}"
                )

                title_text = api.generate_text(
                    config.get("default_model"), prompt_for_title
                )
                title = (title_text or "").strip().replace("\"", "")

            if not title:
                console.print(i18n.tr(language, "chat_no_save_conversation"))
                return

            filename = f"chat_{utils.sanitize_filename(title)}.json"
            save_path = os.path.join(HISTORY_DIR, filename)

            history_payload = []
            for msg in messages:
                role = msg.get("role", "model")
                if role == "assistant":
                    role = "model"
                content = msg.get("content", "")
                parts = []
                
                if isinstance(content, str):
                    parts.append({"text": content})
                elif isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict):
                            if part.get("type") == "text":
                                parts.append({"text": part.get("text", "")})
                            elif part.get("type") == "image_url":
                                # Placeholder for history text view
                                parts.append({"text": "[Image Attachment]"})

                entry = {
                    "role": role,
                    "parts": parts,
                }
                history_payload.append(entry)

            history_data = {
                "title": title,
                "last_modified": datetime.now().isoformat(),
                "history": history_payload,
            }

            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(history_data, f, indent=2, ensure_ascii=False)

            console.print(
                i18n.tr(language, "chat_history_saved_to", path=save_path)
            )

        except (KeyboardInterrupt, EOFError):
            console.print(i18n.tr(language, "chat_no_save_conversation"))
        except Exception as e:  # noqa: BLE001
            console.print(
                i18n.tr(
                    language,
                    "chat_cannot_save_history_error",
                    error=e,
                )
            )

