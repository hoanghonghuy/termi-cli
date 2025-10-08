from termi_cli.config import load_config, save_config

def save_instruction(instruction: str) -> str:
    """
    Lưu một chỉ dẫn tùy chỉnh lâu dài vào file config.json.
    AI nên sử dụng công cụ này khi người dùng yêu cầu ghi nhớ một quy tắc.
    """
    print(f"--- TOOL: Đang lưu chỉ dẫn tùy chỉnh: '{instruction}' ---")
    try:
        config = load_config()
        if "saved_instructions" not in config:
            config["saved_instructions"] = []
        
        if instruction not in config["saved_instructions"]:
            config["saved_instructions"].append(instruction)
            save_config(config)
            # Trả về một thông báo rõ ràng để AI biết và đưa vào context
            # nhắc nhở AI về chỉ dẫn mới ngay trong phiên hiện tại
            return f"Instruction '{instruction}' has been successfully saved for future sessions. I will also adhere to it for the rest of this current session."
        else:
            return f"Instruction '{instruction}' was already saved."
            
    except Exception as e:
        return f"Error while saving instruction: {str(e)}"