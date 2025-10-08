"""
Module xử lý chế độ Agent tự trị, sử dụng mô hình ReAct (Reason + Act)
để thực hiện các nhiệm vụ phức tạp.
"""
import os
import json
import re
import argparse

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from termi_cli import api
from termi_cli.prompts import build_agent_instruction

def run_agent_mode(console: Console, args: argparse.Namespace):
    """
    Chạy chế độ Agent tự trị, quản lý vòng lặp ReAct và xử lý lỗi một cách độc lập.
    """
    console.print(Panel(f"[bold green]🤖 Chế Độ Agent Đã Kích Hoạt 🤖[/bold green]\n[yellow]Mục tiêu:[/yellow] {args.prompt}", border_style="blue"))

    agent_instruction = build_agent_instruction()
    chat_session = api.start_chat_session(
        model_name=args.model,
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
                            # SỬA LỖI Ở ĐÂY: Thêm [0] để truy cập candidate đầu tiên
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
                    display_content = Markdown(str(observation)) # Đảm bảo observation là string

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