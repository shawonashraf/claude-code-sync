from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Paths:
    home: Path
    # repo subtree for OS-specific files (see variant.py); None = repo root
    variant: str | None = None

    @property
    def claude_dir(self) -> Path:
        return self.home / ".claude"

    @property
    def settings_file(self) -> Path:
        return self.claude_dir / "settings.json"

    @property
    def plugins_dir(self) -> Path:
        return self.claude_dir / "plugins"

    @property
    def config_file(self) -> Path:
        return self.home / ".claude-sync.json"

    @property
    def lock_file(self) -> Path:
        return self.home / ".claude-sync.lock"

    def safety_dir(self, timestamp: str) -> Path:
        return self.home / f".claude-sync-backup-{timestamp}"
