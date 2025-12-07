"""Application-level service cho các tác vụ lịch sử trò chuyện.

Tách logic xử lý history khỏi handlers để handler chỉ còn vai trò I/O/CLI.
"""

from __future__ import annotations

import os
import logging
from datetime import datetime
from typing import Any
import argparse

from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

from termi_cli import api, i18n, utils
from termi_cli.config import load_config, APP_DIR
from termi_cli.handlers.core_handler import handle_conversation_turn
from termi_cli.json_utils import JsonPayloadParseError, parse_json_payload
from termi_cli.infrastructure.history_repository import HistoryRepository


HISTORY_DIR = str(APP_DIR / "chat_logs")
logger = logging.getLogger(__name__)


class HistoryService:
    """Service chính cho các thao tác với lịch sử chat.

    Bao gồm:
    - Duyệt danh sách file history, chọn file cần xem.
    - Đọc/parse file history JSON an toàn.
    - In lịch sử ra màn hình.
    - Tóm tắt lịch sử bằng AI (Gemini hoặc HTTP provider tuỳ model).
    - Xoá / đổi tên một lịch sử.
    - Hỗ trợ serialize history từ chat_session để lưu.
    """

    def __init__(self, repository: HistoryRepository | None = None) -> None:
        """Khởi tạo service với một HistoryRepository để thao tác IO.

        Cho phép inject repository khác khi test, mặc định dùng HISTORY_DIR hiện tại.
        """

        self._repository = repository or HistoryRepository(HISTORY_DIR)

    # --- Helpers cấp thấp ---

    def load_history_file(self, file_path: str) -> dict:
        """Đọc file history và parse JSON với sanitizer trailing comma."""

        raw_content = self._repository.read_raw(file_path)
        try:
            return parse_json_payload(raw_content)
        except JsonPayloadParseError as err:  # noqa: TRY003
            snippet = raw_content[:200].replace("\n", " ")
            logger.warning(
                "History '%s' chứa JSON không hợp lệ: %s", file_path, err
            )
            raise ValueError(
                f"Invalid history JSON in {file_path}: {err}. Body: {snippet}"
            ) from err

    def serialize_history(self, history: Any) -> list[dict[str, Any]]:
        """Chuyển đổi history thành format JSON có thể serialize một cách an toàn."""

        serializable: list[dict[str, Any]] = []
        for content in history:
            content_dict: dict[str, Any] = {"role": content.role, "parts": []}
            for part in getattr(content, "parts", []):
                part_dict: dict[str, Any] = {}
                if hasattr(part, "text") and part.text is not None:
                    part_dict["text"] = part.text
                elif hasattr(part, "function_call") and part.function_call is not None:
                    part_dict["function_call"] = {
                        "name": part.function_call.name,
                        "args": dict(part.function_call.args),
                    }
                elif (
                    hasattr(part, "function_response")
                    and part.function_response is not None
                ):
                    part_dict["function_response"] = {
                        "name": part.function_response.name,
                        "response": dict(part.function_response.response),
                    }
                if part_dict:
                    content_dict["parts"].append(part_dict)
            if content_dict["parts"]:
                serializable.append(content_dict)
        return serializable

    def print_formatted_history(self, console: Console, history: list[dict[str, Any]]):
        """In lịch sử trò chuyện đã tải ra màn hình."""

        language = load_config().get("language", "vi")
        console.print(i18n.tr(language, "history_section_header"))
        for item in history:
            role = item.get("role", "unknown")
            text_parts = [
                p.get("text", "") for p in item.get("parts", []) if p.get("text")
            ]
            text = "".join(text_parts).strip()
            if not text:
                continue
            if role == "user":
                console.print(f"\n{i18n.tr(language, 'history_user_label')} {text}")
            elif role == "model":
                console.print(f"\n{i18n.tr(language, 'history_ai_label')}")
                console.print(Markdown(text))
        console.print(i18n.tr(language, "history_section_footer"))

    # --- Browser history ---

    def show_history_browser(
        self, console: Console, filter_query: str | None = None
    ) -> str | None:
        """Hiển thị danh sách history và cho phép người dùng chọn một file."""

        language = load_config().get("language", "vi")
        console.print(i18n.tr(language, "history_scanning_files", dir=HISTORY_DIR))

        if not self._repository.history_dir_exists():
            console.print(i18n.tr(language, "history_dir_missing", dir=HISTORY_DIR))
            return None

        history_files = self._repository.list_history_files()

        if not history_files:
            console.print(i18n.tr(language, "no_history_files_found"))
            return None

        history_metadata: list[dict[str, Any]] = []
        for file_path in history_files:
            try:
                data = self.load_history_file(file_path)
                title = data.get("title", os.path.basename(file_path))
                last_modified_iso = data.get(
                    "last_modified",
                    datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat(),
                )
                history_metadata.append(
                    {
                        "title": title,
                        "last_modified": last_modified_iso,
                        "file_path": file_path,
                    }
                )
            except (ValueError, OSError) as err:  # noqa: PERF203
                logger.warning(
                    "Bỏ qua history '%s' vì lỗi đọc file: %s", file_path, err
                )
                continue

        history_metadata.sort(key=lambda x: x["last_modified"], reverse=True)

        if filter_query:
            q = filter_query.lower()
            history_metadata = [
                meta
                for meta in history_metadata
                if q in str(meta.get("title", "")).lower()
            ]
            if not history_metadata:
                console.print(i18n.tr(language, "no_history_files_found"))
                return None

        table = Table(title=i18n.tr(language, "history_table_title"))
        table.add_column(i18n.tr(language, "history_table_column_index"), style="cyan")
        table.add_column(
            i18n.tr(language, "history_table_column_title"), style="magenta"
        )
        table.add_column(
            i18n.tr(language, "history_table_column_last_updated"), style="green"
        )

        for i, meta in enumerate(history_metadata):
            mod_time_str = datetime.fromisoformat(meta["last_modified"]).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            table.add_row(str(i + 1), meta["title"], mod_time_str)
        console.print(table)
        try:
            choice_str = console.input(
                i18n.tr(language, "history_select_prompt"), markup=False
            )

            if not choice_str:
                console.print(i18n.tr(language, "history_browser_exit"))
                return None

            choice = int(choice_str)
            if 1 <= choice <= len(history_metadata):
                selected_file = history_metadata[choice - 1]["file_path"]
                console.print(
                    i18n.tr(
                        language,
                        "history_loading_selected",
                        title=history_metadata[choice - 1]["title"],
                    )
                )

                return selected_file
            console.print(i18n.tr(language, "history_invalid_choice"))
        except (ValueError, KeyboardInterrupt, EOFError):  # noqa: PERF203
            console.print(i18n.tr(language, "history_browser_exit"))

        return None

    # --- Tóm tắt history ---

    def handle_history_summary(
        self,
        console: Console,
        config: dict,
        history: list[dict[str, Any]],
        cli_help_text: str,
    ) -> None:
        """Sinh bản tóm tắt cho một lịch sử chat đã load."""

        language = config.get("language", "vi")
        console.print(i18n.tr(language, "history_summary_start"))

        history_text = ""
        for item in history:
            role = "User" if item.get("role") == "user" else "AI"
            text = "".join(
                p.get("text", "") for p in item.get("parts", []) if p.get("text")
            ).strip()
            if text:
                history_text += f"{role}: {text}\n"

        if not history_text:
            console.print(i18n.tr(language, "no_history_to_summarize"))
            return

        prompt = (
            "Dưới đây là một cuộc trò chuyện đã được lưu. "
            "Hãy đọc và tóm tắt lại nội dung chính của nó trong vài gạch đầu dòng ngắn gọn.\n\n"
            f"--- NỘI DUNG CUỘC TRÒ CHUYỆN ---\n{history_text}---\n\n"
            "Tóm tắt của bạn:"
        )

        model_name = config.get("default_model")

        # Nếu default_model là HTTP provider (DeepSeek/Groq/OpenRouter/Ollama), tóm tắt trực tiếp qua HTTP.
        use_http = isinstance(model_name, str) and (
            model_name.startswith("deepseek-")
            or model_name.startswith("groq-")
            or api.is_openrouter_model(model_name)
            or api.is_ollama_model(model_name)
        )

        try:
            if use_http:
                console.print(i18n.tr(language, "history_summary_title"))
                response_text = api.generate_text(
                    model_name,
                    prompt,
                    system_instruction="You are a helpful summarizer.",
                )
                if response_text:
                    console.print(Markdown(response_text))
                return

            # Nhánh mặc định: dùng Gemini chat_session + handle_conversation_turn như trước đây.
            chat_session = api.start_chat_session(
                model_name,
                "You are a helpful summarizer.",
                history=[],
                cli_help_text=cli_help_text,
            )

            console.print(i18n.tr(language, "history_summary_title"))
            handle_conversation_turn(
                chat_session,
                [prompt],
                console,
                args=argparse.Namespace(
                    persona=None, format="rich", cli_help_text=cli_help_text
                ),
            )

        except Exception as e:  # noqa: BLE001
            logger.error("Lỗi tóm tắt lịch sử: %s", e)
            console.print(i18n.tr(language, "error_history_summary", error=e))

    # --- Xoá / đổi tên history ---

    def _resolve_history_file(self, target: str) -> str:
        """Chuyển một tham số generic (path hoặc topic) thành đường dẫn file lịch sử."""

        if os.path.exists(target):
            return target
        return os.path.join(HISTORY_DIR, f"chat_{utils.sanitize_filename(target)}.json")

    def delete_history_entry(self, console: Console, target: str) -> bool:
        """Xóa một lịch sử chat theo đường dẫn file hoặc topic (non-interactive)."""
        language = load_config().get("language", "vi")
        file_path = self._resolve_history_file(target)

        if not self._repository.file_exists(file_path):
            console.print(i18n.tr(language, "history_file_not_found", target=target))
            return False

        try:
            title = os.path.basename(file_path)
            try:
                data = self.load_history_file(file_path)
                title = data.get("title", title)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "Không thể đọc meta trước khi xoá history '%s'", file_path
                )

            self._repository.delete_file(file_path)
            console.print(i18n.tr(language, "history_delete_success", title=title))

            return True
        except Exception as e:  # noqa: BLE001
            logger.error("Lỗi xóa lịch sử: %s", e)
            console.print(
                i18n.tr(language, "chat_cannot_save_history_error", error=e)
            )
            return False

    def rename_history_entry(
        self, console: Console, old: str, new_title: str
    ) -> bool:
        """Đổi tên lịch sử chat theo path hoặc topic sang một tiêu đề mới (non-interactive)."""

        language = load_config().get("language", "vi")

        if not new_title:
            console.print(i18n.tr(language, "history_invalid_choice"))
            return False

        file_path = self._resolve_history_file(old)
        if not self._repository.file_exists(file_path):
            console.print(i18n.tr(language, "history_file_not_found", target=old))
            return False

        try:
            try:
                data = self.load_history_file(file_path)
            except Exception:  # noqa: BLE001
                data = {}

            data["title"] = new_title

            new_filename = f"chat_{utils.sanitize_filename(new_title)}.json"
            new_path = os.path.join(HISTORY_DIR, new_filename)

            # Tránh ghi đè file khác nếu trùng tên
            if (
                os.path.abspath(new_path) != os.path.abspath(file_path)
                and self._repository.file_exists(new_path)
            ):
                console.print(
                    i18n.tr(language, "history_rename_conflict", title=new_title)
                )
                return False

            if os.path.abspath(new_path) != os.path.abspath(file_path):
                self._repository.rename_file(file_path, new_path)

            self._repository.write_json(new_path, data)

            console.print(
                i18n.tr(language, "history_rename_success", title=new_title)
            )
            return True
        except Exception as e:  # noqa: BLE001
            console.print(
                i18n.tr(language, "chat_cannot_save_history_error", error=e)
            )
            return False
