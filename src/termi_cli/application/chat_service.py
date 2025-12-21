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

    def run_chat_mode_legacy(
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

    def run_chat_mode(
        self,
        console: Console,
        config: dict,
        args: argparse.Namespace,
        system_instruction: str,
    ) -> None:
        """Chế độ chat dùng HTTP providers (DeepSeek/Groq/OpenRouter) với Multi-modal support."""

        opts = HttpChatOptions.from_args(config, args)
        language = opts.language
        
        # Theme & Auto-complete initialization (moved up)
        from termi_cli.application import theme_manager, autocomplete
        style_prompt = theme_manager.get_theme_style("user_prompt") or "bold white"
        style_response = theme_manager.get_theme_style("ai_response") or "white"
        style_system = theme_manager.get_theme_style("system_message") or "dim"
        console.print(f"[{style_system}]{i18n.tr(language, 'chat_mode_intro')}[/{style_system}]")

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
                    console.print(f"\n[{style_prompt}]{user_label}[/{style_prompt}] {prompt}")
                else:
                    if autocomplete.is_autocomplete_available():
                        # Print label with Rich style first
                        console.print(f"\n[{style_prompt}]{user_label}[/{style_prompt}] ", end="")
                        # Let prompt_toolkit handle input
                        prompt = autocomplete.get_input_with_autocomplete("")
                        # Clear the extra newline potentially added by print
                    else:
                        prompt = console.input(f"\n[{style_prompt}]{user_label}[/{style_prompt}] ")
                
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

                # Alias management
                if prompt.strip().lower().startswith("/alias"):
                    from termi_cli.application import alias_manager
                    parts = prompt.strip().split()
                    if len(parts) == 1:
                        # List aliases
                        aliases = alias_manager.list_aliases()
                        if aliases:
                            console.print(i18n.tr(language, "alias_list_title"))
                            for name, cmd in aliases.items():
                                console.print(f"  {name} -> {cmd}")
                        else:
                            console.print(i18n.tr(language, "alias_empty"))
                    elif len(parts) >= 3 and parts[1] == "add":
                        name = parts[2]
                        if len(parts) <= 3:
                            console.print("[yellow]Error: Alias command cannot be empty.[/yellow]")
                            console.print(i18n.tr(language, "alias_usage"))
                            continue
                        cmd = " ".join(parts[3:])
                        alias_manager.add_alias(name, cmd)
                        console.print(i18n.tr(language, "alias_added", name=name, cmd=cmd))
                    elif len(parts) == 3 and parts[1] == "remove":
                        name = parts[2]
                        if alias_manager.remove_alias(name):
                            console.print(i18n.tr(language, "alias_removed", name=name))
                        else:
                            console.print(i18n.tr(language, "alias_not_found", name=name))
                    else:
                        console.print(i18n.tr(language, "alias_usage"))
                    continue

                # Template management
                if prompt.strip().lower().startswith("/template"):
                    from termi_cli.application import template_manager
                    parts = prompt.strip().split(maxsplit=3)
                    if len(parts) == 1:
                        # List templates
                        templates = template_manager.list_templates()
                        if templates:
                            console.print(i18n.tr(language, "template_list_title"))
                            for name, data in templates.items():
                                desc = data.get("description", "")[:40]
                                console.print(f"  {name}: {desc}")
                        else:
                            console.print(i18n.tr(language, "template_empty"))
                    elif len(parts) >= 3 and parts[1] == "use":
                        name = parts[2]
                        template = template_manager.get_template(name)
                        if template:
                            console.print(i18n.tr(language, "template_applied", name=name))
                            prompt = template["content"]
                            # Don't continue, let this prompt be processed
                        else:
                            console.print(i18n.tr(language, "template_not_found", name=name))
                            continue
                    elif len(parts) >= 4 and parts[1] == "add":
                        name = parts[2]
                        content = parts[3]
                        template_manager.add_template(name, content)
                        console.print(i18n.tr(language, "template_added", name=name))
                        continue
                    elif len(parts) == 3 and parts[1] == "remove":
                        name = parts[2]
                        if template_manager.remove_template(name):
                            console.print(i18n.tr(language, "template_removed", name=name))
                        else:
                            console.print(i18n.tr(language, "template_not_found", name=name))
                        continue
                    else:
                        console.print(i18n.tr(language, "template_usage"))
                        continue

                # Theme management
                if prompt.strip().lower().startswith("/theme"):
                    from termi_cli.application import theme_manager
                    parts = prompt.strip().split(maxsplit=1)
                    if len(parts) == 1:
                        # List themes and show current
                        console.print(i18n.tr(language, "theme_list_title"))
                        current = theme_manager.get_current_theme()
                        for name in theme_manager.list_themes():
                            marker = " ✓" if name == current else ""
                            theme = theme_manager.get_theme_info(name)
                            console.print(f"  {name}{marker}")
                        console.print(i18n.tr(language, "theme_current", name=current))
                    else:
                        theme_name = parts[1].strip().lower()
                        if theme_manager.set_theme(theme_name):
                            console.print(i18n.tr(language, "theme_switched", name=theme_name))
                            # Show preview
                            console.print(theme_manager.preview_theme(theme_name))
                        else:
                            console.print(i18n.tr(language, "theme_not_found", name=theme_name))
                            console.print(i18n.tr(language, "theme_usage"))
                    continue

                # Memory management
                if prompt.strip().lower().startswith("/memory"):
                    from termi_cli.application import memory_manager
                    parts = prompt.strip().split()
                    cmd = parts[1] if len(parts) > 1 else ""
                    
                    if not cmd or cmd == "list":
                        limit = 10
                        if len(parts) > 2 and parts[2].isdigit():
                            limit = int(parts[2])
                        memories = memory_manager.list_memories(limit)
                        console.print(i18n.tr(language, "memory_list_title"))
                        if not memories:
                             console.print("  [dim]Start adding memories with /memory add ...[/dim]")
                        for m in memories:
                            date_str = m.get("created_at", "")
                            console.print(f"  [dim]#{m['id']} ({date_str}):[/dim] {m['content']}")

                    elif cmd == "add":
                        # /memory add <content...>
                        if len(parts) < 3:
                            console.print(i18n.tr(language, "memory_usage"))
                        else:
                            # Re-parse to get full content
                            content = prompt.strip().split(maxsplit=2)[2]
                            memory_manager.add_memory(content)
                            console.print(i18n.tr(language, "memory_added", content=content))

                    elif cmd == "delete":
                        if len(parts) < 3 or not parts[2].isdigit():
                            console.print(i18n.tr(language, "memory_usage"))
                        else:
                            mid = int(parts[2])
                            if memory_manager.delete_memory(mid):
                                 console.print(i18n.tr(language, "memory_deleted", id=mid))
                            else:
                                 console.print(i18n.tr(language, "memory_not_found", id=mid))

                    elif cmd == "search":
                        if len(parts) < 3:
                            console.print(i18n.tr(language, "memory_usage"))
                        else:
                            query = prompt.strip().split(maxsplit=2)[2]
                            results = memory_manager.search_memories(query)
                            console.print(i18n.tr(language, "chat_history_found", count=len(results)))
                            for m in results:
                                console.print(f"  [dim]#{m['id']}:[/dim] {m['content']}")

                    else:
                        console.print(i18n.tr(language, "memory_usage"))
                    continue

                # Plugin management
                if prompt.strip().lower().startswith("/plugins"):
                     # Reload plugins
                     # Reload plugins
                     try:
                         # Hacky re-load: update AVAILABLE_TOOLS directly
                         new_tools = api._load_plugin_tools() # This calls plugin_manager.load_plugins
                         count = 0
                         for name, func in new_tools.items():
                             # Allow override during manual reload
                             api.AVAILABLE_TOOLS[name] = func
                             count += 1
                         
                         console.print("[bold cyan]Plugins System:[/bold cyan]")
                         from termi_cli.application import plugin_manager
                         # List .py files
                         if plugin_manager.PLUGINS_DIR.exists():
                             files = list(plugin_manager.PLUGINS_DIR.glob("*.py"))
                             console.print(f"  Files found: {len(files)}")
                             for f in files:
                                 console.print(f"  - {f.name}")
                         
                         console.print(f"  [green]Tools Loaded & Synced.[/green]")
                     except Exception as e:
                         console.print(f"[red]Plugin Error: {e}[/red]")
                     continue

                # Search/view history
                if prompt.strip().lower().startswith("/history"):
                    parts = prompt.strip().split(maxsplit=1)
                    if len(parts) == 1:
                        # Show recent messages
                        console.print(i18n.tr(language, "chat_history_title"))
                        for i, msg in enumerate(messages[-10:], 1):
                            role = msg.get("role", "user")
                            content = msg.get("content", "")
                            if isinstance(content, list):
                                content = "[multi-modal]"
                            content = content[:80] + "..." if len(content) > 80 else content
                            console.print(f"  {i}. [{role}] {content}")
                    else:
                        # Search history
                        search_term = parts[1].lower()
                        matches = []
                        for msg in messages:
                            content = msg.get("content", "")
                            if isinstance(content, str) and search_term in content.lower():
                                matches.append(msg)
                        if matches:
                            console.print(i18n.tr(language, "chat_history_found", count=len(matches)))
                            for m in matches[:5]:
                                content = m.get("content", "")[:100]
                                console.print(f"  - [{m.get('role')}] {content}...")
                        else:
                            console.print(i18n.tr(language, "chat_history_no_match"))
                    continue

                # Check for updates
                if prompt.strip().lower() == "/update":
                    from termi_cli.application import update_checker
                    console.print(i18n.tr(language, "chat_checking_update"))
                    msg = update_checker.get_update_message(language)
                    console.print(msg)
                    continue

                # Help command
                if prompt.strip().lower() == "/help":
                    console.print(i18n.tr(language, "chat_help_title"))
                    console.print(i18n.tr(language, "chat_help_content"))
                    continue

                # Clear chat history
                if prompt.strip().lower() == "/clear":
                    messages = []
                    console.print(i18n.tr(language, "chat_cleared"))
                    continue

                # Export conversation
                if prompt.strip().lower().startswith("/export"):
                    try:
                        import json
                        from pathlib import Path
                        parts = prompt.strip().split(maxsplit=1)
                        export_name = parts[1] if len(parts) > 1 else f"chat_export_{int(__import__('time').time())}"
                        if not export_name.endswith((".json", ".md")):
                            export_name += ".json"
                        export_path = Path.cwd() / export_name
                        
                        if export_name.endswith(".md"):
                            # Export as markdown
                            with open(export_path, "w", encoding="utf-8") as f:
                                f.write("# Chat Export\n\n")
                                for msg in messages:
                                    role = msg.get("role", "user").upper()
                                    content = msg.get("content", "")
                                    if isinstance(content, list):
                                        content = "[multi-modal content]"
                                    f.write(f"## {role}\n{content}\n\n")
                        else:
                            # Export as JSON
                            with open(export_path, "w", encoding="utf-8") as f:
                                json.dump(messages, f, ensure_ascii=False, indent=2)
                        
                        console.print(i18n.tr(language, "chat_exported", path=str(export_path)))
                    except Exception as e:
                        console.print(i18n.tr(language, "chat_export_error", error=str(e)))
                    continue

                # Show/switch model
                if prompt.strip().lower().startswith("/model"):
                    parts = prompt.strip().split(maxsplit=1)
                    if len(parts) == 1:
                        # Just show current model
                        console.print(i18n.tr(language, "chat_model_current", model=model_name))
                    else:
                        # Switch model
                        new_model = parts[1].strip()
                        model_name = new_model
                        console.print(i18n.tr(language, "chat_model_switched", model=new_model))
                    continue

                # Save session
                if prompt.strip().lower().startswith("/save"):
                    try:
                        import json
                        from termi_cli.config import APP_DIR
                        parts = prompt.strip().split(maxsplit=1)
                        session_name = parts[1] if len(parts) > 1 else "default"
                        session_dir = APP_DIR / "chat_sessions"
                        session_dir.mkdir(exist_ok=True)
                        session_file = session_dir / f"{session_name}.json"
                        with open(session_file, "w", encoding="utf-8") as f:
                            json.dump(messages, f, ensure_ascii=False, indent=2)
                        console.print(i18n.tr(language, "chat_session_saved", name=session_name))
                    except Exception as e:
                        console.print(f"[red]{e}[/red]")
                    continue

                # Load session
                if prompt.strip().lower().startswith("/load"):
                    try:
                        import json
                        from termi_cli.config import APP_DIR
                        parts = prompt.strip().split(maxsplit=1)
                        if len(parts) == 1:
                            # List sessions
                            session_dir = APP_DIR / "chat_sessions"
                            if session_dir.exists():
                                sessions = list(session_dir.glob("*.json"))
                                if sessions:
                                    console.print(i18n.tr(language, "chat_session_list_title"))
                                    for s in sessions:
                                        console.print(f"  - {s.stem}")
                                else:
                                    console.print(i18n.tr(language, "chat_no_sessions"))
                            else:
                                console.print(i18n.tr(language, "chat_no_sessions"))
                        else:
                            session_name = parts[1].strip()
                            session_file = APP_DIR / "chat_sessions" / f"{session_name}.json"
                            if session_file.exists():
                                with open(session_file, "r", encoding="utf-8") as f:
                                    messages = json.load(f)
                                console.print(i18n.tr(language, "chat_session_loaded", name=session_name, count=len(messages)))
                            else:
                                console.print(i18n.tr(language, "chat_session_not_found", name=session_name))
                    except Exception as e:
                        console.print(f"[red]{e}[/red]")
                    continue

                # Voice input command
                if prompt.strip().lower() == "/voice":
                    try:
                        from termi_cli.voice import stt
                        if not stt.is_recording_available():
                            console.print(i18n.tr(language, "chat_voice_not_available"))
                            continue
                        
                        console.print(i18n.tr(language, "voice_listening"))
                        recorder = stt.AudioRecorder()
                        audio_data = recorder.record_until_silence()
                        
                        if audio_data:
                            console.print(i18n.tr(language, "voice_transcribing"))
                            engine = stt.get_stt_engine()
                            text = engine.transcribe(audio_data)
                            if text and not text.startswith("[Error"):
                                console.print(i18n.tr(language, "voice_you_said", text=text))
                                prompt = text  # Use transcribed text as prompt
                            else:
                                console.print(f"[yellow]{text}[/yellow]")
                                continue
                        else:
                            console.print(i18n.tr(language, "chat_no_audio"))
                            continue
                    except Exception as e:
                        console.print(i18n.tr(language, "voice_error", error=str(e)))
                        continue

                if prompt.lower().strip() in ["exit", "quit", "q"]:
                    break
                
                # Nếu prompt rỗng nhưng có pending data thì vẫn gửi
                if not prompt.strip() and not pending_images and not pending_files_content:
                    continue

                console.print(f"\n[{style_response}]{ai_label}[/{style_response}]")

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
                    rag_index_arg = getattr(args, "rag_index", "default")
                    if rag_index_arg == "default":
                        index_name = codebase_query.get_project_index_name()
                    else:
                        index_name = rag_index_arg
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
                        # Dùng spinner thay vì text tĩnh
                        spinner_text = i18n.tr(language, "chat_ai_thinking") # Cần thêm key này vào i18n nếu chưa có hoặc dùng tạm text
                        if not spinner_text or spinner_text.startswith("Key"): spinner_text = "Thinking..."
                        
                        with console.status(f"[{style_system}]{spinner_text}[/{style_system}]", spinner="dots"):
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
                            console.print(f"[{style_response}]{response_text}[/{style_response}]")
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
                    console.print(f"[{style_response}]{response_text}[/{style_response}]")
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

