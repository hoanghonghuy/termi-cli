# src/tools/instruction_tool.py
"""
Công cụ này cho phép AI tự quản lý danh sách chỉ dẫn tùy chỉnh (custom instructions)
bằng cách thêm các chỉ dẫn mới vào file config.
"""

from ..config import load_config, save_config

def save_instruction(instruction: str) -> str:
    """
    Lưu một chỉ dẫn tùy chỉnh lâu dài vào file config.json.
    AI nên sử dụng công cụ này khi người dùng yêu cầu ghi nhớ một quy tắc
    hoặc sở thích nào đó cho các cuộc trò chuyện trong tương lai.

    Args:
        instruction (str): Nội dung chỉ dẫn cần lưu.

    Returns:
        str: Một thông báo xác nhận rằng chỉ dẫn đã được lưu thành công.
    """
    print(f"--- TOOL: Đang lưu chỉ dẫn tùy chỉnh: '{instruction}' ---")
    try:
        config = load_config()
        if "saved_instructions" not in config:
            config["saved_instructions"] = []
        
        # Tránh lưu trùng lặp
        if instruction not in config["saved_instructions"]:
            config["saved_instructions"].append(instruction)
            save_config(config)
            return f"Đã lưu thành công chỉ dẫn mới: '{instruction}'"
        else:
            return f"Chỉ dẫn '{instruction}' đã tồn tại."
            
    except Exception as e:
        return f"Lỗi khi đang lưu chỉ dẫn: {str(e)}"