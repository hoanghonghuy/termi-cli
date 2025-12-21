from textual.widgets import OptionList
from textual.binding import Binding
from textual.message import Message

class SlashMenu(OptionList):
    """Popup menu for slash commands."""
    
    DEFAULT_CSS = """
    SlashMenu {
        layer: overlay;
        width: 30;
        height: auto;
        max-height: 10;
        border: solid $accent;
        background: $surface;
        display: none; /* Hidden by default */
        padding: 0;
    }
    """

    class Selected(Message):
        """Posted when a command is selected."""
        def __init__(self, command: str) -> None:
            super().__init__()
            self.command = command

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.all_commands = [
            "/model - Switch AI Model",
            "/provider - Switch Provider",
            "/theme - Toggle Dark/Light",
            "/history - View Sessions",
            "/context - View System Info",
            "/settings - Open Settings",
            "/agent - Toggle Agent Mode",
            "/imggen - Generate Image",
            "/clear - Clear Chat",
            "/quit - Exit Termi"
        ]
        self.add_options(self.all_commands)

    def filter_options(self, query: str) -> None:
        """Filter commands based on user input."""
        self.clear_options()
        if not query:
            self.add_options(self.all_commands)
            return

        filtered = [cmd for cmd in self.all_commands if cmd.startswith(query)]
        if filtered:
            self.add_options(filtered)
            self.display = True
        else:
            self.display = False # Hide if no matches
