"""Run a generated Linux command inside a throw-away Docker container.

Never run generated commands on the real machine. The container has:
  - no network
  - a read-only root file system (only a fresh tmpfs work folder is writable)
  - a non-root user, no Linux capabilities, no privilege escalation
  - CPU, memory and process limits, and a 10 second timeout
and is removed after every run.
"""

import shutil
import subprocess
from dataclasses import dataclass
from functools import cache
from pathlib import Path

IMAGE = "nl-cli-sandbox"
DOCKERFILE_DIR = Path(__file__).parent / "sandbox"
TIMEOUT_SECONDS = 10
MAX_OUTPUT = 2000

# copy the sample files into the tmpfs, then run the user command with a timeout
_RUNNER = 'cp -a /fixtures/. "$HOME/work" && cd "$HOME/work" && timeout {t} bash -c "$USER_CMD"'


@dataclass
class SandboxResult:
    exit_code: int | None   # None = could not run at all
    output: str

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


def docker_available() -> bool:
    if not shutil.which("docker"):
        return False
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


@cache  # "docker image inspect" takes seconds on Docker Desktop, check it once per process
def ensure_image() -> None:
    have = subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True).returncode == 0
    if not have:
        subprocess.run(["docker", "build", "-t", IMAGE, str(DOCKERFILE_DIR)], check=True, capture_output=True)


def run(command: str) -> SandboxResult:
    try:
        ensure_image()
    except FileNotFoundError:
        return SandboxResult(None, "Docker is not installed.")
    except subprocess.CalledProcessError as e:
        return SandboxResult(None, f"Could not build the sandbox image:\n{e.stderr.decode(errors='replace')[-MAX_OUTPUT:]}")

    docker_cmd = [
        "docker", "run", "--rm",
        "--network", "none",
        "--read-only",
        "--tmpfs", "/tmp:rw,size=16m",
        "--tmpfs", "/home/sandbox/work:rw,size=32m,uid=1000,gid=1000",
        "--memory", "256m", "--cpus", "1", "--pids-limit", "128",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "-e", f"USER_CMD={command}",
        IMAGE, "bash", "-c", _RUNNER.format(t=TIMEOUT_SECONDS),
    ]
    try:
        proc = subprocess.run(docker_cmd, capture_output=True, timeout=TIMEOUT_SECONDS + 30)
    except subprocess.TimeoutExpired:
        return SandboxResult(None, "Timed out.")
    output = (proc.stdout + proc.stderr).decode("utf-8", errors="replace").strip()
    if proc.returncode == 125 and "docker" in output.lower():
        # 125 = docker itself failed (daemon down, bad flag), the command never ran
        ensure_image.cache_clear()
        return SandboxResult(None, f"Docker could not start the sandbox - is Docker Desktop running?\n{output[:MAX_OUTPUT]}")
    if proc.returncode == 124:
        output += "\n[stopped after timeout]"
    return SandboxResult(proc.returncode, output[:MAX_OUTPUT])
