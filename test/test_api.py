import os
from unittest.mock import MagicMock
from termi_cli import api

def test_initialize_api_keys(mocker):
    """
    Kiểm tra việc khởi tạo danh sách API keys từ biến môi trường.
    """
    # Dùng mocker để giả lập các biến môi trường
    mocker.patch.dict(os.environ, {
        "GOOGLE_API_KEY": "key1",
        "GOOGLE_API_KEY_2ND": "key2",
        "GOOGLE_API_KEY_3RD": "key3"
    })
    
    keys = api.initialize_api_keys()
    
    assert keys == ["key1", "key2", "key3"]
    assert len(keys) == 3

def test_get_available_models(mocker):
    """
    Kiểm tra hàm lấy model mà không cần gọi API thật.
    """
    # 1. Tạo các đối tượng model giả, có cấu trúc giống hệt model thật
    mock_model_1 = MagicMock()
    mock_model_1.name = "models/gemini-pro"
    mock_model_1.supported_generation_methods = ['generateContent', 'otherMethod']

    mock_model_2 = MagicMock()
    mock_model_2.name = "models/gemini-flash"
    mock_model_2.supported_generation_methods = ['generateContent']

    mock_model_3 = MagicMock()
    mock_model_3.name = "models/embedding-001"
    mock_model_3.supported_generation_methods = ['embedContent'] # Model này sẽ bị loại

    # 2. Dùng mocker để "vá" hàm list_models của thư viện genai
    mock_list_models = mocker.patch('google.generativeai.list_models')
    # 3. Thiết lập giá trị trả về cho hàm giả
    mock_list_models.return_value = [mock_model_1, mock_model_2, mock_model_3]
    
    # 4. Gọi hàm cần test
    available_models = api.get_available_models()
    
    # 5. Kiểm tra kết quả
    assert "models/gemini-pro" in available_models
    assert "models/gemini-flash" in available_models
    assert "models/embedding-001" not in available_models
    assert len(available_models) == 2