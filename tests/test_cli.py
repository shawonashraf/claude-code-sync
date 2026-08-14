import json

from claude_sync.cli import main
from claude_sync.config import load_config


def _env_home(monkeypatch, home):
    monkeypatch.setenv("CLAUDE_SYNC_HOME", str(home))


def test_backup_not_configured_exits_nonzero(fake_claude, monkeypatch, capsys):
    _env_home(monkeypatch, fake_claude.home)
    assert main(["backup"]) == 1
    assert "init" in capsys.readouterr().err


def test_init_yes_then_backup_then_status(fake_claude, tmp_path, monkeypatch, capsys):
    _env_home(monkeypatch, fake_claude.home)
    dest = tmp_path / "dest"
    assert main(["init", str(dest), "--yes"]) == 0
    assert load_config(fake_claude) is not None
    assert main(["backup"]) == 0  # unchanged → still exit 0
    assert main(["status"]) == 0
    out = capsys.readouterr().out
    assert "Destination" in out


def test_backup_quiet_prints_nothing_when_unchanged(fake_claude, tmp_path, monkeypatch, capsys):
    _env_home(monkeypatch, fake_claude.home)
    main(["init", str(tmp_path / "dest"), "--yes"])
    capsys.readouterr()
    assert main(["backup", "--quiet"]) == 0
    out = capsys.readouterr()
    assert out.out == ""


def test_backup_show_redactions(fake_claude, tmp_path, monkeypatch, capsys):
    _env_home(monkeypatch, fake_claude.home)
    main(["init", str(tmp_path / "dest"), "--yes"])
    (fake_claude.claude_dir / "CLAUDE.md").write_text("changed\n")
    capsys.readouterr()
    assert main(["backup", "--show-redactions"]) == 0
    assert "MY_API_KEY" in capsys.readouterr().out


def test_hook_install_uninstall(fake_claude, tmp_path, monkeypatch):
    _env_home(monkeypatch, fake_claude.home)
    main(["init", str(tmp_path / "dest"), "--yes"])
    assert main(["hook", "uninstall"]) == 0
    settings = json.loads(fake_claude.settings_file.read_text())
    assert settings["hooks"]["SessionEnd"] == []
    assert main(["hook", "install"]) == 0


def test_restore_via_cli(fake_claude, tmp_path, monkeypatch, capsys):
    _env_home(monkeypatch, fake_claude.home)
    dest = tmp_path / "dest"
    main(["init", str(dest), "--yes"])
    home2 = tmp_path / "home2"
    _env_home(monkeypatch, home2)
    monkeypatch.setattr("shutil.which", lambda name: None)  # no claude CLI
    assert main(["restore", str(dest)]) == 0
    out = capsys.readouterr().out
    assert "MY_API_KEY" in out  # redaction checklist printed
    assert (home2 / ".claude" / "CLAUDE.md").exists()


def test_malformed_settings_json_yields_actionable_error(fake_claude, tmp_path, monkeypatch, capsys):
    _env_home(monkeypatch, fake_claude.home)
    dest = tmp_path / "dest"
    main(["init", str(dest), "--yes"])
    fake_claude.settings_file.write_text("{not json")
    assert main(["backup"]) == 1
    err = capsys.readouterr().err
    assert "invalid JSON" in err
