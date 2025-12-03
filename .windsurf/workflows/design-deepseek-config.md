---
description: Thiết lập cấu hình model per-use-case (chat/agent/code) với DeepSeek và Gemini
---

1. Mở file cấu hình chính của Termi CLI
   - Đường dẫn: `src/termi_cli/config.py`.
   - Xác nhận các key mặc định trong `defaults`:
     - `default_model`: dùng cho chat + single-turn.
     - `agent_model`: dùng cho Agent.
     - `code_model`: dùng cho các tiện ích code (refactor/document) và có thể trỏ sang DeepSeek.

2. Sửa file `config.py` để thêm key `code_model`
   - Trong dict `defaults`, thêm dòng:
     - `"code_model": "models/gemini-flash-latest",`
   - Mục tiêu: nếu người dùng không cấu hình gì, code tool vẫn dùng Gemini như cũ.

3. Sử dụng `code_model` trong `code_tool.py`
   - Mở `src/termi_cli/tools/code_tool.py`.
   - Trong hàm `refactor_code` và `document_code`:
     - Thay `model_name = config.get("default_model")` bằng:
       - `model_name = config.get("code_model") or config.get("default_model")`.
     - Sau đó gọi `api.generate_text(model_name, prompt)` như bình thường.
   - Điều này cho phép:
     - `code_model = "deepseek-chat"` để refactor/document dùng DeepSeek.
     - Trong khi `default_model` và `agent_model` vẫn trỏ Gemini cho chat/agent.

4. Không thay đổi logic model cho chat/agent
   - Chat & single-turn:
     - Vẫn dùng `args.model or config.get("default_model")` trong `__main__.py` và `chat_handler`.
   - Agent:
     - Vẫn dùng `config.get("agent_model", "models/gemini-pro-latest")` trong `agent_handler`.
   - Điều này đảm bảo việc thêm DeepSeek cho code **không ảnh hưởng** behaviour hiện có của Gemini.

5. Cấu hình `.env` cho DeepSeek
   - Thêm các biến môi trường riêng cho DeepSeek:
     - `DEEPSEEK_API_KEY=...`
     - `DEEPSEEK_API_KEY_2ND=...` (tùy chọn)
   - Không sử dụng chung với `GOOGLE_API_KEY*`.

6. Cập nhật `config.json` để chọn model per-use-case
   - Ví dụ cấu hình:
   ```json
   {
     "default_model": "models/gemini-flash-latest",
     "agent_model": "models/gemini-pro-latest",
     "code_model": "deepseek-chat"
   }
   ```
   - Khi đó:
     - Chat / single-turn / history summary vẫn dùng Gemini.
     - Agent dùng `agent_model` (Gemini Pro).
     - Refactor/document code dùng DeepSeek qua `api.generate_text`.

7. Kiểm thử
   - Chạy `py -m pytest` để đảm bảo toàn bộ test pass.
   - Tạo một file demo và chạy:
     - `termi --refactor demo.py -m deepseek-chat` (hoặc để CLI tự lấy từ `code_model`).
   - Đảm bảo:
     - Code refactor/document chạy được.
     - Chat/agent vẫn hoạt động với Gemini.
