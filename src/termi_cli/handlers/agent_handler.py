# src/termi_cli/handlers/agent_handler.py

"""
Module xử lý các chế độ Agent, với cơ chế retry và chuyển đổi API key toàn cục.
"""
import os
import json
import re
import argparse
import time

from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.json import JSON
from rich.text import Text
from rich.tree import Tree
from rich.table import Table
from google.api_core.exceptions import ResourceExhausted

from termi_cli import api, i18n
from termi_cli.api import RPDQuotaExhausted # Import exception tùy chỉnh
from termi_cli.prompts import build_agent_instruction, build_master_agent_prompt, build_executor_instruction
from termi_cli.config import load_config
from .core_handler import confirm_and_write_file

def _format_plan_for_display(project_plan: dict) -> Panel:
    """
    Chuyển đổi đối tượng JSON kế hoạch thành một Panel rich đẹp mắt, dễ đọc.
    """
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
    
    structure_header = Text(i18n.tr(language, "agent_structure_header"), style="bold cyan")
    
    tree = Tree("", guide_style="cyan")

    def generate_tree(structure: dict, parent_node: Tree):
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


def _build_plan_checklist(project_plan: dict, language: str):
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
    json_match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
    if not json_match:
        json_match = re.search(r'(\{.*?\})', text, re.DOTALL)
    return json_match


def _get_safe_agent_model(console: Console, config: dict) -> str:
    """Đảm bảo Agent luôn dùng model Gemini an toàn.

    Nếu config.agent_model là DeepSeek/Groq (HTTP provider), in cảnh báo và
    fallback sang một model Gemini (ưu tiên default_model nếu có dạng Gemini).
    """
    language = config.get("language", "vi")
    agent_model = config.get("agent_model", "models/gemini-pro-latest")

    provider = "gemini"
    if isinstance(agent_model, str):
        if agent_model.startswith("deepseek-"):
            provider = "deepseek"
        elif agent_model.startswith("groq-"):
            provider = "groq"

    if provider == "gemini":
        return agent_model

    # Tìm fallback Gemini an toàn
    fallback = config.get("default_model") or "models/gemini-pro-latest"
    if not isinstance(fallback, str) or not (
        fallback.startswith("models/") or "gemini" in fallback.lower()
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


def run_master_agent(console: Console, args: argparse.Namespace):
    """
    Hàm chính điều khiển Agent, với vòng lặp retry mạnh mẽ để xử lý lỗi Quota.
    """
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
    console.print(f"[dim]🤖 Model: {agent_model_name.replace('models/', '')} (Agent)[/dim]")
    if getattr(args, "agent_max_steps", None):
        console.print(
            i18n.tr(
                language,
                "agent_max_steps_override",
                max_steps=args.agent_max_steps,
            )
        )
    

    initial_response = None
    
    while True:
        try:
            agent_model_name = _get_safe_agent_model(console, config)
            model = api.genai.GenerativeModel(agent_model_name)
            
            master_prompt = build_master_agent_prompt(args.prompt)
            
            response = api.resilient_generate_content(model, master_prompt)

            raw_text = api.get_response_text(response)
            json_match = _extract_first_json_match(raw_text)
            if not json_match:
                raise ValueError("Agent không trả về JSON hợp lệ ban đầu.")

            initial_response = json.loads(json_match.group(1))
            break 

        except RPDQuotaExhausted:
            # API call đã tự xử lý việc chuyển key và in thông báo.
            # Chỉ cần lặp lại vòng lặp để thử lại với key mới.
            continue
        
        except Exception as e:
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
        execute_project_plan(console, args, initial_response.get("plan", {}))
    elif task_type == "simple_task":
        execute_simple_task(console, args, initial_response.get("step", {}))
    else:
        console.print(
            i18n.tr(
                language,
                "agent_unknown_task_type",
                task_type=task_type,
            )
        )


def _execute_tool(console: Console, tool_name: str, tool_args: dict, dry_run: bool = False) -> str:
    if tool_name not in api.AVAILABLE_TOOLS:
        raise ValueError(f"Agent tried to call a non-existent tool: {tool_name}")
    tool_function = api.AVAILABLE_TOOLS[tool_name]
    language = load_config().get("language", "vi")

    if dry_run:
        # Không thực thi tool thật, chỉ mô phỏng kết quả để an toàn.
        return i18n.tr(
            language,
            "agent_dry_run_tool_observation",
            tool_name=tool_name,
            tool_args=tool_args,
        )

    if tool_name == 'write_file':

        # Gọi tool write_file để trả về yêu cầu xác nhận, sau đó dùng helper chung để hỏi và ghi file.
        result = tool_function(**tool_args)
        if isinstance(result, str) and result.startswith("USER_CONFIRMATION_REQUIRED:WRITE_FILE:"):
            file_path_to_write = result.split(":", 2)[2]
            content_to_write = tool_args.get("content", "")
            return confirm_and_write_file(console, file_path_to_write, content_to_write)
        return str(result)
    else:
        with console.status(
            i18n.tr(language, "agent_tool_status_running", tool_name=tool_name)
        ):
            return tool_function(**tool_args)


def execute_project_plan(console: Console, args: argparse.Namespace, project_plan: dict):
    config = load_config()
    language = config.get("language", "vi")
    dry_run = getattr(args, "agent_dry_run", False)

    if not project_plan:
        console.print(i18n.tr(language, "agent_empty_project_plan_error")); return
        
    display_panel = _format_plan_for_display(project_plan)
    console.print(display_panel)

    checklist = _build_plan_checklist(project_plan, language)
    if checklist is not None:
        console.print(checklist)

    if dry_run:
        console.print(i18n.tr(language, "agent_dry_run_mode_header"))
    console.print(i18n.tr(language, "agent_execution_phase_start"))

    agent_model_name = _get_safe_agent_model(console, config)

    executor_instruction = build_executor_instruction()
    chat_session = api.start_chat_session(model_name=agent_model_name, system_instruction=executor_instruction)
    plan_str = json.dumps(project_plan, indent=2, ensure_ascii=False)
    scratchpad = f"I have been given a plan to execute.\n\n**PROJECT PLAN:**\n```json\n{plan_str}\n```\n\nMy task is to implement this plan step-by-step."
    max_steps = getattr(args, "agent_max_steps", None) or 30

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

        dynamic_prompt = f"<scratchpad>\n{scratchpad}\n</scratchpad>\nBased on the plan and my scratchpad, what is the single next action I should take?"
        
        while True:
            try:
                response = api.resilient_send_message(chat_session, dynamic_prompt)

                raw_text = api.get_response_text(response)
                json_match = _extract_first_json_match(raw_text)
                if not json_match:
                    raise ValueError("No valid JSON found.")

                plan = json.loads(json_match.group(1))
                thought = plan.get("thought", "")
                action = plan.get("action", {})
                
                console.print(
                    Panel(
                        Markdown(thought),
                        title=i18n.tr(language, "agent_executor_thought_title"),
                        border_style="magenta",
                    )
                )

                tool_name = action.get("tool_name", "")
                tool_args = action.get("tool_args", {})

                if tool_name == "finish":
                    final_answer = tool_args.get(
                        "answer",
                        i18n.tr(language, "agent_project_finished_default"),
                    )
                    console.print(
                        Panel(
                            Markdown(final_answer),
                            title=i18n.tr(language, "agent_project_finished_title"),
                            border_style="green",
                        )
                    )

                    flag = "có" if language == "vi" and dry_run else "không" if language == "vi" else ("yes" if dry_run else "no")
                    console.print(
                        i18n.tr(
                            language,
                            "agent_session_summary",
                            steps=step + 1,
                            flag=flag,
                        )
                    )
                    return

                observation = _execute_tool(console, tool_name, tool_args, dry_run=dry_run)
                console.print(
                    Panel(
                        Markdown(str(observation)),
                        title=i18n.tr(language, "agent_executor_result_title"),
                        border_style="blue",
                        expand=False,
                    )
                )

                scratchpad += f"\n\n**Step {step + 1}:**\n- **Thought:** {thought}\n- **Action:** Called `{tool_name}` with args `{tool_args}`.\n- **Observation:** {observation}"
                break

            except RPDQuotaExhausted:
                console.print(i18n.tr(language, "agent_recreate_session_quota"))
                chat_session = api.start_chat_session(model_name=agent_model_name, system_instruction=executor_instruction)
            except Exception as e:
                console.print(
                    i18n.tr(
                        language,
                        "agent_executor_unrecoverable_error",
                        error=e,
                    )
                )
                return
    else:
        console.print(i18n.tr(language, "agent_max_steps_reached", max_steps=max_steps))


def execute_simple_task(console: Console, args: argparse.Namespace, first_step: dict):
    config = load_config()
    language = config.get("language", "vi")
    dry_run = getattr(args, "agent_dry_run", False)

    if not first_step:
        console.print(i18n.tr(language, "agent_no_first_react_step")); return

    console.print(i18n.tr(language, "agent_simple_task_intro"))
    if dry_run:
        console.print(i18n.tr(language, "agent_dry_run_mode_header"))
    
    agent_model_name = _get_safe_agent_model(console, config)

    agent_instruction = build_agent_instruction()
    chat_session = api.start_chat_session(model_name=agent_model_name, system_instruction=agent_instruction)
    
    current_step_json = first_step
    max_steps = getattr(args, "agent_max_steps", None) or 10

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

        # Xử lý bước đầu tiên đã có sẵn
        if step == 0:
            thought = current_step_json.get("thought", "")
            action = current_step_json.get("action", {})
        # Các bước tiếp theo sẽ được lấy từ API call
        else:
            while True:
                try:
                    response = api.resilient_send_message(chat_session, next_prompt)
                    raw_text = api.get_response_text(response)
                    json_match = _extract_first_json_match(raw_text)
                    if not json_match:
                        raise ValueError("No valid JSON found.")

                    current_step_json = json.loads(json_match.group(1))
                    thought = current_step_json.get("thought", "")
                    action = current_step_json.get("action", {})
                    break
                except RPDQuotaExhausted:
                    console.print(i18n.tr(language, "agent_recreate_session_quota"))
                    chat_session = api.start_chat_session(model_name=agent_model_name, system_instruction=agent_instruction)
                except Exception as e:
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
                    title=i18n.tr(language, "agent_executor_thought_title"),
                    border_style="magenta",
                )
            )

            tool_name = action.get("tool_name", "")
            tool_args = action.get("tool_args", {})

            if tool_name == "finish":
                final_answer = tool_args.get(
                    "answer",
                    i18n.tr(language, "agent_simple_task_finished_default"),
                )
                console.print(
                    Panel(
                        Markdown(final_answer),
                        title=i18n.tr(language, "agent_simple_task_finished_title"),
                        border_style="green",
                    )
                )

                flag = "có" if language == "vi" and dry_run else "không" if language == "vi" else ("yes" if dry_run else "no")
                console.print(
                    i18n.tr(
                        language,
                        "agent_session_summary",
                        steps=step + 1,
                        flag=flag,
                    )
                )
                return

            observation = _execute_tool(console, tool_name, tool_args, dry_run=dry_run)
            console.print(
                Panel(
                    Markdown(str(observation)),
                    title=i18n.tr(language, "agent_observation_title"),
                    border_style="blue",
                    expand=False,
                )
            )

            next_prompt = f"This was the result of my last action:\n\n{observation}\n\nBased on this, what is my next thought and action?"

        except Exception as e:
            console.print(
                i18n.tr(language, "agent_react_unrecoverable_error", error=e)
            )
            return
    else:
        console.print(i18n.tr(language, "agent_max_steps_reached", max_steps=max_steps))