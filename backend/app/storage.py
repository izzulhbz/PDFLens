"""Where uploaded PDFs are kept on disk.

Files are saved under random names that the server generates
(32 hex characters + ".pdf"). The filename the client sent is stored in the
database for display only and never used to build a path, because it could
contain "../" (path traversal), clash with another user's file, or contain
characters the filesystem rejects.
"""

import os
import secrets
from pathlib import Path


class UploadStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory.resolve()

    def save(self, data: bytes) -> str:
        """Write `data` to a new file and return its generated name."""
        # Created on first use, so building an app (in tests, say) never
        # creates directories as a side effect.
        self.directory.mkdir(parents=True, exist_ok=True)
        name = f"{secrets.token_hex(16)}.pdf"
        # O_EXCL: fail rather than overwrite if the name somehow exists.
        # 0o600: only the app's own user can read the file.
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        fd = os.open(self.path_for(name), flags, 0o600)
        with os.fdopen(fd, "wb") as file:
            file.write(data)
        return name

    def path_for(self, name: str) -> Path:
        path = (self.directory / name).resolve()
        # Defence in depth: names come from save(), but never allow a name
        # that would point outside the upload directory.
        if path.parent != self.directory:
            raise ValueError("Stored filename must be a plain file name.")
        return path

    def delete(self, name: str) -> None:
        self.path_for(name).unlink(missing_ok=True)
