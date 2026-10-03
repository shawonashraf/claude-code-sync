import json
import platform
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from claude_sync import __version__, gitutils
from claude_sync.config import load_config, save_config
from claude_sync.lock import sync_lock
from claude_sync.mirror import apply_changes, diff_dest
from claude_sync.paths import Paths
from claude_sync.syncset import build_sync_set

Resolver = Callable[[], str | None]


@dataclass
class BackupResult:
    status: str
    committed: bool = False
    redacted: list[str] = field(default_factory=list)
    git_mode: bool = False
    push_failed: bool = False


def _bad_destination(dest: Path, claude_dir: Path) -> bool:
    """True when dest is inside claude_dir, equal to it, or contains it."""
    dest_r = dest.resolve()
    claude_r = claude_dir.resolve()
    return (
        dest_r == claude_r
        or dest_r.is_relative_to(claude_r)
        or claude_r.is_relative_to(dest_r)
    )


def run_backup(
    paths: Paths,
    resolver: Resolver | None = None,
    machine: str | None = None,
) -> BackupResult:
    cfg = load_config(paths)
    if cfg is None:
        return BackupResult(status="not-configured")
    dest = Path(cfg.destination)
    if _bad_destination(dest, paths.claude_dir):
        return BackupResult(status="bad-destination")
    machine = machine or platform.node()

    with sync_lock(paths.lock_file):
        if cfg.git_mode and (gitutils.has_conflict(dest) or gitutils.is_diverged(dest)):
            if resolver is None:
                cfg.conflict_pending = True
                save_config(paths, cfg)
                return BackupResult(status="conflict-pending")
            choice = resolver()
            if choice is None:
                cfg.conflict_pending = True
                save_config(paths, cfg)
                return BackupResult(status="conflict-pending")
            gitutils.abort_merge(dest)
            if choice == "repo":
                gitutils.merge_keep_repo(dest)
                cfg.conflict_pending = False
                save_config(paths, cfg)
                return BackupResult(status="kept-repo")
            if choice == "local":
                gitutils.merge_keep_local(dest)
            else:
                return BackupResult(status="conflict-pending")

        sync_set = build_sync_set(paths.claude_dir, paths.variant)
        executables = frozenset(sync_set.executables)
        changes = diff_dest(sync_set.files, dest, executables, paths.variant)
        if changes.empty:
            cfg.conflict_pending = False
            save_config(paths, cfg)
            return BackupResult(status="unchanged", redacted=sync_set.redacted_env)

        timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        apply_changes(sync_set.files, dest, changes, executables)
        (dest / "claude-sync.meta.json").write_text(json.dumps({
            "schema": 1,
            "tool_version": __version__,
            "last_sync": timestamp,
            "machine": machine,
        }, indent=2) + "\n", encoding="utf-8")

        committed = False
        git_mode = False
        push_failed = False
        if cfg.git_mode:
            git_mode = True
            committed = gitutils.commit_all(
                dest, f"claude-sync: {machine} {timestamp}"
            )
            if cfg.auto_push and not gitutils.push(dest):
                push_failed = True  # commit is safe locally; push will be retried on next backup

        cfg.last_backup = timestamp
        cfg.conflict_pending = False
        save_config(paths, cfg)
        return BackupResult(
            status="ok",
            committed=committed,
            redacted=sync_set.redacted_env,
            git_mode=git_mode,
            push_failed=push_failed,
        )
