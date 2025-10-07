import chromadb
from chromadb.config import Settings
import time
import os
import shutil

# Tạo một thư mục để lưu trữ database
DB_PATH = "memory_db"

try:
    client = chromadb.PersistentClient(
        path=DB_PATH,
        settings=Settings(anonymized_telemetry=False)
    )
    collection = client.get_or_create_collection(name="long_term_memory")
except Exception as e:
    print(f"--- MEMORY WARNING: Không thể khởi tạo database tại '{DB_PATH}'. Lỗi: {e} ---")
    print(f"--- MEMORY WARNING: Có thể database đã bị hỏng. Đang thử tạo lại... ---")
    try:
        corrupted_db_path = f"{DB_PATH}_corrupted_{int(time.time())}"
        shutil.move(DB_PATH, corrupted_db_path)
        print(f"--- MEMORY WARNING: Đã đổi tên thư mục DB hỏng thành '{corrupted_db_path}'. ---")
        
        client = chromadb.PersistentClient(
            path=DB_PATH,
            settings=Settings(anonymized_telemetry=False)
        )
        collection = client.get_or_create_collection(name="long_term_memory")
        print("--- MEMORY: Đã tạo lại database trí nhớ thành công. ---")
    except Exception as final_e:
        print(f"--- MEMORY CRITICAL ERROR: Không thể tạo lại database. Trí nhớ sẽ bị vô hiệu hóa. Lỗi: {final_e} ---")
        def add_memory(*args, **kwargs): pass
        def search_memory(*args, **kwargs): return ""

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
        return

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
        
        collection.add(
            documents=[document],
            ids=[doc_id]
        )
        print(f"--- MEMORY: Đã ghi nhớ 1 lượt tương tác hoàn chỉnh. ---")
    except Exception as e:
        print(f"--- MEMORY ERROR: Không thể ghi nhớ: {e} ---")

def search_memory(query: str, n_results: int = 2) -> str:
    """
    Tìm kiếm trong trí nhớ các đoạn hội thoại liên quan nhất.
    """
    try:
        results = collection.query(
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
        print(f"--- MEMORY ERROR: Không thể tìm kiếm: {e} ---")
        return ""