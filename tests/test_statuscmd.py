from claude_sync.backup import run_backup
from claude_sync.config import SyncConfig, save_config
from claude_sync.hook import install_hook
from claude_sync.statuscmd import gather_status, render_status


def test_status_unconfigured(fake_claude):
    info = gather_status(fake_claude)
    assert info.configured is False
    assert "not configured" in render_status(info).lower()


def test_status_after_backup_is_clean(fake_claude, tmp_path):
    dest = tmp_path / "dest"
    dest.mkdir()
    save_config(fake_claude, SyncConfig(destination=str(dest)))
    run_backup(fake_claude)
    info = gather_status(fake_claude)
    assert info.configured and not info.dirty
    assert info.last_backup is not None
    assert info.redacted_env == ["MY_API_KEY"]
    assert info.hook_installed is False


def test_status_detects_drift_and_hook(fake_claude, tmp_path):
    dest = tmp_path / "dest"
    dest.mkdir()
    save_config(fake_claude, SyncConfig(destination=str(dest)))
    run_backup(fake_claude)
    (fake_claude.claude_dir / "skills" / "new-skill").mkdir()
    (fake_claude.claude_dir / "skills" / "new-skill" / "SKILL.md").write_text("new")
    install_hook(fake_claude.settings_file)
    info = gather_status(fake_claude)
    assert info.dirty is True
    assert info.hook_installed is True
    text = render_status(info)
    assert "MY_API_KEY" in text
