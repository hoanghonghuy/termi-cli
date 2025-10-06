import os
import google.generativeai as genai
from dotenv import load_dotenv

# Tải API key
load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")

if not api_key:
    print("Không tìm thấy GOOGLE_API_KEY trong file .env")
else:
    try:
        # Cấu hình
        genai.configure(api_key=api_key)

        print("Đang lấy danh sách các model khả dụng cho key của bạn...")
        print("-" * 50)

        # Lặp qua tất cả model và chỉ in ra những model hỗ trợ 'generateContent'
        found_model = False
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                print(f"-> {m.name}")
                found_model = True

        if not found_model:
            print("Không tìm thấy model nào hỗ trợ generateContent cho API key này.")

        print("-" * 50)

    except Exception as e:
        print(f"Đã xảy ra lỗi khi kết nối tới API: {e}")