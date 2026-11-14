# ament_cmake_venv_uv

Builds a package's Python venv with [uv](https://docs.astral.sh/uv/) at colcon build time.

```cmake
find_package(ament_cmake_venv REQUIRED)
find_package(ament_cmake_venv_uv REQUIRED)

uv_venv(
  PROJECTFILE pyproject.toml
  TEST_EXTRA test
  POST_INSTALL "--no-build-isolation git+https://example.org/pkg.git@<sha>"
)
```

`uv_venv` installs the project (with the `TEST_EXTRA` extra when `BUILD_TESTING` is on) into `build/<pkg>/venv`, runs one more `uv pip install` per `POST_INSTALL` entry, and installs the venv and a `python` wrapper under `lib/<pkg>`. `DIRECTORY` names a project directory other than the package's own. `uv_venv_pytest(<name> <path>)` registers a pytest run in the venv as an ament test.

The venv is keyed by a hash of its inputs: every project file by content (symlinks by target, `.git`, `.venv`, `__pycache__`, `*.egg-info` and `*.pyc` left out), the extra, the `POST_INSTALL` entries, the interpreter `uv python find` picks, `uv --version`, and every override file with the `pyproject.toml`, `setup.cfg` and `setup.py` of each local path it names. A build with unchanged inputs does nothing.

| Variable | Effect |
| --- | --- |
| `AMENT_CMAKE_VENV_UV_OVERRIDES` | Colon-separated override files passed to every install as `--override` |
| `AMENT_CMAKE_VENV_UV_STORE` | Store directory. Each venv is built once into `<store>/<hash>` as a relocatable venv and `build/<pkg>/venv` becomes a symlink to it. Unset, the venv is built in place |
| `AMENT_CMAKE_VENV_UV_STORE_VIEW` | Directory the symlinks point into instead of the store, for a read-only mount of it |

Store entries are built under a per-hash lock in a temporary directory and renamed into place once installed and checked, so concurrent builds of one project build it once and a failed build leaves nothing behind. Store builds hardlink from the uv cache, which must share a mount with the store. In-place builds hardlink when `UV_CACHE_DIR` shares a mount with the venv. Removing unused store entries is up to the caller.

Tests: `python3 -m pytest` from the repo root, with `uv` on the path.
