"""A Git checkout must preserve strict artifact checks outside root metadata."""

import pytest

from artifact.paper1_hotmobile2027 import verify_release


@pytest.mark.parametrize("git_directory", [True, False])
def test_root_git_metadata_is_not_artifact_evidence(tmp_path, monkeypatch, git_directory):
    monkeypatch.setattr(verify_release, "ROOT", tmp_path)
    (tmp_path / "README.md").write_text("artifact", encoding="utf-8")
    metadata = tmp_path / ".git"
    if git_directory:
        metadata.mkdir()
        (metadata / "config").write_text("local clone configuration", encoding="utf-8")
    else:
        metadata.write_text("gitdir: another-worktree", encoding="utf-8")
    assert verify_release.actual_paths() == ["README.md"]


def test_other_extras_are_not_silently_ignored(tmp_path, monkeypatch):
    monkeypatch.setattr(verify_release, "ROOT", tmp_path)
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "extra.txt").write_text("unexpected", encoding="utf-8")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / ".git").write_text("not root metadata", encoding="utf-8")
    assert verify_release.actual_paths() == [".venv/extra.txt", "nested/.git"]
