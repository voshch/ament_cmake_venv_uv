"""Build the uv venv of a project, shared through a content-addressed store when AMENT_CMAKE_VENV_UV_STORE is set."""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

FORMAT = 1
SKIP_NAMES = frozenset({".git", ".venv", ".ruff_cache", "__pycache__"})
METADATA = ("pyproject.toml", "setup.cfg", "setup.py")


def _skipped(name: str) -> bool:
    return name in SKIP_NAMES or name.endswith((".egg-info", ".pyc"))


def _file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _entries(root: Path, rel: str = "") -> Iterator[tuple[str, str]]:
    with os.scandir(root / rel) as it:
        for e in sorted(it, key=lambda e: e.name):
            if _skipped(e.name):
                continue
            path = f"{rel}/{e.name}" if rel else e.name
            if e.is_symlink():
                yield path, "link:" + os.readlink(e.path)
            elif e.is_dir():
                yield from _entries(root, path)
            else:
                yield path, "file:" + _file_digest(Path(e.path))


def overrides() -> list[str]:
    """Override files named by AMENT_CMAKE_VENV_UV_OVERRIDES."""
    return [p for p in os.environ.get("AMENT_CMAKE_VENV_UV_OVERRIDES", "").split(":") if p]


def _local_path(line: str) -> Path | None:
    spec = line.strip().removeprefix("-e").strip()
    return Path(spec.removeprefix("file://")) if spec.startswith("file://") else None


def _override_inputs(path: str) -> dict[str, object]:
    if not Path(path).is_file():
        raise SystemExit(f"uv_venv: override file {path} from AMENT_CMAKE_VENV_UV_OVERRIDES does not exist")
    text = Path(path).read_text()
    local = {}
    for line in text.splitlines():
        target = _local_path(line)
        if target is not None:
            local[str(target)] = {name: (target / name).read_text() for name in METADATA if (target / name).is_file()}
    return {"path": path, "text": text, "local": local}


def inputs_digest(project: Path, extra: str | None, post_install: list[str], python: str, uv: str) -> str:
    """Hash of everything the venv of project is built from."""
    key = {
        "format": FORMAT,
        "uv": uv,
        "python": python,
        "extra": extra,
        "post_install": post_install,
        "overrides": [_override_inputs(p) for p in overrides()],
        "files": list(_entries(project)),
    }
    return hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()


def _run(cmd: list[str], env: dict[str, str], cwd: Path | None = None) -> str:
    return subprocess.run(cmd, cwd=cwd, env=env, check=True, stdout=subprocess.PIPE, text=True).stdout.strip()


def _python(project: Path, env: dict[str, str]) -> str:
    found = subprocess.run(["uv", "python", "find"], cwd=project, env=env, stdout=subprocess.PIPE, text=True, check=False)
    if found.returncode:
        _run(["uv", "python", "install"], env, project)
        return _run(["uv", "python", "find"], env, project)
    return found.stdout.strip()


def _stage(project: Path, build: Path) -> None:
    shutil.rmtree(build, ignore_errors=True)
    shutil.copytree(project, build, symlinks=True, ignore=lambda _, names: [n for n in names if _skipped(n)])


def _install(venv: Path, build: Path, extra: str | None, post_install: list[str], python: str, env: dict[str, str], relocatable: bool) -> None:
    _run(["uv", "venv", "--clear", "--python", python, *(["--relocatable"] if relocatable else []), str(venv)], env, build)
    pip = ["uv", "pip", "install", "--python", str(venv / "bin" / "python"), "--compile-bytecode"]
    _run([*pip, *[a for p in overrides() for a in ("--override", p)], f"{build}[{extra}]" if extra else str(build)], env, build)
    for args in post_install:
        _run([*pip, *shlex.split(args)], env, build)
    _run([str(venv / "bin" / "python"), "-c", "import sys"], env)


def mount_point(path: Path) -> Path:
    """Mount point holding path, existing or not."""
    path = path.resolve()
    while not path.is_mount():
        path = path.parent
    return path


@contextlib.contextmanager
def _locked(path: Path) -> Iterator[None]:
    with path.open("a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


def _link(venv: Path, target: Path) -> None:
    if venv.is_symlink():
        if os.readlink(venv) == str(target):
            return
    elif venv.exists():
        shutil.rmtree(venv)
    venv.parent.mkdir(parents=True, exist_ok=True)
    tmp = venv.with_name(f".{venv.name}-{os.getpid()}")
    tmp.unlink(missing_ok=True)
    tmp.symlink_to(target)
    os.replace(tmp, venv)


def _store(store: Path, view: Path, digest: str, venv: Path, build: Callable[[Path], None]) -> str:
    entry = store / digest
    action = "reused"
    if not (entry / ".complete").is_file():
        (store / ".locks").mkdir(exist_ok=True)
        with _locked(store / ".locks" / digest):
            if not (entry / ".complete").is_file():
                tmp = store / f".tmp-{digest}-{os.getpid()}"
                shutil.rmtree(tmp, ignore_errors=True)
                try:
                    build(tmp)
                    (tmp / ".complete").touch()
                    shutil.rmtree(entry, ignore_errors=True)
                    os.rename(tmp, entry)
                finally:
                    shutil.rmtree(tmp, ignore_errors=True)
                action = "built"
    if not (view / digest / ".complete").is_file():
        raise SystemExit(f"uv_venv: store view {view} does not show {digest} from store {store}")
    _link(venv, view / digest)
    return action


def _in_place(venv: Path, digest: str, build: Callable[[Path], None]) -> str:
    stamp = venv / ".built"
    if not venv.is_symlink() and stamp.is_file() and stamp.read_text() == digest:
        return "reused"
    if venv.is_symlink():
        venv.unlink()
    build(venv)
    stamp.write_text(digest)
    return "built"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path, help="project directory")
    parser.add_argument("build", type=Path, help="staging copy of the project the venv installs from")
    parser.add_argument("venv", type=Path, help="venv path, a symlink into the store when AMENT_CMAKE_VENV_UV_STORE is set")
    parser.add_argument("--extra", help="extra of the project to install")
    parser.add_argument("--post-install", action="append", default=[], help="arguments of one more uv pip install into the venv")
    args = parser.parse_args(argv)

    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "VIRTUAL_ENV")}
    store_dir = os.environ.get("AMENT_CMAKE_VENV_UV_STORE")
    cache = os.environ.get("UV_CACHE_DIR")
    if store_dir or (cache and mount_point(Path(cache)) == mount_point(args.venv.parent)):
        env["UV_LINK_MODE"] = "hardlink"
    try:
        python = _python(args.project, env)
        digest = inputs_digest(args.project, args.extra, args.post_install, python, _run(["uv", "--version"], env))

        def build(venv: Path) -> None:
            _stage(args.project, args.build)
            _install(venv, args.build, args.extra, args.post_install, python, env, relocatable=bool(store_dir))

        if store_dir:
            store = Path(store_dir)
            if not store.is_dir():
                raise SystemExit(f"uv_venv: AMENT_CMAKE_VENV_UV_STORE={store} is not a directory")
            action = _store(store, Path(os.environ.get("AMENT_CMAKE_VENV_UV_STORE_VIEW") or store), digest, args.venv, build)
        else:
            action = _in_place(args.venv, digest, build)
    except subprocess.CalledProcessError as e:
        print(f"uv_venv: {shlex.join(e.cmd)} exited {e.returncode}", file=sys.stderr)
        return 1
    print(f"uv_venv: {action} {digest[:12]} for {args.project}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
