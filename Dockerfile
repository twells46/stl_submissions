# Pinned to CPython 3.13 because the bpy 5.2 wheel in requirements.txt targets it.
FROM docker.io/library/python:3.13.15-trixie

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Dev tools, plus:
#   lib* - shared libraries the bpy wheel loads (it bundles Blender, not its X11/GL deps)
#   shellcheck - lints the pipeline's shell scripts
RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        bubblewrap \
        ca-certificates \
        curl \
        fd-find \
        fish \
        fzf \
        git \
        jq \
        libdbus-1-3 \
        libegl1 \
        libgl1 \
        libglib2.0-0 \
        libice6 \
        libsm6 \
        libx11-6 \
        libxcursor1 \
        libxext6 \
        libxfixes3 \
        libxi6 \
        libxinerama1 \
        libxkbcommon0 \
        libxrandr2 \
        libxrender1 \
        libxxf86vm1 \
        openssh-client \
        ripgrep \
        shellcheck \
        wget \
    && ln -s "$(command -v fdfind)" /usr/local/bin/fd \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/pipeline-requirements.txt

RUN python -m pip install --requirement /tmp/pipeline-requirements.txt \
    && rm /tmp/pipeline-requirements.txt \
    && python -c "import bpy; print('bpy', bpy.app.version_string)"

# Same user in every devcontainer: the shared agent volumes hold absolute paths under /home/code.
RUN groupadd --gid 1000 code \
    && useradd --uid 1000 --gid 1000 --create-home --shell /usr/bin/fish code

USER code

# Agent state lives in named volumes; a new volume inherits this ownership.
# CLAUDE_CONFIG_DIR also moves ~/.claude.json inside the volume.
ENV CLAUDE_CONFIG_DIR=/home/code/.claude \
    CODEX_HOME=/home/code/.codex \
    PATH=/home/code/.local/bin:$PATH
RUN mkdir -p "$CLAUDE_CONFIG_DIR" "$CODEX_HOME" \
    && curl -fsSL https://claude.ai/install.sh | bash \
    # The Codex installer unpacks into $CODEX_HOME/packages, which the codex-config volume
    # would hide; install the package outside the volume instead.
    && curl -fsSL https://chatgpt.com/codex/install.sh \
        | CODEX_HOME=/home/code/.local/share/codex CODEX_NON_INTERACTIVE=1 sh \
    && claude --version \
    && codex --version
