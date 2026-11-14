"""Tests for uv_venv_store.py with real uv on a small local project."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
import uv_venv_store

SCRIPT = Path(__file__).resolve().parents[1] / "cmake" / "uv_venv_store.py"
PYPROJECT = """[project]
name = "{name}"
version = "0.0.0"
requires-python = ">=3.10"
dependencies = []

[project.scripts]
{name}-hello = "{name}:main"

[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[tool.setuptools]
py-modules = ["{name}"]
"""


def make_project(root: Path, name: str) -> Path:
    root.mkdir(parents=True)
    (root / "pyproject.toml").write_text(PYPROJECT.format(name=name))
    (root / f"{name}.py").write_text("def main():\n    print('hello')\n")
    return root


@pytest.fixture(scope="session")
def uv_cache(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("uv-cache")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return make_project(tmp_path / "demo", "demo")


@pytest.fixture
def store(tmp_path: Path) -> Path:
    path = tmp_path / "store"
    path.mkdir()
    return path


def run(tmp_path: Path, project: Path, uv_cache: Path, store: Path | None, *extra: str, view: Path | None = None, pkg: str = "pkg") -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("AMENT_CMAKE_VENV_UV_")}
    env["UV_CACHE_DIR"] = str(uv_cache)
    if store is not None:
        env["AMENT_CMAKE_VENV_UV_STORE"] = str(store)
    if view is not None:
        env["AMENT_CMAKE_VENV_UV_STORE_VIEW"] = str(view)
    build = tmp_path / pkg
    cmd = [sys.executable, str(SCRIPT), str(project), str(build / "venv_build"), str(build / "venv"), *extra]
    return subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)


def entries(store: Path) -> list[str]:
    return sorted(p.name for p in store.iterdir() if not p.name.startswith("."))


def digest(project: Path, extra: str | None = None, post: list[str] | None = None, python: str = "py", uv: str = "uv") -> str:
    return uv_venv_store.inputs_digest(project, extra, post or [], python, uv)


def test_mount_point_matches_within_one_mount(tmp_path: Path) -> None:
    (tmp_path / "cache").mkdir()
    assert uv_venv_store.mount_point(tmp_path / "cache") == uv_venv_store.mount_point(tmp_path / "build" / "pkg")


def test_mount_point_differs_across_mounts() -> None:
    assert uv_venv_store.mount_point(Path("/proc/self")) != uv_venv_store.mount_point(Path("/"))


def test_in_place_build_hardlinks_a_cache_on_the_same_mount(tmp_path: Path, project: Path, uv_cache: Path) -> None:
    assert run(tmp_path, project, uv_cache, None).returncode == 0
    assert any(p.stat().st_nlink > 1 for p in (tmp_path / "pkg" / "venv" / "lib").rglob("demo.py"))


def test_digest_ignores_mtimes_and_skipped_names(project: Path) -> None:
    before = digest(project)
    os.utime(project / "demo.py", (1, 1))
    (project / "__pycache__").mkdir()
    (project / "__pycache__" / "demo.cpython-312.pyc").write_bytes(b"x")
    (project / ".git").write_text("gitdir: elsewhere\n")
    (project / "demo.egg-info").mkdir()
    assert digest(project) == before


def test_digest_follows_file_content(project: Path) -> None:
    before = digest(project)
    (project / "demo.py").write_text("def main():\n    print('bye')\n")
    assert digest(project) != before


def test_digest_follows_symlink_targets(project: Path) -> None:
    (project / "data").symlink_to("demo.py")
    before = digest(project)
    (project / "data").unlink()
    (project / "data").symlink_to("pyproject.toml")
    assert digest(project) != before


def test_digest_follows_override_text_and_overridden_metadata(tmp_path: Path, project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    local = make_project(tmp_path / "local", "local")
    overrides = tmp_path / "overrides.txt"
    overrides.write_text(f"-e file://{local}\n")
    monkeypatch.setenv("AMENT_CMAKE_VENV_UV_OVERRIDES", str(overrides))
    before = digest(project)
    (local / "local.py").write_text("x = 1\n")
    assert digest(project) == before
    (local / "pyproject.toml").write_text(PYPROJECT.format(name="local").replace("dependencies = []", 'dependencies = ["six"]'))
    changed = digest(project)
    assert changed != before
    overrides.write_text(f"-e file://{local}\nsix==1.16.0\n")
    assert digest(project) != changed


def test_digest_follows_extra_post_install_python_and_uv(project: Path) -> None:
    base = digest(project)
    assert len({base, digest(project, extra="test"), digest(project, post=["six"]), digest(project, python="py2"), digest(project, uv="uv2")}) == 5


def test_store_build_links_the_venv_to_a_complete_relocatable_entry(tmp_path: Path, project: Path, uv_cache: Path, store: Path) -> None:
    extra = make_project(tmp_path / "extra", "extra")
    result = run(tmp_path, project, uv_cache, store, "--post-install", str(extra))
    assert result.returncode == 0, result.stderr
    assert "uv_venv: built" in result.stdout
    venv = tmp_path / "pkg" / "venv"
    [name] = entries(store)
    assert os.readlink(venv) == str(store / name)
    assert (store / name / ".complete").is_file()
    assert "relocatable = true" in (venv / "pyvenv.cfg").read_text()
    assert subprocess.run([str(venv / "bin" / "demo-hello")], capture_output=True, text=True, check=True).stdout == "hello\n"
    subprocess.run([str(venv / "bin" / "python"), "-c", "import extra"], check=True)


def test_rerun_reuses_the_entry(tmp_path: Path, project: Path, uv_cache: Path, store: Path) -> None:
    run(tmp_path, project, uv_cache, store)
    [name] = entries(store)
    inode = (store / name / "pyvenv.cfg").stat().st_ino
    result = run(tmp_path, project, uv_cache, store)
    assert result.returncode == 0, result.stderr
    assert "uv_venv: reused" in result.stdout
    assert (store / name / "pyvenv.cfg").stat().st_ino == inode


def test_a_real_venv_dir_is_replaced_by_the_link(tmp_path: Path, project: Path, uv_cache: Path, store: Path) -> None:
    (tmp_path / "pkg" / "venv").mkdir(parents=True)
    (tmp_path / "pkg" / "venv" / "old").write_text("old\n")
    assert run(tmp_path, project, uv_cache, store).returncode == 0
    assert (tmp_path / "pkg" / "venv").is_symlink()


def test_concurrent_builds_of_one_project_build_once(tmp_path: Path, project: Path, uv_cache: Path, store: Path) -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("AMENT_CMAKE_VENV_UV_")}
    env.update(UV_CACHE_DIR=str(uv_cache), AMENT_CMAKE_VENV_UV_STORE=str(store))
    procs = [subprocess.Popen([sys.executable, str(SCRIPT), str(project), str(tmp_path / pkg / "venv_build"), str(tmp_path / pkg / "venv")], env=env, stdout=subprocess.PIPE, text=True) for pkg in ("a", "b")]
    outs = [p.communicate()[0] for p in procs]
    assert [p.returncode for p in procs] == [0, 0]
    assert sorted(o.split()[1] for o in outs) == ["built", "reused"]
    [name] = entries(store)
    assert os.readlink(tmp_path / "a" / "venv") == os.readlink(tmp_path / "b" / "venv") == str(store / name)
    assert not [p for p in store.iterdir() if p.name.startswith(".tmp-")]


def test_a_failed_install_leaves_no_entry_and_no_link(tmp_path: Path, project: Path, uv_cache: Path, store: Path) -> None:
    result = run(tmp_path, project, uv_cache, store, "--post-install", str(tmp_path / "missing"))
    assert result.returncode == 1
    assert "uv_venv: uv pip install" in result.stderr
    assert entries(store) == []
    assert not [p for p in store.iterdir() if p.name.startswith(".tmp-")]
    assert not (tmp_path / "pkg" / "venv").exists()


def test_entry_files_hardlink_the_uv_cache(tmp_path: Path, project: Path, uv_cache: Path, store: Path) -> None:
    assert run(tmp_path, project, uv_cache, store).returncode == 0
    [name] = entries(store)
    assert any(p.stat().st_nlink > 1 for p in (store / name / "lib").rglob("demo.py"))


def test_a_missing_override_file_fails_naming_it(tmp_path: Path, project: Path, uv_cache: Path, store: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AMENT_CMAKE_VENV_UV_OVERRIDES", str(tmp_path / "gone.txt"))
    env = {**os.environ, "UV_CACHE_DIR": str(uv_cache), "AMENT_CMAKE_VENV_UV_STORE": str(store)}
    result = subprocess.run([sys.executable, str(SCRIPT), str(project), str(tmp_path / "pkg" / "venv_build"), str(tmp_path / "pkg" / "venv")], env=env, capture_output=True, text=True, check=False)
    assert result.returncode == 1
    assert f"override file {tmp_path / 'gone.txt'}" in result.stderr
    assert "Traceback" not in result.stderr


def test_a_view_without_the_entry_fails(tmp_path: Path, project: Path, uv_cache: Path, store: Path) -> None:
    view = tmp_path / "view"
    view.mkdir()
    result = run(tmp_path, project, uv_cache, store, view=view)
    assert result.returncode == 1
    assert f"store view {view} does not show" in result.stderr
    assert not (tmp_path / "pkg" / "venv").exists()


def test_the_link_points_into_the_view(tmp_path: Path, project: Path, uv_cache: Path, store: Path) -> None:
    view = tmp_path / "view"
    view.symlink_to(store)
    assert run(tmp_path, project, uv_cache, store, view=view).returncode == 0
    [name] = entries(store)
    assert os.readlink(tmp_path / "pkg" / "venv") == str(view / name)


def test_without_a_store_the_venv_builds_in_place_once(tmp_path: Path, project: Path, uv_cache: Path) -> None:
    first = run(tmp_path, project, uv_cache, None)
    assert first.returncode == 0, first.stderr
    venv = tmp_path / "pkg" / "venv"
    assert not venv.is_symlink()
    assert len((venv / ".built").read_text()) == 64
    second = run(tmp_path, project, uv_cache, None)
    assert "uv_venv: reused" in second.stdout


def test_an_in_place_build_replaces_a_store_link_and_leaves_the_entry(tmp_path: Path, project: Path, uv_cache: Path, store: Path) -> None:
    assert run(tmp_path, project, uv_cache, store).returncode == 0
    [name] = entries(store)
    files = sorted(p.relative_to(store / name) for p in (store / name).rglob("*"))
    assert run(tmp_path, project, uv_cache, None).returncode == 0
    assert not (tmp_path / "pkg" / "venv").is_symlink()
    assert (store / name / ".complete").is_file()
    assert sorted(p.relative_to(store / name) for p in (store / name).rglob("*")) == files
