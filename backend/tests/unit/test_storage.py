import re

import pytest

from app.api.documents import display_filename
from app.storage import UploadStore


def test_saved_files_get_random_names_and_keep_their_bytes(tmp_path):
    store = UploadStore(tmp_path)

    first, second = store.save(b"%PDF-one"), store.save(b"%PDF-two")

    assert re.fullmatch(r"[0-9a-f]{32}\.pdf", first)
    assert first != second
    assert store.path_for(first).read_bytes() == b"%PDF-one"


def test_an_existing_file_is_never_overwritten(tmp_path, monkeypatch):
    store = UploadStore(tmp_path)
    monkeypatch.setattr("app.storage.secrets.token_hex", lambda _n: "same")
    store.save(b"original")

    with pytest.raises(FileExistsError):
        store.save(b"replacement")
    assert store.path_for("same.pdf").read_bytes() == b"original"


@pytest.mark.parametrize("name", ["../escape.pdf", "sub/inner.pdf", "..", "/etc/passwd"])
def test_names_that_point_outside_the_directory_are_refused(tmp_path, name):
    with pytest.raises(ValueError, match="plain file name"):
        UploadStore(tmp_path).path_for(name)


def test_directory_is_only_created_when_a_file_is_saved(tmp_path):
    store = UploadStore(tmp_path / "uploads")
    assert not (tmp_path / "uploads").exists()

    store.save(b"%PDF-x")

    assert (tmp_path / "uploads").is_dir()


def test_delete_removes_the_file(tmp_path):
    store = UploadStore(tmp_path)
    name = store.save(b"%PDF-x")

    store.delete(name)

    assert not store.path_for(name).exists()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("lecture.pdf", "lecture.pdf"),
        ("C:\\Users\\me\\Week 3.pdf", "Week 3.pdf"),
        ("../../etc/evil.pdf", "evil.pdf"),
        ("bad\x00name\n.pdf", "badname.pdf"),
        ("   ", "document.pdf"),
        ("a" * 300 + ".pdf", "a" * 255),
    ],
)
def test_display_filename_is_safe_to_store_and_show(raw, expected):
    assert display_filename(raw) == expected
