"""
TUI ChatScreen - Main Chat Interface
Refactored to use modals.py for SOLID compliance.
"""
from textual import work
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer, Input, Static
from textual.containers import Horizontal, VerticalScroll, Container
from textual.binding import Binding
from termi_cli.tui.widgets.chat_message import ChatMessage
from termi_cli.tui.widgets.slash_menu import SlashMenu
from termi_cli.tui.screens.modals import (
    ProviderModal, ModelModal, HistoryModal, ContextModal, SettingsModal
)
from termi_cli import api
from termi_cli.i18n import tr
from termi_cli.application.image_generator import generate_image

class ChatScreen(Screen):
    """Zen Mode Chat Screen - Full Focus, Modal-Driven."""

    BINDINGS = [
        Binding("ctrl+l", "clear_chat", "Clear"),
        Binding("ctrl+s", "open_history", "History"), 
        Binding("ctrl+m", "toggle_model", "Model"),
        Binding("ctrl+p", "open_context", "Context"),
        Binding("ctrl+g", "open_provider", "Provider"),
        Binding("d", "toggle_theme", "Theme"),
    ]

    def __init__(self, app_config: dict, **kwargs):
        super().__init__(**kwargs)
        self.app_config = app_config
        self.chat_session = None
        self.lang = app_config.get("language", "en")

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        
        with Container(id="main-container"):
            with VerticalScroll(id="chat-view"):
                yield ChatMessage("system", tr(self.lang, "tui_welcome_message"))
            
            yield SlashMenu(id="slash-menu")

            with Horizontal(id="input-wrapper"):
                yield Input(placeholder=tr(self.lang, "tui_input_placeholder"), id="chat-input")

        yield Footer()

    # --- Theme ---
    def action_toggle_theme(self) -> None:
        self.toggle_class("light")

    # --- Slash Menu ---
    def on_input_changed(self, event: Input.Changed) -> None:
        value = event.value
        menu = self.query_one(SlashMenu)
        if value.startswith("/"):
            menu.display = True
            menu.filter_options(value)
        else:
            menu.display = False

    def on_option_list_option_selected(self, event) -> None:
        if hasattr(event, 'option_list') and event.option_list.id == "slash-menu":
            command = str(event.option.prompt).split(" - ")[0]
            self.handle_slash_command(command)
            self.query_one("#chat-input", Input).value = ""
            self.query_one(SlashMenu).display = False

    def handle_slash_command(self, command: str) -> None:
        cmd_map = {
            "/model": self.action_toggle_model,
            "/provider": self.action_open_provider,
            "/theme": self.action_toggle_theme,
            "/history": self.action_open_history,
            "/context": self.action_open_context,
            "/settings": self.action_open_settings,
            "/clear": lambda: self.run_worker(self.action_clear_chat()),
            "/quit": self.app.exit,
            "/agent": self._toggle_agent_mode,
            "/imggen": self._prompt_imggen,
        }
        action = cmd_map.get(command)
        if action:
            action()
        else:
            self._show_system_message(f"Unknown command: {command}")

    def _toggle_agent_mode(self) -> None:
        current = self.app_config.get("agent_mode", False)
        self.app_config["agent_mode"] = not current
        status = "ON 🤖" if not current else "OFF"
        self._show_system_message(f"Agent Mode: {status}")

    # --- Message Handling ---
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        message = event.value.strip()
        if not message:
            return

        if message.startswith("/"):
            parts = message.split(maxsplit=1)
            command = parts[0]
            
            # Handle /imggen with prompt
            if command == "/imggen" and len(parts) > 1:
                self._run_imggen(parts[1])
                self.query_one("#chat-input", Input).value = ""
                self.query_one(SlashMenu).display = False
                return
            
            self.handle_slash_command(command)
            self.query_one("#chat-input", Input).value = ""
            self.query_one(SlashMenu).display = False
            return
            
        chat_view = self.query_one("#chat-view", VerticalScroll)
        input_widget = self.query_one("#chat-input", Input)
        
        chat_view.mount(ChatMessage("user", message))
        input_widget.value = ""
        self.query_one(SlashMenu).display = False
        chat_view.scroll_end(animate=False)
        
        self.generate_response(message)

    @work(exclusive=True, thread=True)
    def generate_response(self, user_message: str) -> None:
        model_name = self.app_config.get("default_model") or "models/gemini-pro"
        
        if not self.chat_session:
            self.chat_session = api.start_chat_session(model_name=model_name)

        try:
            response = api.resilient_send_message(self.chat_session, user_message)
            response_text = api.get_response_text(response)
            self.app.call_from_thread(self._show_response, response_text)
        except Exception as e:
            self.app.call_from_thread(self._show_error, str(e))

    def _show_response(self, text: str) -> None:
        chat_view = self.query_one("#chat-view", VerticalScroll)
        chat_view.mount(ChatMessage("model", text))
        chat_view.scroll_end(animate=False)

    def _show_error(self, error_msg: str) -> None:
        chat_view = self.query_one("#chat-view", VerticalScroll)
        chat_view.mount(ChatMessage("system", f"❌ Error: {error_msg}"))
        chat_view.scroll_end(animate=False)

    def _show_system_message(self, text: str) -> None:
        chat_view = self.query_one("#chat-view", VerticalScroll)
        chat_view.mount(ChatMessage("system", text))
        chat_view.scroll_end(animate=False)

    # --- Actions (Modal Openers) ---
    async def action_clear_chat(self) -> None:
        chat_view = self.query_one("#chat-view", VerticalScroll)
        await chat_view.remove_children()
        chat_view.mount(ChatMessage("system", "✨ Chat cleared."))

    def action_open_history(self) -> None:
        def on_select(session_id: str | None) -> None:
            if session_id:
                self._show_system_message(f"Loading session: {session_id}")
        self.app.push_screen(HistoryModal(self.app_config), on_select)

    def action_open_context(self) -> None:
        self.app.push_screen(ContextModal(self.app_config))

    def action_open_provider(self) -> None:
        def on_select(provider: str | None) -> None:
            if provider:
                self.app_config["provider"] = provider
                self.chat_session = None  # Reset session for new provider
                self._show_system_message(f"Switched to provider: {provider}")
        self.app.push_screen(ProviderModal(self.app_config), on_select)

    def action_toggle_model(self) -> None:
        def on_select(model: str | None) -> None:
            if model:
                self.app_config["default_model"] = model
                self.chat_session = None
                self._show_system_message(f"Switched to model: {model}")
        self.app.push_screen(ModelModal(self.app_config), on_select)

    def action_open_settings(self) -> None:
        def on_close(result: str | None) -> None:
            if result == "lang_changed":
                self.lang = self.app_config.get("language", "en")
                self._show_system_message(f"Language changed to: {self.lang.upper()}")
        self.app.push_screen(SettingsModal(self.app_config), on_close)

    # --- Image Generation ---
    def _prompt_imggen(self) -> None:
        """Prompt user for image generation."""
        self._show_system_message("🎨 Enter image prompt after /imggen (e.g., /imggen a cat in space)")
        # Note: Actual parsing happens in on_input_submitted when detecting /imggen <prompt>

    @work(exclusive=True, thread=True)
    def _run_imggen(self, prompt: str) -> None:
        """Generate image in background thread."""
        self.app.call_from_thread(self._show_system_message, f"🎨 Generating image: {prompt}...")
        
        result = generate_image(self.app_config, prompt, self.lang)
        
        if result["success"]:
            msg = f"✅ Image saved: {result['path']}"
        else:
            msg = f"❌ Image generation failed: {result['error']}"
        
        self.app.call_from_thread(self._show_system_message, msg)
