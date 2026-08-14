import contextlib
import os
from pathlib import Path


class AlreadyRunning(Exception):
    """Another claude-sync run holds the lock."""


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, ValueError):
        return False
    except PermissionError:
        return True
    return True


@contextlib.contextmanager
def sync_lock(lock_file: Path):
    try:
        fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            holder = int(lock_file.read_text().strip() or "0")
        except (ValueError, OSError):
            holder = 0
        if holder and _pid_alive(holder):
            raise AlreadyRunning(f"lock {lock_file} held by pid {holder}")
        lock_file.unlink(missing_ok=True)
        fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        lock_file.unlink(missing_ok=True)
