"""
Module xử lý các tiện ích độc lập như git-commit, document, refactor.
"""
import os
import sys
import re
import argparse
import subprocess
from rich.console import Console
from rich.markdown import Markdown

from termi_cli import api, utils, i18n
from termi_cli.config import load_config
from termi_cli.tools import code_tool
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