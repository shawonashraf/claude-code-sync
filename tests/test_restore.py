import json
from types import SimpleNamespace

import pytest

from claude_sync.backup import run_backup
from claude_sync.config import SyncConfig, load_config, save_config
from claude_sync.paths import Paths
from claude_sync.redact import REDACTED
from claude_sync.restore import RestoreError, run_restore


@pytest.fixture
def backup_dir(fake_claude, tmp_path):
    dest = tmp_path / "dest"
    dest.mkdir()
    save_config(fake_claude, SyncConfig(destination=str(dest)))
    run_backup(fake_claude)
    return dest


def _fake_run_factory(calls, fail_for=()):
    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        name = cmd[-1]
        if name in fail_for:
            return SimpleNamespace(returncode=1, stdout="", stderr=f"no such plugin {name}")
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    return fake_run


def test_restore_onto_fresh_machine(backup_dir, tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/claude")
    new_home = tmp_path / "home2"
    paths = Paths(home=new_home)
    calls = []
    result = run_restore(paths, str(backup_dir), run=_fake_run_factory(calls))
    assert (paths.claude_dir / "skills" / "my-skill" / "SKILL.md").exists()
    assert (paths.claude_dir / "CLAUDE.md").exists()
    settings = json.loads(paths.settings_file.read_text())
    assert settings["env"]["MY_API_KEY"] == REDACTED
    assert result.redacted_env == ["MY_API_KEY"]
    assert result.failed_plugins == []
    # marketplace added, both plugins installed
    assert ["/usr/bin/claude", "plugin", "marketplace", "add",
            "anthropics/claude-plugins-official"] in calls
    installs = [c for c in calls if c[1:3] == ["plugin", "install"]]
    assert len(installs) == 2
    # machine is configured for future backups
    cfg = load_config(paths)
    assert cfg.destination == str(backup_dir)
    assert result.safety_dir is None  # nothing pre-existing


def test_restore_saves_safety_copy_of_overwritten_files(backup_dir, tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    new_home = tmp_path / "home2"
    paths = Paths(home=new_home)
    paths.claude_dir.mkdir(parents=True)
    (paths.claude_dir / "CLAUDE.md").write_text("old local content")
    result = run_restore(paths, str(backup_dir), run=_fake_run_factory([]))
    assert result.safety_dir is not None
    assert (result.safety_dir / "CLAUDE.md").read_text() == "old local content"
    assert (paths.claude_dir / "CLAUDE.md").read_text() == "global instructions\n"


def test_restore_plugin_failure_is_fail_soft(backup_dir, tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/claude")
    paths = Paths(home=tmp_path / "home2")
    calls = []
    result = run_restore(
        paths, str(backup_dir),
        run=_fake_run_factory(calls, fail_for={"swift-lsp@claude-plugins-official"}),
    )
    assert len(result.failed_plugins) == 1
    assert result.failed_plugins[0][0] == "swift-lsp@claude-plugins-official"
    assert len([c for c in calls if c[1:3] == ["plugin", "install"]]) == 2


def test_restore_without_claude_cli_reports_all_plugins_failed(backup_dir, tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    paths = Paths(home=tmp_path / "home2")
    result = run_restore(paths, str(backup_dir), run=_fake_run_factory([]))
    assert len(result.failed_plugins) == 2
    assert all("claude CLI not found" in err for _, err in result.failed_plugins)


def test_restore_missing_source_raises(tmp_path):
    paths = Paths(home=tmp_path / "home2")
    with pytest.raises(RestoreError):
        run_restore(paths, str(tmp_path / "nope"))
    with pytest.raises(RestoreError):
        run_restore(paths, None)  # no source and not configured
