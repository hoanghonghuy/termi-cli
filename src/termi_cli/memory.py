import chromadb
from chromadb.config import Settings
import time
import os
import shutil
import logging

from termi_cli.config import APP_DIR

DB_PATH = str(APP_DIR / "memory_db")

logger = logging.getLogger(__name__)

# Khởi tạo lười để tránh mở file SQLite khi chỉ muốn xoá DB (reset-memory).
client = None
collection = None
MEMORY_DISABLED = False


def _ensure_collection():
    """Đảm bảo collection ChromaDB đã được khởi tạo, với xử lý fallback khi DB hỏng.

    Trả về đối tượng collection hoặc None nếu trí nhớ bị vô hiệu hoá.
    """
    global client, collection, MEMORY_DISABLED

    if MEMORY_DISABLED:
        return None
    if collection is not None:
        return collection

    try:
        os.makedirs(DB_PATH, exist_ok=True)
        client = chromadb.PersistentClient(
            path=DB_PATH,
            settings=Settings(anonymized_telemetry=False),
        )
        collection = client.get_or_create_collection(name="long_term_memory")
        return collection
    except Exception as e:
        logger.warning(
            "--- MEMORY WARNING: Không thể khởi tạo database tại '%s'. Lỗi: %s ---",
            DB_PATH,
            e,
        )
        logger.warning(
            "--- MEMORY WARNING: Có thể database đã bị hỏng. Đang thử tạo lại... ---"
        )

        try:
            corrupted_db_path = f"{DB_PATH}_corrupted_{int(time.time())}"
            if os.path.exists(DB_PATH):
                shutil.move(DB_PATH, corrupted_db_path)
                logger.warning(
                    "--- MEMORY WARNING: Đã đổi tên thư mục DB hỏng thành '%s'. ---",
                    corrupted_db_path,
                )

            os.makedirs(DB_PATH, exist_ok=True)
            client = chromadb.PersistentClient(
                path=DB_PATH,
                settings=Settings(anonymized_telemetry=False),
            )
            collection = client.get_or_create_collection(name="long_term_memory")
            logger.info("--- MEMORY: Đã tạo lại database trí nhớ thành công. ---")
            return collection
        except Exception as final_e:
            logger.error(
                "--- MEMORY CRITICAL ERROR: Không thể tạo lại database. Trí nhớ sẽ bị vô hiệu hóa. Lỗi: %s ---",
                final_e,
            )
            MEMORY_DISABLED = True
            return None


def reset_memory_db() -> bool:
    """Xoá toàn bộ database trí nhớ dài hạn (thư mục memory_db)."""
    global client, collection, MEMORY_DISABLED
    try:
        # Ngắt tham chiếu client/collection trong tiến trình hiện tại
        client = None
        collection = None
        MEMORY_DISABLED = False

        if os.path.exists(DB_PATH):
            shutil.rmtree(DB_PATH)
        return True
    except Exception as e:
        logger.error("--- MEMORY ERROR: Không thể xoá database memory_db: %s ---", e)
        return False


def add_memory(user_intent: str, tool_calls_log: list, final_response: str):
    """
    Thêm một lượt hội thoại hoàn chỉnh, bao gồm cả log gọi tool, vào trí nhớ.
    Args:
        user_intent (str): Ý định ban đầu của người dùng.
        tool_calls_log (list): Một danh sách các dictionary, mỗi dict ghi lại một tool call.
        final_response (str): Câu trả lời cuối cùng của AI.
    """
    # Bỏ qua các lệnh đơn giản hoặc các phản hồi ngắn không có giá trị
    if len(user_intent) < 15 or len(final_response) < 20:
        return False

    collection_obj = _ensure_collection()
    if collection_obj is None:
        return False

    try:
        # Xây dựng một "tài liệu" hoàn chỉnh mô tả toàn bộ lượt tương tác
        document = f"User's intent was: {user_intent}\n"

        if tool_calls_log:
            document += "The AI performed the following actions:\n"
            for log in tool_calls_log:
                document += f"- Called tool `{log['name']}` with arguments `{log['args']}`.\n"
                # Chỉ hiển thị một phần kết quả của tool để tránh làm document quá dài
                tool_result_snippet = (log['result'][:200] + '...') if len(log['result']) > 200 else log['result']
                document += f"  - Tool returned: {tool_result_snippet}\n"

        document += f"Finally, the AI responded: {final_response}"

        doc_id = str(time.time())

        collection_obj.add(
            documents=[document],
            ids=[doc_id]
        )
        logger.debug("MEMORY: saved 1 interaction to long-term store.")
        return True
    except Exception as e:
        logger.error("--- MEMORY ERROR: Không thể ghi nhớ: %s ---", e)
        return False


def search_memory(query: str, n_results: int = 2) -> str:
    """
    Tìm kiếm trong trí nhớ các đoạn hội thoại liên quan nhất.
    """
    collection_obj = _ensure_collection()
    if collection_obj is None:
        return ""

    try:
        results = collection_obj.query(
            query_texts=[query],
            n_results=n_results
        )

        documents = results.get('documents', [[]])[0]
        if not documents:
            return ""

        context = "### Relevant Past Interactions (from Long-Term Memory):\n"
        for doc in documents:
            context += f"---\n{doc}\n"
        return context
    except Exception as e:
        logger.error("--- MEMORY ERROR: Không thể tìm kiếm: %s ---", e)
        return ""