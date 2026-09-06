import json

from claude_sync.redact import REDACTED
from claude_sync.syncset import build_sync_set


def test_sync_set_contains_exactly_the_managed_paths(fake_claude):
    ss = build_sync_set(fake_claude.claude_dir)
    assert set(ss.files) == {
        "skills/my-skill/SKILL.md",
        "hooks/peon/run.sh",
        "agents/helper.md",
        "CLAUDE.md",
        "keybindings.json",
        "settings.json",
        "plugins-manifest.json",
    }


def test_sync_set_never_includes_history_or_projects(fake_claude):
    ss = build_sync_set(fake_claude.claude_dir)
    assert not any("history" in k or "projects" in k for k in ss.files)


def test_settings_are_redacted_in_sync_set(fake_claude):
    ss = build_sync_set(fake_claude.claude_dir)
    settings = json.loads(ss.files["settings.json"])
    assert settings["env"]["MY_API_KEY"] == REDACTED
    assert settings["env"]["EDITOR"] == "vim"
    assert ss.redacted_env == ["MY_API_KEY"]


def test_cache_symlinks_skipped_and_recorded(fake_claude):
    cache_target = fake_claude.plugins_dir / "cache" / "mp" / "plug" / "skill-dir"
    cache_target.mkdir(parents=True)
    link = fake_claude.claude_dir / "skills" / "linked-skill"
    link.symlink_to(cache_target)
    ss = build_sync_set(fake_claude.claude_dir)
    assert not any(k.startswith("skills/linked-skill") for k in ss.files)
    manifest = json.loads(ss.files["plugins-manifest.json"])
    assert manifest["cache_symlinks"] == ["skills/linked-skill"]


def test_missing_optional_pieces_are_fine(tmp_path):
    (tmp_path / "skills").mkdir()
    ss = build_sync_set(tmp_path)
    assert "plugins-manifest.json" in ss.files
    assert "keybindings.json" not in ss.files
    assert "settings.json" not in ss.files


def test_runtime_dotfiles_in_mirror_dirs_are_skipped(fake_claude):
    state = fake_claude.claude_dir / "hooks" / "peon" / ".state.json"
    state.write_text('{"volume": 5}')
    (fake_claude.claude_dir / "hooks" / "peon" / ".sound.pid").write_text("123")
    ss = build_sync_set(fake_claude.claude_dir)
    assert not any(k.endswith(".state.json") or k.endswith(".sound.pid") for k in ss.files)
    assert "hooks/peon/run.sh" in ss.files  # non-dotfiles still mirrored


def test_sync_set_records_executable_hooks(fake_claude):
    hook = fake_claude.claude_dir / "hooks" / "peon" / "run.sh"
    hook.chmod(0o755)
    ss = build_sync_set(fake_claude.claude_dir)
    assert ss.executables == {"hooks/peon/run.sh"}
