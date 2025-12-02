"""
Module xử lý các tác vụ liên quan đến cấu hình của ứng dụng,
bao gồm quản lý persona, custom instructions và lựa chọn model.
"""

from rich.console import Console
from rich.table import Table

from termi_cli import api, i18n
from termi_cli.config import save_config
from termi_cli.handlers import mini_agent


def model_selection_wizard(console: Console, config: dict):
    """UI chọn model nâng cao: default_model, code_model, commit_model.

    Bước đầu tiên: chọn provider (Gemini / DeepSeek / Groq / OpenRouter),
    sau đó chọn model tương ứng cho từng vai trò.
    """
    language = config.get("language", "vi")
    model_labels = config.get("model_labels") or {}

    providers = [
        ("gemini", "", i18n.tr(language, "config_provider_desc_gemini")),
        ("deepseek", "", i18n.tr(language, "config_provider_desc_deepseek")),
        ("groq", "", i18n.tr(language, "config_provider_desc_groq")),
        ("openrouter", "", i18n.tr(language, "config_provider_desc_openrouter")),
        ("ollama", "", i18n.tr(language, "config_provider_desc_ollama")),
    ]

    providers = [
        ("gemini", "🟢 Gemini", i18n.tr(language, "config_provider_desc_gemini")),
        ("deepseek", "🟣 DeepSeek", i18n.tr(language, "config_provider_desc_deepseek")),
        ("groq", "🟠 Groq", i18n.tr(language, "config_provider_desc_groq")),
        ("openrouter", "🔵 OpenRouter", i18n.tr(language, "config_provider_desc_openrouter")),
        ("ollama", "⚫ Ollama", i18n.tr(language, "config_provider_desc_ollama")),
    ]

    table = Table(title=i18n.tr(language, "config_provider_selection_title"))
    table.add_column("#", style="cyan")
    table.add_column("Provider", style="green")
    table.add_column("Mô tả" if language == "vi" else "Description", style="magenta")
    for idx, (_, label, desc) in enumerate(providers, start=1):
        table.add_row(str(idx), label, desc)
    console.print(table)

    while True:
        try:
            choice_str = console.input(
                i18n.tr(language, "config_provider_select_prompt"),
                markup=False,
            ).strip()
            choice = int(choice_str) - 1
            if 0 <= choice < len(providers):
                provider_key = providers[choice][0]
                break
            console.print(i18n.tr(language, "config_invalid_choice"))
        except ValueError:
            console.print(i18n.tr(language, "config_please_enter_number"))
        except (KeyboardInterrupt, EOFError):
            console.print(i18n.tr(language, "config_selection_cancelled"))
            return

    def _print_provider_hint(model_name: str):
        if not isinstance(model_name, str):
            console.print(i18n.tr(language, "config_model_provider_hint_gemini"))
            return
        if model_name.startswith("deepseek-"):
            console.print(i18n.tr(language, "config_model_provider_hint_deepseek"))
        elif model_name.startswith("groq-"):
            console.print(i18n.tr(language, "config_model_provider_hint_groq"))
        elif api.is_openrouter_model(model_name):
            console.print(i18n.tr(language, "config_model_provider_hint_openrouter"))
        elif api.is_ollama_model(model_name):
            console.print(i18n.tr(language, "config_model_provider_hint_ollama"))
        else:
            console.print(i18n.tr(language, "config_model_provider_hint_gemini"))

    def _display_name(model_name: str) -> str:
        label = model_labels.get(model_name)
        if label:
            return f"{model_name} {label}"
        return model_name

    def _select_index(sorted_models: list[str], prompt_key: str, allow_blank: bool = False, default_index: int | None = None):
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

    # --- Nhánh Gemini: dùng get_available_models như trước ---
    if provider_key == "gemini":
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
            table.add_row(str(i + 1), _display_name(model_name))
        console.print(table)

        console.print(i18n.tr(language, "config_model_quick_tips"))

        default_index = _select_index(sorted_models, "config_select_model_prompt")
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

        # Đơn giản hoá: dùng cùng một model cho default/code/commit
        config["code_model"] = default_model
        config["commit_model"] = default_model
        console.print(i18n.tr(language, "config_code_model_same_as_default"))
        console.print(i18n.tr(language, "config_commit_model_same_as_code_or_default"))

        save_config(config)
        return

    # --- Nhánh Ollama: nhập tag model thủ công, prefix "ollama/" ---
    if provider_key == "ollama":

        def _ask_ollama_model(prompt_key: str, prefix: str) -> str | None:
            while True:
                try:
                    choice_str = console.input(i18n.tr(language, prompt_key), markup=False).strip()
                    if not choice_str:
                        console.print(i18n.tr(language, "config_selection_cancelled"))
                        return None
                    if not choice_str.startswith(prefix):
                        choice_str = f"{prefix}{choice_str}"
                    return choice_str
                except (KeyboardInterrupt, EOFError):
                    console.print(i18n.tr(language, "config_selection_cancelled"))
                    return None

        variant_raw = console.input(i18n.tr(language, "config_ollama_variant_prompt"), markup=False).strip()
        variant = 2 if variant_raw == "2" else 1

        if variant == 2:
            console.print(i18n.tr(language, "config_ollama_cloud_api_hint"))
            default_model = _ask_ollama_model("config_ollama_cloud_model_prompt", "ollama-cloud/")
        else:
            default_model = _ask_ollama_model("config_ollama_default_model_prompt", "ollama/")

        if default_model is None:
            return

        config["default_model"] = default_model
        config["code_model"] = default_model
        config["commit_model"] = default_model
        config["model_fallback_order"] = [default_model]
        console.print(i18n.tr(language, "config_default_model_set", model=default_model))
        _print_provider_hint(default_model)
        console.print(i18n.tr(language, "config_code_model_same_as_default"))
        console.print(i18n.tr(language, "config_commit_model_same_as_code_or_default"))

        save_config(config)
        return

    # --- Nhánh DeepSeek / Groq: dùng danh sách static đơn giản ---
    if provider_key == "deepseek":
        stable_models = sorted([
            "deepseek-chat",
            "deepseek-reasoner",
        ])
        sorted_models = stable_models
    elif provider_key == "groq":
        stable_models = sorted([
            "groq-chat",
            "groq-llama-3.3-70b-versatile",
            "groq-llama3-8b-8192",
        ])
        sorted_models = stable_models
    else:
        # --- Nhánh OpenRouter: hiển thị danh sách gợi ý + cho phép nhập thủ công ID model ---
        openrouter_models = [
            "openai/gpt-4o-mini",
            "google/gemma-2-9b-it",
            "google/gemma-2-27b-it",
            "meta-llama/llama-3.1-8b-instruct",
            "meta-llama/llama-3.1-70b-instruct",
            "mistralai/mistral-7b-instruct",
            "mistralai/mixtral-8x7b-instruct",
            "qwen/qwen2.5-7b-instruct",
        ]
        stable_models = sorted(openrouter_models)
        sorted_models = stable_models

        def _openrouter_usage_hint(model_name: str) -> str:
            if model_name == "openai/gpt-4o-mini":
                return i18n.tr(language, "config_model_hint_openrouter_gpt4o_mini")
            if model_name == "meta-llama/llama-3.1-8b-instruct":
                return i18n.tr(language, "config_model_hint_openrouter_llama_8b")
            if model_name == "meta-llama/llama-3.1-70b-instruct":
                return i18n.tr(language, "config_model_hint_openrouter_llama_70b")
            if model_name == "mistralai/mixtral-8x7b-instruct":
                return i18n.tr(language, "config_model_hint_openrouter_mixtral")
            return ""

        table = Table(title=i18n.tr(language, "config_model_selection_title"))
        table.add_column("#", style="cyan")
        table.add_column("Model Name", style="magenta")
        usage_col = "Gợi ý sử dụng" if language == "vi" else "Usage hint"
        table.add_column(usage_col, style="green")
        for i, model_name in enumerate(sorted_models):
            table.add_row(str(i + 1), _display_name(model_name), _openrouter_usage_hint(model_name))
        console.print(table)
        console.print(i18n.tr(language, "config_openrouter_intro_examples"))

        def _ask_openrouter_model(prompt_key: str, allow_blank: bool, baseline: str | None = None) -> str | None:
            while True:
                try:
                    choice_str = console.input(i18n.tr(language, prompt_key), markup=False).strip()
                    if allow_blank and choice_str == "":
                        return baseline
                    # Cho phép chọn theo số thứ tự trong bảng gợi ý
                    if choice_str.isdigit():
                        idx = int(choice_str) - 1
                        if 0 <= idx < len(sorted_models):
                            return sorted_models[idx]
                        console.print(i18n.tr(language, "config_invalid_choice"))
                        continue
                    # Nếu không phải số, coi như ID model đầy đủ
                    if not api.is_openrouter_model(choice_str):
                        console.print(i18n.tr(language, "config_openrouter_invalid_model"))
                        continue
                    return choice_str
                except (KeyboardInterrupt, EOFError):
                    return None

        # Một lần chọn model cho tất cả vai trò
        default_model = _ask_openrouter_model("config_openrouter_default_model_prompt", allow_blank=False)
        if default_model is None:
            console.print(i18n.tr(language, "config_selection_cancelled"))
            return

        config["default_model"] = default_model
        config["code_model"] = default_model
        config["commit_model"] = default_model
        config["model_fallback_order"] = [default_model]
        console.print(i18n.tr(language, "config_default_model_set", model=default_model))
        _print_provider_hint(default_model)
        console.print(i18n.tr(language, "config_code_model_same_as_default"))
        console.print(i18n.tr(language, "config_commit_model_same_as_code_or_default"))

        save_config(config)
        return

    # DeepSeek / Groq: chọn model theo index giống Gemini nhưng không gọi API từ xa
    def _static_model_usage_hint(model_name: str) -> str:
        if provider_key == "deepseek":
            if model_name == "deepseek-chat":
                return i18n.tr(language, "config_model_hint_deepseek_chat")
            if model_name == "deepseek-reasoner":
                return i18n.tr(language, "config_model_hint_deepseek_reasoner")
        elif provider_key == "groq":
            if model_name == "groq-chat":
                return i18n.tr(language, "config_model_hint_groq_chat")
            if model_name == "groq-llama-3.3-70b-versatile":
                return i18n.tr(language, "config_model_hint_groq_llama_3_3_70b")
            if model_name == "groq-llama3-8b-8192":
                return i18n.tr(language, "config_model_hint_groq_llama3_8b")
        return ""

    table = Table(title=i18n.tr(language, "config_model_selection_title"))
    table.add_column("#", style="cyan")
    table.add_column("Model Name", style="magenta")
    usage_col = "Gợi ý sử dụng" if language == "vi" else "Usage hint"
    table.add_column(usage_col, style="green")
    for i, model_name in enumerate(sorted_models):
        table.add_row(str(i + 1), _display_name(model_name), _static_model_usage_hint(model_name))
    console.print(table)

    default_index = _select_index(sorted_models, "config_select_model_prompt")
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

    # Đơn giản hoá: dùng cùng một model cho default/code/commit
    config["code_model"] = default_model
    config["commit_model"] = default_model
    console.print(i18n.tr(language, "config_code_model_same_as_default"))
    console.print(i18n.tr(language, "config_commit_model_same_as_code_or_default"))

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
        if api.is_ollama_model(model_name):
            return "Ollama"
        if api.is_ollama_cloud_model(model_name):
            return "Ollama Cloud"
        if api.is_openrouter_model(model_name):
            return "OpenRouter"
        return "Gemini"

    def _provider_label(model_name: str) -> str:
        name = _provider_name(model_name)
        icons = {
            "Gemini": "🟢 Gemini",
            "DeepSeek": "🟣 DeepSeek",
            "Groq": "🟠 Groq",
            "OpenRouter": "🔵 OpenRouter",
            "Ollama": "⚫ Ollama",
            "Ollama Cloud": "⚫☁️ Ollama Cloud",
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
        openrouter_keys = []
        try:
            deepseek_keys = _api.initialize_deepseek_api_keys() or []
        except Exception:
            deepseek_keys = []
        try:
            groq_keys = _api.initialize_groq_api_keys() or []
        except Exception:
            groq_keys = []
        try:
            openrouter_keys = _api.initialize_openrouter_api_keys() or []
        except Exception:
            openrouter_keys = []

        console.print(
            i18n.tr(language, "diagnostics_google_keys", count=len(google_keys))
        )
        console.print(
            i18n.tr(language, "diagnostics_deepseek_keys", count=len(deepseek_keys))
        )
        console.print(
            i18n.tr(language, "diagnostics_groq_keys", count=len(groq_keys))
        )
        console.print(
            i18n.tr(language, "diagnostics_openrouter_keys", count=len(openrouter_keys))
        )

    except Exception:
        # Không để lỗi diagnostics API key làm vỡ lệnh
        pass

    # Giải thích rõ hành vi fallback của Agent khi dùng DeepSeek/Groq
    if isinstance(agent_model, str) and (
        agent_model.startswith("deepseek-") or agent_model.startswith("groq-")
    ):
        console.print(i18n.tr(language, "diagnostics_agent_fallback_note"))

    # Gợi ý thêm về cách dùng cho từng provider đang hiện diện trong cấu hình
    providers_in_use = { _provider_name(model_name) for _, model_name in rows if model_name is not None }
    for provider in sorted(providers_in_use):
        if provider == "Gemini":
            hint_key = "diagnostics_hint_gemini"
        elif provider == "DeepSeek":
            hint_key = "diagnostics_hint_deepseek"
        elif provider == "Groq":
            hint_key = "diagnostics_hint_groq"
        elif provider == "OpenRouter":
            hint_key = "diagnostics_hint_openrouter"
        else:
            continue
        console.print(i18n.tr(language, hint_key))

    # Thông tin mini-agent HTTP (single-turn) để dễ debug cấu hình
    mini_cfg = config.get("mini_agent") or {}
    rules = mini_cfg.get("rules") or []
    tools = sorted({
        rule.get("tool_name")
        for rule in rules
        if isinstance(rule, dict) and rule.get("tool_name")
    })
    enabled = bool(mini_cfg.get("enabled", True))

    if language == "vi":
        status = "bật" if enabled else "tắt"
        console.print(
            f"[dim]Mini-agent HTTP (single-turn): {status}, {len(rules)} rule, tools: {', '.join(tools) or '-'}[/dim]"
        )
    else:
        status = "enabled" if enabled else "disabled"
        console.print(
            f"[dim]HTTP mini-agent (single-turn): {status}, {len(rules)} rules, tools: {', '.join(tools) or '-'}[/dim]"
        )

    issues = mini_agent.validate_mini_agent_rules(config)
    if issues:
        warning_prefix = i18n.tr(language, "diagnostics_mini_agent_warnings")
        console.print(warning_prefix)
        for msg in issues:
            console.print(f"[yellow]- {msg}[/yellow]")