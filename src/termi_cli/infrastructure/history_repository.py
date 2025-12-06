"""Infrastructure-level repository cho IO lịch sử trò chuyện.

Đảm nhiệm đọc/ghi/ghi đè/xoá file history JSON trên đĩa.
Logic nghiệp vụ (i18n, lựa chọn file, hiển thị) nằm ở HistoryService.
"""

from __future__ import annotations

import glob
import json
import os
from typing import Any


class HistoryRepository:
    """Repository đơn giản thao tác với các file history JSON."""

    def __init__(self, history_dir: str) -> None:
        self._history_dir = history_dir

    @property
    def history_dir(self) -> str:
        return self._history_dir

    def history_dir_exists(self) -> bool:
        return os.path.exists(self._history_dir)

    def ensure_history_dir(self) -> None:
        os.makedirs(self._history_dir, exist_ok=True)

    def list_history_files(self) -> list[str]:
        """Liệt kê tất cả file history (*.json) trong thư mục history."""

        pattern = os.path.join(self._history_dir, "*.json")
        return glob.glob(pattern)

    def read_raw(self, file_path: str) -> str:
        """Đọc toàn bộ nội dung file history dưới dạng text raw."""

        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    def write_json(self, file_path: str, data: dict[str, Any]) -> None:
        """Ghi dữ liệu JSON ra file history."""

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def delete_file(self, file_path: str) -> None:
        """Xoá một file history cụ thể."""

        os.remove(file_path)

    def rename_file(self, old_path: str, new_path: str) -> None:
        """Đổi tên file history từ old_path sang new_path."""

        os.rename(old_path, new_path)

    def file_exists(self, file_path: str) -> bool:
        """Kiểm tra sự tồn tại của một file history cụ thể."""

        return os.path.exists(file_path)
