"""Auto-complete for Termi CLI chat.

Provides slash command auto-completion using prompt_toolkit.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Check for prompt_toolkit availability
_PROMPT_TOOLKIT_AVAILABLE = False
try:
    from prompt_toolkit import prompt as pt_prompt
    from prompt_toolkit.completion import Completer, Completion
    from prompt_toolkit.styles import Style
    _PROMPT_TOOLKIT_AVAILABLE = True
except ImportError:
    pt_prompt = None
    Completer = None
    Completion = None
    Style = None
    logger.debug("prompt_toolkit not available, auto-complete disabled")


# All available slash commands
SLASH_COMMANDS = [
    ("/help", "Hiển thị trợ giúp"),
    ("/tools", "Liệt kê tools khả dụng"),
    ("/alias", "Quản lý phím tắt"),
    ("/alias add", "Thêm alias mới"),
    ("/alias remove", "Xóa alias"),
    ("/template", "Quản lý templates"),
    ("/template use", "Sử dụng template"),
    ("/template add", "Thêm template"),
    ("/template remove", "Xóa template"),
    ("/rag", "Bật/tắt chế độ RAG"),
    ("/clear", "Xóa lịch sử chat"),
    ("/export", "Xuất cuộc hội thoại"),
    ("/model", "Xem/đổi model"),
    ("/save", "Lưu phiên"),
    ("/load", "Tải phiên"),
    ("/history", "Xem lịch sử"),
    ("/update", "Kiểm tra cập nhật"),
    ("/theme", "Đổi theme"),
    ("/image", "Đính kèm ảnh"),
    ("/file", "Đính kèm file"),
    ("/voice", "Thu âm giọng nói"),
    ("exit", "Thoát chat"),
]


class SlashCommandCompleter(Completer if _PROMPT_TOOLKIT_AVAILABLE else object):
    """Completer for slash commands."""
    
    def get_completions(self, document, complete_event):
        """Yield completions for current input."""
        if not _PROMPT_TOOLKIT_AVAILABLE:
            return
        
        text = document.text_before_cursor.lower()
        
        # Only complete if starts with /
        if not text.startswith("/"):
            return
        
        for cmd, desc in SLASH_COMMANDS:
            if cmd.lower().startswith(text):
                yield Completion(
                    cmd,
                    start_position=-len(text),
                    display=cmd,
                    display_meta=desc,
                )


def get_input_with_autocomplete(prompt_text: str = "You: ") -> str:
    """Get user input with auto-complete support.
    
    Args:
        prompt_text: Prompt to display
        
    Returns:
        User input string
    """
    if not _PROMPT_TOOLKIT_AVAILABLE:
        # Fallback to standard input
        return input(prompt_text)
    
    try:
        style = Style.from_dict({
            "prompt": "bold green",
            "": "white",
        })
        
        return pt_prompt(
            prompt_text,
            completer=SlashCommandCompleter(),
            style=style,
            complete_while_typing=True,
        )
    except (KeyboardInterrupt, EOFError):
        return "exit"
    except Exception as e:
        logger.warning("Auto-complete failed: %s", e)
        return input(prompt_text)


def is_autocomplete_available() -> bool:
    """Check if auto-complete is available."""
    return _PROMPT_TOOLKIT_AVAILABLE
