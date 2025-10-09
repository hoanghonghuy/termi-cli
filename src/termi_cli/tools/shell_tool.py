import subprocess
import shlex

# DANH SÁCH TRẮNG: Chỉ những lệnh này mới được phép thực thi
SAFE_COMMANDS = {
    'git': ['status', 'diff', 'log', 'branch', 'commit', 'add', 'init'],
    'ls': None,  # Cho phép 'ls' với mọi tham số
    'dir': None, # Lệnh tương đương 'ls' trên Windows
    'pip': ['install', 'list', 'freeze'],
    'python': None, # Cho phép chạy script python
    'python3': None, # Alias cho python
    'node': ['--version'],
    'npm': ['--version', 'install'],
    'pytest': None, # Cho phép chạy test
}

def execute_command(command: str) -> str:
    """
    Thực thi một lệnh shell an toàn từ danh sách trắng và trả về kết quả.
    Args:
        command (str): Lệnh cần thực thi (ví dụ: 'git status', 'pip install -r requirements.txt').
    """
    print(f"--- TOOL: Yêu cầu thực thi lệnh: '{command}' ---")
    try:
        parts = shlex.split(command)
        if not parts:
            return "Lỗi: Lệnh rỗng."

        main_command = parts[0]
        
        if main_command not in SAFE_COMMANDS:
            return f"Lỗi: Lệnh '{main_command}' không được phép thực thi vì lý do an toàn."

        allowed_subcommands = SAFE_COMMANDS[main_command]
        if allowed_subcommands is not None:
            # Kiểm tra subcommand nếu có (ví dụ: git status)
            if len(parts) > 1 and parts[1] not in allowed_subcommands:
                 # Cho phép các flag đi kèm (ví dụ: pip install -r)
                if not parts[1].startswith('-'):
                    return f"Lỗi: Lệnh con của '{main_command}' không được phép. Chỉ cho phép: {', '.join(allowed_subcommands)}."

        result = subprocess.run(
            command, 
            shell=True, 
            capture_output=True, 
            text=True, 
            encoding='utf-8',
            timeout=60
        )

        output = ""
        if result.stdout:
            output += f"--- STDOUT ---\n{result.stdout}\n"
        if result.stderr:
            output += f"--- STDERR ---\n{result.stderr}\n"
        
        return output if output else "Lệnh đã được thực thi thành công mà không có output."

    except subprocess.TimeoutExpired:
        return "Lỗi: Lệnh thực thi quá lâu và đã bị ngắt."
    except Exception as e:
        return f"Lỗi khi thực thi lệnh: {e}"