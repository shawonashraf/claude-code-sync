import json

from claude_sync.cli import main
from claude_sync.paths import Paths
from claude_sync.redact import REDACTED
from tests.conftest import git


def test_full_lifecycle(fake_claude, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_SYNC_HOME", str(fake_claude.home))
    dest = tmp_path / "backup-repo"

    # Machine 1: init (git mode via --yes defaults), first backup committed
    assert main(["init", str(dest), "--yes"]) == 0
    assert "claude-sync:" in git(dest, "log", "--oneline").stdout

    # settings change → quiet (hook-style) backup makes a second commit
    settings = json.loads(fake_claude.settings_file.read_text())
    settings["model"] = "sonnet"
    fake_claude.settings_file.write_text(json.dumps(settings))
    assert main(["backup", "--quiet"]) == 0
    assert git(dest, "log", "--oneline").stdout.count("\n") >= 2

    # no history ever leaked into the backup
    backed_up = {p.name for p in dest.rglob("*") if p.is_file()}
    assert "history.jsonl" not in backed_up
    raw = b"".join(p.read_bytes() for p in dest.rglob("*.json") if p.is_file())
    assert b"supersecret" not in raw

    # Machine 2: one-command restore
    home2 = tmp_path / "home2"
    monkeypatch.setenv("CLAUDE_SYNC_HOME", str(home2))
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert main(["restore", str(dest)]) == 0
    paths2 = Paths(home=home2)
    restored = json.loads(paths2.settings_file.read_text())
    assert restored["model"] == "sonnet"
    assert restored["env"]["MY_API_KEY"] == REDACTED
    assert (paths2.claude_dir / "skills" / "my-skill" / "SKILL.md").exists()

    # Machine 2 is configured; unchanged backup is a no-op
    assert main(["backup"]) == 0
