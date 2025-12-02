from datetime import datetime


def get_current_time() -> str:
    """Trả về thời gian hiện tại của hệ thống ở dạng thân thiện cho người dùng."""
    now = datetime.now()
    # Định dạng: HH:MM:SS, dd/MM/YYYY
    return now.strftime("Bây giờ là %H:%M:%S, ngày %d/%m/%Y (theo giờ hệ thống).")
