from src import handlers

def test_add_instruction(mocker):
    """Kiểm tra việc thêm một chỉ dẫn mới."""
    # 1. Giả lập hàm save_config để nó không ghi file thật
    mock_save = mocker.patch('src.handlers.save_config')
    
    # 2. Tạo config ban đầu
    config = {"saved_instructions": ["rule1"]}
    
    # 3. Gọi hàm cần test
    handlers.add_instruction(console=mocker.MagicMock(), config=config, instruction="rule2")
    
    # 4. Kiểm tra
    assert "rule2" in config["saved_instructions"]
    assert len(config["saved_instructions"]) == 2
    mock_save.assert_called_once_with(config)

def test_remove_instruction(mocker):
    """Kiểm tra việc xóa một chỉ dẫn."""
    mock_save = mocker.patch('src.handlers.save_config')
    config = {"saved_instructions": ["rule1", "rule2", "rule3"]}
    
    # Xóa item ở giữa (index=2)
    handlers.remove_instruction(console=mocker.MagicMock(), config=config, index=2)
    
    assert config["saved_instructions"] == ["rule1", "rule3"]
    mock_save.assert_called_once_with(config)

def test_add_persona(mocker):
    """Kiểm tra việc thêm một persona mới."""
    mock_save = mocker.patch('src.handlers.save_config')
    config = {"personas": {"coder": "You are a coder."}}
    
    handlers.add_persona(console=mocker.MagicMock(), config=config, name="tester", instruction="You are a tester.")
    
    assert "tester" in config["personas"]
    assert config["personas"]["tester"] == "You are a tester."
    mock_save.assert_called_once_with(config)

def test_remove_persona(mocker):
    """Kiểm tra việc xóa một persona."""
    mock_save = mocker.patch('src.handlers.save_config')
    config = {"personas": {"coder": "...", "tester": "..."}}
    
    handlers.remove_persona(console=mocker.MagicMock(), config=config, name="coder")
    
    assert "coder" not in config["personas"]
    assert "tester" in config["personas"]
    mock_save.assert_called_once_with(config)