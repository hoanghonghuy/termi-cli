"""
Module xử lý các tiện ích độc lập như git-commit, document, refactor.
"""
import argparse
from rich.console import Console

from termi_cli.application.utility_service import UtilityService


def generate_git_commit_message(
    console: Console,
    args: argparse.Namespace,
    short: bool = False,
) -> None:
    """Wrapper mỏng uỷ quyền cho UtilityService.generate_git_commit_message."""

    service = UtilityService()
    return service.generate_git_commit_message(console, args, short=short)


def document_code_file(console: Console, args: argparse.Namespace) -> None:
    """Wrapper mỏng uỷ quyền cho UtilityService.document_code_file."""

    service = UtilityService()
    return service.document_code_file(console, args)


def refactor_code_file(console: Console, args: argparse.Namespace) -> None:
    """Wrapper mỏng uỷ quyền cho UtilityService.refactor_code_file."""

    service = UtilityService()
    return service.refactor_code_file(console, args)