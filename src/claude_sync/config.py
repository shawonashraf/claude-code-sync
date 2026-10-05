import dataclasses
import json
from dataclasses import dataclass

from claude_sync.paths import Paths


@dataclass
class SyncConfig:
    destination: str
    git_mode: bool = False
    auto_push: bool = False
    conflict_pending: bool = False
    last_backup: str | None = None


def load_config(paths: Paths) -> SyncConfig | None:
    if not paths.config_file.exists():
        return None
    data = json.loads(paths.config_file.read_text())
    known = {f.name for f in dataclasses.fields(SyncConfig)}
    return SyncConfig(**{k: v for k, v in data.items() if k in known})


def save_config(paths: Paths, config: SyncConfig) -> None:
    paths.config_file.write_text(
        json.dumps(dataclasses.asdict(config), indent=2) + "\n"
    )
