from textual.widgets import Static
from rich.console import RenderableType
from rich.markdown import Markdown
from rich.text import Text

class ChatMessage(Static):
    """Widget hiển thị một tin nhắn trong cuộc hội thoại."""

    def __init__(self, role: str, content: str | RenderableType, **kwargs):
        """
        Args:
            role: "user" | "model" | "system" | "tool"
            content: Nội dung tin nhắn (string hoặc Renderable)
        """
        super().__init__(**kwargs)
        self.role = role
        self.content = content
        
    def on_mount(self) -> None:
        """Render nội dung khi widget được mount."""
        if isinstance(self.content, str):
            # Render Markdown cho text content
            self.update(Markdown(self.content))
        else:
            # Render trực tiếp nếu là Renderable (vd: Table, Panel)
            self.update(self.content)
            
        # Thêm CSS class tương ứng với role
        self.add_class(f"message-{self.role}")
