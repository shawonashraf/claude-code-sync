import os
import time

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
    assert list(tmp_path.iterdir()) == []  # no leftover stale files


def test_lock_released_on_exception(tmp_path):
    lock = tmp_path / "l.lock"
    with pytest.raises(ValueError):
        with sync_lock(lock):
            raise ValueError("boom")
    assert not lock.exists()


def test_empty_recent_lock_is_respected(tmp_path):
    """Empty lock with recent mtime is treated as mid-creation."""
    lock = tmp_path / "l.lock"
    lock.write_text("")  # Empty with fresh mtime
    with pytest.raises(AlreadyRunning):
        with sync_lock(lock):
            pass


def test_empty_old_lock_is_stolen(tmp_path):
    """Empty lock older than STALE_GRACE_SECONDS is stolen."""
    lock = tmp_path / "l.lock"
    lock.write_text("")
    # Set mtime to 120 seconds ago
    old_time = time.time() - 120
    os.utime(lock, (old_time, old_time))
    with sync_lock(lock):
        assert lock.exists()
    assert not lock.exists()
    assert list(tmp_path.iterdir()) == []  # no leftover stale files


def test_negative_pid_lock_is_stolen(tmp_path):
    """Negative PID in lock file is treated as stale."""
    lock = tmp_path / "l.lock"
    lock.write_text("-1")
    with sync_lock(lock):
        assert lock.exists()
    assert not lock.exists()
    assert list(tmp_path.iterdir()) == []  # no leftover stale files
