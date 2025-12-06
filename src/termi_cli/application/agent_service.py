"""Application-level service cho các chế độ Agent.

Tách logic Agent khỏi presentation layer/CLI để dễ test và mở rộng.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import dataclass

from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from termi_cli import api, i18n
from termi_cli.api import RPDQuotaExhausted
from termi_cli.config import load_config
from termi_cli.json_utils import JsonPayloadParseError, parse_json_payload
from termi_cli.prompts import (
    build_agent_instruction,
    build_executor_instruction,
    build_master_agent_prompt,
)
from termi_cli.handlers.core_handler import confirm_and_write_file


def _format_plan_for_display(project_plan: dict) -> Panel:
    """Chuyển kế hoạch dự án dạng JSON thành Panel rich dễ đọc."""

    config = load_config()
    language = config.get("language", "vi")

    project_name = project_plan.get(
        "project_name", i18n.tr(language, "agent_project_name_default")
    )
    reasoning = project_plan.get(
        "reasoning", i18n.tr(language, "agent_reasoning_default")
    )

    header_text = Text()
    header_text.append(
        i18n.tr(language, "agent_header_project_name_label"), style="bold cyan"
    )
    header_text.append(f"{project_name}\n", style="yellow")
    header_text.append(
        i18n.tr(language, "agent_header_reasoning_label"), style="bold cyan"
    )
    header_text.append(f"{reasoning}\n", style="default")

    structure_header = Text(  # type: ignore[call-arg]
        i18n.tr(language, "agent_structure_header"), style="bold cyan"
    )

    tree = Tree("", guide_style="cyan")

    def generate_tree(structure: dict, parent_node: Tree) -> None:
        sorted_items = sorted(
            structure.items(),
            key=lambda item: isinstance(item[1], dict),
            reverse=True,
        )
        for name, content in sorted_items:
            if isinstance(content, dict):
                node = parent_node.add(f" [bold magenta]{name}[/]")
                generate_tree(content, node)
            else:
                parent_node.add(f" [default]{name}[/]")

    if structure := project_plan.get("structure"):
        try:
            root_folder_name = next(iter(structure))
            root_node = tree.add(f" [bold magenta]{root_folder_name}[/]")
            generate_tree(structure[root_folder_name], root_node)
        except (StopIteration, AttributeError):
            tree.add(i18n.tr(language, "agent_structure_tree_error"))

    display_group = Group(header_text, structure_header, tree)

    return Panel(
        display_group,
        title=i18n.tr(language, "agent_plan_panel_title"),
        border_style="green",
        expand=False,
    )


def _build_plan_checklist(project_plan: dict, language: str) -> Table | None:
    """Tạo bảng checklist các file trong kế hoạch dự án (nếu có)."""

    files = project_plan.get("files") or []
    if not files:
        return None

    table = Table(title=i18n.tr(language, "agent_plan_title_panel"))
    table.add_column("[ ]", style="cyan", no_wrap=True)
    table.add_column("Path", style="magenta")
    table.add_column("Description", style="green")

    for file_info in files:
        path = str(file_info.get("path", "")).strip()
        desc = str(file_info.get("description", "")).strip()
        table.add_row("☐", path, desc)

    return table


def _extract_first_json_match(text: str):
    json_match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not json_match:
        json_match = re.search(r"(\{.*?\})", text, re.DOTALL)
    return json_match


class AgentJsonParseError(ValueError):
    """Raised khi JSON của Agent không thể parse an toàn."""


_MAX_AGENT_JSON_RETRIES = 3


def _parse_agent_json_payload(payload: str) -> dict:
    """Parse JSON với fallback loại bỏ dấu phẩy dư thừa trước khi đóng khối."""

    try:
        return parse_json_payload(payload)
    except JsonPayloadParseError as original_err:  # noqa: TRY003
        raise AgentJsonParseError(str(original_err)) from original_err


def _print_json_retry_notice(
    console: Console, language: str, attempt: int, max_attempts: int
) -> None:
    if language == "vi":
        console.print(
            f"[yellow]JSON từ Agent không hợp lệ (lần {attempt}/{max_attempts}). Đang yêu cầu lại...[/yellow]"
        )
    else:
        console.print(
            f"[yellow]Agent returned invalid JSON (attempt {attempt}/{max_attempts}). Retrying...[/yellow]"
        )


def _get_safe_agent_model(console: Console, config: dict) -> str:
    """Đảm bảo Agent luôn dùng model an toàn.

    - Nếu agent_model là HTTP provider (DeepSeek/Groq/OpenRouter), chỉ dùng khi agent_allow_http=True.
    - Model local Ollama (ollama/*) luôn được phép dùng trực tiếp.
    - Ngược lại, fallback sang model Gemini an toàn.
    """

    language = config.get("language", "vi")
    agent_model = config.get("agent_model", "models/gemini-pro-latest")

    if isinstance(agent_model, str) and api.is_ollama_model(agent_model):
        return agent_model

    provider = "gemini"
    if isinstance(agent_model, str):
        if agent_model.startswith("deepseek-"):
            provider = "deepseek"
        elif agent_model.startswith("groq-"):
            provider = "groq"
        elif api.is_openrouter_model(agent_model):
            provider = "openrouter"

    if provider == "gemini":
        return agent_model

    allow_http_for_agent = config.get("agent_allow_http", False)
    if allow_http_for_agent:
        return agent_model

    fallback = config.get("default_model")
    if not (
        isinstance(fallback, str)
        and (fallback.startswith("models/") or "gemini" in fallback.lower())
    ):
        for candidate in config.get("model_fallback_order", []):
            if isinstance(candidate, str) and (
                candidate.startswith("models/")
                or "gemini" in candidate.lower()
            ):
                fallback = candidate
                break
    if not (
        isinstance(fallback, str)
        and (fallback.startswith("models/") or "gemini" in fallback.lower())
    ):
        fallback = "models/gemini-pro-latest"

    console.print(
        i18n.tr(
            language,
            "agent_http_provider_not_supported_for_agent",
            model=agent_model,
            fallback_model=fallback,
        )
    )
    return fallback


def _get_gemini_fallback_model(config: dict) -> str:
    """Chọn một model Gemini an toàn để fallback khi HTTP provider hết quota/balance cho Agent."""

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


def _execute_tool(
    console: Console, tool_name: str, tool_args: dict, dry_run: bool = False
) -> str:
    if tool_name not in api.AVAILABLE_TOOLS:
        raise ValueError(
            f"Agent tried to call a non-existent tool: {tool_name}"
        )
    tool_function = api.AVAILABLE_TOOLS[tool_name]
    language = load_config().get("language", "vi")

    if dry_run:
        return i18n.tr(
            language,
            "agent_dry_run_tool_observation",
            tool_name=tool_name,
            tool_args=tool_args,
        )

    if tool_name == "write_file":
        result = tool_function(**tool_args)
        if isinstance(result, str) and result.startswith(
            "USER_CONFIRMATION_REQUIRED:WRITE_FILE:"
        ):
            file_path_to_write = result.split(":", 2)[2]
            content_to_write = tool_args.get("content", "")
            return confirm_and_write_file(
                console, file_path_to_write, content_to_write
            )
        return str(result)

    with console.status(
        i18n.tr(language, "agent_tool_status_running", tool_name=tool_name)
    ):
        return tool_function(**tool_args)


@dataclass
class AgentExecutionContext:
    """DTO gom tuỳ chọn chạy Agent từ config + args.

    Dùng chung cho execute_project_plan và execute_simple_task để tránh lặp lại
    logic đọc config, tính toán language/dry_run/model/max_steps.
    """

    config: dict
    language: str
    dry_run: bool
    agent_model_name: str
    use_http_agent: bool
    max_steps: int

    @classmethod
    def from_args(
        cls,
        console: Console,
        args: argparse.Namespace,
        default_max_steps: int,
    ) -> "AgentExecutionContext":
        config = load_config()
        language = config.get("language", "vi")
        dry_run = getattr(args, "agent_dry_run", False)

        agent_model_name = _get_safe_agent_model(console, config)
        allow_http_for_agent = config.get("agent_allow_http", False)
        use_http_agent = (
            isinstance(agent_model_name, str)
            and (
                (
                    allow_http_for_agent
                    and (
                        agent_model_name.startswith("deepseek-")
                        or agent_model_name.startswith("groq-")
                        or api.is_openrouter_model(agent_model_name)
                    )
                )
                or api.is_ollama_model(agent_model_name)
            )
        )

        max_steps = getattr(args, "agent_max_steps", None) or default_max_steps

        return cls(
            config=config,
            language=language,
            dry_run=dry_run,
            agent_model_name=agent_model_name,
            use_http_agent=use_http_agent,
            max_steps=max_steps,
        )


class AgentService:
    """Service chính cho các chế độ Agent (master agent + executor)."""

    def run_master_agent(
        self, console: Console, args: argparse.Namespace
    ) -> None:
        """Phân tích yêu cầu Agent và điều hướng sang project_plan hoặc simple_task."""

        config = load_config()
        language = config.get("language", "vi")
        dry_run = getattr(args, "agent_dry_run", False)
        agent_model_name = _get_safe_agent_model(console, config)

        header_body = i18n.tr(
            language,
            "agent_master_panel_body",
            goal=args.prompt,
        )

        mode_name = "DRY-RUN" if dry_run else "Normal"
        mode_label = i18n.tr(language, "agent_mode_label", mode=mode_name)
        header_body = f"{header_body}\n\n{mode_label}"

        console.print(Panel(header_body, border_style="blue"))
        console.print(
            f"[dim]🤖 Model: {agent_model_name.replace('models/', '')} (Agent)[/dim]"
        )
        if getattr(args, "agent_max_steps", None):
            console.print(
                i18n.tr(
                    language,
                    "agent_max_steps_override",
                    max_steps=args.agent_max_steps,
                )
            )

        initial_response: dict | None = None

        attempt = 0
        while True:
            try:
                attempt += 1
                agent_model_name = _get_safe_agent_model(console, config)
                master_prompt = build_master_agent_prompt(args.prompt)

                allow_http_for_agent = config.get("agent_allow_http", False)
                use_http_agent = (
                    isinstance(agent_model_name, str)
                    and (
                        (
                            allow_http_for_agent
                            and (
                                agent_model_name.startswith("deepseek-")
                                or agent_model_name.startswith("groq-")
                                or api.is_openrouter_model(agent_model_name)
                            )
                        )
                        or api.is_ollama_model(agent_model_name)
                    )
                )

                if use_http_agent:
                    raw_text = api.generate_text(
                        agent_model_name,
                        master_prompt,
                        system_instruction=build_agent_instruction(),
                    )
                else:
                    model = api.genai.GenerativeModel(agent_model_name)
                    response = api.resilient_generate_content(
                        model, master_prompt
                    )
                    raw_text = api.get_response_text(response)

                json_match = _extract_first_json_match(raw_text)
                if not json_match:
                    raise AgentJsonParseError(
                        "Agent không trả về JSON hợp lệ ban đầu."
                    )

                initial_response = _parse_agent_json_payload(
                    json_match.group(1)
                )
                break

            except RPDQuotaExhausted:
                continue

            except (
                api.DeepseekInsufficientBalance,
                api.GroqInsufficientBalance,
                api.OpenRouterInsufficientBalance,
            ) as e:
                if isinstance(e, api.DeepseekInsufficientBalance):
                    provider = "DeepSeek"
                elif isinstance(e, api.GroqInsufficientBalance):
                    provider = "Groq"
                else:
                    provider = "OpenRouter"

                console.print(
                    i18n.tr(
                        language,
                        "http_insufficient_balance_single_turn",
                        provider=provider,
                    )
                )

                if not getattr(api, "GEMINI_AVAILABLE", True):
                    console.print(
                        i18n.tr(
                            language,
                            "agent_unexpected_analysis_error",
                            error=e,
                        )
                    )
                    return

                fallback_model = _get_gemini_fallback_model(config)
                console.print(
                    i18n.tr(
                        language,
                        "http_switch_to_gemini_single_turn",
                        fallback_model=fallback_model,
                    )
                )

                config["agent_model"] = fallback_model
                config["agent_allow_http"] = False
                continue

            except AgentJsonParseError as parse_err:
                if attempt >= _MAX_AGENT_JSON_RETRIES:
                    console.print(str(parse_err))
                    return
                _print_json_retry_notice(
                    console, language, attempt, _MAX_AGENT_JSON_RETRIES
                )
                time.sleep(0.5)
                continue

            except Exception as e:  # noqa: BLE001
                console.print(
                    i18n.tr(
                        language,
                        "agent_unexpected_analysis_error",
                        error=e,
                    )
                )
                return

        if not initial_response:
            console.print(i18n.tr(language, "agent_no_response_after_retries"))
            return

        task_type = initial_response.get("task_type")
        if task_type == "project_plan":
            self.execute_project_plan(
                console, args, initial_response.get("plan", {})
            )
        elif task_type == "simple_task":
            self.execute_simple_task(
                console, args, initial_response.get("step", {})
            )
        else:
            console.print(
                i18n.tr(
                    language,
                    "agent_unknown_task_type",
                    task_type=task_type,
                )
            )

    def execute_project_plan(
        self, console: Console, args: argparse.Namespace, project_plan: dict
    ) -> None:
        """Thực thi một project plan nhiều bước sử dụng executor Agent."""
        ctx = AgentExecutionContext.from_args(
            console=console,
            args=args,
            default_max_steps=30,
        )

        config = ctx.config
        language = ctx.language
        dry_run = ctx.dry_run

        if not project_plan:
            console.print(i18n.tr(language, "agent_empty_project_plan_error"))
            return

        display_panel = _format_plan_for_display(project_plan)
        console.print(display_panel)

        checklist = _build_plan_checklist(project_plan, language)
        if checklist is not None:
            console.print(checklist)

        if dry_run:
            console.print(i18n.tr(language, "agent_dry_run_mode_header"))
        console.print(i18n.tr(language, "agent_execution_phase_start"))

        agent_model_name = ctx.agent_model_name
        use_http_agent = ctx.use_http_agent

        executor_instruction = build_executor_instruction()
        if not use_http_agent:
            chat_session = api.start_chat_session(
                model_name=agent_model_name,
                system_instruction=executor_instruction,
            )
        else:
            chat_session = None

        plan_str = json.dumps(project_plan, indent=2, ensure_ascii=False)
        scratchpad = (
            "I have been given a plan to execute.\n\n"
            "**PROJECT PLAN:**\n```json\n"
            f"{plan_str}\n```\n\nMy task is to implement this plan step-by-step."
        )
        max_steps = ctx.max_steps

        for step in range(max_steps):
            iteration_header = i18n.tr(
                language,
                "agent_iteration_header",
                step=step + 1,
                max_steps=max_steps,
            )
            if dry_run:
                iteration_header = f"{iteration_header} (DRY-RUN)"
            console.print(iteration_header)

            dynamic_prompt = (
                f"<scratchpad>\n{scratchpad}\n</scratchpad>\n"
                "Based on the plan and my scratchpad, what is the single next action I should take?"
            )

            json_attempt = 0
            while True:
                try:
                    if use_http_agent:
                        raw_text = api.generate_text(
                            agent_model_name,
                            dynamic_prompt,
                            system_instruction=executor_instruction,
                        )
                    else:
                        assert chat_session is not None
                        response = api.resilient_send_message(
                            chat_session, dynamic_prompt
                        )
                        raw_text = api.get_response_text(response)
                    json_match = _extract_first_json_match(raw_text)
                    if not json_match:
                        raise AgentJsonParseError("No valid JSON found.")

                    plan = _parse_agent_json_payload(json_match.group(1))
                    thought = plan.get("thought", "")
                    action = plan.get("action", {})

                    console.print(
                        Panel(
                            Markdown(thought),
                            title=i18n.tr(
                                language, "agent_executor_thought_title"
                            ),
                            border_style="magenta",
                        )
                    )

                    tool_name = action.get("tool_name", "")
                    tool_args = action.get("tool_args", {})

                    if tool_name == "finish":
                        final_answer = tool_args.get(
                            "answer",
                            i18n.tr(
                                language, "agent_project_finished_default"
                            ),
                        )
                        console.print(
                            Panel(
                                Markdown(final_answer),
                                title=i18n.tr(
                                    language, "agent_project_finished_title"
                                ),
                                border_style="green",
                            )
                        )

                        flag = (
                            "có"
                            if language == "vi" and dry_run
                            else "không"
                            if language == "vi"
                            else ("yes" if dry_run else "no")
                        )
                        console.print(
                            i18n.tr(
                                language,
                                "agent_session_summary",
                                steps=step + 1,
                                flag=flag,
                            )
                        )
                        return

                    observation = _execute_tool(
                        console, tool_name, tool_args, dry_run=dry_run
                    )
                    console.print(
                        Panel(
                            Markdown(str(observation)),
                            title=i18n.tr(
                                language, "agent_executor_result_title"
                            ),
                            border_style="blue",
                            expand=False,
                        )
                    )

                    scratchpad += (
                        f"\n\n**Step {step + 1}:**\n"
                        f"- **Thought:** {thought}\n"
                        f"- **Action:** Called `{tool_name}` with args `{tool_args}`.\n"
                        f"- **Observation:** {observation}"
                    )
                    break

                except AgentJsonParseError as parse_err:
                    json_attempt += 1
                    if json_attempt >= _MAX_AGENT_JSON_RETRIES:
                        console.print(
                            i18n.tr(
                                language,
                                "agent_executor_unrecoverable_error",
                                error=parse_err,
                            )
                        )
                        return
                    _print_json_retry_notice(
                        console,
                        language,
                        json_attempt,
                        _MAX_AGENT_JSON_RETRIES,
                    )
                    time.sleep(0.5)
                    continue

                except RPDQuotaExhausted:
                    if use_http_agent:
                        raise
                    console.print(
                        i18n.tr(language, "agent_recreate_session_quota")
                    )
                    chat_session = api.start_chat_session(
                        model_name=agent_model_name,
                        system_instruction=executor_instruction,
                    )
                except Exception as e:  # noqa: BLE001
                    console.print(
                        i18n.tr(
                            language,
                            "agent_executor_unrecoverable_error",
                            error=e,
                        )
                    )
                    return
        else:
            console.print(
                i18n.tr(
                    language,
                    "agent_max_steps_reached",
                    max_steps=max_steps,
                )
            )

    def execute_simple_task(
        self, console: Console, args: argparse.Namespace, first_step: dict
    ) -> None:
        """Thực thi một simple-task ReAct nhiều bước."""
        ctx = AgentExecutionContext.from_args(
            console=console,
            args=args,
            default_max_steps=10,
        )

        config = ctx.config
        language = ctx.language
        dry_run = ctx.dry_run

        if not first_step:
            console.print(i18n.tr(language, "agent_no_first_react_step"))
            return

        console.print(i18n.tr(language, "agent_simple_task_intro"))
        if dry_run:
            console.print(i18n.tr(language, "agent_dry_run_mode_header"))

        agent_model_name = _get_safe_agent_model(console, config)

        allow_http_for_agent = config.get("agent_allow_http", False)
        use_http_agent = (
            isinstance(agent_model_name, str)
            and (
                (
                    allow_http_for_agent
                    and (
                        agent_model_name.startswith("deepseek-")
                        or agent_model_name.startswith("groq-")
                        or api.is_openrouter_model(agent_model_name)
                    )
                )
                or api.is_ollama_model(agent_model_name)
            )
        )

        agent_instruction = build_agent_instruction()
        if not use_http_agent:
            chat_session = api.start_chat_session(
                model_name=agent_model_name,
                system_instruction=agent_instruction,
            )
        else:
            chat_session = None

        current_step_json = first_step
        max_steps = ctx.max_steps
        previous_observation: str | None = None
        _react_followup_template = (
            "This was the result of my last action:\n\n{observation}\n\n"
            "Based on this, what is my next thought and action?"
        )

        for step in range(max_steps):
            iteration_header = i18n.tr(
                language,
                "agent_iteration_header",
                step=step + 1,
                max_steps=max_steps,
            )
            if dry_run:
                iteration_header = f"{iteration_header} (DRY-RUN)"
            console.print(iteration_header)

            if step == 0:
                thought = current_step_json.get("thought", "")
                action = current_step_json.get("action", {})
            else:
                json_attempt = 0
                while True:
                    try:
                        if previous_observation is None:
                            console.print(
                                i18n.tr(
                                    language,
                                    "agent_executor_unrecoverable_error",
                                    error="Missing observation for next prompt",
                                )
                            )
                            return

                        followup_prompt = _react_followup_template.format(
                            observation=previous_observation
                        )
                        if use_http_agent:
                            raw_text = api.generate_text(
                                agent_model_name,
                                followup_prompt,
                                system_instruction=agent_instruction,
                            )
                        else:
                            assert chat_session is not None
                            response = api.resilient_send_message(
                                chat_session, followup_prompt
                            )
                            raw_text = api.get_response_text(response)

                        json_match = _extract_first_json_match(raw_text)
                        if not json_match:
                            raise AgentJsonParseError("No valid JSON found.")

                        current_step_json = _parse_agent_json_payload(
                            json_match.group(1)
                        )
                        thought = current_step_json.get("thought", "")
                        action = current_step_json.get("action", {})
                        break
                    except RPDQuotaExhausted:
                        if use_http_agent:
                            raise
                        console.print(
                            i18n.tr(language, "agent_recreate_session_quota")
                        )
                        chat_session = api.start_chat_session(
                            model_name=agent_model_name,
                            system_instruction=agent_instruction,
                        )
                    except AgentJsonParseError as parse_err:
                        json_attempt += 1
                        if json_attempt >= _MAX_AGENT_JSON_RETRIES:
                            console.print(
                                i18n.tr(
                                    language,
                                    "agent_executor_unrecoverable_error",
                                    error=parse_err,
                                )
                            )
                            return
                        _print_json_retry_notice(
                            console,
                            language,
                            json_attempt,
                            _MAX_AGENT_JSON_RETRIES,
                        )
                        time.sleep(0.5)
                        continue
                    except Exception as e:  # noqa: BLE001
                        console.print(
                            i18n.tr(
                                language,
                                "agent_executor_unrecoverable_error",
                                error=e,
                            )
                        )
                        return

            try:
                console.print(
                    Panel(
                        Markdown(thought),
                        title=i18n.tr(
                            language, "agent_executor_thought_title"
                        ),
                        border_style="magenta",
                    )
                )

                tool_name = action.get("tool_name", "")
                tool_args = action.get("tool_args", {})

                if tool_name == "finish":
                    final_answer = tool_args.get(
                        "answer",
                        i18n.tr(
                            language, "agent_simple_task_finished_default"
                        ),
                    )
                    console.print(
                        Panel(
                            Markdown(final_answer),
                            title=i18n.tr(
                                language, "agent_simple_task_finished_title"
                            ),
                            border_style="green",
                        )
                    )

                    flag = (
                        "có"
                        if language == "vi" and dry_run
                        else "không"
                        if language == "vi"
                        else ("yes" if dry_run else "no")
                    )
                    console.print(
                        i18n.tr(
                            language,
                            "agent_session_summary",
                            steps=step + 1,
                            flag=flag,
                        )
                    )
                    return

                observation = _execute_tool(
                    console, tool_name, tool_args, dry_run=dry_run
                )
                console.print(
                    Panel(
                        Markdown(str(observation)),
                        title=i18n.tr(language, "agent_observation_title"),
                        border_style="blue",
                        expand=False,
                    )
                )

                previous_observation = observation

            except Exception as e:  # noqa: BLE001
                console.print(
                    i18n.tr(
                        language,
                        "agent_react_unrecoverable_error",
                        error=e,
                    )
                )
                return
        else:
            console.print(
                i18n.tr(
                    language,
                    "agent_max_steps_reached",
                    max_steps=max_steps,
                )
            )
