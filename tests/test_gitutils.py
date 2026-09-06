from claude_sync import gitutils
from tests.conftest import git, make_repo


def test_is_git_repo(tmp_path):
    assert not gitutils.is_git_repo(tmp_path)
    make_repo(tmp_path / "r")
    assert gitutils.is_git_repo(tmp_path / "r")


def test_init_and_commit_all(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    gitutils.init_repo(repo)
    (repo / "f.txt").write_text("hello")
    assert gitutils.commit_all(repo, "first") is True
    assert gitutils.commit_all(repo, "empty") is False
    log = git(repo, "log", "--oneline").stdout
    assert "first" in log


def test_divergence_detection(diverged_clones):
    clone1, clone2 = diverged_clones
    assert gitutils.is_diverged(clone2) is True
    assert gitutils.is_diverged(clone1) is False


def test_no_upstream_means_not_diverged(tmp_path):
    repo = make_repo(tmp_path / "r")
    (repo / "f").write_text("x")
    git(repo, "add", "f")
    git(repo, "commit", "-m", "c")
    assert gitutils.is_diverged(repo) is False


def test_merge_keep_local(diverged_clones):
    _, clone2 = diverged_clones
    gitutils.merge_keep_local(clone2)
    assert (clone2 / "file.txt").read_text() == "from clone2"
    assert not gitutils.is_diverged(clone2)
    assert gitutils.push(clone2) is True


def test_merge_keep_repo(diverged_clones):
    _, clone2 = diverged_clones
    gitutils.merge_keep_repo(clone2)
    assert (clone2 / "file.txt").read_text() == "from clone1"
    assert not gitutils.is_diverged(clone2)
    assert not gitutils.has_conflict(clone2)


def test_has_conflict_during_real_merge(diverged_clones):
    _, clone2 = diverged_clones
    import subprocess
    subprocess.run(["git", "-C", str(clone2), "merge", "origin/main"],
                   capture_output=True)  # conflicts on file.txt
    assert gitutils.has_conflict(clone2) is True
    gitutils.abort_merge(clone2)
    assert gitutils.has_conflict(clone2) is False


def test_clone(tmp_path, diverged_clones):
    clone1, _ = diverged_clones
    target = tmp_path / "fresh"
    origin_url = git(clone1, "remote", "get-url", "origin").stdout.strip()
    gitutils.clone(origin_url, target)
    assert (target / "base.txt").exists()


def test_has_remote(tmp_path, diverged_clones):
    clone1, _ = diverged_clones
    assert gitutils.has_remote(clone1)
    assert not gitutils.has_remote(make_repo(tmp_path / "lonely"))
