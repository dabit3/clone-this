"""Compute a reproducible content fingerprint for a clone-this destination.

The fingerprint covers the clone source, tests, configuration, and fixtures.
It excludes the run directory (.devin/clone-this) so that manifest and evidence
updates never change the revision they describe.
"""
import argparse
import hashlib
import os
from pathlib import Path
import stat
import subprocess
import sys


RUN_DIRECTORY = ".devin/clone-this"
EXCLUDED_FILES = frozenset((".DS_Store", "Thumbs.db"))
WALK_EXCLUDED_DIRECTORIES = frozenset((
    ".git", ".hg", ".svn", ".cache", ".gradle", ".mypy_cache", ".next", ".nuxt",
    ".parcel-cache", ".pytest_cache", ".ruff_cache", ".svelte-kit", ".turbo", ".venv",
    "DerivedData", "Pods", "__pycache__", "build", "coverage", "dist", "node_modules",
    "out", "playwright-report", "target", "test-results", "venv",
))
CHUNK_SIZE = 1 << 16


def git_files(root):
    """Return git's view of tracked plus untracked, non-ignored files, or None outside a repository."""
    def run(*arguments):
        return subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", *arguments],
            capture_output=True, check=True, env={**os.environ, "LC_ALL": "C"},
        ).stdout.split(b"\0")

    repository = any(os.path.lexists(parent / ".git") for parent in (root, *root.parents))
    try:
        tracked = run("--cached", "--stage")
        untracked = run("--others", "--exclude-standard")
    except FileNotFoundError:
        if repository:
            raise ValueError("Git is required to fingerprint this repository.")
        return None
    except subprocess.CalledProcessError as error:
        if not repository and b"not a git repository" in (error.stderr or b""):
            return None
        raise ValueError("Git could not list the clone files. Resolve the Git error before retrying.") from error
    paths = []
    for entry in tracked:
        if not entry:
            continue
        metadata, raw_path = entry.split(b"\t", 1)
        path = raw_path.decode("utf-8", "surrogateescape")
        if metadata.split()[0] == b"160000" and not (root / path / ".git").exists():
            raise ValueError(f"Submodule {path!r} is not initialized. Obtain authorized source access before retrying.")
        paths.append(path)
    paths.extend(entry.decode("utf-8", "surrogateescape") for entry in untracked if entry)
    return paths


def walk_files(root):
    """Return every file below root except well-known generated and dependency directories."""
    root = Path(root)
    paths = []

    def fail(error):
        raise error

    for directory, names, files in os.walk(root, onerror=fail):
        relative = Path(directory).relative_to(root)
        names[:] = [name for name in names if name not in WALK_EXCLUDED_DIRECTORIES
                    and (relative / name).as_posix() != RUN_DIRECTORY]
        links = [name for name in names if (Path(directory) / name).is_symlink()]
        names[:] = [name for name in names if name not in links]
        paths.extend((relative / name).as_posix() for name in files + links)
    return paths


def list_files(root):
    """Return the listing method and the sorted relative POSIX paths included in the fingerprint."""
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("The clone root must be an existing directory.")
    listed = git_files(root)
    method = "walk" if listed is None else "git"
    if listed is None:
        listed = walk_files(root)
    selected = set()
    for relative in listed:
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("The file listing contains a path outside the clone root.")
        relative = path.as_posix()
        if relative == RUN_DIRECTORY or relative.startswith(RUN_DIRECTORY + "/") or path.name in EXCLUDED_FILES:
            continue
        full_path = root / path
        full_path.parent.resolve().relative_to(root)
        if not full_path.is_symlink() and full_path.is_dir():
            selected.update((path / child).as_posix() for child in list_files(full_path)[1])
        else:
            selected.add(relative)
    return method, sorted(selected)


def compute_fingerprint(root):
    """Return a sha256 digest of every included path and its content."""
    root = Path(root).resolve(strict=True)
    method, paths = list_files(root)
    digest = hashlib.sha256(b"clone-this-fingerprint-v2\0" + method.encode("ascii") + b"\0")

    def record(kind, relative, size, content):
        digest.update(b"%s\0%s\0%d\0" % (kind, relative.encode("utf-8", "surrogateescape"), size))
        for chunk in content:
            digest.update(chunk)

    def signature(info):
        return info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns

    def read_chunks(path, expected):
        with path.open("rb") as handle:
            if signature(os.fstat(handle.fileno())) != signature(expected):
                raise ValueError("The clone changed during fingerprinting. Stop writers and retry.")
            for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
                yield chunk
            if signature(os.fstat(handle.fileno())) != signature(expected):
                raise ValueError("The clone changed during fingerprinting. Stop writers and retry.")
        if signature(path.lstat()) != signature(expected):
            raise ValueError("The clone changed during fingerprinting. Stop writers and retry.")

    for relative in paths:
        path = root / relative
        path.parent.resolve().relative_to(root)
        try:
            info = os.lstat(path)
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode):
            resolved = path.resolve(strict=True)
            target_path = resolved.relative_to(root).as_posix()
            if resolved.is_file() and target_path not in paths:
                raise ValueError(f"Symlink {relative!r} targets an excluded file. Include its source before retrying.")
            if resolved.is_dir() and target_path != "." and not any(p.startswith(target_path + "/") for p in paths):
                raise ValueError(f"Symlink {relative!r} targets an uncovered directory.")
            target = os.readlink(path).encode("utf-8", "surrogateescape")
            record(b"link", relative, len(target), (target,))
        elif stat.S_ISREG(info.st_mode):
            kind = b"file:%03o" % (info.st_mode & 0o111)
            record(kind, relative, info.st_size, read_chunks(path, info))
        else:
            raise ValueError(f"Cannot fingerprint non-regular file {relative!r}.")
    if (method, paths) != list_files(root):
        raise ValueError("The file listing changed during fingerprinting. Stop writers and retry.")
    return "sha256:" + digest.hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Print the content fingerprint of a clone destination.")
    parser.add_argument("clone_root", type=Path, help="Path to the clone destination")
    parser.add_argument("--list", action="store_true", help="Print the listing method and every included path instead")
    args = parser.parse_args(argv)
    try:
        if args.list:
            method, paths = list_files(args.clone_root)
            print(f"# method: {method}")
            for path in paths:
                print(path)
        else:
            print(compute_fingerprint(args.clone_root))
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Cannot fingerprint the clone: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
