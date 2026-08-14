from pathlib import Path

from claude_sync.config import SyncConfig, load_config, save_config
from claude_sync.paths import Paths


def test_paths_layout(tmp_path):
    p = Paths(home=tmp_path)
    assert p.claude_dir == tmp_path / ".claude"
    assert p.settings_file == tmp_path / ".claude" / "settings.json"
    assert p.plugins_dir == tmp_path / ".claude" / "plugins"
    assert p.config_file == tmp_path / ".claude-sync.json"
    assert p.lock_file == tmp_path / ".claude-sync.lock"
    assert p.safety_dir("20260814-051500") == tmp_path / ".claude-sync-backup-20260814-051500"


def test_load_config_missing_returns_none(tmp_path):
    assert load_config(Paths(home=tmp_path)) is None


def test_config_roundtrip(tmp_path):
    p = Paths(home=tmp_path)
    cfg = SyncConfig(destination="/backups/claude", git_mode=True, auto_push=True)
    save_config(p, cfg)
    loaded = load_config(p)
    assert loaded == cfg
    assert loaded.conflict_pending is False
    assert loaded.last_backup is None


def test_load_config_ignores_unknown_keys(tmp_path):
    p = Paths(home=tmp_path)
    p.config_file.write_text('{"destination": "/d", "future_field": 1}')
    assert load_config(p) == SyncConfig(destination="/d")
