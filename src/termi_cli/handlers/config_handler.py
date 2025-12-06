"""
Module xử lý các tác vụ liên quan đến cấu hình của ứng dụng,
bao gồm quản lý persona, custom instructions và lựa chọn model.
"""

import subprocess

from rich.console import Console
from rich.table import Table

from termi_cli import api, i18n
from termi_cli.config import save_config
from termi_cli.handlers import mini_agent
from termi_cli.application.config_service import ConfigService


def model_selection_wizard(console: Console, config: dict):
    """UI chọn model nâng cao: default_model, code_model, commit_model.

    Bước đầu tiên: chọn provider (Gemini / DeepSeek / Groq / OpenRouter),
    sau đó chọn model tương ứng cho từng vai trò.
    """
    language = config.get("language", "vi")
    model_labels = config.get("model_labels") or {}

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

        def _get_ollama_local_models() -> list[dict]:
            """Lấy danh sách model Ollama local bằng cách parse output của `ollama list`.

            Output mẫu:
                NAME                       ID              SIZE      MODIFIED
                deepseek-r1:1.5b           e0979632db5a    1.1 GB    2 minutes ago
                qwen3:8b                   500a1f067a9f    5.2 GB    31 hours ago
                qwen3-coder:480b-cloud     e30e45586389    -         31 hours ago
            """
            try:
                result = subprocess.run(
                    ["ollama", "list"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode != 0:
                    return []
            except (FileNotFoundError, subprocess.SubprocessError, subprocess.TimeoutExpired):
                return []

            models: list[dict] = []
            lines = result.stdout.strip().splitlines()

            for line in lines:
                line = line.strip()
                if not line:
                    continue
                # Bỏ qua dòng header
                if line.upper().startswith("NAME"):
                    continue

                tokens = line.split()
                if len(tokens) < 3:
                    continue

                name = tokens[0]
                # tokens[1] là ID, bỏ qua

                # Parse size: có thể là "1.1 GB", "986 MB", hoặc "-" (cloud model)
                size_mb = 0.0
                if tokens[2] == "-":
                    size_mb = 0.0
                elif len(tokens) >= 4:
                    try:
                        size_val = float(tokens[2])
                        size_unit = tokens[3].upper()
                        if size_unit == "GB":
                            size_mb = size_val * 1024
                        elif size_unit == "MB":
                            size_mb = size_val
                        elif size_unit == "KB":
                            size_mb = size_val / 1024
                    except ValueError:
                        size_mb = 0.0

                models.append({"name": name, "size_mb": size_mb})

            # Loại bỏ duplicate (nếu có)
            unique_models: list[dict] = []
            seen: set[str] = set()
            for item in models:
                if item["name"] not in seen:
                    unique_models.append(item)
                    seen.add(item["name"])
            return unique_models

        variant_raw = console.input(i18n.tr(language, "config_ollama_variant_prompt"), markup=False).strip()
        variant = 2 if variant_raw == "2" else 1

        if variant == 2:
            console.print(i18n.tr(language, "config_ollama_cloud_api_hint"))
            default_model = _ask_ollama_model("config_ollama_cloud_model_prompt", "ollama-cloud/")
        else:
            local_models = _get_ollama_local_models()
            if local_models:
                table = Table(title=i18n.tr(language, "config_model_selection_title"))
                table.add_column("#", style="cyan")
                table.add_column("Model tag", style="magenta")
                table.add_column("Size (MB)", style="green")
                for idx, item in enumerate(local_models, start=1):
                    size_display = f"{item['size_mb']:.1f}" if item["size_mb"] else "-"
                    table.add_row(str(idx), item["name"], size_display)
                console.print(table)

                while True:
                    try:
                        prompt = i18n.tr(language, "config_ollama_local_select_prompt")
                        choice_str = console.input(prompt, markup=False).strip()
                        if not choice_str:
                            console.print(i18n.tr(language, "config_selection_cancelled"))
                            return None
                        if choice_str.isdigit():
                            idx = int(choice_str) - 1
                            if 0 <= idx < len(local_models):
                                selected = local_models[idx]["name"]
                                default_model = f"ollama/{selected}"
                                break
                            console.print(i18n.tr(language, "config_invalid_choice"))
                            continue
                        selected = choice_str
                        if not selected.startswith("ollama/"):
                            selected = f"ollama/{selected}"
                        default_model = selected
                        break
                    except (KeyboardInterrupt, EOFError):
                        console.print(i18n.tr(language, "config_selection_cancelled"))
                        return None
            else:
                console.print(i18n.tr(language, "config_ollama_local_no_models"))
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
    """Wrapper mỏng gọi ConfigService.add_instruction."""

    service = ConfigService()
    return service.add_instruction(console, config, instruction)


def list_instructions(console: Console, config: dict):
    """Wrapper mỏng gọi ConfigService.list_instructions."""

    service = ConfigService()
    return service.list_instructions(console, config)


def remove_instruction(console: Console, config: dict, index: int):
    """Wrapper mỏng gọi ConfigService.remove_instruction."""

    service = ConfigService()
    return service.remove_instruction(console, config, index)


def add_persona(console: Console, config: dict, name: str, instruction: str):
    """Wrapper mỏng gọi ConfigService.add_persona."""

    service = ConfigService()
    return service.add_persona(console, config, name, instruction)


def list_personas(console: Console, config: dict):
    """Wrapper mỏng gọi ConfigService.list_personas."""

    service = ConfigService()
    return service.list_personas(console, config)


def remove_persona(console: Console, config: dict, name: str):
    """Wrapper mỏng gọi ConfigService.remove_persona."""

    service = ConfigService()
    return service.remove_persona(console, config, name)


def save_profile(console: Console, config: dict, name: str):
    """Wrapper mỏng gọi ConfigService.save_profile."""

    service = ConfigService()
    return service.save_profile(console, config, name)


def list_profiles(console: Console, config: dict):
    """Wrapper mỏng gọi ConfigService.list_profiles."""

    service = ConfigService()
    return service.list_profiles(console, config)


def remove_profile(console: Console, config: dict, name: str):
    """Wrapper mỏng gọi ConfigService.remove_profile."""

    service = ConfigService()
    return service.remove_profile(console, config, name)


def apply_profile(console: Console, config: dict, name: str):
    """Wrapper mỏng gọi ConfigService.apply_profile."""

    service = ConfigService()
    return service.apply_profile(console, config, name)


def show_diagnostics(console: Console, config: dict):
    """Wrapper mỏng gọi ConfigService.show_diagnostics."""

    service = ConfigService()
    return service.show_diagnostics(console, config)


def model_selection_wizard(console: Console, config: dict):
    """Wrapper mỏng gọi ConfigService.model_selection_wizard.

    Hàm này override định nghĩa ban đầu ở đầu file để handler trở nên mỏng,
    chỉ uỷ quyền logic lựa chọn model cho ConfigService trong application layer.
    """

    service = ConfigService()
    return service.model_selection_wizard(console, config)