import os
import time
import requests

# Biến toàn cục để theo dõi thời gian request cuối cùng
LAST_REQUEST_TIME = 0

def search_web(query: str):
    """
    Performs a web search using the official Brave Search API, respecting rate limits.
    Args:
        query (str): The search query to find information on the web.
    Returns:
        str: Formatted search results with titles, URLs, and snippets.
    """
    global LAST_REQUEST_TIME
    
    # --- Logic xử lý Rate Limit ---
    current_time = time.time()
    elapsed_since_last_request = current_time - LAST_REQUEST_TIME
    
    if elapsed_since_last_request < 1.0:
        sleep_duration = 1.0 - elapsed_since_last_request
        print(f"--- TOOL: Chờ {sleep_duration:.2f}s để tuân thủ giới hạn 1 request/giây ---")
        time.sleep(sleep_duration)
    # --- Kết thúc logic Rate Limit ---

    print(f"--- TOOL: Đang tìm kiếm Brave với từ khóa: '{query}' ---")
    
    try:
        api_key = os.getenv("BRAVE_API_KEY")

        if not api_key:
            return "Lỗi: Vui lòng cấu hình BRAVE_API_KEY trong file .env"

        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": api_key
        }
        
        params = {
            "q": query,
            "count": 5
        }

        # Thực hiện request và cập nhật thời gian
        response = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers=headers,
            params=params,
            timeout=10
        )
        LAST_REQUEST_TIME = time.time() # Cập nhật thời gian sau khi request hoàn tất
        response.raise_for_status()

        search_data = response.json()
        search_items = search_data.get("web", {}).get("results", [])

        if not search_items:
            return "Không tìm thấy kết quả nào phù hợp."

        results_str = f"Tìm thấy {len(search_items)} kết quả cho '{query}':\n\n"
        
        for i, item in enumerate(search_items, 1):
            title = item.get('title', 'Không có tiêu đề')
            url = item.get('url', 'Không có URL')
            snippet = item.get('description', 'Không có mô tả').replace('\n', ' ')
            
            results_str += f"[{i}] {title}\n"
            results_str += f"URL: {url}\n"
            results_str += f"Nội dung: {snippet}\n\n"
            
        return results_str

    except requests.exceptions.RequestException as e:
        LAST_REQUEST_TIME = time.time() # Cập nhật thời gian ngay cả khi có lỗi
        error_msg = f"Lỗi mạng khi gọi Brave API: {str(e)}"
        print(error_msg)
        return error_msg
    except Exception as e:
        LAST_REQUEST_TIME = time.time() # Cập nhật thời gian ngay cả khi có lỗi
        error_msg = f"Lỗi không xác định khi tìm kiếm: {str(e)}"
        print(error_msg)
        return error_msg