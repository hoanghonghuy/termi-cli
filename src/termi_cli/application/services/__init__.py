"""Service container đơn giản cho layer application.

Cung cấp các hàm get_*_service() để các handler/CLI lấy singleton service,
tránh phải khởi tạo lặp lại và chuẩn bị cho DI rõ ràng hơn.
"""

from __future__ import annotations

from termi_cli.application.chat_service import ChatService
from termi_cli.application.agent_service import AgentService
from termi_cli.application.history_service import HistoryService
from termi_cli.application.config_service import ConfigService
from termi_cli.application.utility_service import UtilityService


_chat_service = ChatService()
_agent_service = AgentService()
_history_service = HistoryService()
_config_service = ConfigService()
_utility_service = UtilityService()


def get_chat_service() -> ChatService:
    return _chat_service


def get_agent_service() -> AgentService:
    return _agent_service


def get_history_service() -> HistoryService:
    return _history_service


def get_config_service() -> ConfigService:
    return _config_service


def get_utility_service() -> UtilityService:
    return _utility_service
