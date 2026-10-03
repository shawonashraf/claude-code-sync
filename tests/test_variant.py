import json
from dataclasses import replace

from claude_sync.backup import run_backup
from claude_sync.config import SyncConfig, save_config
from claude_sync.mirror import apply_changes, diff_dest
from claude_sync.paths import Paths
from claude_sync.restore import run_restore
from claude_sync.syncset import build_sync_set
from claude_sync.variant import current_variant, local_rel, repo_rel


def test_current_variant_per_platform(monkeypatch):
    for plat, expected in (("win32", "windows"), ("darwin", "macos"), ("linux", None)):
        monkeypatch.setattr("sys.platform", plat)
        assert current_variant() == expected


def test_repo_rel_prefixes_only_os_specific_files():
    assert repo_rel("settings.json", "windows") == "windows/settings.json"
    assert repo_rel("hooks/a/b.sh", "windows") == "windows/hooks/a/b.sh"
    assert repo_rel("skills/x/SKILL.md", "windows") == "skills/x/SKILL.md"
    assert repo_rel("settings.json", None) == "settings.json"
    assert local_rel("windows/hooks/a.ps1", "windows") == "hooks/a.ps1"
    assert local_rel("skills/x/SKILL.md", "windows") == "skills/x/SKILL.md"


def test_sync_set_puts_os_files_under_variant(fake_claude):
    ss = build_sync_set(fake_claude.claude_dir, "windows")
    assert "windows/settings.json" in ss.files
    assert "windows/hooks/peon/run.sh" in ss.files
    assert "settings.json" not in ss.files and "hooks/peon/run.sh" not in ss.files
    assert "skills/my-skill/SKILL.md" in ss.files  # shared stays shared


def test_variant_backup_never_deletes_other_os_files(tmp_path):
    dest = tmp_path / "dest"
    (dest / "hooks").mkdir(parents=True)
    (dest / "hooks" / "linux.sh").write_text("x")
    (dest / "settings.json").write_text("{}")
    files = {"windows/settings.json": b"{}"}
    changes = diff_dest(files, dest, variant="windows")
    assert changes.deletes == []
    apply_changes(files, dest, changes)
    assert (dest / "hooks" / "linux.sh").exists()
    assert (dest / "settings.json").read_text() == "{}"


def test_linux_backup_never_deletes_windows_subtree(tmp_path):
    dest = tmp_path / "dest"
    (dest / "windows" / "hooks").mkdir(parents=True)
    (dest / "windows" / "hooks" / "a.ps1").write_text("x")
    changes = diff_dest({"settings.json": b"{}"}, dest, variant=None)
    assert changes.deletes == []


def _machine(tmp_path, name, variant):
    return Paths(home=tmp_path / name, variant=variant)


def test_two_oses_share_one_repo_without_touching_each_other(fake_claude, tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    dest = tmp_path / "dest"
    dest.mkdir()

    linux = replace(fake_claude, variant=None)
    save_config(linux, SyncConfig(destination=str(dest)))
    run_backup(linux)
    linux_settings = (dest / "settings.json").read_bytes()
    linux_hook = (dest / "hooks" / "peon" / "run.sh").read_bytes()

    # a fresh Windows machine restores: no windows variant yet, local files kept
    win = _machine(tmp_path, "win", "windows")
    win.settings_file.parent.mkdir(parents=True)
    win.settings_file.write_text(json.dumps({"model": "win-model"}))
    result = run_restore(win, str(dest))
    assert result.missing_variant == "windows"
    assert json.loads(win.settings_file.read_text()) == {"model": "win-model"}
    assert not (win.claude_dir / "hooks").exists()
    assert (win.claude_dir / "skills" / "my-skill" / "SKILL.md").exists()  # shared

    # its first backup creates the windows subtree and leaves Linux's alone
    (win.claude_dir / "hooks" / "peon").mkdir(parents=True)
    (win.claude_dir / "hooks" / "peon" / "run.ps1").write_text("win")
    assert run_backup(win).status == "ok"
    assert json.loads((dest / "windows" / "settings.json").read_text()) == {"model": "win-model"}
    assert (dest / "windows" / "hooks" / "peon" / "run.ps1").exists()
    assert (dest / "settings.json").read_bytes() == linux_settings
    assert (dest / "hooks" / "peon" / "run.sh").read_bytes() == linux_hook

    # Linux backs up again: windows subtree survives
    (linux.claude_dir / "CLAUDE.md").write_text("changed\n")
    run_backup(linux)
    assert (dest / "windows" / "settings.json").exists()

    # a second Windows machine restores its own variant, not Linux's
    win2 = _machine(tmp_path, "win2", "windows")
    result = run_restore(win2, str(dest))
    assert result.missing_variant is None
    assert json.loads(win2.settings_file.read_text()) == {"model": "win-model"}
    assert (win2.claude_dir / "hooks" / "peon" / "run.ps1").exists()
    assert not (win2.claude_dir / "hooks" / "peon" / "run.sh").exists()


def test_skills_are_shared_across_oses(fake_claude, tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    dest = tmp_path / "dest"
    dest.mkdir()
    synced = ("skills", "synced", "acct", "pptx", "SKILL.md")

    linux = replace(fake_claude, variant=None)
    linux.claude_dir.joinpath(*synced).parent.mkdir(parents=True)
    linux.claude_dir.joinpath(*synced).write_text("linux copy")
    save_config(linux, SyncConfig(destination=str(dest)))
    run_backup(linux)

    win = _machine(tmp_path, "win", "windows")
    run_restore(win, str(dest))
    assert win.claude_dir.joinpath(*synced).read_text() == "linux copy"

    win.claude_dir.joinpath(*synced).write_text("windows copy")
    run_backup(win)
    assert dest.joinpath(*synced).read_text() == "windows copy"
    assert not (dest / "windows" / "skills").exists()
