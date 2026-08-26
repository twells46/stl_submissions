FROM docker.io/library/python:3.13.15-trixie

ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=${USER_UID}

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        ca-certificates \
        fd-find \
        git \
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
        shellcheck \
    && ln -s /usr/bin/fdfind /usr/local/bin/fd \
    && groupadd --gid "${USER_GID}" "${USERNAME}" \
    && useradd --uid "${USER_UID}" --gid "${USER_GID}" --create-home --shell /bin/bash "${USERNAME}" \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/pipeline-requirements.txt

RUN python -m pip install --requirement /tmp/pipeline-requirements.txt \
    && rm /tmp/pipeline-requirements.txt

USER ${USERNAME}
