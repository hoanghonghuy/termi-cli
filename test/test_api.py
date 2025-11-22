import os
from unittest.mock import MagicMock
from rich.console import Console
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

def test_load_plugin_tools_returns_empty_when_no_plugins(tmp_path, monkeypatch):
    """_load_plugin_tools trả về dict rỗng khi không có thư mục plugins."""
    # Gán APP_DIR tạm thởi sang một thư mục trống
    monkeypatch.setattr(api, "APP_DIR", tmp_path)
    tools = api._load_plugin_tools()
    assert tools == {}

def test_load_plugin_tools_loads_valid_plugin(tmp_path, monkeypatch):
    """_load_plugin_tools phải load được PLUGIN_TOOLS hợp lệ từ file plugin."""
    plugins_root = tmp_path
    plugins_dir = plugins_root / "plugins"
    plugins_dir.mkdir()

    plugin_file = plugins_dir / "sample_plugin.py"
    plugin_file.write_text(
        "def sample_tool():\n"
        "    return 'OK'\n\n"
        "PLUGIN_TOOLS = {'sample_tool': sample_tool}\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(api, "APP_DIR", plugins_root)
    tools = api._load_plugin_tools()

    assert "sample_tool" in tools
    assert callable(tools["sample_tool"])

def test_load_plugin_tools_ignores_invalid_tools_dict(tmp_path, monkeypatch):
    """Plugin với PLUGIN_TOOLS không phải dict phải bị bỏ qua."""
    plugins_root = tmp_path
    plugins_dir = plugins_root / "plugins"
    plugins_dir.mkdir()

    plugin_file = plugins_dir / "bad_plugin.py"
    plugin_file.write_text("PLUGIN_TOOLS = 'not-a-dict'\n", encoding="utf-8")

    monkeypatch.setattr(api, "APP_DIR", plugins_root)
    tools = api._load_plugin_tools()

    assert tools == {}

def test_list_tools_prints_core_and_plugin_tools(monkeypatch):
    """list_tools phải in được cả core tool và plugin tool mà không crash."""
    def core_tool():
        """Core tool for test."""
        return "core"

    def plugin_tool():
        """Plugin tool for test."""
        return "plugin"

    monkeypatch.setattr(
        api,
        "AVAILABLE_TOOLS",
        {"core_tool": core_tool, "plugin_tool": plugin_tool},
        raising=False,
    )
    monkeypatch.setattr(api, "_PLUGIN_TOOLS", {"plugin_tool": plugin_tool}, raising=False)

    console = Console(record=True)
    api.list_tools(console)

    output = console.export_text()
    assert "core_tool" in output
    assert "plugin_tool" in output

def test_initialize_deepseek_api_keys(mocker):
    """Khởi tạo DeepSeek API keys từ biến môi trường."""
    mocker.patch.dict(
        os.environ,
        {
            "DEEPSEEK_API_KEY": "d1",
            "DEEPSEEK_API_KEY_2ND": "d2",
            "DEEPSEEK_API_KEY_3RD": "d3",
        },
        clear=True,
    )

    keys = api.initialize_deepseek_api_keys()

    assert keys == ["d1", "d2", "d3"]
    assert len(keys) == 3

def test_initialize_groq_api_keys(mocker):
    """Khởi tạo Groq API keys từ biến môi trường."""
    mocker.patch.dict(
        os.environ,
        {
            "GROQ_API_KEY": "g1",
            "GROQ_API_KEY_2ND": "g2",
            "GROQ_API_KEY_3RD": "g3",
        },
        clear=True,
    )

    keys = api.initialize_groq_api_keys()

    assert keys == ["g1", "g2", "g3"]
    assert len(keys) == 3

def test_generate_text_routes_to_groq(monkeypatch):
    """generate_text phải route đúng sang _resilient_groq_api_call khi dùng groq-* model."""

    captured = {}

    def fake_groq_call(model_name, messages):  # type: ignore[override]
        captured["model_name"] = model_name
        captured["messages"] = messages
        return {"choices": [{"message": {"content": "hi from groq"}}]}

    monkeypatch.setattr(api, "_resilient_groq_api_call", fake_groq_call, raising=True)

    text = api.generate_text(
        "groq-llama-3.1-70b", "hello", system_instruction="sys-instr"
    )

    assert text == "hi from groq"
    # Model name phải được normalize sang model Groq thật tương ứng
    assert captured["model_name"] == "llama-3.3-70b-versatile"

    assert captured["messages"][0] == {"role": "system", "content": "sys-instr"}
    assert captured["messages"][1] == {"role": "user", "content": "hello"}