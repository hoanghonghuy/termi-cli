"""Infrastructure-level repository cho các thao tác git cơ bản.

Được UtilityService sử dụng để tách riêng phần IO/subprocess khỏi logic ứng dụng.
"""

from __future__ import annotations

import subprocess
from typing import Any


class GitRepository:
    """Repository đơn giản bọc quanh các lệnh git mà UtilityService cần.

    Mục tiêu là giúp test dễ hơn (có thể mock GitRepository) và gom phần
    subprocess lại một chỗ.
    """

    def get_status_porcelain(self) -> str:
        """Trả về output của `git status --porcelain` (có thể rỗng)."""

        return subprocess.check_output(
            ["git", "status", "--porcelain"],
            text=True,
            encoding="utf-8",
        ).strip()

    def stage_all(self) -> None:
        """Chạy `git add .` với check=True để báo lỗi nếu lệnh thất bại."""

        subprocess.run(
            ["git", "add", "."],
            check=True,
            capture_output=True,
        )

    def get_staged_diff(self) -> str:
        """Trả về output của `git diff --staged` (có thể rỗng)."""

        return subprocess.check_output(
            ["git", "diff", "--staged"],
            text=True,
            encoding="utf-8",
        ).strip()
