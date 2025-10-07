import pytest
import os
from src import utils

def test_sanitize_filename():
    """
    Kiểm tra hàm sanitize_filename với nhiều trường hợp khác nhau.
    """
    assert utils.sanitize_filename("Hello World") == "hello_world"
    assert utils.sanitize_filename("Chào Đại Ca") == "chao_dai_ca"
    assert utils.sanitize_filename("File*Name?/!@#$%^&.txt") == "filename.txt"
    assert utils.sanitize_filename("  leading -- and -- trailing  ") == "leading_and_trailing"
    assert utils.sanitize_filename("") == ""
    assert utils.sanitize_filename("!@#$%^") == ""

def test_get_directory_context(tmp_path, monkeypatch):
    """
    Kiểm tra hàm get_directory_context.
    """
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    
    (project_dir / "main.py").write_text("print('hello')")
    (project_dir / "README.md").write_text("# My Project")
    (project_dir / "config.ini").write_text("key=value")
    
    sub_dir = project_dir / "subdir"
    sub_dir.mkdir()
    (sub_dir / "logic.js").write_text("console.log('logic');")
    
    monkeypatch.chdir(project_dir)
    
    context = utils.get_directory_context()
    
    # Kiểm tra với các đường dẫn đã được chuẩn hóa, không còn './'
    main_py_path = "main.py"
    readme_path = "README.md"
    logic_js_path = os.path.join('subdir', 'logic.js')

    assert f"--- START OF FILE: {main_py_path} ---" in context
    assert "print('hello')" in context
    
    assert f"--- START OF FILE: {readme_path} ---" in context
    assert "# My Project" in context
    
    assert f"--- START OF FILE: {logic_js_path} ---" in context
    assert "console.log('logic');" in context
    
    assert "config.ini" not in context
    assert "key=value" not in context