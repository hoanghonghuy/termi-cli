# src/termi_cli/handlers/agent_handler.py

"""
Module xử lý các chế độ Agent, với cơ chế retry và chuyển đổi API key toàn cục.
"""
import json
import re
import argparse
import time

from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel

from rich.text import Text
from rich.tree import Tree
from rich.table import Table

from termi_cli import api, i18n
from termi_cli.api import RPDQuotaExhausted # Import exception tùy chỉnh

from termi_cli.prompts import build_agent_instruction, build_master_agent_prompt, build_executor_instruction
from termi_cli.config import load_config
from .core_handler import confirm_and_write_file
from termi_cli.json_utils import JsonPayloadParseError, parse_json_payload
from termi_cli.application.services import get_agent_service


def run_master_agent(console: Console, args: argparse.Namespace) -> None:
    """Hàm chính điều khiển Agent (wrapper mỏng).

    Handler chỉ uỷ quyền toàn bộ logic cho AgentService ở application layer
    thông qua service container.
    """

    service = get_agent_service()
    return service.run_master_agent(console, args)


def execute_project_plan(
    console: Console, args: argparse.Namespace, project_plan: dict
) -> None:
    """Wrapper mỏng uỷ quyền cho AgentService.execute_project_plan."""

    service = get_agent_service()
    return service.execute_project_plan(console, args, project_plan)


def execute_simple_task(
    console: Console, args: argparse.Namespace, first_step: dict
) -> None:
    """Wrapper mỏng uỷ quyền cho AgentService.execute_simple_task."""

    service = get_agent_service()
    return service.execute_simple_task(console, args, first_step)