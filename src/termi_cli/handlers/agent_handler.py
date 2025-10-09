"""
Module xử lý các chế độ Agent, với cơ chế retry và chuyển đổi API key toàn cục.
"""
import os
import json
import re
import argparse
import time

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.json import JSON
from google.api_core.exceptions import ResourceExhausted

from termi_cli import api
from termi_cli.prompts import build_agent_instruction, build_master_agent_prompt, build_executor_instruction
from termi_cli.config import load_config, MODEL_RPM_LIMITS

def run_master_agent(console: Console, args: argparse.Namespace):
    """
    Hàm chính điều khiển Agent, với vòng lặp retry mạnh mẽ để xử lý lỗi Quota.
    """
    console.print(Panel(f"[bold green]🤖 Agent Đa Năng Đã Kích Hoạt 🤖[/bold green]\n[yellow]Mục tiêu:[/yellow] {args.prompt}", border_style="blue"))

    initial_response = None
    max_attempts = len(api._api_keys)
    current_attempt = 0
    
    while current_attempt < max_attempts:
        try:
            with console.status("[bold cyan]🧠 Agent đang phân tích yêu cầu...[/bold cyan]") as status:
                master_prompt = build_master_agent_prompt(args.prompt)
                config = load_config()
                agent_model_name = config.get("agent_model", "models/gemini-pro-latest")
                model = api.genai.GenerativeModel(agent_model_name)
                response = api.safe_generate_content(model, master_prompt)

                if not response or not response.text:
                    raise ValueError("Không nhận được phản hồi hợp lệ từ AI.")

                json_match = re.search(r'```json\s*(\{.*?\})\s*```', response.text, re.DOTALL)
                if not json_match: json_match = re.search(r'(\{.*?\})', response.text, re.DOTALL)
                if not json_match: raise ValueError("Agent không trả về JSON hợp lệ ban đầu.")

                initial_response = json.loads(json_match.group(1))
                break 

        except ResourceExhausted as e:
            error_message = str(e)
            
            # SỬA LỖI: Ưu tiên kiểm tra lỗi "cứng" (RPD) trước
            if "free_tier_requests" in error_message or "daily" in error_message:
                current_attempt += 1
                console.print(f"[bold yellow]⚠️ Gặp lỗi Quota hàng ngày (RPD). Đang thử chuyển key... ({current_attempt}/{max_attempts})[/bold yellow]")
                success, msg = api.switch_to_next_api_key()
                if not success:
                    console.print(f"[bold red]❌ {msg}. Đã hết tất cả API keys.[/bold red]"); return
            # Nếu không phải lỗi cứng, mới kiểm tra lỗi "mềm" (RPM)
            elif (match := re.search(r"Please retry in (\d+\.\d+)s", error_message)):
                wait_time = float(match.group(1)) + 1
                with console.status(f"[bold yellow]⏳ Gặp lỗi Quota (RPM). Tự động chờ {wait_time:.1f}s...[/bold yellow]", spinner="clock"):
                    time.sleep(wait_time)
                continue # Thử lại với cùng key
            # Trường hợp còn lại, coi như lỗi cứng và chuyển key
            else:
                current_attempt += 1
                console.print(f"[bold yellow]⚠️ Gặp lỗi Quota không xác định. Đang thử chuyển key... ({current_attempt}/{max_attempts})[/bold yellow]")
                success, msg = api.switch_to_next_api_key()
                if not success:
                    console.print(f"[bold red]❌ {msg}. Đã hết tất cả API keys.[/bold red]"); return
        
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
    # ... (Hàm này giữ nguyên, không thay đổi) ...
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
    # ... (Phần đầu hàm giữ nguyên) ...
    if not project_plan: console.print("[bold red]Lỗi: Kế hoạch dự án trống.[/bold red]"); return
    plan_str = json.dumps(project_plan, indent=2, ensure_ascii=False)
    console.print(Panel(JSON(plan_str), title="[bold green]📝 Kế Hoạch Dự Án Chi Tiết[/bold green]", border_style="green", expand=False))
    console.print("\n[bold green]🚀 Bắt đầu pha thực thi...[/bold green]")
    config = load_config()
    agent_model_name = config.get("agent_model", "models/gemini-pro-latest")
    executor_instruction = build_executor_instruction()
    chat_session = api.start_chat_session(model_name=agent_model_name, system_instruction=executor_instruction)
    scratchpad = f"I have been given a plan to execute.\n\n**PROJECT PLAN:**\n```json\n{plan_str}\n```\n\nMy task is to implement this plan step-by-step."
    max_steps = 30

    for step in range(max_steps):
        console.print(f"\n[bold]--- Vòng {step + 1}/{max_steps} ---[/bold]")
        dynamic_prompt = f"<scratchpad>\n{scratchpad}\n</scratchpad>\nBased on the plan and my scratchpad, what is the single next action I should take?"
        
        max_attempts = len(api._api_keys)
        current_attempt = 0
        step_success = False
        while current_attempt <= max_attempts and not step_success:
            try:
                with console.status("[magenta]👩‍💻 Executor đang suy nghĩ...[/magenta]"):
                    response = chat_session.send_message(dynamic_prompt)
                
                # ... (logic xử lý response và tool giữ nguyên) ...
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
                step_success = True

            except ResourceExhausted as e:
                # SỬA LỖI: Áp dụng logic kiểm tra lỗi "cứng" trước
                error_message = str(e)
                if "free_tier_requests" in error_message or "daily" in error_message:
                    current_attempt += 1
                    console.print(f"[yellow]⚠️ Gặp lỗi Quota (RPD). Đang chuyển key... ({current_attempt}/{max_attempts})[/yellow]")
                    success, msg = api.switch_to_next_api_key()
                    if success:
                        console.print(f"[green]✅ Đã chuyển sang {msg}. Đang tạo lại session...[/green]")
                        chat_session = api.start_chat_session(model_name=agent_model_name, system_instruction=executor_instruction)
                    else:
                        console.print(f"[bold red]❌ {msg}. Hết API keys.[/bold red]"); return
                elif (match := re.search(r"Please retry in (\d+\.\d+)s", error_message)):
                    wait_time = float(match.group(1)) + 1
                    with console.status(f"[yellow]⏳ Gặp lỗi Quota (RPM). Chờ {wait_time:.1f}s...[/yellow]", spinner="clock"):
                        time.sleep(wait_time)
                else:
                    current_attempt += 1
                    console.print(f"[yellow]⚠️ Gặp lỗi Quota không xác định. Đang chuyển key... ({current_attempt}/{max_attempts})[/yellow]")
                    success, msg = api.switch_to_next_api_key()
                    if success:
                        console.print(f"[green]✅ Đã chuyển sang {msg}. Đang tạo lại session...[/green]")
                        chat_session = api.start_chat_session(model_name=agent_model_name, system_instruction=executor_instruction)
                    else:
                        console.print(f"[bold red]❌ {msg}. Hết API keys.[/bold red]"); return
            except Exception as e:
                console.print(f"[bold red]Lỗi trong vòng lặp Executor: {e}[/bold red]"); return
        
        if not step_success:
            console.print(f"[bold red]Lỗi: Không thể hoàn thành bước {step + 1} sau nhiều lần thử.[/bold red]"); return
    else:
        console.print(f"[bold yellow]⚠️ Agent đã đạt đến giới hạn {max_steps} bước.[/bold yellow]")

def execute_simple_task(console: Console, args: argparse.Namespace, first_step: dict):
    # ... (Phần đầu hàm giữ nguyên) ...
    if not first_step: console.print("[bold red]Lỗi: Không có bước ReAct đầu tiên.[/bold red]"); return
    console.print("[green]=> Yêu cầu được phân loại là 'Tác vụ đơn giản', kích hoạt chế độ ReAct.[/green]")
    config = load_config()
    agent_model_name = config.get("agent_model", "models/gemini-pro-latest")
    agent_instruction = build_agent_instruction()
    chat_session = api.start_chat_session(model_name=agent_model_name, system_instruction=agent_instruction)
    current_step_json = first_step
    max_steps = 10

    for step in range(max_steps):
        console.print(f"\n[bold]--- Vòng {step + 1}/{max_steps} ---[/bold]")
        try:
            # ... (logic xử lý step và tool giữ nguyên) ...
            thought = current_step_json.get("thought", "")
            action = current_step_json.get("action", {})
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
            
            max_attempts = len(api._api_keys)
            current_attempt = 0
            step_success = False
            while current_attempt <= max_attempts and not step_success:
                try:
                    with console.status("[magenta]🧠 Agent đang suy nghĩ...[/magenta]"):
                        response = chat_session.send_message(next_prompt)
                    
                    # ... (logic parse response giữ nguyên) ...
                    json_match = re.search(r'```json\s*(\{.*?\})\s*```', response.text, re.DOTALL)
                    if not json_match: json_match = re.search(r'(\{.*?\})', response.text, re.DOTALL)
                    if not json_match: raise ValueError(f"No valid JSON found. Raw response:\n{response.text}")
                    current_step_json = json.loads(json_match.group(1))
                    step_success = True

                except ResourceExhausted as e:
                    # SỬA LỖI: Áp dụng logic kiểm tra lỗi "cứng" trước
                    error_message = str(e)
                    if "free_tier_requests" in error_message or "daily" in error_message:
                        current_attempt += 1
                        console.print(f"[yellow]⚠️ Gặp lỗi Quota (RPD). Đang chuyển key... ({current_attempt}/{max_attempts})[/yellow]")
                        success, msg = api.switch_to_next_api_key()
                        if success:
                            console.print(f"[green]✅ Đã chuyển sang {msg}. Đang tạo lại session...[/green]")
                            chat_session = api.start_chat_session(model_name=agent_model_name, system_instruction=agent_instruction)
                        else:
                            console.print(f"[bold red]❌ {msg}. Hết API keys.[/bold red]"); return
                    elif (match := re.search(r"Please retry in (\d+\.\d+)s", error_message)):
                        wait_time = float(match.group(1)) + 1
                        with console.status(f"[yellow]⏳ Gặp lỗi Quota (RPM). Chờ {wait_time:.1f}s...[/yellow]", spinner="clock"):
                            time.sleep(wait_time)
                    else:
                        current_attempt += 1
                        console.print(f"[yellow]⚠️ Gặp lỗi Quota không xác định. Đang chuyển key... ({current_attempt}/{max_attempts})[/yellow]")
                        success, msg = api.switch_to_next_api_key()
                        if success:
                            console.print(f"[green]✅ Đã chuyển sang {msg}. Đang tạo lại session...[/green]")
                            chat_session = api.start_chat_session(model_name=agent_model_name, system_instruction=agent_instruction)
                        else:
                            console.print(f"[bold red]❌ {msg}. Hết API keys.[/bold red]"); return
            
            if not step_success:
                console.print(f"[bold red]Lỗi: Không thể tiếp tục bước tiếp theo sau nhiều lần thử.[/bold red]"); return

        except Exception as e:
            console.print(f"[bold red]Lỗi trong vòng lặp ReAct: {e}[/bold red]"); return
    else:
        console.print(f"[bold yellow]⚠️ Agent đã đạt đến giới hạn {max_steps} bước.[/bold yellow]")