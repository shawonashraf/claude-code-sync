import contextlib
import os
import sys
import time
from pathlib import Path


STALE_GRACE_SECONDS = 60

class AlreadyRunning(Exception):
    """Another claude-sync run holds the lock."""


def _pid_alive_windows(pid: int) -> bool:
    # os.kill(pid, 0) would TERMINATE the process on Windows, so ask the OS instead
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    handle = kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
    if not handle:
        return ctypes.get_last_error() == 5  # access denied: exists, not ours
    try:
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return True
        return code.value == 259  # STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        return _pid_alive_windows(pid)
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, ValueError):
        return False
    except PermissionError:
        return True
    return True


@contextlib.contextmanager
def sync_lock(lock_file: Path):
    # Try to create the lock exclusively
    try:
        fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        # Lock exists, check if stale or held by live process
        try:
            content = lock_file.read_text(encoding="utf-8").strip()
            holder = int(content) if content else None
        except (ValueError, OSError):
            holder = None

        # Decide staleness
        if holder is not None and _pid_alive(holder):
            # Lock held by live process
            raise AlreadyRunning(f"lock {lock_file} held by pid {holder}")

        # Lock is stale or unparseable; check mtime for unparseable locks
        if holder is None:
            try:
                mtime = lock_file.stat().st_mtime
                age = time.time() - mtime
                if age < STALE_GRACE_SECONDS:
                    # Recent unparseable lock; probably mid-creation
                    raise AlreadyRunning(f"lock {lock_file} is recent and unparseable")
            except OSError:
                pass

        # Lock is stale; steal it atomically via rename
        claimed = lock_file.with_name(lock_file.name + f".stale-{os.getpid()}")
        try:
            os.rename(lock_file, claimed)
        except FileNotFoundError:
            # Another process won the race to steal; we lost
            raise AlreadyRunning(f"lock {lock_file} stolen by another process")

        # Winner: unlink the claimed lock and try to create fresh
        claimed.unlink(missing_ok=True)
        try:
            fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            # Another process created a new lock while we were stealing
            raise AlreadyRunning(f"lock {lock_file} created by another process during steal")

    # Write PID and close fd (always close)
    try:
        os.write(fd, str(os.getpid()).encode())
    finally:
        os.close(fd)

    # Hold lock during yield
    try:
        yield
    finally:
        lock_file.unlink(missing_ok=True)
