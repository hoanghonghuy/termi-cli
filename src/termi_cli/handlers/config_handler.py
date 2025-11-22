"""
Module xử lý các tác vụ liên quan đến cấu hình của ứng dụng,
bao gồm quản lý persona, custom instructions và lựa chọn model.
"""

from rich.console import Console
from rich.table import Table

from termi_cli import api, i18n
from termi_cli.config import save_config

def model_selection_wizard(console: Console, config: dict):
    language = config.get("language", "vi")
    console.print(i18n.tr(language, "config_fetching_models"))

    try:
        models = api.get_available_models()
        if not models:
            console.print(i18n.tr(language, "config_no_models_found"))
            return
    except Exception as e:
        console.print(i18n.tr(language, "config_error_fetching_models", error=e))
        return

    table = Table(title=i18n.tr(language, "config_model_selection_title"))

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
            choice_str = console.input(i18n.tr(language, "config_select_model_prompt"), markup=False)
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
                    i18n.tr(language, "config_default_model_set", model=selected_model)
                )
                console.print(
                    i18n.tr(language, "config_fallback_order_updated")
                )
                break
            else:
                console.print(
                    i18n.tr(language, "config_invalid_choice")
                )
        except ValueError:
            console.print(i18n.tr(language, "config_please_enter_number"))
        except (KeyboardInterrupt, EOFError):
            console.print(i18n.tr(language, "config_selection_cancelled"))
            break

# --- Handlers for custom instructions ---
def add_instruction(console: Console, config: dict, instruction: str):
    language = config.get("language", "vi")
    if "saved_instructions" not in config:
        config["saved_instructions"] = []
    if instruction not in config["saved_instructions"]:
        config["saved_instructions"].append(instruction)
        save_config(config)
        console.print(
            i18n.tr(language, "config_instruction_added", instruction=instruction)
        )
    else:
        console.print(i18n.tr(language, "config_instruction_exists"))

def list_instructions(console: Console, config: dict):
    instructions = config.get("saved_instructions", [])
    language = config.get("language", "vi")
    if not instructions:
        console.print(i18n.tr(language, "config_no_instructions"))
        return

    table = Table(title=i18n.tr(language, "config_instructions_table_title"))

    table.add_column("#", style="cyan")
    table.add_column("Chỉ Dẫn", style="magenta")
    for i, instruction in enumerate(instructions):
        table.add_row(str(i + 1), instruction)
    console.print(table)

def remove_instruction(console: Console, config: dict, index: int):
    instructions = config.get("saved_instructions", [])
    language = config.get("language", "vi")
    if not 1 <= index <= len(instructions):
        console.print(
            i18n.tr(language, "config_invalid_instruction_index", max_index=len(instructions))
        )
        return

    removed_instruction = instructions.pop(index - 1)
    config["saved_instructions"] = instructions
    save_config(config)
    console.print(
        i18n.tr(language, "config_instruction_removed", instruction=removed_instruction)
    )

# --- Handlers for persona ---
def add_persona(console: Console, config: dict, name: str, instruction: str):
    """Thêm một persona mới vào config."""
    language = config.get("language", "vi")
    if "personas" not in config:
        config["personas"] = {}
    
    config["personas"][name] = instruction
    save_config(config)
    console.print(i18n.tr(language, "config_persona_saved", name=name))

def list_personas(console: Console, config: dict):
    """Liệt kê các persona đã lưu."""
    personas = config.get("personas", {})
    language = config.get("language", "vi")
    if not personas:
        console.print(i18n.tr(language, "config_no_personas"))
        return

    table = Table(title=i18n.tr(language, "config_personas_table_title"))

    table.add_column("Tên Persona", style="cyan")
    table.add_column("Chỉ Dẫn Hệ Thống", style="magenta")
    for name, instruction in personas.items():
        table.add_row(name, instruction)
    console.print(table)

def remove_persona(console: Console, config: dict, name: str):
    """Xóa một persona theo tên."""
    personas = config.get("personas", {})
    language = config.get("language", "vi")
    if name not in personas:
        console.print(i18n.tr(language, "config_persona_not_found", name=name))
        return

    removed_instruction = personas.pop(name)
    config["personas"] = personas
    save_config(config)
    console.print(i18n.tr(language, "config_persona_removed", name=name))