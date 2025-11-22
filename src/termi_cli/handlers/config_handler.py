"""
Module xử lý các tác vụ liên quan đến cấu hình của ứng dụng,
bao gồm quản lý persona, custom instructions và lựa chọn model.
"""

from rich.console import Console
from rich.table import Table

from termi_cli import api, i18n
from termi_cli.config import save_config


def model_selection_wizard(console: Console, config: dict):
    """UI chọn model nâng cao: default_model, code_model, commit_model.

    - Bước 1: chọn default_model.
    - Bước 2: tùy chọn chọn code_model (Enter để dùng cùng default).
    - Bước 3: tùy chọn chọn commit_model (Enter để dùng cùng code_model/default).
    """
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

    stable_models = sorted([m for m in models if "preview" not in m and "exp" not in m])
    preview_models = sorted([m for m in models if "preview" in m or "exp" in m])
    sorted_models = stable_models + preview_models

    table = Table(title=i18n.tr(language, "config_model_selection_title"))
    table.add_column("#", style="cyan")
    table.add_column("Model Name", style="magenta")
    for i, model_name in enumerate(sorted_models):
        table.add_row(str(i + 1), model_name)
    console.print(table)

    # Gợi ý nhanh về cách chọn giữa flash/pro cho Gemini
    console.print(i18n.tr(language, "config_model_quick_tips"))

    def _select_index(prompt_key: str, allow_blank: bool = False, default_index: int | None = None):
        while True:
            try:
                choice_str = console.input(i18n.tr(language, prompt_key), markup=False).strip()
                if allow_blank and choice_str == "":
                    return default_index
                choice = int(choice_str) - 1
                if 0 <= choice < len(sorted_models):
                    return choice
                console.print(i18n.tr(language, "config_invalid_choice"))
            except ValueError:
                console.print(i18n.tr(language, "config_please_enter_number"))
            except (KeyboardInterrupt, EOFError):
                console.print(i18n.tr(language, "config_selection_cancelled"))
                return None

    def _print_provider_hint(model_name: str):
        """In ra hint provider dựa trên prefix model."""
        if not isinstance(model_name, str):
            console.print(i18n.tr(language, "config_model_provider_hint_gemini"))
            return
        if model_name.startswith("deepseek-"):
            console.print(i18n.tr(language, "config_model_provider_hint_deepseek"))
        elif model_name.startswith("groq-"):
            console.print(i18n.tr(language, "config_model_provider_hint_groq"))
        else:
            console.print(i18n.tr(language, "config_model_provider_hint_gemini"))

    # Bước 1: chọn default_model
    default_index = _select_index("config_select_model_prompt")
    if default_index is None:
        return

    default_model = sorted_models[default_index]
    config["default_model"] = default_model

    fallback_list = [default_model]
    for m in stable_models:
        if m != default_model and m not in fallback_list:
            fallback_list.append(m)
    config["model_fallback_order"] = fallback_list

    console.print(i18n.tr(language, "config_default_model_set", model=default_model))
    _print_provider_hint(default_model)
    console.print(i18n.tr(language, "config_fallback_order_updated"))

    # Bước 2: chọn code_model (Enter => dùng cùng default)
    code_index = _select_index(
        "config_select_code_model_prompt",
        allow_blank=True,
        default_index=default_index,
    )
    if code_index is None:
        # Người dùng hủy, giữ nguyên config vừa set default
        save_config(config)
        return

    code_model = sorted_models[code_index]
    config["code_model"] = code_model
    if code_index == default_index:
        console.print(i18n.tr(language, "config_code_model_same_as_default"))
    else:
        console.print(i18n.tr(language, "config_code_model_set", model=code_model))
    _print_provider_hint(code_model)

    # Bước 3: chọn commit_model (Enter => dùng cùng code_model/default)
    baseline_index = code_index
    commit_index = _select_index(
        "config_select_commit_model_prompt",
        allow_blank=True,
        default_index=baseline_index,
    )
    if commit_index is None:
        save_config(config)
        return

    commit_model = sorted_models[commit_index]
    config["commit_model"] = commit_model
    if commit_index == baseline_index:
        console.print(i18n.tr(language, "config_commit_model_same_as_code_or_default"))
    else:
        console.print(i18n.tr(language, "config_commit_model_set", model=commit_model))
    _print_provider_hint(commit_model)

    save_config(config)


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
    console.print(
        i18n.tr(language, "config_persona_removed", name=name)
    )


def save_profile(console: Console, config: dict, name: str):
    """Lưu snapshot cấu hình model hiện tại thành một profile nhanh."""
    language = config.get("language", "vi")
    profiles = config.get("profiles") or {}

    profiles[name] = {
        "default_model": config.get("default_model"),
        "code_model": config.get("code_model"),
        "commit_model": config.get("commit_model"),
        "agent_model": config.get("agent_model", "models/gemini-pro-latest"),
        "language": config.get("language", "vi"),
        "default_system_instruction": config.get(
            "default_system_instruction",
            "You are a helpful AI assistant.",
        ),
    }

    config["profiles"] = profiles
    save_config(config)
    console.print(
        i18n.tr(language, "config_profile_saved", name=name)
    )


def list_profiles(console: Console, config: dict):
    """Liệt kê các profile cấu hình nhanh đã lưu."""
    language = config.get("language", "vi")
    profiles = config.get("profiles") or {}

    if not profiles:
        console.print(i18n.tr(language, "config_no_profiles"))
        return

    title = i18n.tr(language, "config_profile_table_title")
    table = Table(title=title)
    table.add_column("#", style="cyan")
    table.add_column("Profile", style="magenta")
    table.add_column("default_model", style="green")
    table.add_column("language", style="yellow")

    for idx, (name, data) in enumerate(profiles.items(), start=1):
        table.add_row(
            str(idx),
            name,
            str(data.get("default_model", "-")),
            str(data.get("language", "-")),
        )

    console.print(table)


def remove_profile(console: Console, config: dict, name: str):
    """Xóa một profile cấu hình nhanh theo tên."""
    language = config.get("language", "vi")
    profiles = config.get("profiles") or {}

    if name not in profiles:
        console.print(
            i18n.tr(language, "config_profile_not_found", name=name)
        )
        return

    profiles.pop(name)
    config["profiles"] = profiles
    save_config(config)
    console.print(
        i18n.tr(language, "config_profile_removed", name=name)
    )


def apply_profile(console: Console, config: dict, name: str):
    """Áp dụng một profile cho runtime hiện tại (không ghi file)."""
    language = config.get("language", "vi")
    profiles = config.get("profiles") or {}

    if name not in profiles:
        console.print(
            i18n.tr(language, "config_profile_not_found", name=name)
        )
        return

    profile = profiles[name]

    for key in [
        "default_model",
        "code_model",
        "commit_model",
        "agent_model",
        "language",
        "default_system_instruction",
    ]:
        if key in profile:
            config[key] = profile[key]

    console.print(
        i18n.tr(language, "config_profile_applied", name=name)
    )


def show_diagnostics(console: Console, config: dict):
    """Hiển thị thông tin cấu hình hiện tại cho các loại model chính."""
    language = config.get("language", "vi")

    default_model = config.get("default_model")
    code_model = config.get("code_model") or default_model
    commit_model = config.get("commit_model") or code_model or default_model
    agent_model = config.get("agent_model", "models/gemini-pro-latest")

    def _provider_name(model_name: str) -> str:
        if not isinstance(model_name, str):
            return "Gemini"
        if model_name.startswith("deepseek-"):
            return "DeepSeek"
        if model_name.startswith("groq-"):
            return "Groq"
        return "Gemini"

    def _provider_label(model_name: str) -> str:
        name = _provider_name(model_name)
        icons = {
            "Gemini": "🟢 Gemini",
            "DeepSeek": "🟣 DeepSeek",
            "Groq": "🟠 Groq",
        }
        return icons.get(name, name)

    title = (
        "Thông tin cấu hình model hiện tại"
        if language == "vi"
        else "Current model configuration diagnostics"
    )

    table = Table(title=title)
    role_col = "Vai trò" if language == "vi" else "Role"
    table.add_column(role_col, style="cyan", no_wrap=True)
    table.add_column("Model", style="magenta")
    table.add_column("Provider", style="green", no_wrap=True)

    rows = [
        ("default", default_model),
        ("code", code_model),
        ("commit", commit_model),
        ("agent", agent_model),
    ]

    for role, model_name in rows:
        if language == "vi":
            if role == "default":
                role_label = "default_model"
            elif role == "code":
                role_label = "code_model"
            elif role == "commit":
                role_label = "commit_model"
            else:
                role_label = "agent_model"
        else:
            role_label = role

        model_str = str(model_name) if model_name is not None else "-"
        table.add_row(role_label, model_str, _provider_label(model_name))

    console.print(table)

    # Thông tin số lượng API key (không in giá trị)
    try:
        from termi_cli import api as _api

        google_keys = _api.initialize_api_keys() or []
        deepseek_keys = []
        groq_keys = []
        try:
            deepseek_keys = _api.initialize_deepseek_api_keys() or []
        except Exception:
            deepseek_keys = []
        try:
            groq_keys = _api.initialize_groq_api_keys() or []
        except Exception:
            groq_keys = []

        console.print(
            i18n.tr(language, "diagnostics_google_keys", count=len(google_keys))
        )
        console.print(
            i18n.tr(language, "diagnostics_deepseek_keys", count=len(deepseek_keys))
        )
        console.print(
            i18n.tr(language, "diagnostics_groq_keys", count=len(groq_keys))
        )
    except Exception:
        # Không để lỗi diagnostics API key làm vỡ lệnh
        pass

    # Giải thích rõ hành vi fallback của Agent khi dùng DeepSeek/Groq
    if isinstance(agent_model, str) and (
        agent_model.startswith("deepseek-") or agent_model.startswith("groq-")
    ):
        console.print(i18n.tr(language, "diagnostics_agent_fallback_note"))