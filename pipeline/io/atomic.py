"""
Atomic file writes and safe environment handling.

The previous implementation rewrote each CSV in place on every run. A crash or a
cancelled CI job mid-write truncated the dataset, and because those files ARE the
database, only git history stood between us and data loss. Writes now go to a
temporary file in the same directory and are renamed into place -- rename is
atomic on POSIX, so a reader either sees the whole old file or the whole new one.
"""
from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager


@contextmanager
def atomic_write(path, mode="w", encoding="utf-8", newline=""):
    """Write to `path` atomically. The target is only replaced on clean exit."""
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tmp-", suffix=".part")
    os.close(fd)
    try:
        kwargs = {"encoding": encoding} if "b" not in mode else {}
        if "b" not in mode:
            kwargs["newline"] = newline
        with open(tmp, mode, **kwargs) as fh:
            yield fh
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def write_json(path, obj, indent=2):
    with atomic_write(path) as fh:
        json.dump(obj, fh, indent=indent, default=str)
    return path


def read_json(path, default=None):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return default
