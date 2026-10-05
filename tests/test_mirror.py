from claude_sync.mirror import Changes, apply_changes, diff_dest

FILES = {
    "skills/a/SKILL.md": b"alpha",
    "settings.json": b"{}",
}


def test_fresh_dest_writes_everything(tmp_path):
    changes = diff_dest(FILES, tmp_path)
    assert sorted(changes.writes) == ["settings.json", "skills/a/SKILL.md"]
    assert changes.deletes == []
    assert not changes.empty


def test_apply_then_rediff_is_empty(tmp_path):
    changes = diff_dest(FILES, tmp_path)
    apply_changes(FILES, tmp_path, changes)
    assert (tmp_path / "skills" / "a" / "SKILL.md").read_bytes() == b"alpha"
    assert diff_dest(FILES, tmp_path).empty


def test_changed_content_rewrites_only_that_file(tmp_path):
    apply_changes(FILES, tmp_path, diff_dest(FILES, tmp_path))
    updated = dict(FILES, **{"skills/a/SKILL.md": b"alpha v2"})
    changes = diff_dest(updated, tmp_path)
    assert changes.writes == ["skills/a/SKILL.md"] and changes.deletes == []


def test_stale_managed_files_are_deleted(tmp_path):
    apply_changes(FILES, tmp_path, diff_dest(FILES, tmp_path))
    shrunk = {"settings.json": b"{}"}
    changes = diff_dest(shrunk, tmp_path)
    assert changes.deletes == ["skills/a/SKILL.md"]
    apply_changes(shrunk, tmp_path, changes)
    assert not (tmp_path / "skills" / "a").exists()  # empty dirs pruned


def test_git_and_meta_never_deleted(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref")
    (tmp_path / "claude-sync.meta.json").write_text("{}")
    (tmp_path / "unmanaged-note.txt").write_text("keep me")
    changes = diff_dest(FILES, tmp_path)
    assert changes.deletes == []


def test_executable_bit_is_mirrored_and_tracked(tmp_path):
    files = {"hooks/h/run.sh": b"#!/bin/sh\n", "hooks/h/notes.md": b"n"}
    execs = frozenset({"hooks/h/run.sh"})
    apply_changes(files, tmp_path, diff_dest(files, tmp_path, execs), execs)
    assert (tmp_path / "hooks" / "h" / "run.sh").stat().st_mode & 0o111
    assert not (tmp_path / "hooks" / "h" / "notes.md").stat().st_mode & 0o111
    assert diff_dest(files, tmp_path, execs).empty

    # losing the exec bit locally is a change even when content is identical
    changes = diff_dest(files, tmp_path, frozenset())
    assert changes.writes == ["hooks/h/run.sh"]
    apply_changes(files, tmp_path, changes, frozenset())
    assert not (tmp_path / "hooks" / "h" / "run.sh").stat().st_mode & 0o111
