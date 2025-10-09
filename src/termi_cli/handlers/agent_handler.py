"""
Module xử lý các chế độ Agent, bao gồm ReAct đơn giản và Agent tạo dự án phức tạp.
"""
import os
import json
import re
import argparse

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.json import JSON

from termi_cli import api
from termi_cli.prompts import build_agent_instruction, build_planner_instruction
from termi_cli.config import load_config
from termi_cli.prompts import build_agent_instruction, build_planner_instruction, build_executor_instruction



def classify_agent_intent(console: Console, args: argparse.Namespace) -> str:
    """
    Sử dụng LLM để phân loại yêu cầu của người dùng là 'simple' hay 'project'.
    """
    with console.status("[bold cyan]🧠 Phân loại yêu cầu của Agent...[/bold cyan]"):
        try:
            classification_prompt = f"""
Analyze the user's request and determine if it's a 'simple task' or a 'project build'.
- 'simple task': A single action or a short sequence of related actions (e.g., searching, reading/writing one file, running a command).
- 'project build': Requires creating a multi-file structure, developing a cohesive application, or setting up a complete environment.

Here are some examples:

Request: "What is the capital of France?"
Classification: simple

Request: "Read the content of README.md and summarize it."
Classification: simple

Request: "Create a python script that takes a URL as an argument and downloads the image."
Classification: project

Request: "Build me a personal portfolio website using Flask and Bootstrap."
Classification: project

Request: "thời tiết ở hà nội hôm nay"
Classification: simple

Now, classify the following request:

Request: "{args.prompt}"
Classification:
"""
            config = load_config()
            agent_model_name = config.get("agent_model", "models/gemini-pro-latest")
            
            # Sử dụng model agent để phân loại cho chính xác
            model = api.genai.GenerativeModel(agent_model_name)
            response = model.generate_content(classification_prompt)
            
            intent = response.text.strip().lower()
            if "project" in intent:
                console.print("[green]=> Yêu cầu được phân loại là 'Dự án', kích hoạt chế độ Kiến trúc sư.[/green]")
                return "project"
            else:
                console.print("[green]=> Yêu cầu được phân loại là 'Tác vụ đơn giản', kích hoạt chế độ ReAct.[/green]")
                return "simple"
        except Exception as e:
            console.print(f"[yellow]⚠️ Không thể phân loại yêu cầu, mặc định chạy chế độ ReAct đơn giản. Lỗi: {e}[/yellow]")
            return "simple"


def run_generative_agent_mode(console: Console, args: argparse.Namespace):
    """
    Chạy chế độ Agent tạo dự án (Planner + Executor).
    """
    console.print(Panel(f"[bold green]🤖 Chế Độ Kiến Trúc Sư Đã Kích Hoạt 🤖[/bold green]\n[yellow]Mục tiêu:[/yellow] {args.prompt}", border_style="blue"))

    # --- PHA 1: LẬP KẾ HOẠCH ---
    plan_str = ""
    project_plan = {}
    with console.status("[bold cyan]📝 Agent đang phân tích và lập kế hoạch chi tiết cho dự án...[/bold cyan]"):
        try:
            planner_prompt = build_planner_instruction(args.prompt)
            config = load_config()
            agent_model_name = config.get("agent_model", "models/gemini-pro-latest")
            model = api.genai.GenerativeModel(agent_model_name) 
            response = model.generate_content(planner_prompt)
            
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', response.text, re.DOTALL)
            if not json_match: json_match = re.search(r'(\{.*?\})', response.text, re.DOTALL)

            if not json_match:
                console.print("[bold red]Lỗi: Planner không trả về một bản kế hoạch JSON hợp lệ.[/bold red]"); return

            plan_str = json_match.group(1)
            project_plan = json.loads(plan_str)
        except Exception as e:
            console.print(f"[bold red]Đã xảy ra lỗi trong pha lập kế hoạch: {e}[/bold red]"); return

    console.print(Panel(JSON(plan_str), title="[bold green]📝 Kế Hoạch Dự Án Chi Tiết[/bold green]", border_style="green"))
    
    # --- PHA 2: THỰC THI ---
    console.print("\n[bold green]🚀 Bắt đầu pha thực thi...[/bold green]")
    
    executor_instruction = build_executor_instruction()
    chat_session = api.start_chat_session(
        model_name=agent_model_name,
        system_instruction=executor_instruction
    )

    # Khởi tạo bộ nhớ ngắn hạn (Scratchpad)
    scratchpad = f"I have been given a plan to execute.\n\n**PROJECT PLAN:**\n```json\n{plan_str}\n```\n\nMy task is to implement this plan step-by-step."
    max_steps = 30 # Tăng số bước cho các nhiệm vụ phức tạp
    
    for step in range(max_steps):
        console.print(f"\n[bold]--- Vòng {step + 1}/{max_steps} ---[/bold]")
        
        # Xây dựng prompt động cho Executor
        dynamic_prompt = f"""
Here is my scratchpad with the history of my work so far:
<scratchpad>
{scratchpad}
</scratchpad>

Based on the original plan and my scratchpad, what is the single next action I should take?
"""
        
        # Lấy thought và action từ LLM
        response_text = ""
        try:
            with console.status("[magenta]👩‍💻 Executor đang suy nghĩ bước tiếp theo...[/magenta]"):
                response = chat_session.send_message(dynamic_prompt)
                response_text = response.text
        except Exception as e:
            console.print(f"[bold red]Lỗi khi giao tiếp với Executor: {e}[/bold red]"); break

        # Phân tích JSON
        try:
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL)
            if not json_match: json_match = re.search(r'(\{.*?\})', response_text, re.DOTALL)
            
            if not json_match:
                console.print("[bold red]Lỗi: Executor không trả về định dạng JSON hợp lệ.[/bold red]")
                console.print(f"Phản hồi thô:\n{response_text}"); break

            json_str = json_match.group(1)
            plan = json.loads(json_str)
            thought = plan.get("thought", "")
            action = plan.get("action", {})
            
            console.print(Panel(Markdown(thought), title="[bold magenta]Suy nghĩ của Executor[/bold magenta]", border_style="magenta"))

            tool_name = action.get("tool_name", "")
            tool_args = action.get("tool_args", {})

            if tool_name == "finish":
                final_answer = tool_args.get("answer", "Dự án đã hoàn thành.")
                console.print(Panel(Markdown(final_answer), title="[bold green]✅ Dự Án Hoàn Thành[/bold green]", border_style="green"))
                break

            # Thực thi tool
            observation = ""
            if tool_name in api.AVAILABLE_TOOLS:
                console.print(f"[yellow]🎬 Hành động:[/yellow] Gọi tool [bold cyan]{tool_name}[/bold cyan] với tham số {tool_args}")
                tool_function = api.AVAILABLE_TOOLS[tool_name]
                
                # Xử lý xác nhận cho write_file
                if tool_name == 'write_file':
                    confirm_choice = console.input(f"  [bold yellow]⚠️ AI muốn ghi vào file '{tool_args.get('path')}'. Đồng ý? [y/n]: [/bold yellow]", markup=True).lower()
                    if confirm_choice != 'y':
                        observation = "User denied the file write operation."
                    else:
                        try:
                            content_to_write = tool_args.get('content', '')
                            path_to_write = tool_args.get('path')
                            parent_dir = os.path.dirname(path_to_write)
                            if parent_dir: os.makedirs(parent_dir, exist_ok=True)
                            with open(path_to_write, 'w', encoding='utf-8') as f: f.write(content_to_write)
                            observation = f"Successfully wrote to file '{path_to_write}'."
                        except Exception as e:
                            observation = f"Error writing to file: {e}"
                else:
                    with console.status(f"[green]Đang chạy tool {tool_name}...[/green]"):
                        observation = tool_function(**tool_args)
                
                console.print(Panel(Markdown(str(observation)), title="[bold blue]👀 Kết quả[/bold blue]", border_style="blue", expand=False))
                
                # Cập nhật Scratchpad
                scratchpad += f"\n\n**Step {step + 1}:**\n- **Thought:** {thought}\n- **Action:** Called `{tool_name}` with args `{tool_args}`.\n- **Observation:** {observation}"

            else:
                console.print(f"[bold red]Lỗi: Executor cố gắng gọi một tool không tồn tại: {tool_name}[/bold red]"); break

        except (json.JSONDecodeError, ValueError) as e:
            console.print(f"[bold red]Lỗi khi phân tích phản hồi của Executor: {e}[/bold red]")
            console.print(f"Phản hồi thô:\n{response_text}"); break
        except Exception as e:
            console.print(f"[bold red]Đã xảy ra lỗi không mong muốn trong vòng lặp Executor: {e}[/bold red]"); break
    else:
        console.print(f"[bold yellow]⚠️ Agent đã đạt đến giới hạn {max_steps} bước và sẽ tự động dừng lại.[/bold yellow]")


def run_react_agent_mode(console: Console, args: argparse.Namespace):
    """
    Chạy chế độ Agent ReAct đơn giản cho các tác vụ nhỏ.
    """
    console.print(Panel(f"[bold green]🤖 Chế Độ ReAct Đã Kích Hoạt 🤖[/bold green]\n[yellow]Mục tiêu:[/yellow] {args.prompt}", border_style="blue"))

    agent_instruction = build_agent_instruction()
    
    config = load_config()
    agent_model_name = config.get("agent_model", "models/gemini-pro-latest")
    
    chat_session = api.start_chat_session(
        model_name=agent_model_name,
        system_instruction=agent_instruction
    )

    current_prompt_parts = [{"text": args.prompt}]
    max_steps = 10
    
    for step in range(max_steps):
        console.print(f"\n[bold]--- Vòng {step + 1}/{max_steps} ---[/bold]")
        
        response_text = ""
        for _ in range(2):
            try:
                with console.status("[magenta]🧠 Agent đang suy nghĩ...[/magenta]"):
                    response_stream = api.send_message(chat_session, current_prompt_parts)
                    response_text = ""
                    for chunk in response_stream:
                        if chunk.candidates:
                            for part in chunk.candidates[0].content.parts:
                                if part.text:
                                    response_text += part.text
                if response_text.strip():
                    break
                console.print("[yellow]Cảnh báo: AI trả về phản hồi trống, đang thử lại...[/yellow]")
            except Exception as e:
                console.print(f"[bold red]Lỗi khi giao tiếp với AI: {e}[/bold red]")
                return

        if not response_text.strip():
            console.print("[bold red]Lỗi: AI liên tục trả về phản hồi trống. Đang dừng Agent.[/bold red]")
            return

        try:
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL)
            if not json_match:
                json_match = re.search(r'(\{.*?\})', response_text, re.DOTALL)
            
            if not json_match:
                console.print("[bold red]Lỗi: AI không trả về định dạng JSON hợp lệ. Đang dừng Agent.[/bold red]")
                console.print(f"Phản hồi thô:\n{response_text}")
                break

            json_str = json_match.group(1)
            
            def escape_newlines(match):
                return match.group(0).replace('\n', '\\n')
            json_str_fixed = re.sub(r'"[^"]*"', escape_newlines, json_str)

            plan = json.loads(json_str_fixed)
            thought = plan.get("thought")
            action = plan.get("action")
            
            if not thought or not action:
                raise ValueError("Phản hồi JSON thiếu 'thought' hoặc 'action'.")

            console.print(Panel(Markdown(thought), title="[bold magenta]Kế Hoạch Của Agent[/bold magenta]", border_style="magenta"))

            tool_name_raw = action.get("tool_name", "")
            tool_name = tool_name_raw.split(':')[-1]
            
            tool_args = action.get("tool_args", {})

            if tool_name == "finish":
                final_answer = tool_args.get("answer", "Nhiệm vụ đã hoàn thành.")
                console.print(Panel(Markdown(final_answer), title="[bold green]✅ Nhiệm Vụ Hoàn Thành[/bold green]", border_style="green"))
                break

            if tool_name in api.AVAILABLE_TOOLS:
                console.print(f"[yellow]🎬 Hành động:[/yellow] Gọi tool [bold cyan]{tool_name}[/bold cyan] với tham số {tool_args}")
                tool_function = api.AVAILABLE_TOOLS[tool_name]
                
                observation = ""
                if tool_name == 'write_file':
                    confirm_choice = console.input(f"  [bold yellow]⚠️ AI muốn ghi vào file '{tool_args.get('path')}'. Đồng ý? [y/n]: [/bold yellow]", markup=True).lower()
                    if confirm_choice != 'y':
                        observation = "User denied the file write operation."
                    else:
                        try:
                            content_to_write = tool_args.get('content', '')
                            path_to_write = tool_args.get('path')
                            parent_dir = os.path.dirname(path_to_write)
                            if parent_dir: os.makedirs(parent_dir, exist_ok=True)
                            with open(path_to_write, 'w', encoding='utf-8') as f: f.write(content_to_write)
                            observation = f"Successfully wrote to file '{path_to_write}'."
                        except Exception as e:
                            observation = f"Error writing to file: {e}"
                else:
                    with console.status(f"[green]Đang chạy tool {tool_name}...[/green]"):
                        observation = tool_function(**tool_args)
                
                display_content = None
                if tool_name == 'read_file':
                    file_extension = os.path.splitext(tool_args.get("path", ""))[1].lstrip('.')
                    lang = file_extension if file_extension else "text"
                    display_content = Markdown(f"```{lang}\n{observation}\n```")
                else:
                    display_content = Markdown(str(observation))

                console.print(Panel(display_content, title="[bold blue]👀 Quan sát[/bold blue]", border_style="blue", expand=False))
                
                current_prompt_parts = [{"text": f"This was the result of your last action:\n\n{observation}\n\nBased on this, what is your next thought and action to achieve the original objective: '{args.prompt}'?"}]
            else:
                console.print(f"[bold red]Lỗi: AI cố gắng gọi một tool không tồn tại: {tool_name_raw}[/bold red]")
                break

        except (json.JSONDecodeError, ValueError) as e:
            console.print(f"[bold red]Lỗi khi phân tích phản hồi của Agent: {e}[/bold red]")
            console.print(f"Phản hồi thô:\n{response_text}")
            break
        except Exception as e:
            console.print(f"[bold red]Đã xảy ra lỗi không mong muốn trong vòng lặp Agent: {e}[/bold red]")
            break
    else:
        console.print(f"[bold yellow]⚠️ Agent đã đạt đến giới hạn {max_steps} bước và sẽ tự động dừng lại.[/bold yellow]")