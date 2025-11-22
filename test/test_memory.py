import os

from termi_cli import memory


def test_reset_memory_db_removes_directory_and_resets_state(tmp_path, monkeypatch):
    """reset_memory_db phải xoá thư mục DB và reset lại state toàn cục."""
    db_dir = tmp_path / "memory_db"
    db_dir.mkdir()
    (db_dir / "dummy.txt").write_text("x", encoding="utf-8")

    # Trỏ DB_PATH sang thư mục tạm để không đụng APP_DIR thật
    monkeypatch.setattr(memory, "DB_PATH", str(db_dir), raising=False)

    # Giả lập state đang giữ client/collection và bị disable
    memory.client = object()
    memory.collection = object()
    memory.MEMORY_DISABLED = True

    ok = memory.reset_memory_db()

    assert ok is True
    assert not db_dir.exists()
    assert memory.client is None
    assert memory.collection is None
    assert memory.MEMORY_DISABLED is False


def test_ensure_collection_early_returns_when_disabled(monkeypatch):
    """Khi MEMORY_DISABLED=True thì _ensure_collection phải trả về None và không đụng file system."""
    memory.MEMORY_DISABLED = True

    called = []

    def fake_makedirs(path, exist_ok=False):  # noqa: ARG001
        called.append(path)
        raise AssertionError("os.makedirs should not be called when MEMORY_DISABLED")

    monkeypatch.setattr(memory.os, "makedirs", fake_makedirs)

    coll = memory._ensure_collection()

    assert coll is None
    assert called == []

    # Reset flag để không ảnh hưởng test khác
    memory.MEMORY_DISABLED = False
