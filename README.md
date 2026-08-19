<div align="center">

# Blender MCP

**Connect Blender to any LLM**

Prompt-assisted 3D modeling, scene creation, and manipulation — driven by AI.

[![PyPI Downloads](https://static.pepy.tech/personalized-badge/blender-mcp?period=total&units=INTERNATIONAL_SYSTEM&left_color=BLACK&right_color=GREEN&left_text=downloads)](https://pepy.tech/projects/blender-mcp)
[![PyPI Version](https://img.shields.io/pypi/v/blender-mcp?color=blue)](https://pypi.org/project/blender-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Discord](https://img.shields.io/badge/Discord-join-5865F2?logo=discord&logoColor=white)](https://discord.gg/SNqPn4TcKQ)

[**Website**](https://blendermcp.org/) · [**Full Tutorial**](https://www.youtube.com/watch?v=lCyQ717DuzQ) · [**Discord**](https://discord.gg/SNqPn4TcKQ) · [**Releases**](https://github.com/ahujasid/blender-mcp/releases) · [**Sponsor**](https://github.com/sponsors/ahujasid)

<a href="https://trendshift.io/repositories/14834?utm_source=repository-badge&amp;utm_medium=badge&amp;utm_campaign=badge-repository-14834" target="_blank" rel="noopener noreferrer"><img src="https://trendshift.io/api/badge/repositories/14834" alt="ahujasid%2Fblender-mcp | Trendshift" width="250" height="55"/></a>

<br />

**Supporters**

[CodeRabbit](https://www.coderabbit.ai/)
[Kevin Guanche Darias](https://github.com/KevinGuancheDarias)

**All supporters:** [Support this project](https://github.com/sponsors/ahujasid)

</div>

---

## Quickstart

Docker is the standard installation method. It pins the Python interpreter and every
dependency to a fixed image, so the server behaves identically on every machine.

Five steps: install Docker, pull the image, point your MCP client at it, install the Blender addon, connect.

**1. Install Docker**

- **macOS / Windows:** [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- **Linux:** [Docker Engine](https://docs.docker.com/engine/install/) (20.10 or newer)

**2. Pull the image first**

```bash
docker pull ghcr.io/ahujasid/blender-mcp:latest
```

> **Do this before configuring your client.** Some MCP clients time out while a first-run
> download is still in progress and mark the server as failed.

> **Pinning a version.** `:latest` follows each release. To keep a machine on one exact
> build — recommended if you want reproducible behaviour across a team — replace `:latest`
> with a version tag everywhere below, for example
> `ghcr.io/ahujasid/blender-mcp:1.8.3`. Upgrade the addon and the image together, since
> both ship from the same tag.

**3. Add the MCP server to your client**

<details open>
<summary><b>Claude Desktop</b> — Settings → Developer → Edit Config</summary>

**macOS** — first create the shared screenshot directory once:

```bash
mkdir -p /tmp/blender-mcp-shared
```

```json
{
    "mcpServers": {
        "blender": {
            "command": "docker",
            "args": [
                "run", "-i", "--rm",
                "-e", "TMPDIR=/tmp/blender-mcp-shared",
                "-v", "/tmp/blender-mcp-shared:/tmp/blender-mcp-shared",
                "ghcr.io/ahujasid/blender-mcp:latest"
            ]
        }
    }
}
```

**Linux** — same, plus host networking so the container reaches Blender on loopback:

```bash
mkdir -p /tmp/blender-mcp-shared
```

```json
{
    "mcpServers": {
        "blender": {
            "command": "docker",
            "args": [
                "run", "-i", "--rm", "--network=host",
                "-e", "BLENDER_HOST=localhost",
                "-e", "TMPDIR=/tmp/blender-mcp-shared",
                "-v", "/tmp/blender-mcp-shared:/tmp/blender-mcp-shared",
                "ghcr.io/ahujasid/blender-mcp:latest"
            ]
        }
    }
}
```

**Windows** — no shared directory, because Windows host paths cannot be mapped to an
identical path inside the container:

```json
{
    "mcpServers": {
        "blender": {
            "command": "docker",
            "args": [
                "run", "-i", "--rm",
                "ghcr.io/ahujasid/blender-mcp:latest"
            ]
        }
    }
}
```

> **Windows limitation:** tools that exchange files between Blender and the server are
> unavailable in this configuration — `get_viewport_screenshot`, and Hyper3D generation
> from *local image paths*. Everything else, including Hyper3D from image URLs, works
> normally. See [Host file access](#host-file-access).
</details>

<details>
<summary><b>Claude Code</b></summary>

**macOS:**

```bash
mkdir -p /tmp/blender-mcp-shared
claude mcp add blender -- docker run -i --rm \
  -e TMPDIR=/tmp/blender-mcp-shared \
  -v /tmp/blender-mcp-shared:/tmp/blender-mcp-shared \
  ghcr.io/ahujasid/blender-mcp:latest
```

**Windows** — no shared directory; screenshots are unavailable:

```bash
claude mcp add blender -- docker run -i --rm ghcr.io/ahujasid/blender-mcp:latest
```

**Linux:**

```bash
mkdir -p /tmp/blender-mcp-shared
claude mcp add blender -- docker run -i --rm --network=host \
  -e BLENDER_HOST=localhost \
  -e TMPDIR=/tmp/blender-mcp-shared \
  -v /tmp/blender-mcp-shared:/tmp/blender-mcp-shared \
  ghcr.io/ahujasid/blender-mcp:latest
```
</details>

<details>
<summary><b>Cursor / VS Code / OpenCode</b></summary>

See [MCP Client Setup](#mcp-client-setup) below for per-client instructions.
</details>

**4. Install the Blender addon**

Mount your Blender addons folder into the container. Replace `4.2` with your Blender version:

```bash
# macOS
docker run --rm \
  -v "$HOME/Library/Application Support/Blender/4.2/scripts/addons:/addons" \
  ghcr.io/ahujasid/blender-mcp:latest install-addon --addons-dir /addons

# Linux
docker run --rm \
  -v "$HOME/.config/blender/4.2/scripts/addons:/addons" \
  ghcr.io/ahujasid/blender-mcp:latest install-addon --addons-dir /addons
```

```powershell
# Windows (PowerShell)
docker run --rm `
  -v "$env:APPDATA\Blender Foundation\Blender\4.2\scripts\addons:/addons" `
  ghcr.io/ahujasid/blender-mcp:latest install-addon --addons-dir /addons
```

The addon ships inside the image, so it matches the server **as long as you install it
from the same image reference you run**. If you later pull a newer image, reinstall the
addon from that image too.

Then in Blender: **Edit → Preferences → Add-ons** → enable **Interface: Blender MCP**.

**5. Connect**

In Blender's 3D viewport, press `N` → open the **BlenderMCP** tab → click **Connect to MCP server**. That's it — ask Claude to build something.

> **Note:** Only run **one** instance of the MCP server (either Cursor or Claude Desktop), not both.

---

## Table of Contents

- [Quickstart](#quickstart)
- [Features](#features)
- [Components](#components)
- [Installation](#installation)
  - [Prerequisites](#prerequisites)
  - [Why Docker is the standard method](#why-docker-is-the-standard-method)
  - [Platform differences](#platform-differences)
  - [Networking](#networking)
  - [Host file access](#host-file-access)
  - [Verifying the installation](#verifying-the-installation)
  - [Environment variables](#environment-variables)
- [Deprecated: installing with uvx](#deprecated-installing-with-uvx)
- [MCP Client Setup](#mcp-client-setup)
  - [Claude for Desktop](#claude-for-desktop)
  - [Cursor](#cursor)
  - [Visual Studio Code](#visual-studio-code)
  - [OpenCode](#opencode)
- [Installing the Blender Addon](#installing-the-blender-addon)
- [Upgrading (existing users)](#upgrading-existing-users)
- [Usage](#usage)
  - [Starting the Connection](#starting-the-connection)
  - [Using with Claude](#using-with-claude)
  - [Capabilities](#capabilities)
  - [Example Commands](#example-commands)
- [Persistent API Credentials](#persistent-api-credentials)
- [Troubleshooting](#troubleshooting)
- [Technical Details](#technical-details)
- [Limitations & Security Considerations](#limitations--security-considerations)
- [Telemetry Control](#telemetry-control)
- [Feedback](#feedback)
- [Contributing](#contributing)
- [Disclaimer](#disclaimer)
- [Star History](#star-history)

---

## Features

| | |
|---|---|
| **Two-way communication** | Connect Claude AI to Blender through a socket-based server |
| **Object manipulation** | Create, modify, and delete 3D objects in Blender |
| **Material control** | Apply and modify materials and colors |
| **Scene inspection** | Get detailed information about the current Blender scene |
| **Code execution** | Run arbitrary Python code in Blender from Claude |
| **Asset & model generation** | Poly Haven assets, Sketchfab models, and AI-generated 3D models via Hyper3D Rodin and Hunyuan3D |

## Components

The system consists of two main components:

1. **Blender Addon** (`addon.py`) — a Blender addon that creates a socket server within Blender to receive and execute commands
2. **MCP Server** (`src/blender_mcp/server.py`) — a Python server that implements the Model Context Protocol and connects to the Blender addon

---

## Installation

### Prerequisites

- **Blender** 3.0 or newer
- **Docker** — [Docker Desktop](https://www.docker.com/products/docker-desktop/) on macOS/Windows, or [Docker Engine](https://docs.docker.com/engine/install/) 20.10+ on Linux

No Python installation is required on the host. The image supplies its own interpreter.

### Why Docker is the standard method

The image fixes the Python interpreter and every dependency, so the server is identical on
every machine. That removes an entire category of reported problems: dependency build
failures on Windows, `ModuleNotFoundError` from mismatched `mcp` versions, conda/pyenv
interpreter conflicts, console encoding corruption, and `spawn uvx ENOENT` when a
GUI-launched client cannot see `~/.local/bin`.

It also keeps the addon and the server in lockstep, since both ship in the same image.

### Platform differences

Every example in this README is written in its **macOS** form. This table is the single
place that describes how to adapt it — the client sections below do not repeat it.

| | macOS | Linux | Windows |
|---|---|---|---|
| Networking | default | add `--network=host` and `-e BLENDER_HOST=localhost` | default |
| Shared directory | `-e TMPDIR=/tmp/blender-mcp-shared` and `-v /tmp/blender-mcp-shared:/tmp/blender-mcp-shared` | same as macOS | **omit** — not possible |
| File-based tools | work | work | unavailable |
| Non-1000 user id | n/a | add `--user $(id -u):$(id -g)` | n/a |

**Linux notes.** `--network=host` requires rootful Docker Engine. Under rootless Docker it
is namespaced and cannot reach the host's loopback, so Blender is unreachable. If your host
user id is not 1000, add `--user $(id -u):$(id -g)` so the container can write to the
directories you mount.

### Networking

Blender runs on your host, not in the container. The container connects out to it on
port 9876.

- **macOS / Windows (Docker Desktop):** works with no extra flags. `host.docker.internal`
  resolves to the host, and Docker Desktop proxies the connection so Blender's default
  `localhost` binding is reachable.
- **Linux (rootful Docker Engine):** use `--network=host` with `BLENDER_HOST=localhost`. The
  container then shares the host network namespace and reaches Blender's loopback socket
  directly. Do **not** reconfigure Blender to listen on `0.0.0.0` — that would expose the
  addon's code-execution socket to your whole network.

### Host file access

Some tools pass a *file path* between Blender and the server. Since the server runs in a
container, those paths only work if the directory exists at the **same absolute path** on
both sides. That is what these arguments do:

```
-e TMPDIR=/tmp/blender-mcp-shared
-v /tmp/blender-mcp-shared:/tmp/blender-mcp-shared
```

Create it once with `mkdir -p /tmp/blender-mcp-shared`. Affected tools:

- **`get_viewport_screenshot`** — Blender writes the image, the server reads it back.
  Without the shared directory it fails with `Screenshot file was not created`.
- **Hyper3D generation from local image paths** — the server opens the files you name, so
  they must be inside the shared directory. Generating from image *URLs* is unaffected.

> **Known limitation:** on Windows, host paths (`C:\...`) cannot be mapped to an identical
> container path, so the tools above are unavailable when running the server in Docker on
> Windows. Everything else works normally.

### Verifying the installation

```bash
docker run --rm ghcr.io/ahujasid/blender-mcp:latest --help
```

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `BLENDER_HOST` | `host.docker.internal` (in the image) | Host address for the Blender socket server |
| `BLENDER_PORT` | `9876` | Port for the Blender socket server |
| `TMPDIR` | `/tmp` | Directory used for screenshot hand-off; must be a shared mount |

---

## Deprecated: installing with uvx

> **Deprecated.** The `uvx blender-mcp` path still works and is still published to PyPI,
> but it is no longer the recommended installation and receives no new setup
> documentation. New installs should use Docker. Existing setups keep working; migrate
> when convenient.

<details>
<summary><b>Legacy uvx instructions</b></summary>

**Prerequisites:** Blender 3.0+, Python 3.10+, and the `uv` package manager.

**Installing uv**

```bash
# macOS
brew install uv

# Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

On Windows, add uv to the user path (restart Claude Desktop afterwards):

```powershell
$localBin = "$env:USERPROFILE\.local\bin"
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
[Environment]::SetEnvironmentVariable("Path", "$userPath;$localBin", "User")
```

On every OS, use uv's official installer — **not** `pip install uv`, which may not create
the `uvx` command and can hide uv inside an environment your client cannot see.

**Migrating to Docker**

Replace the `uvx` command in your client configuration with the Docker command shown in
[Quickstart](#quickstart). Your Blender addon and existing projects do not need to change.
If anything goes wrong, restoring the previous `uvx` configuration returns you to the old
behaviour.

### Make your client find uvx

MCP clients started from a GUI (Claude Desktop, Cursor, VS Code from the Dock/Start menu) do **not** inherit your terminal's PATH, so a bare `"command": "uvx"` can fail with **`spawn uvx ENOENT`** even though `uvx` works in your terminal. If that happens:

- Find uvx's full path — `which uvx` (macOS/Linux) or `where uvx` (Windows) — and use it as `"command"`, e.g. `/opt/homebrew/bin/uvx` or `C:\Users\<you>\.local\bin\uvx.exe`.
- On Windows you can instead wrap it: `"command": "cmd", "args": ["/c", "uvx", "blender-mcp"]`.
- After any PATH or config change, **fully quit and relaunch** the client (Windows: quit from the system tray, not just the window; macOS: <kbd>Cmd</kbd>+<kbd>Q</kbd>).

### Pin the Python version

*Avoid conda / pyenv / version conflicts.*

uv chooses which Python runs the server. On machines with conda (auto-activated base), pyenv, or asdf — or with a newer CPython release that some dependencies do not have wheels for yet — uv can grab an interpreter that makes installation fail. Pin Python 3.11 and prefer uv-managed interpreters to avoid using whatever is on your PATH:

```json
{
    "mcpServers": {
        "blender": {
            "command": "uvx",
            "args": ["--python", "3.11", "blender-mcp"],
            "env": { "UV_PYTHON_PREFERENCE": "only-managed" }
        }
    }
}
```

`--python 3.11` still satisfies this package's `requires-python >=3.10`, and `UV_PYTHON_PREFERENCE=only-managed` keeps uv from selecting conda, pyenv, asdf, or system Python first. (The repo's `.python-version` is only a hint for contributors and does **not** affect `uvx`.)

If a previous failed attempt keeps replaying after a fix, clear the cache:

```bash
uv cache clean blender-mcp && uvx --refresh blender-mcp
```

### Install without uv

On locked-down machines you can skip uvx entirely with [`pipx`](https://pipx.pypa.io), then point your client at the installed command:

```bash
pipx install blender-mcp
pipx ensurepath          # then restart your shell / client
```

Use the resulting absolute path as `"command"` (find it with `which blender-mcp` / `where blender-mcp`) and omit `args`.

When running outside Docker, `BLENDER_HOST` defaults to `localhost`.

</details>

---

## MCP Client Setup

All clients run the same image, with the same arguments. **Every configuration below is
written in its macOS form** — see [Platform differences](#platform-differences) for the one
table that describes how to adapt it for Linux and Windows.

On macOS and Linux, create the shared directory once:

```bash
mkdir -p /tmp/blender-mcp-shared
```

### Claude for Desktop

Go to **Claude → Settings → Developer → Edit Config → `claude_desktop_config.json`** and include the following:

```json
{
    "mcpServers": {
        "blender": {
            "command": "docker",
            "args": [
                "run", "-i", "--rm",
                "-e", "TMPDIR=/tmp/blender-mcp-shared",
                "-v", "/tmp/blender-mcp-shared:/tmp/blender-mcp-shared",
                "ghcr.io/ahujasid/blender-mcp:latest"
            ]
        }
    }
}
```

<details>
<summary><b>Claude Code</b></summary>

Use the Claude Code CLI to add the blender MCP server:

```bash
claude mcp add blender -- docker run -i --rm \
  -e TMPDIR=/tmp/blender-mcp-shared \
  -v /tmp/blender-mcp-shared:/tmp/blender-mcp-shared \
  ghcr.io/ahujasid/blender-mcp:latest
```
</details>

### Cursor

Go to **Settings → MCP** and paste the following:

- To use as a global server, use the *"add new global MCP server"* button and paste
- To use as a project-specific server, create `.cursor/mcp.json` in the root of the project and paste

```json
{
    "mcpServers": {
        "blender": {
            "command": "docker",
            "args": [
                "run", "-i", "--rm",
                "-e", "TMPDIR=/tmp/blender-mcp-shared",
                "-v", "/tmp/blender-mcp-shared:/tmp/blender-mcp-shared",
                "ghcr.io/ahujasid/blender-mcp:latest"
            ]
        }
    }
}
```

This is the macOS form. On Linux and Windows, adjust it as described in
[Platform differences](#platform-differences). No `cmd /c` wrapper is needed on Windows,
because `docker` resolves on the PATH that GUI applications inherit.

> **Note:** Only run **one** instance of the MCP server (either on Cursor or Claude Desktop), not both.

### Visual Studio Code

*Prerequisites*: Make sure you have [Visual Studio Code](https://code.visualstudio.com/) installed before proceeding.

Add the server to `mcp.json` (macOS form — see
[Platform differences](#platform-differences)):

```json
{
    "servers": {
        "blender-mcp": {
            "type": "stdio",
            "command": "docker",
            "args": [
                "run", "-i", "--rm",
                "-e", "TMPDIR=/tmp/blender-mcp-shared",
                "-v", "/tmp/blender-mcp-shared:/tmp/blender-mcp-shared",
                "ghcr.io/ahujasid/blender-mcp:latest"
            ]
        }
    }
}
```

### OpenCode

macOS form — see [Platform differences](#platform-differences) for Linux and Windows:

```json
{
  "mcp": {
    "blender-mcp": {
      "type": "local",
      "command": ["docker", "run", "-i", "--rm",
                  "-e", "TMPDIR=/tmp/blender-mcp-shared",
                  "-v", "/tmp/blender-mcp-shared:/tmp/blender-mcp-shared",
                  "ghcr.io/ahujasid/blender-mcp:latest"],
      "enabled": true
    }
  }
}
```

---

## Installing the Blender Addon

**1. Recommended** — mount your Blender addons folder into the container and run the
installer. Replace `4.2` with your Blender version:

```bash
# macOS
docker run --rm \
  -v "$HOME/Library/Application Support/Blender/4.2/scripts/addons:/addons" \
  ghcr.io/ahujasid/blender-mcp:latest install-addon --addons-dir /addons

# Linux
docker run --rm \
  -v "$HOME/.config/blender/4.2/scripts/addons:/addons" \
  ghcr.io/ahujasid/blender-mcp:latest install-addon --addons-dir /addons
```

```powershell
# Windows (PowerShell)
docker run --rm `
  -v "$env:APPDATA\Blender Foundation\Blender\4.2\scripts\addons:/addons" `
  ghcr.io/ahujasid/blender-mcp:latest install-addon --addons-dir /addons
```

This copies the addon into that folder as `blender_mcp.py`. It prints where it wrote to, and keeps a `.bak` of any file it replaces.

The addon ships inside the image, so it matches the server **as long as you install it
from the same image reference you run**. If you later pull a newer image, reinstall the
addon from that image too.

**2.** Open Blender

**3.** Go to **Edit → Preferences → Add-ons**

**4.** Enable **Interface: Blender MCP** (search "Blender MCP"). If it doesn't appear yet, click **Install…** and select the copied `blender_mcp.py` / `addon.py`, or restart Blender.

**5. Manual alternative** — if the command above can't find your Blender install, or you prefer doing it by hand: download `addon.py` from this repo → in Blender, **Edit → Preferences → Add-ons → Install…** → select the downloaded `addon.py` → enable it.

Then open the **BlenderMCP** tab in Blender's sidebar (press `N` in the 3D viewport) and click **Connect to MCP server**. See [Starting the Connection](#starting-the-connection) below.

## Upgrading (existing users)

> For newcomers, go straight to [Quickstart](#quickstart). For existing users, see below.

**1.** Pull the image:

```bash
docker pull ghcr.io/ahujasid/blender-mcp:latest
```

> If your client configuration pins a version tag rather than `:latest`, pull **that** tag
> here, install the addon from the same tag below, and update the tag in your client
> configuration together. Mixing a pinned client with a `:latest` addon pairs mismatched
> versions.

Then reinstall the addon from it, using the command for your platform from
[Installing the Blender Addon](#installing-the-blender-addon). On macOS, for example:

```bash
docker run --rm \
  -v "$HOME/Library/Application Support/Blender/4.2/scripts/addons:/addons" \
  ghcr.io/ahujasid/blender-mcp:latest install-addon --addons-dir /addons
```

**2.** In Blender: **Preferences → Add-ons** → disable and re-enable **Interface: Blender MCP** (or restart Blender), then click **Connect to MCP server** again.

**3.** Delete the MCP server from Claude and add it back again if the server package itself needs a refresh.

> **Note:** the MCP server never modifies your Blender addon files on its own. When it starts, it checks whether the installed addon is behind the bundled copy and logs how to update; `install-addon` is what actually writes, and it keeps a `.bak` of the file it replaces. Trajectory capture still works on older loaded addons via an `execute_code` fallback.

---

## Usage

### Starting the Connection

![BlenderMCP in the sidebar](assets/addon-instructions.png)

1. In Blender, go to the 3D View sidebar (press <kbd>N</kbd> if not visible)
2. Find the **BlenderMCP** tab
3. Turn on the checkboxes you'd like to use (see more under [Capabilities](#capabilities) below)
4. Click **Connect to Claude**
5. Keep your MCP client running — it launches the container for you. Do not run the `docker run` command yourself.

### Using with Claude

Once the config file has been set on Claude, and the addon is running on Blender, you will see a hammer icon with tools for the Blender MCP.

![BlenderMCP in the sidebar](assets/hammer-icon.png)

### Capabilities

- Get scene and object information
- Create, delete and modify shapes
- Apply or create materials for objects
- Execute any Python code in Blender
- Download the right models, assets and HDRIs through [Poly Haven](https://polyhaven.com/)
- Search and download models from [Sketchfab](https://sketchfab.com/)
- AI generated 3D models through [Hyper3D Rodin](https://hyper3d.ai/) and [Hunyuan3D](https://3d.hunyuan.tencent.com/)

### Example Commands

Here are some examples of what you can ask Claude to do:

| Prompt | Demo |
|---|---|
| *"Create a low poly scene in a dungeon, with a dragon guarding a pot of gold"* | [Watch](https://www.youtube.com/watch?v=DqgKuLYUv00) |
| *"Create a beach vibe using HDRIs, textures, and models like rocks and vegetation from Poly Haven"* | [Watch](https://www.youtube.com/watch?v=I29rn92gkC4) |
| Give a reference image, and create a Blender scene out of it | [Watch](https://www.youtube.com/watch?v=FDRb03XPiRo) |
| *"Get information about the current scene, and make a threejs sketch from it"* | [Watch](https://www.youtube.com/watch?v=jxbNI5L7AH8) |
| *"Generate a 3D model of a garden gnome through Hyper3D"* | |
| *"Make this car red and metallic"* | |
| *"Create a sphere and place it above the cube"* | |
| *"Make the lighting like a studio"* | |
| *"Point the camera at the scene, and make it isometric"* | |

---

## Persistent API Credentials

BlenderMCP supports persistent credentials via Blender Add-on Preferences:

**Edit → Preferences → Add-ons → Blender MCP**

You can store these values there so they survive Blender restarts:

- Sketchfab API Key
- Hyper3D API Key
- Hunyuan3D SecretId / SecretKey
- Hunyuan3D API URL

For headless setups or CI, credentials can also be injected by environment variables:

| Variable |
|---|
| `BLENDERMCP_SKETCHFAB_API_KEY` |
| `BLENDERMCP_HYPER3D_API_KEY` |
| `BLENDERMCP_HUNYUAN3D_SECRET_ID` |
| `BLENDERMCP_HUNYUAN3D_SECRET_KEY` |
| `BLENDERMCP_HUNYUAN3D_API_URL` |

---

## Troubleshooting

| Problem | Fix |
|---|---|
| **Connection issues** | Make sure the Blender addon server is running, and the MCP server is configured on Claude. **Do not** run the `docker run` command in the terminal yourself — your MCP client launches it. Sometimes the first command won't go through, but after that it starts working. |
| **Timeout errors** | Try simplifying your requests or breaking them into smaller steps. |
| **Poly Haven integration** | Claude is sometimes erratic with its behaviour. |
| **Have you tried turning it off and on again?** | If you're still having connection errors, try restarting both Claude and the Blender server. |

## Technical Details

### Communication Protocol

The system uses a simple JSON-based protocol over TCP sockets:

- **Commands** are sent as JSON objects with a `type` and optional `params`
- **Responses** are JSON objects with a `status` and `result` or `message`

## Limitations & Security Considerations

> **Warning:** The `execute_blender_code` tool allows running arbitrary Python code in Blender, which can be powerful but potentially dangerous. Use with caution in production environments. **ALWAYS save your work before using it.**

- Poly Haven requires downloading models, textures, and HDRI images. If you do not want to use it, please turn it off in the checkbox in Blender.
- Complex operations might need to be broken down into smaller steps.

## Telemetry Control

BlenderMCP collects anonymous usage data to help improve the tool. Telemetry consent is **on by default**, and you can turn it off in two ways:

**1. In Blender** — go to **Edit → Preferences → Add-ons → Blender MCP** and uncheck the telemetry consent checkbox.

- With consent (checked, the default): view the TnC for more details on data collected.

**2. Environment Variable** — completely disable all telemetry by adding these two
arguments to whichever configuration you already use:

```
"-e", "DISABLE_TELEMETRY=true",
```

They go in the client configuration, not a terminal command: your MCP client launches its
own container, so running `docker run` by hand only affects that one throwaway process.
Place them before the image name, for example:

```
"args": [
    "run", "-i", "--rm",
    "-e", "DISABLE_TELEMETRY=true",
    "-e", "TMPDIR=/tmp/blender-mcp-shared",
    "-v", "/tmp/blender-mcp-shared:/tmp/blender-mcp-shared",
    "ghcr.io/ahujasid/blender-mcp:latest"
]
```

Telemetry data is not linked to your name or account. It may be used to improve BlenderMCP, for research, and to train AI models.

Full detail on what is collected, and the license you grant by leaving telemetry on, is in [TERMS_AND_CONDITIONS.md](TERMS_AND_CONDITIONS.md).

---

## Feedback

We are actively looking for feedback on Blender MCP. If you have thoughts, share them [here](https://bit.ly/blender-mcp-form).

If you have more detailed feedback, you can schedule a call with us [here](https://bit.ly/blender-mcp-call) — we will credit you in the project.

### Join the Community

Give feedback, get inspired, and build on top of the MCP: [**Discord**](https://discord.gg/SNqPn4TcKQ)

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Disclaimer

This is a third-party integration and not made by Blender. Made by [Siddharth](https://x.com/sidahuj).

---

## Star History

<a href="https://star-history.com/#ahujasid/blender-mcp&Date">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=ahujasid/blender-mcp&type=Date&theme=dark" />
    <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=ahujasid/blender-mcp&type=Date" />
    <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=ahujasid/blender-mcp&type=Date" width="600" />
  </picture>
</a>

<div align="center">

**If Blender MCP is useful to you, consider starring the repo**

</div>
