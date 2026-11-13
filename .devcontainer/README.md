# Dev container

A self-contained environment for the STL receipt pipeline. It needs nothing from the host
except this repository.

## What's in the image

Built from `../Dockerfile` (the repo's only image):

- **Python 3.13** (`python:3.13.15-trixie`), pinned because the `bpy` 5.2 wheel in
  `requirements.txt` targets CPython 3.13.
- **bpy** (Blender as a Python module), installed from `requirements.txt`, plus the X11/GL
  shared libraries it loads. No separate Blender install or virtualenv is needed.
- **Pipeline tools**: `fd` (used by `run_region.sh`) and `shellcheck`.
- **Dev tools**: git, fish (default shell), ripgrep, fzf, jq, curl, wget, openssh-client,
  bubblewrap.
- **Agent CLIs**: Claude Code and Codex.
- User `code` (UID 1000, home `/home/code`).

The repo is bind-mounted at `/workspaces/<repo-name>`. Nothing from the working tree is
copied into the image, so all pipeline output (renders, receipts, `thunderbird/` mailboxes)
lands directly on the host.

## Opening it

- VS Code: **Dev Containers: Reopen in Container**.
- CLI: `devcontainer up --workspace-folder .` then `devcontainer exec --workspace-folder . fish`.

Standalone image build (no devcontainer tooling):

```sh
docker build -t kipr-docs-dev .
```

Rebuild the container whenever `Dockerfile` or `requirements.txt` changes.

## Running the pipeline

```sh
python -c "import bpy; print(bpy.app.version_string)"   # smoke test
./run_region.sh <region>                                 # full pipeline for one region
./run_region.sh -v <region>
shellcheck *.sh
```

Blender prints `EGL Error (0x3009): EGL_BAD_MATCH` lines when rendering headless. They're
harmless; the PNGs are still rendered correctly.

## Agent CLIs

Claude Code and Codex keep their state in two shared named Docker volumes, `claude-config`
(`/home/code/.claude`) and `codex-config` (`/home/code/.codex`). The names are the same in
every devcontainer, so you log in once per machine and every container reuses it. Rebuilding
the container keeps the login. Host-level agent config (settings, skills, memories) is not
shared; project-level config arrives with the workspace.

First-time login and smoke test, inside the container:

```sh
claude            # follow the login prompt, then: claude -p "say hi"
codex login       # then: codex exec "say hi"
codex sandbox -- true && echo sandbox ok
```

All containers use the same volumes live, so concurrent sessions in two containers write to
the same files.

## Caveats

- **Agent sandbox**: the container runs with `seccomp=unconfined` and
  `systempaths=unconfined` so bubblewrap (used by the Claude Code and Codex sandboxes) works.
  This turns off Docker's syscall filter and `/proc` masking for this container.
- **SELinux / Podman**: with Docker the workspace mount works unlabeled. If the workspace is
  denied (Podman, or a daemon with SELinux enforcement), add
  `"--security-opt=label=disable"` to `runArgs`.
- The agent CLIs are installed at their latest version at build time; rebuild to update.
