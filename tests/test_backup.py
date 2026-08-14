import json

from claude_sync import gitutils
from claude_sync.backup import run_backup
from claude_sync.config import SyncConfig, load_config, save_config
from tests.conftest import git


def _configure(paths, dest, git_mode=False):
    dest.mkdir(parents=True, exist_ok=True)
    save_config(paths, SyncConfig(destination=str(dest), git_mode=git_mode))


def test_not_configured(fake_claude):
    assert run_backup(fake_claude).status == "not-configured"


def test_plain_backup_mirrors_files(fake_claude, tmp_path):
    dest = tmp_path / "dest"
    _configure(fake_claude, dest)
    result = run_backup(fake_claude)
    assert result.status == "ok"
    assert (dest / "skills" / "my-skill" / "SKILL.md").exists()
    assert (dest / "plugins-manifest.json").exists()
    meta = json.loads((dest / "claude-sync.meta.json").read_text())
    assert meta["schema"] == 1 and "last_sync" in meta and "machine" in meta
    assert result.redacted == ["MY_API_KEY"]
    assert load_config(fake_claude).last_backup is not None


def test_unchanged_backup_is_silent_noop(fake_claude, tmp_path):
    dest = tmp_path / "dest"
    _configure(fake_claude, dest)
    run_backup(fake_claude)
    meta_before = (dest / "claude-sync.meta.json").read_bytes()
    result = run_backup(fake_claude)
    assert result.status == "unchanged"
    assert (dest / "claude-sync.meta.json").read_bytes() == meta_before


def test_git_backup_commits(fake_claude, tmp_path):
    from tests.conftest import make_repo
    dest = make_repo(tmp_path / "dest")
    _configure(fake_claude, dest, git_mode=True)
    result = run_backup(fake_claude, machine="testbox")
    assert result.status == "ok" and result.committed
    log = git(dest, "log", "--oneline").stdout
    assert "claude-sync: testbox" in log
    # second run: no change, no commit
    assert run_backup(fake_claude).status == "unchanged"
    assert git(dest, "log", "--oneline").stdout.count("\n") == 1


def test_conflict_noninteractive_sets_pending(fake_claude, diverged_clones):
    _, clone2 = diverged_clones
    git(clone2, "config", "user.email", "t@t")
    _configure(fake_claude, clone2, git_mode=True)
    result = run_backup(fake_claude, resolver=None)
    assert result.status == "conflict-pending"
    assert load_config(fake_claude).conflict_pending is True


def test_conflict_resolver_keep_local_then_backs_up(fake_claude, diverged_clones):
    _, clone2 = diverged_clones
    _configure(fake_claude, clone2, git_mode=True)
    result = run_backup(fake_claude, resolver=lambda: "local")
    assert result.status == "ok"
    assert load_config(fake_claude).conflict_pending is False
    assert (clone2 / "skills" / "my-skill" / "SKILL.md").exists()


def test_conflict_resolver_keep_repo_skips_backup(fake_claude, diverged_clones):
    _, clone2 = diverged_clones
    _configure(fake_claude, clone2, git_mode=True)
    result = run_backup(fake_claude, resolver=lambda: "repo")
    assert result.status == "kept-repo"
    assert (clone2 / "file.txt").read_text() == "from clone1"
    assert not (clone2 / "skills").exists()


def test_conflict_resolver_cancel_leaves_repo_untouched(fake_claude, diverged_clones):
    _, clone2 = diverged_clones
    _configure(fake_claude, clone2, git_mode=True)
    result = run_backup(fake_claude, resolver=lambda: None)
    assert result.status == "conflict-pending"
    assert load_config(fake_claude).conflict_pending is True
    assert gitutils.is_diverged(clone2) is True
    assert not (clone2 / "skills").exists()


def test_failed_auto_push_does_not_fail_backup(fake_claude, tmp_path):
    from tests.conftest import make_repo
    dest = make_repo(tmp_path / "dest")
    # No remote configured, so push will fail
    _configure(fake_claude, dest, git_mode=True)
    cfg = load_config(fake_claude)
    cfg.auto_push = True
    save_config(fake_claude, cfg)
    result = run_backup(fake_claude)
    assert result.status == "ok" and result.committed
    assert load_config(fake_claude).last_backup is not None
