"""Per-OS layout of the backup repo.

settings.json and hooks/ hold absolute paths and shell scripts that only make
sense on the OS that wrote them. Linux keeps the original layout at the repo
root (so existing backups keep working); other OSes get their own subtree.
Everything else (skills, agents, CLAUDE.md, keybindings, plugin manifest) is
shared across machines.
"""
import sys

SHARED_DIRS = ("skills", "agents")
SHARED_FILES = ("keybindings.json", "CLAUDE.md", "plugins-manifest.json")
OS_DIRS = ("hooks",)
OS_FILES = ("settings.json",)


def current_variant() -> str | None:
    """Repo subtree for this OS; None means the repo root (Linux, legacy)."""
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return None


def _prefix(variant: str | None) -> str:
    return f"{variant}/" if variant else ""


def is_os_specific(rel: str) -> bool:
    return rel in OS_FILES or rel.split("/", 1)[0] in OS_DIRS


def repo_rel(rel: str, variant: str | None) -> str:
    """Path of a ~/.claude-relative file inside the backup repo."""
    return _prefix(variant) + rel if is_os_specific(rel) else rel


def local_rel(repo_path: str, variant: str | None) -> str:
    """Inverse of repo_rel for paths taken from the managed layout."""
    prefix = _prefix(variant)
    return repo_path[len(prefix):] if prefix and repo_path.startswith(prefix) else repo_path


def managed_dirs(variant: str | None) -> tuple[str, ...]:
    return SHARED_DIRS + tuple(_prefix(variant) + d for d in OS_DIRS)


def managed_files(variant: str | None) -> tuple[str, ...]:
    return SHARED_FILES + tuple(_prefix(variant) + f for f in OS_FILES)
