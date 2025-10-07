import chromadb
from chromadb.config import Settings
import time
import os
import shutil # Thêm thư viện để xử lý file/thư mục

DB_PATH = "memory_db"

try:
    # Cố gắng khởi tạo client
    client = chromadb.PersistentClient(
        path=DB_PATH,
        settings=Settings(anonymized_telemetry=False)
    )
    # Cố gắng truy cập collection để kiểm tra xem DB có hoạt động không
    collection = client.get_or_create_collection(name="long_term_memory")
except Exception as e:
    print(f"--- MEMORY WARNING: Không thể khởi tạo database tại '{DB_PATH}'. Lỗi: {e} ---")
    print(f"--- MEMORY WARNING: Có thể database đã bị hỏng. Đang thử tạo lại... ---")
    try:
        # Đổi tên thư mục DB bị hỏng
        corrupted_db_path = f"{DB_PATH}_corrupted_{int(time.time())}"
        shutil.move(DB_PATH, corrupted_db_path)
        print(f"--- MEMORY WARNING: Đã đổi tên thư mục DB hỏng thành '{corrupted_db_path}'. ---")
        
        # Thử khởi tạo lại từ đầu
        client = chromadb.PersistentClient(
            path=DB_PATH,
            settings=Settings(anonymized_telemetry=False)
        )
        collection = client.get_or_create_collection(name="long_term_memory")
        print("--- MEMORY: Đã tạo lại database trí nhớ thành công. ---")
    except Exception as final_e:
        print(f"--- MEMORY CRITICAL ERROR: Không thể tạo lại database. Trí nhớ sẽ bị vô hiệu hóa. Lỗi: {final_e} ---")
        # Vô hiệu hóa các hàm nếu không thể tạo lại DB
        def add_memory(*args, **kwargs): pass
        def search_memory(*args, **kwargs): return ""


def add_memory(user_prompt: str, ai_response: str):
    """
    Thêm một lượt hội thoại vào trí nhớ dài hạn.
    """
    if len(user_prompt) < 15 or len(ai_response) < 20:
        return

    try:
        document = f"User asked: {user_prompt}\nAI responded: {ai_response}"
        doc_id = str(time.time())
        
        collection.add(
            documents=[document],
            ids=[doc_id]
        )
        print(f"--- MEMORY: Đã ghi nhớ 1 đoạn hội thoại. ---")
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
            
        context = "### Relevant Past Conversations:\n"
        for doc in documents:
            context += f"- {doc}\n"
        return context
    except Exception as e:
        print(f"--- MEMORY ERROR: Không thể tìm kiếm: {e} ---")
        return ""