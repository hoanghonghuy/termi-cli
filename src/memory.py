import chromadb
import time
import os
from chromadb.config import Settings

# Tạo một thư mục để lưu trữ database
DB_PATH = "memory_db"
if not os.path.exists(DB_PATH):
    os.makedirs(DB_PATH)

# Sử dụng PersistentClient để dữ liệu được lưu vào đĩa
client = chromadb.PersistentClient(
    path=DB_PATH,
    settings=Settings(anonymized_telemetry=False)
)

# Lấy hoặc tạo một "collection" (giống như một bảng)
# Collection này sẽ lưu trữ các đoạn hội thoại
collection = client.get_or_create_collection(name="long_term_memory")

def add_memory(user_prompt: str, ai_response: str):
    """
    Thêm một lượt hội thoại vào trí nhớ dài hạn.
    """
    # Bỏ qua các lệnh đơn giản hoặc các phản hồi ngắn không có giá trị
    if len(user_prompt) < 15 or len(ai_response) < 20:
        return

    try:
        document = f"User asked: {user_prompt}\nAI responded: {ai_response}"
        # Dùng timestamp làm ID duy nhất
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
            
        # Định dạng kết quả để đưa vào prompt cho AI
        context = "### Relevant Past Conversations:\n"
        for doc in documents:
            context += f"- {doc}\n"
        return context
    except Exception as e:
        print(f"--- MEMORY ERROR: Không thể tìm kiếm: {e} ---")
        return ""