"""
TUI Modals Module - SOLID Compliant
Single Responsibility: Each Modal handles one specific UI function.
"""
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Label, ListView, ListItem, OptionList, Input, Button, Static, Switch
from textual.containers import Container, Horizontal, Vertical
from textual.binding import Binding
from termi_cli.i18n import tr

# --- Base Modal ---

class BaseModal(ModalScreen):
    """Base class for all TUI Modals. Provides ESC to dismiss."""
    
    BINDINGS = [Binding("escape", "dismiss", "Close", show=False)]

    def __init__(self, app_config: dict, **kwargs):
        super().__init__(**kwargs)
        self.app_config = app_config
        self.lang = app_config.get("language", "en")

    def action_dismiss(self) -> None:
        self.app.pop_screen()

# --- Provider Modal ---

class ProviderModal(BaseModal):
    """Modal to switch AI provider (Ctrl+g or /provider)."""

    PROVIDERS = ["gemini", "openai_compatible", "groq", "ollama"]

    def compose(self) -> ComposeResult:
        with Container(classes="modal-container"):
            yield Label(tr(self.lang, "tui_provider_modal_title"), classes="modal-title")
            yield OptionList(*self.PROVIDERS, id="provider-options")
            yield Label(tr(self.lang, "tui_modal_esc_hint"), classes="label-small")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        selected = str(event.option.prompt)
        self.dismiss(selected)

# --- Model Modal (Refactored) ---

class ModelModal(BaseModal):
    """Modal to switch AI model (Ctrl+m or /model)."""

    # Default model map - can be overridden by config
    DEFAULT_MODEL_MAP = {
        "gemini": ["models/gemini-pro", "models/gemini-1.5-flash", "models/gemini-2.0-flash"],
        "openai_compatible": ["deepseek-chat", "deepseek-reasoner", "gpt-4o-mini", "gpt-4o", "claude-3-haiku"],
        "groq": ["llama3-8b-8192", "llama3-70b-8192", "mixtral-8x7b-32768"],
        "ollama": ["llama3", "codellama", "mistral", "qwen2.5-coder"],
    }

    def compose(self) -> ComposeResult:
        provider = self.app_config.get("provider", "gemini")
        
        # Try to get models from config first, then fallback to default
        config_models = self.app_config.get("models_by_provider", {}).get(provider)
        models = config_models if config_models else self.DEFAULT_MODEL_MAP.get(provider, self.DEFAULT_MODEL_MAP["openai_compatible"])
        
        with Container(classes="modal-container"):
            yield Label(tr(self.lang, "tui_model_modal_title", provider=provider), classes="modal-title")
            yield OptionList(*models, id="model-options")
            yield Label(tr(self.lang, "tui_modal_esc_hint"), classes="label-small")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        selected = str(event.option.prompt)
        self.dismiss(selected)

# --- History Modal ---

class HistoryModal(BaseModal):
    """Modal to select recent sessions (Ctrl+s or /history)."""

    def compose(self) -> ComposeResult:
        with Container(classes="modal-container"):
            yield Label(tr(self.lang, "tui_history_modal_title"), classes="modal-title")
            
            # Load history from config or default to empty
            history = self.app_config.get("session_history", [])
            if history:
                items = [ListItem(Label(h.get("name", f"Session {i}")), id=f"sess-{i}") 
                         for i, h in enumerate(history)]
                yield ListView(*items, id="history-list")
            else:
                yield Label(tr(self.lang, "tui_history_empty"), classes="label-small")
            
            yield Label(tr(self.lang, "tui_modal_esc_hint"), classes="label-small")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self.dismiss(event.item.id)

# --- Context Modal ---

class ContextModal(BaseModal):
    """Modal to view System Context & Plugins (Ctrl+p or /context)."""

    def compose(self) -> ComposeResult:
        model = self.app_config.get("default_model", "Unknown")
        provider = self.app_config.get("provider", "auto")
        memory = "✅" if self.app_config.get("memory_enabled") else "❌"
        agent_mode = "🤖 ON" if self.app_config.get("agent_mode") else "OFF"
        plugins = self.app_config.get("plugins", [])
        
        with Container(classes="modal-container"):
            yield Label(tr(self.lang, "tui_context_modal_title"), classes="modal-title")
            yield Label(f"Model: {model}", classes="label-label")
            yield Label(f"Provider: {provider}", classes="label-label")
            yield Label(f"Memory: {memory}", classes="label-label")
            yield Label(f"Agent Mode: {agent_mode}", classes="label-label")
            yield Label("---", classes="label-small")
            yield Label(tr(self.lang, "tui_plugins_title"), classes="label-label")
            if plugins:
                yield Label("\n".join([f"• {p}" for p in plugins]))
            else:
                yield Label("None loaded")
            yield Label(tr(self.lang, "tui_modal_esc_hint"), classes="label-small")

# --- Settings Modal ---

class SettingsModal(BaseModal):
    """Modal for application settings (/settings)."""

    def compose(self) -> ComposeResult:
        with Container(classes="modal-container modal-settings"):
            yield Label(tr(self.lang, "tui_settings_modal_title"), classes="modal-title")
            
            # Language
            with Horizontal(classes="setting-row"):
                yield Label(tr(self.lang, "tui_settings_language"), classes="setting-label")
                yield Button("VI", id="lang-vi", variant="primary" if self.lang == "vi" else "default")
                yield Button("EN", id="lang-en", variant="primary" if self.lang == "en" else "default")
            
            # Provider
            with Horizontal(classes="setting-row"):
                yield Label(tr(self.lang, "tui_settings_provider"), classes="setting-label")
                yield Button(self.app_config.get("provider", "gemini").upper(), id="btn-provider")
            
            # Agent Mode Toggle
            with Horizontal(classes="setting-row"):
                yield Label(tr(self.lang, "tui_settings_agent_mode"), classes="setting-label")
                yield Switch(value=self.app_config.get("agent_mode", False), id="agent-toggle")

            # Memory Toggle
            with Horizontal(classes="setting-row"):
                yield Label(tr(self.lang, "tui_settings_memory"), classes="setting-label")
                yield Switch(value=self.app_config.get("memory_enabled", False), id="memory-toggle")
            
            yield Label(tr(self.lang, "tui_modal_esc_hint"), classes="label-small")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "lang-vi":
            self.app_config["language"] = "vi"
            self.dismiss("lang_changed")
        elif event.button.id == "lang-en":
            self.app_config["language"] = "en"
            self.dismiss("lang_changed")
        elif event.button.id == "btn-provider":
            # Open Provider Modal (nested)
            self.app.push_screen(ProviderModal(self.app_config), self._on_provider_selected)

    def on_switch_changed(self, event: Switch.Changed) -> None:
        if event.switch.id == "agent-toggle":
            self.app_config["agent_mode"] = event.value
        elif event.switch.id == "memory-toggle":
            self.app_config["memory_enabled"] = event.value

    def _on_provider_selected(self, provider: str | None) -> None:
        if provider:
            self.app_config["provider"] = provider
            # Update button text (refresh would be better, but this is simpler)
            btn = self.query_one("#btn-provider", Button)
            btn.label = provider.upper()
