import json
from pathlib import Path
from src import config

def test_load_and_save_config(tmp_path):
    """
    Kiểm tra việc lưu và tải cấu hình.
    """
    # 1. Trỏ đường dẫn config tới một file trong thư mục tạm
    config.CONFIG_PATH = tmp_path / "test_config.json"
    
    # 2. Tạo một dictionary config mẫu
    sample_config = {
        "default_model": "gemini-test",
        "personas": {
            "tester": "You are a testing assistant."
        }
    }
    
    # 3. Lưu config
    config.save_config(sample_config)
    
    # 4. Kiểm tra xem file đã được tạo và có nội dung đúng chưa
    assert config.CONFIG_PATH.exists()
    with open(config.CONFIG_PATH, 'r') as f:
        data_on_disk = json.load(f)
    assert data_on_disk["default_model"] == "gemini-test"
    
    # 5. Tải lại config và so sánh
    loaded_config = config.load_config()
    assert loaded_config == sample_config

def test_load_default_config_if_not_exists(tmp_path):
    """
    Kiểm tra việc tải config mặc định nếu file không tồn tại.
    """
    config.CONFIG_PATH = tmp_path / "non_existent_config.json"
    
    loaded_config = config.load_config()
    
    # Kiểm tra một vài giá trị mặc định quan trọng
    assert "default_model" in loaded_config
    assert loaded_config["personas"] == {}