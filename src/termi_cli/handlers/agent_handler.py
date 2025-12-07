# src/termi_cli/handlers/agent_handler.py

"""
Module xử lý các chế độ Agent.

Handler giờ chỉ đóng vai trò wrapper mỏng, uỷ quyền logic cho AgentService.
"""
import argparse

from rich.console import Console

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