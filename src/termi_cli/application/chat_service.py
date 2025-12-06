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
        """Chế độ chat dùng HTTP providers (DeepSeek/Groq/OpenRouter) với tool-calls JSON cơ bản."""

        opts = HttpChatOptions.from_args(config, args)
        language = opts.language
        console.print(i18n.tr(language, "chat_mode_intro"))

        model_name = opts.model_name
        dialogue: list[tuple[str, str]] = []  # (role, text) với role in {"user", "assistant"}

        tool_names = ", ".join(sorted(api.AVAILABLE_TOOLS.keys()))
        tool_usage_hint = (
            "If you need to run a tool (shell/files/web/etc.), return exactly one JSON object like "
            '{"tool_name": "<name>", "tool_args": { ... }} without Markdown fences. '
            f"Valid tool_name values: {tool_names}. If no tool is needed, answer normally."
        )

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

                dialogue.append(("user", prompt))

                mini_agent_response = None
                if not opts.mini_agent_off:
                    mini_agent_response = mini_agent.run_http_mini_agent(
                        prompt_text=prompt,
                        user_intent=prompt,
                        config=config,
                    )

                if mini_agent_response:
                    console.print(mini_agent_response)
                    dialogue.append(("assistant", mini_agent_response))
                    utils.execute_suggested_commands(mini_agent_response, console)
                    continue

                max_tool_loops = 3
                tool_loop_count = 0

                while True:
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
                        f"{tool_usage_hint}\n\n"
                        "Your reply (do not repeat previous messages):"
                    )

                    try:
                        response_text = api.generate_text(
                            model_name,
                            composite_prompt,
                            system_instruction=system_instruction,
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
                            dialogue.append(("assistant", response_text))
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
                        console.print(
                            f"[bold cyan]Tool '{tool_name}' result:[/bold cyan] {observation}"
                        )
                        dialogue.append(
                            (
                                "assistant",
                                f"[TOOL {tool_name}] {observation}",
                            )
                        )
                        continue

                    dialogue.append(("assistant", response_text))
                    console.print(response_text)
                    utils.execute_suggested_commands(response_text, console)
                    break

        except (KeyboardInterrupt, EOFError):
            console.print(i18n.tr(language, "interrupted_by_user"))

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
