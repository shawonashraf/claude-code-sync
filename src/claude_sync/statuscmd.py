from dataclasses import dataclass, field
from pathlib import Path

from claude_sync.config import load_config
from claude_sync.hook import is_hook_installed
from claude_sync.mirror import diff_dest
from claude_sync.paths import Paths
from claude_sync.syncset import build_sync_set


@dataclass
class StatusInfo:
    configured: bool
    destination: str | None = None
    git_mode: bool = False
    last_backup: str | None = None
    conflict_pending: bool = False
    hook_installed: bool = False
    dirty: bool = False
    redacted_env: list[str] = field(default_factory=list)


def gather_status(paths: Paths) -> StatusInfo:
    cfg = load_config(paths)
    if cfg is None:
        return StatusInfo(configured=False)
    sync_set = build_sync_set(paths.claude_dir)
    changes = diff_dest(sync_set.files, Path(cfg.destination))
    return StatusInfo(
        configured=True,
        destination=cfg.destination,
        git_mode=cfg.git_mode,
        last_backup=cfg.last_backup,
        conflict_pending=cfg.conflict_pending,
        hook_installed=is_hook_installed(paths.settings_file),
        dirty=not changes.empty,
        redacted_env=sync_set.redacted_env,
    )


def render_status(info: StatusInfo) -> str:
    if not info.configured:
        return "claude-sync is not configured. Run: claude-sync init"
    lines = [
        f"Destination:      {info.destination} ({'git' if info.git_mode else 'plain folder'})",
        f"Last backup:      {info.last_backup or 'never'}",
        f"Local changes:    {'yes — run claude-sync backup' if info.dirty else 'none (in sync)'}",
        f"Session-end hook: {'installed' if info.hook_installed else 'not installed'}",
    ]
    if info.conflict_pending:
        lines.append("CONFLICT PENDING: run claude-sync resolve to choose a version")
    if info.redacted_env:
        lines.append("Redacted env vars (re-supply after restore): "
                     + ", ".join(info.redacted_env))
    return "\n".join(lines)
