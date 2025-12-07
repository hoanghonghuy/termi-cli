from datetime import datetime


def get_current_time() -> str:
    """Return the current system time in a human‑friendly string."""
    now = datetime.now()
    # Định dạng: HH:MM:SS, dd/MM/YYYY
    return now.strftime("Bây giờ là %H:%M:%S, ngày %d/%m/%Y (theo giờ hệ thống).")
