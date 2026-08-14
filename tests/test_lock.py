import pytest

from claude_sync.lock import AlreadyRunning, sync_lock


def test_lock_acquire_release(tmp_path):
    lock = tmp_path / "l.lock"
    with sync_lock(lock):
        assert lock.exists()
    assert not lock.exists()


def test_second_acquire_raises(tmp_path):
    lock = tmp_path / "l.lock"
    with sync_lock(lock):
        with pytest.raises(AlreadyRunning):
            with sync_lock(lock):
                pass


def test_stale_lock_from_dead_pid_is_stolen(tmp_path):
    lock = tmp_path / "l.lock"
    lock.write_text("99999999")  # no such pid
    with sync_lock(lock):
        assert lock.exists()
    assert not lock.exists()


def test_lock_released_on_exception(tmp_path):
    lock = tmp_path / "l.lock"
    with pytest.raises(ValueError):
        with sync_lock(lock):
            raise ValueError("boom")
    assert not lock.exists()
