"""
Module xử lý các tác vụ liên quan đến cấu hình của ứng dụng,
bao gồm quản lý persona, custom instructions và lựa chọn model.
"""

from rich.console import Console
from rich.table import Table

from termi_cli import api
from termi_cli.config import save_config

def model_selection_wizard(console: Console, config: dict):
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
            choice_str = console.input("Nhập số thứ tự của model bạn muốn chọn: ", markup=False)
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

# --- Handlers for custom instructions ---
def add_instruction(console: Console, config: dict, instruction: str):
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

# --- Handlers for persona ---
def add_persona(console: Console, config: dict, name: str, instruction: str):
    """Thêm một persona mới vào config."""
    if "personas" not in config:
        config["personas"] = {}
    
    config["personas"][name] = instruction
    save_config(config)
    console.print(f"[bold green]✅ Đã lưu persona [cyan]'{name}'[/cyan].[/bold green]")

def list_personas(console: Console, config: dict):
    """Liệt kê các persona đã lưu."""
    personas = config.get("personas", {})
    if not personas:
        console.print("[yellow]Không có persona nào được lưu.[/yellow]")
        return

    table = Table(title="🎭 Các Persona Đã Lưu")
    table.add_column("Tên Persona", style="cyan")
    table.add_column("Chỉ Dẫn Hệ Thống", style="magenta")
    for name, instruction in personas.items():
        table.add_row(name, instruction)
    console.print(table)

def remove_persona(console: Console, config: dict, name: str):
    """Xóa một persona theo tên."""
    personas = config.get("personas", {})
    if name not in personas:
        console.print(f"[bold red]Lỗi: Không tìm thấy persona có tên '{name}'.[/bold red]")
        return

    removed_instruction = personas.pop(name)
    config["personas"] = personas
    save_config(config)
    console.print(f"[bold green]✅ Đã xóa persona [cyan]'{name}'[/cyan].[/bold green]")