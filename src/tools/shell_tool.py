import subprocess
import shlex

# DANH SÁCH TRẮNG: Chỉ những lệnh này mới được phép thực thi
SAFE_COMMANDS = {
    'git': ['status', 'diff', 'log', 'branch', 'commit', 'add'],
    'ls': None,  # Cho phép 'ls' với mọi tham số
    'dir': None, # Lệnh tương đương 'ls' trên Windows
    'pip': ['list', 'freeze'],
    'python': ['--version'],
    'node': ['--version'],
    'npm': ['--version'],
}

def execute_command(command: str) -> str:
    """
    Thực thi một lệnh shell an toàn từ danh sách trắng và trả về kết quả.
    Args:
        command (str): Lệnh cần thực thi (ví dụ: 'git status', 'ls -l').
    """
    print(f"--- TOOL: Yêu cầu thực thi lệnh: '{command}' ---")
    try:
        # Phân tách lệnh thành các phần để kiểm tra an toàn
        parts = shlex.split(command)
        if not parts:
            return "Lỗi: Lệnh rỗng."

        main_command = parts[0]
        
        # Kiểm tra xem lệnh chính có trong danh sách trắng không
        if main_command not in SAFE_COMMANDS:
            return f"Lỗi: Lệnh '{main_command}' không được phép thực thi vì lý do an toàn."

        # Nếu lệnh có các lệnh con bị giới hạn, hãy kiểm tra chúng
        allowed_subcommands = SAFE_COMMANDS[main_command]
        if allowed_subcommands is not None:
            if len(parts) < 2 or parts[1] not in allowed_subcommands:
                return f"Lỗi: Lệnh con của '{main_command}' không được phép. Chỉ cho phép: {', '.join(allowed_subcommands)}."

        # Thực thi lệnh
        result = subprocess.run(
            command, 
            shell=True, 
            capture_output=True, 
            text=True, 
            encoding='utf-8',
            timeout=30 # Đặt timeout để tránh lệnh bị treo
        )

        output = ""
        if result.stdout:
            output += f"--- STDOUT ---\n{result.stdout}\n"
        if result.stderr:
            output += f"--- STDERR ---\n{result.stderr}\n"
        
        return output if output else "Lệnh đã được thực thi mà không có output."

    except subprocess.TimeoutExpired:
        return "Lỗi: Lệnh thực thi quá lâu và đã bị ngắt."
    except Exception as e:
        return f"Lỗi khi thực thi lệnh: {e}"