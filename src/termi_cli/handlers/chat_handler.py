"""Module handler cho chế độ chat.

Hiện tại giữ public API cũ nhưng uỷ quyền logic chính cho ChatService ở application.chat_service.
"""

import argparse

from rich.console import Console

from termi_cli.application.services import get_chat_service


def run_chat_mode_legacy(
    chat_session,
    console: Console,
    config: dict,
    args: argparse.Namespace,
) -> None:
    """Wrapper mỏng gọi ChatService cho chat Gemini (Legacy)."""

    service = get_chat_service()
    service.run_chat_mode_legacy(chat_session, console, config, args)


def run_chat_mode(
    console: Console,
    config: dict,
    args: argparse.Namespace,
    system_instruction: str,
) -> None:
    """Wrapper mỏng gọi ChatService cho chat HTTP providers (Universal)."""

    service = get_chat_service()
    service.run_chat_mode(console, config, args, system_instruction)