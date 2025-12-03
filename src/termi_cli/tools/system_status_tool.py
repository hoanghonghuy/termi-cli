import time

_APP_START_TS = time.time()


def get_cli_uptime() -> str:
    """Trả về thời gian Termi CLI hiện tại đã chạy (tính từ lúc tiến trình được khởi động)."""
    elapsed = int(time.time() - _APP_START_TS)
    days, rem = divmod(elapsed, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)

    parts = []
    if days:
        parts.append(f"{days} ngày")
    if hours:
        parts.append(f"{hours} giờ")
    if minutes:
        parts.append(f"{minutes} phút")
    parts.append(f"{seconds} giây")

    human = ", ".join(parts)
    return f"Termi CLI đã chạy được khoảng {human} (tính từ khi tiến trình hiện tại được khởi động)."
