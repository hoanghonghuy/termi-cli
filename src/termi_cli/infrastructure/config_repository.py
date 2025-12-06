"""Infrastructure-level repository cho cấu hình Termi CLI.

Đóng gói load/save config để application layer có thể phụ thuộc vào abstraction.
"""

from __future__ import annotations

from typing import Any

from termi_cli.config import load_config, save_config


class ConfigRepository:
    """Repository đơn giản thao tác với config.json thông qua module config."""

    def load(self) -> dict[str, Any]:
        """Tải cấu hình hiện tại từ file config.json (bao gồm merge defaults)."""

        return load_config()

    def save(self, config: dict[str, Any]) -> None:
        """Lưu cấu hình ra file config.json."""

        save_config(config)
