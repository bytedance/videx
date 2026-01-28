"""
VIDEX container entrypoint.

This entrypoint provides two modes:
- `server`: start the long-running VIDEX stats server (default)
- `sync`:   run the one-shot sync/env build script and exit

Design notes:
- Keep argument handling minimal.
- Do not rewrite user arguments.
- Best-effort warnings are emitted for common container networking pitfalls
  (e.g. using localhost/127.0.0.1 in --target inside a container).
"""

from __future__ import annotations

import os
import sys
import subprocess
from typing import List, Optional, Tuple

LOCALHOST_NAMES = {"127.0.0.1", "localhost", "::1"}


def _in_container_best_effort() -> bool:
    """
    Best-effort heuristics to detect container environment.
    Used only for warnings (never for rewriting args or failing).
    """
    explicit = os.environ.get("VIDEX_CONTAINER")
    if explicit and explicit.strip().lower() not in {"0", "false", "no"}:
        return True

    if os.path.exists("/.dockerenv"):
        return True

    if os.environ.get("container"):
        return True

    try:
        with open("/proc/1/cgroup", "rt", encoding="utf-8") as f:
            c = f.read()
        hints = ("docker", "containerd", "kubepods", "podman")
        return any(h in c for h in hints)
    except OSError:
        return False


def _usage() -> str:
    return (
        "Usage:\n"
        "  <image> [server]\n"
        "  <image> sync --target HOST:PORT:DB:USER:PASS [--videx ...] [other args]\n"
        "\n"
        "Commands:\n"
        "  server   Start VIDEX server (default).\n"
        "  sync     Run one-shot scripts to collect metadata from --target, then add metadata into videx-server, and create virtual tables in --videx.\n"
        "\n"
        "Notes:\n"
        "  In a container, 127.0.0.1/localhost refers to the container itself.\n"
        "  See doc/VIDEX_SERVER_DOCKER.md for Docker networking tips.\n"
    )


def _extract_flag_value(argv: List[str], name: str) -> Tuple[Optional[str], bool]:
    """
    Extract the value of a CLI flag from argv, supporting:
      --name value
      --name=value

    Returns (value, present):
      - present=False => flag not present
      - present=True and value=None => flag present but missing value
    """
    for i, tok in enumerate(argv):
        if tok == name:
            if i + 1 >= len(argv) or argv[i + 1].startswith("--"):
                return None, True
            return argv[i + 1], True
        if tok.startswith(name + "="):
            return tok.split("=", 1)[1], True
    return None, False


def _parse_target_host(target: str) -> Optional[str]:
    """
    Parse host from a connection string of form:
      host:port:db:user:password

    We only need host for warnings, so do not over-validate.
    If format is unexpected, return None.
    """
    if not target or ":" not in target:
        return None
    host = target.split(":", 1)[0].strip()
    return host or None


def _maybe_warn_localhost_target(argv: List[str]) -> None:
    """
    Print best-effort warnings about using localhost/127.0.0.1 inside containers.
    No rewriting; no hard failure.
    """
    target, present = _extract_flag_value(argv, "--target")

    if not present:
        sys.stderr.write(
            "Warning: 'sync' usually needs --target HOST:PORT:DB:USER:PASS.\n"
            "         The sync script will likely fail without it.\n\n"
        )
        return

    if target is None:
        sys.stderr.write(
            "Warning: '--target' flag is present but has no value.\n"
            "         The sync script will likely fail. Usage:\n\n"
            f"{_usage()}\n"
        )
        return

    host = _parse_target_host(target)
    if not host or host not in LOCALHOST_NAMES:
        return

    if not _in_container_best_effort():
        return

    sys.stderr.write(
        "Warning: You may be running in a container, but the `--target` parameter is configured with 127.0.0.1/localhost.\n"
        "         In a container, localhost usually refers to the container itself.\n"
        "         If your MariaDB/VIDEX runs on the host machine, this may fail.\n\n"
        "Suggestions:\n"
        "  - Docker Desktop (Mac/Windows): try host.docker.internal in --target.\n"
        "  - Linux Docker Engine: add this when running the container:\n"
        "      --add-host=host.docker.internal:host-gateway\n"
        "    then use host.docker.internal in --target.\n"
        "  - If DB runs in the same container / same network namespace, localhost can be correct.\n\n"
    )


def _run_module(module: str, argv: List[str]) -> int:
    cmd = [sys.executable, "-m", module] + argv
    return subprocess.call(cmd)


def _run_server(argv: List[str]) -> int:
    # Runs: python -m sub_platforms.sql_opt.videx.scripts.start_videx_server ...
    return _run_module("sub_platforms.sql_opt.videx.scripts.start_videx_server", argv)


def _run_sync(argv: List[str]) -> int:
    # Runs: python -m sub_platforms.sql_opt.videx.scripts.videx_build_env ...
    return _run_module("sub_platforms.sql_opt.videx.scripts.videx_build_env", argv)


def main() -> int:
    if len(sys.argv) <= 1:
        return _run_server([])

    subcmd = sys.argv[1]
    argv = sys.argv[2:]

    if subcmd in ("-h", "--help", "help"):
        sys.stdout.write(_usage())
        return 0

    if subcmd == "server":
        return _run_server(argv)

    if subcmd == "sync":
        _maybe_warn_localhost_target(argv)
        return _run_sync(argv)

    # Convenience: if user passes flags without 'server', treat as server args.
    if subcmd.startswith("-"):
        return _run_server([subcmd] + argv)

    sys.stderr.write(f"Error: unknown command '{subcmd}'.\n\n{_usage()}\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())