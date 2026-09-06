from pathlib import Path
from typing import Protocol

from claude_sync import gitutils
from claude_sync.backup import Resolver, _bad_destination, run_backup
from claude_sync.config import SyncConfig, save_config
from claude_sync.hook import install_hook
from claude_sync.paths import Paths

DIVERGENCE_NOTE = (
    "Note: if you back up from multiple machines to the same repo, their "
    "histories can diverge. claude-sync never merges automatically — it "
    "detects divergence and walks you through choosing which version to keep."
)


class Prompts(Protocol):
    def ask_destination(self, default: str) -> str: ...
    def confirm(self, message: str, default: bool = True) -> bool: ...
    def info(self, message: str) -> None: ...


def _choose_auto_push(
    dest: Path, git_mode: bool, yes: bool, prompts: Prompts,
    explicit: bool | None,
) -> bool:
    """Explicit flag wins; otherwise push only when a remote exists."""
    if not git_mode:
        return False
    if explicit is not None:
        return explicit
    if not gitutils.has_remote(dest):
        return False
    return yes or prompts.confirm(
        "Push every backup commit to the remote automatically?", default=True
    )


def run_init(
    paths: Paths,
    destination: str | None,
    yes: bool,
    prompts: Prompts,
    resolver: Resolver | None = None,
    auto_push: bool | None = None,
) -> int:
    default_dest = str(paths.home / "claude-backup")
    dest_input = destination or (
        default_dest if yes else prompts.ask_destination(default_dest)
    )
    dest = Path(dest_input).expanduser()
    if _bad_destination(dest, paths.claude_dir):
        prompts.info(
            "Error: the backup destination cannot be inside ~/.claude "
            "(or contain it). Choose a different directory."
        )
        return 1
    dest.mkdir(parents=True, exist_ok=True)

    if gitutils.is_git_repo(dest):
        git_mode = yes or prompts.confirm(
            "Treat this as a git-backed destination? "
            "Commits will be made automatically.", default=True,
        )
    else:
        git_mode = yes or prompts.confirm(
            "Initialize a git repository here so backups get history?",
            default=True,
        )
        if git_mode:
            gitutils.init_repo(dest)
    if git_mode:
        prompts.info(DIVERGENCE_NOTE)

    save_config(paths, SyncConfig(
        destination=str(dest), git_mode=git_mode,
        auto_push=_choose_auto_push(dest, git_mode, yes, prompts, auto_push),
    ))

    if yes or prompts.confirm(
        "Install the Claude Code session-end hook so backups run automatically?",
        default=True,
    ):
        install_hook(paths.settings_file)

    result = run_backup(paths, resolver=resolver)
    prompts.info(f"First backup: {result.status} → {dest}")
    if result.redacted:
        prompts.info(
            "Redacted from settings.json (never leaves this machine): "
            + ", ".join(result.redacted)
        )
    return 0 if result.status in ("ok", "unchanged") else 1
