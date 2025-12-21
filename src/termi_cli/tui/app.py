from textual.app import App
from termi_cli.tui.screens.chat_screen import ChatScreen

class TermiApp(App):
    """Termi CLI - Textual Interface."""
    
    CSS_PATH = "termi.tcss"
    TITLE = "Termi CLI"
    
    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("?", "push_screen('help')", "Help"),
    ]

    def __init__(self, config: dict, language: str, **kwargs):
        super().__init__(**kwargs)
        self.config = config
        self.language = language

    def on_mount(self) -> None:
        self.push_screen(ChatScreen(app_config=self.config))

    def action_toggle_dark(self) -> None:
        """Toggle dark mode."""
        self.toggle_class("light")

if __name__ == "__main__":
    app = TermiApp(config={}, language="en")
    app.run()
