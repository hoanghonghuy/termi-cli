"""
Package handler, giúp gom nhóm và export các hàm xử lý chính của ứng dụng.
"""

# Export các hàm từ các module con để tiện import từ bên ngoài
from .config_handler import (
    add_instruction,
    list_instructions,
    remove_instruction,
    add_persona,
    list_personas,
    remove_persona,
    model_selection_wizard,
)
from .history_handler import (
    show_history_browser,
    handle_history_summary,
    print_formatted_history,
    serialize_history,
)
from .chat_handler import run_chat_mode
from .agent_handler import run_agent_mode
from .core_handler import handle_conversation_turn