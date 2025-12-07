"""
Module xử lý các tác vụ liên quan đến lịch sử trò chuyện,
bao gồm hiển thị, tải, tóm tắt và lưu trữ.
"""
import logging

from rich.console import Console

from termi_cli.config import APP_DIR
from termi_cli.application.history_service import HistoryService

# --- CONSTANTS ---
HISTORY_DIR = str(APP_DIR / "chat_logs")
logger = logging.getLogger(__name__)

def load_history_file(file_path: str) -> dict:
    """Wrapper mỏng uỷ quyền cho HistoryService.load_history_file.

    Giữ nguyên API cũ để các module khác (chat_service, __main__) không cần đổi chữ ký.
    """

    service = HistoryService()
    return service.load_history_file(file_path)

def print_formatted_history(console: Console, history: list):
    """Wrapper mỏng gọi HistoryService.print_formatted_history."""

    service = HistoryService()
    return service.print_formatted_history(console, history)

def serialize_history(history):
    """Wrapper mỏng gọi HistoryService.serialize_history."""

    service = HistoryService()
    return service.serialize_history(history)

def show_history_browser(console: Console, filter_query: str | None = None):
    """Wrapper mỏng gọi HistoryService.show_history_browser."""

    service = HistoryService()
    return service.show_history_browser(console, filter_query)

def handle_history_summary(
    console: Console, config: dict, history: list, cli_help_text: str
):

    """Wrapper mỏng gọi HistoryService.handle_history_summary."""

    service = HistoryService()
    return service.handle_history_summary(console, config, history, cli_help_text)

def _resolve_history_file(target: str) -> str:
    """Giữ lại helper cũ để tương thích, uỷ quyền cho HistoryService._resolve_history_file."""

    service = HistoryService()
    return service._resolve_history_file(target)

def delete_history_entry(console: Console, target: str) -> bool:
    """Wrapper mỏng gọi HistoryService.delete_history_entry."""

    service = HistoryService()
    return service.delete_history_entry(console, target)

def rename_history_entry(console: Console, old: str, new_title: str) -> bool:
    """Wrapper mỏng gọi HistoryService.rename_history_entry."""

    service = HistoryService()
    return service.rename_history_entry(console, old, new_title)