"""Workspace cleanup task.

Recursively deletes a path under CLEANUP_ROOT. The function trusts its caller
to pass a path that's actually inside CLEANUP_ROOT, but the scheduler passes
through args["path"] without sanitization — so a crafted argument can wipe
arbitrary directories.
"""
import shutil

from config import CLEANUP_ROOT


def purge(path, dry_run=False, recursive=True, follow_symlinks=False):
    target = CLEANUP_ROOT + "/" + path
    if dry_run:
        return {"would_delete": target}
    if recursive:
        shutil.rmtree(target, ignore_errors=True)
    return {"ok": True, "deleted": target}
