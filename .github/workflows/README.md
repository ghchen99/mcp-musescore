# GitHub Actions workflows

This folder holds the CI workflows. GitHub Actions only reads the `.yml` files here; this README is documentation.

| Workflow | Runs on | What it checks |
|---|---|---|
| [`pr-validation.yml`](pr-validation.yml) | every pull request, and every push to `main` | dependencies, the server, the tool list, and the test suite with and without MuseScore |

## `pr-validation.yml`

The workflow has two jobs. They run in parallel, and both must pass.

### Job `test`: the Python checks

Runs the test suite without MuseScore, the way most contributors run it.

1. **`uv sync --locked`** installs the exact versions from `uv.lock`, and fails if the lock file is out of date with `pyproject.toml`.
2. **Server imports**: `import server` must work.
3. **List registered tools**: `fastmcp inspect server.py` must succeed.
4. **Node.js** (`actions/setup-node`), for the plugin JavaScript syntax check.
5. **Checks** (`make check`, which runs `uv run prek run --all-files`): the same checks contributors run before every commit, from `prek.toml`. prek fails when a hook changes a file, so these also act as checks in CI:
   - **generate requirements.txt from uv.lock**: regenerates `requirements.txt` with `uv export`; fails if it was out of date with `uv.lock`;
   - **deptry**: no missing or unused dependencies;
   - **ruff lint**, **ruff format** and **docstring-tailor docstring format**: the code follows the lint rules and is formatted; in CI these fail if they would change a file;
   - **ty type check**: no type errors in `src/`, `server.py`, `dev/` and `tests/`;
   - **plugin JavaScript syntax check**: `node dev/check_plugin_js_syntax.js` parses the JavaScript functions in the plugin.
6. **Tests with coverage** (`make test`, which runs `uv run pytest --no-musescore --cov`): the test suite without the MuseScore tests (they run in the `musescore-tests` job), with branch coverage of `src/` as configured in `pyproject.toml`; it fails below 86%. This is the coverage without MuseScore, the same on every machine.

   See [docs/development.md](../../docs/development.md#checks-before-committing-prek) for both.

### Job `musescore-tests`: the tests with real MuseScore

Runs the full test suite, including the tests that need MuseScore (`tests/test_plugin_headless.py` and the file round-trip tests), so changes to the plugin are checked too.

**Two MuseScore versions**, as a matrix:

- **`4.7.0`**: the oldest supported version. This keeps the documented minimum honest: a change that breaks 4.7 fails here.
- **`latest`**: the newest MuseScore release, looked up when the job runs. A new MuseScore release is tested automatically, without changing the workflow.

`fail-fast: false` lets both versions finish even if one fails, so you can see whether a failure is version-specific.

**The steps:**

1. **Install the system libraries MuseScore needs.** MuseScore is a desktop application, and the runner is a bare Ubuntu server. The workflow lists the packages by purpose:

   | Group | Packages | Why |
   |---|---|---|
   | Virtual display | `xvfb`, `xauth` | `xvfb-run` starts an invisible X server; `xauth` handles its access key |
   | OpenGL | `libegl1`, `libgl1`, `libglx0`, `libopengl0` | The interface is drawn with Qt Quick, even when nothing is shown |
   | X11 and keyboard | `libx11-6`, `libxkbcommon-x11-0` | Talking to the X server |
   | Qt's X11 platform plugin | `libxcb-cursor0`, `libxcb-icccm4`, `libxcb-image0`, `libxcb-keysyms1`, `libxcb-randr0`, `libxcb-render-util0`, `libxcb-shape0`, `libxcb-xinerama0`, `libxcb-xkb1` | Loaded by Qt 6 for X11 |
   | Audio | `libasound2t64`, `libpipewire-0.3-0t64` | Linked at startup, although no sound is played |
   | Fonts | `libfontconfig1`, `libfreetype6` | Fonts, including the music symbols |
   | Utilities | `libglib2.0-0t64` | A library Qt builds on |

   The `t64` in some names is specific to Ubuntu 24.04. That is why both jobs run on `ubuntu-24.04` instead of `ubuntu-latest`, which moves to a newer Ubuntu over time: a newer release can rename these packages and break the job.

2. **Find the MuseScore AppImage.** Asks the GitHub API for the release (`tags/v4.7.0`, or `latest`) and picks its `x86_64.AppImage`.
3. **Cache the AppImage.** About 190 MB, cached under its file name, so it is downloaded again only when the version changes.
4. **Unpack MuseScore.** The AppImage is unpacked with `--appimage-extract` instead of mounted, because the runner has no FUSE. `MUSESCORE_BIN` then points at the unpacked `AppRun`, which is how the tests find MuseScore.
5. **Run the tests.** First a guard: if MuseScore is not found, the job fails, so the MuseScore tests cannot quietly skip themselves and look like a pass. Then `pytest` runs under `xvfb-run`.

**Why `xvfb-run`:** MuseScore uses the X11 platform on Linux even when asked to run offscreen (`QT_QPA_PLATFORM=offscreen`). On a desktop that goes unnoticed; on a server without a display, MuseScore aborts. `xvfb-run` gives it a virtual display.

### Common changes

- **Raising the minimum MuseScore version:** change `4.7.0` in the matrix, and update the version in the README, [docs/setup.md](../../docs/setup.md) and [docs/tools.md](../../docs/tools.md#version-requirements).
- **A new MuseScore release needs another library:** the job then fails at `--version` or in the tests, usually naming the missing library (`... cannot open shared object file`) or the Qt plugin. Add the Ubuntu package to the matching group in the list.
- **A new check:** add a step to the `test` job if it does not need MuseScore; it then also runs for contributors without MuseScore.

### Reproducing the MuseScore job locally

The job can be reproduced in an Ubuntu 24.04 container, which has even fewer libraries than GitHub's runner. With MuseScore unpacked in `squashfs-root` (run the AppImage with `--appimage-extract`), from the repository root:

```bash
podman run --rm -v "$PWD":/repo:ro -v "$PWD/squashfs-root":/ms:ro ubuntu:24.04 bash -c '
  apt-get update && apt-get install -y --no-install-recommends ca-certificates curl xvfb xauth <the packages above>
  curl -LsSf https://astral.sh/uv/install.sh | sh && export PATH=$HOME/.local/bin:$PATH
  cp -r /repo /work && cd /work && rm -rf .venv && uv sync --locked
  MUSESCORE_BIN=/ms/AppRun xvfb-run -a uv run pytest tests
'
```

`docker` works the same way. On a desktop with MuseScore installed, it is simpler to point `MUSESCORE_BIN` at it and run `uv run pytest`.
