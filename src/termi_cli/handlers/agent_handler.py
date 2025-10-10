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
from google.api_core.exceptions import ResourceExhausted

from termi_cli import api
from termi_cli.api import RPDQuotaExhausted # Import exception tùy chỉnh
from termi_cli.prompts import build_agent_instruction, build_master_agent_prompt, build_executor_instruction
from termi_cli.config import load_config

def _format_plan_for_display(project_plan: dict) -> Panel:
    """
    Chuyển đổi đối tượng JSON kế hoạch thành một Panel rich đẹp mắt, dễ đọc.
    """
    project_name = project_plan.get("project_name", "Không có tên")
    reasoning = project_plan.get("reasoning", "Không có giải thích.")
    
    header_text = Text()
    header_text.append("✨ Tên Dự Án: ", style="bold cyan")
    header_text.append(f"{project_name}\n", style="yellow")
    header_text.append("🧠 Lý do & Kiến trúc: ", style="bold cyan")
    header_text.append(f"{reasoning}\n", style="default")
    
    structure_header = Text("\n📂 Cấu Trúc Thư Mục & File:", style="bold cyan")
    
    tree = Tree("", guide_style="cyan")

    def generate_tree(structure: dict, parent_node: Tree):
        sorted_items = sorted(structure.items(), key=lambda item: isinstance(item[1], dict), reverse=True)
        for name, content in sorted_items:
            if isinstance(content, dict):
                node = parent_node.add(f"📁 [bold magenta]{name}[/]")
                generate_tree(content, node)
            else:
                parent_node.add(f"📄 [default]{name}[/]")

    if structure := project_plan.get("structure"):
        try:
            root_folder_name = next(iter(structure))
            root_node = tree.add(f"📁 [bold magenta]{root_folder_name}[/]")
            generate_tree(structure[root_folder_name], root_node)
        except (StopIteration, AttributeError):
            tree.add("[red]Không thể hiển thị cấu trúc thư mục.[/red]")

    display_group = Group(header_text, structure_header, tree)
    
    return Panel(display_group, title="[bold green]📝 Kế Hoạch Dự Án Chi Tiết[/bold green]", border_style="green", expand=False)

def run_master_agent(console: Console, args: argparse.Namespace):
    """
    Hàm chính điều khiển Agent, với vòng lặp retry mạnh mẽ để xử lý lỗi Quota.
    """
    console.print(Panel(f"[bold green]🤖 Agent Đa Năng Đã Kích Hoạt 🤖[/bold green]\n[yellow]Mục tiêu:[/yellow] {args.prompt}", border_style="blue"))

    initial_response = None
    
    while True:
        try:
            config = load_config()
            agent_model_name = config.get("agent_model", "models/gemini-pro-latest")
            model = api.genai.GenerativeModel(agent_model_name)
            master_prompt = build_master_agent_prompt(args.prompt)
            
            response = api.resilient_generate_content(model, master_prompt)

            json_match = re.search(r'```json\s*(\{.*?\})\s*```', response.text, re.DOTALL)
            if not json_match: json_match = re.search(r'(\{.*?\})', response.text, re.DOTALL)
            if not json_match: raise ValueError("Agent không trả về JSON hợp lệ ban đầu.")

            initial_response = json.loads(json_match.group(1))
            break 

        except RPDQuotaExhausted:
            # API call đã tự xử lý việc chuyển key và in thông báo.
            # Chỉ cần lặp lại vòng lặp để thử lại với key mới.
            continue
        
        except Exception as e:
            console.print(f"[bold red]Đã xảy ra lỗi không mong muốn trong pha phân tích: {e}[/bold red]"); return

    if not initial_response:
        console.print("[bold red]Lỗi: Không thể lấy được phản hồi từ AI sau nhiều lần thử.[/bold red]"); return

    task_type = initial_response.get("task_type")
    if task_type == "project_plan":
        execute_project_plan(console, args, initial_response.get("plan", {}))
    elif task_type == "simple_task":
        execute_simple_task(console, args, initial_response.get("step", {}))
    else:
        console.print(f"[bold red]Lỗi: Agent trả về loại tác vụ không xác định: '{task_type}'[/bold red]")

def _execute_tool(console: Console, tool_name: str, tool_args: dict) -> str:
    if tool_name not in api.AVAILABLE_TOOLS:
        raise ValueError(f"Agent tried to call a non-existent tool: {tool_name}")
    tool_function = api.AVAILABLE_TOOLS[tool_name]
    console.print(f"[yellow]🎬 Hành động:[/yellow] Gọi tool [bold cyan]{tool_name}[/bold cyan] với tham số {tool_args}")
    if tool_name == 'write_file':
        confirm_choice = console.input(f"  [bold yellow]⚠️ AI muốn ghi vào file '{tool_args.get('path')}'. Đồng ý? [y/n]: [/bold yellow]", markup=True).lower()
        if confirm_choice != 'y': return "User denied the file write operation."
        try:
            content_to_write = tool_args.get('content', '')
            path_to_write = tool_args.get('path')
            parent_dir = os.path.dirname(path_to_write)
            if parent_dir: os.makedirs(parent_dir, exist_ok=True)
            with open(path_to_write, 'w', encoding='utf-8') as f: f.write(content_to_write)
            return f"Successfully wrote to file '{path_to_write}'."
        except Exception as e: return f"Error writing to file: {e}"
    else:
        with console.status(f"[green]Đang chạy tool {tool_name}...[/green]"):
            return tool_function(**tool_args)

def execute_project_plan(console: Console, args: argparse.Namespace, project_plan: dict):
    if not project_plan:
        console.print("[bold red]Lỗi: Kế hoạch dự án trống.[/bold red]"); return
        
    display_panel = _format_plan_for_display(project_plan)
    console.print(display_panel)
    console.print("\n[bold green]🚀 Bắt đầu pha thực thi...[/bold green]")

    config = load_config()
    agent_model_name = config.get("agent_model", "models/gemini-pro-latest")
    executor_instruction = build_executor_instruction()
    chat_session = api.start_chat_session(model_name=agent_model_name, system_instruction=executor_instruction)
    plan_str = json.dumps(project_plan, indent=2, ensure_ascii=False)
    scratchpad = f"I have been given a plan to execute.\n\n**PROJECT PLAN:**\n```json\n{plan_str}\n```\n\nMy task is to implement this plan step-by-step."
    max_steps = 30

    for step in range(max_steps):
        console.print(f"\n[bold]--- Vòng {step + 1}/{max_steps} ---[/bold]")
        dynamic_prompt = f"<scratchpad>\n{scratchpad}\n</scratchpad>\nBased on the plan and my scratchpad, what is the single next action I should take?"
        
        while True:
            try:
                response = api.resilient_send_message(chat_session, dynamic_prompt)
                
                json_match = re.search(r'```json\s*(\{.*?\})\s*```', response.text, re.DOTALL)
                if not json_match: json_match = re.search(r'(\{.*?\})', response.text, re.DOTALL)
                if not json_match: raise ValueError(f"No valid JSON found. Raw response:\n{response.text}")

                plan = json.loads(json_match.group(1))
                thought = plan.get("thought", "")
                action = plan.get("action", {})
                
                console.print(Panel(Markdown(thought), title="[bold magenta]Suy nghĩ của Executor[/bold magenta]", border_style="magenta"))

                tool_name = action.get("tool_name", "")
                tool_args = action.get("tool_args", {})

                if tool_name == "finish":
                    final_answer = tool_args.get("answer", "Dự án đã hoàn thành.")
                    console.print(Panel(Markdown(final_answer), title="[bold green]✅ Dự Án Hoàn Thành[/bold green]", border_style="green"))
                    return

                observation = _execute_tool(console, tool_name, tool_args)
                console.print(Panel(Markdown(str(observation)), title="[bold blue]👀 Kết quả[/bold blue]", border_style="blue", expand=False))
                scratchpad += f"\n\n**Step {step + 1}:**\n- **Thought:** {thought}\n- **Action:** Called `{tool_name}` with args `{tool_args}`.\n- **Observation:** {observation}"
                break

            except RPDQuotaExhausted:
                console.print("[green]... Tái tạo session với key mới...[/green]")
                chat_session = api.start_chat_session(model_name=agent_model_name, system_instruction=executor_instruction)
            except Exception as e:
                console.print(f"[bold red]Lỗi không thể phục hồi trong vòng lặp Executor: {e}[/bold red]"); return
    else:
        console.print(f"[bold yellow]⚠️ Agent đã đạt đến giới hạn {max_steps} bước.[/bold yellow]")

def execute_simple_task(console: Console, args: argparse.Namespace, first_step: dict):
    if not first_step:
        console.print("[bold red]Lỗi: Không có bước ReAct đầu tiên.[/bold red]"); return

    console.print("[green]=> Yêu cầu được phân loại là 'Tác vụ đơn giản', kích hoạt chế độ ReAct.[/green]")
    
    config = load_config()
    agent_model_name = config.get("agent_model", "models/gemini-pro-latest")
    agent_instruction = build_agent_instruction()
    chat_session = api.start_chat_session(model_name=agent_model_name, system_instruction=agent_instruction)
    
    current_step_json = first_step
    max_steps = 10

    for step in range(max_steps):
        console.print(f"\n[bold]--- Vòng {step + 1}/{max_steps} ---[/bold]")
        
        # Xử lý bước đầu tiên đã có sẵn
        if step == 0:
            thought = current_step_json.get("thought", "")
            action = current_step_json.get("action", {})
        # Các bước tiếp theo sẽ được lấy từ API call
        else:
            while True:
                try:
                    response = api.resilient_send_message(chat_session, next_prompt)
                    json_match = re.search(r'```json\s*(\{.*?\})\s*```', response.text, re.DOTALL)
                    if not json_match: json_match = re.search(r'(\{.*?\})', response.text, re.DOTALL)
                    if not json_match: raise ValueError(f"No valid JSON found. Raw response:\n{response.text}")
                    current_step_json = json.loads(json_match.group(1))
                    thought = current_step_json.get("thought", "")
                    action = current_step_json.get("action", {})
                    break
                except RPDQuotaExhausted:
                    console.print("[green]... Tái tạo session với key mới...[/green]")
                    chat_session = api.start_chat_session(model_name=agent_model_name, system_instruction=agent_instruction)
                except Exception as e:
                    console.print(f"[bold red]Lỗi không thể phục hồi trong vòng lặp ReAct: {e}[/bold red]"); return

        try:
            console.print(Panel(Markdown(thought), title="[bold magenta]Kế Hoạch Của Agent[/bold magenta]", border_style="magenta"))
            tool_name = action.get("tool_name", "")
            tool_args = action.get("tool_args", {})

            if tool_name == "finish":
                final_answer = tool_args.get("answer", "Nhiệm vụ đã hoàn thành.")
                console.print(Panel(Markdown(final_answer), title="[bold green]✅ Nhiệm Vụ Hoàn Thành[/bold green]", border_style="green"))
                return

            observation = _execute_tool(console, tool_name, tool_args)
            console.print(Panel(Markdown(str(observation)), title="[bold blue]👀 Quan sát[/bold blue]", border_style="blue", expand=False))
            
            next_prompt = f"This was the result of my last action:\n\n{observation}\n\nBased on this, what is my next thought and action?"

        except Exception as e:
            console.print(f"[bold red]Lỗi trong khi thực thi bước ReAct: {e}[/bold red]"); return
    else:
        console.print(f"[bold yellow]⚠️ Agent đã đạt đến giới hạn {max_steps} bước.[/bold yellow]")