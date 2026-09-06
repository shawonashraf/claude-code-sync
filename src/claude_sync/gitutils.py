import subprocess
from pathlib import Path


def _git(dest: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(dest), *args], capture_output=True, text=True
    )


def is_git_repo(dest: Path) -> bool:
    p = _git(dest, "rev-parse", "--is-inside-work-tree")
    return p.returncode == 0 and p.stdout.strip() == "true"


def init_repo(dest: Path) -> None:
    _git(dest, "init", "-b", "main")


def has_conflict(dest: Path) -> bool:
    if (dest / ".git" / "MERGE_HEAD").exists():
        return True
    p = _git(dest, "ls-files", "-u")
    return bool(p.stdout.strip())


def _upstream(dest: Path) -> str | None:
    p = _git(dest, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    return p.stdout.strip() if p.returncode == 0 else None


def is_diverged(dest: Path) -> bool:
    upstream = _upstream(dest)
    if not upstream:
        return False
    p = _git(dest, "rev-list", "--left-right", "--count", f"{upstream}...HEAD")
    if p.returncode != 0:
        return False
    behind, ahead = (int(n) for n in p.stdout.split())
    return behind > 0 and ahead > 0


def _identity_args(dest: Path) -> list[str]:
    """Fallback identity so commits work on machines with no git config."""
    if _git(dest, "config", "user.email").stdout.strip():
        return []
    return ["-c", "user.name=claude-sync", "-c", "user.email=claude-sync@localhost"]


def commit_all(dest: Path, message: str) -> bool:
    _git(dest, "add", "-A")
    p = _git(dest, *_identity_args(dest), "commit", "-m", message)
    return p.returncode == 0


def has_remote(dest: Path) -> bool:
    return bool(_git(dest, "remote").stdout.strip())


def push(dest: Path) -> bool:
    return _git(dest, "push").returncode == 0


def abort_merge(dest: Path) -> None:
    if (dest / ".git" / "MERGE_HEAD").exists():
        _git(dest, "merge", "--abort")


def merge_keep_local(dest: Path) -> None:
    upstream = _upstream(dest)
    if upstream:
        _git(dest, *_identity_args(dest), "merge", "-s", "ours", "--no-edit", upstream)


def merge_keep_repo(dest: Path) -> None:
    upstream = _upstream(dest)
    if not upstream:
        return
    _git(dest, "merge", "-s", "ours", "--no-commit", "--no-ff", upstream)
    _git(dest, "read-tree", "-m", "-u", upstream)
    _git(dest, *_identity_args(dest), "commit", "-m", "claude-sync: adopt repo version")


def clone(url: str, dest: Path) -> None:
    subprocess.run(
        ["git", "clone", "--depth", "1", url, str(dest)],
        capture_output=True, text=True, check=True,
    )
