"""
Copyright (c) 2024 Bytedance Ltd. and/or its affiliates
SPDX-License-Identifier: MIT

Health check for the VIDEX server, intended for container HEALTHCHECK,
Docker Compose `condition: service_healthy`, and Kubernetes probes.

Exit code 0 means healthy, 1 means unhealthy, which is what Docker expects.

Uses only the standard library, so it works even in a slim image without
curl and does not depend on `requests` being importable.

Examples:
    python -m sub_platforms.sql_opt.videx.scripts.videx_healthcheck
    python -m sub_platforms.sql_opt.videx.scripts.videx_healthcheck --port 5001 --timeout 5
"""
import argparse
import json
import sys
import urllib.error
import urllib.request

DEFAULT_PORT = 5001
DEFAULT_HOST = "127.0.0.1"
DEFAULT_TIMEOUT = 5.0
DEFAULT_PATH = "/health"

EXIT_HEALTHY = 0
EXIT_UNHEALTHY = 1


def check(host: str, port: int, timeout: float, path: str) -> int:
    url = f"http://{host}:{port}{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read(4096)
            if resp.status != 200:
                print(f"unhealthy: {url} returned HTTP {resp.status}", file=sys.stderr)
                return EXIT_UNHEALTHY
    except urllib.error.HTTPError as e:
        print(f"unhealthy: {url} returned HTTP {e.code}", file=sys.stderr)
        return EXIT_UNHEALTHY
    except urllib.error.URLError as e:
        print(f"unhealthy: cannot reach {url}: {e.reason}", file=sys.stderr)
        return EXIT_UNHEALTHY
    except OSError as e:
        print(f"unhealthy: cannot reach {url}: {e}", file=sys.stderr)
        return EXIT_UNHEALTHY

    # The server answers with an application-level code inside the payload, so a
    # 200 alone is not sufficient; treat a non-200 payload code as unhealthy.
    try:
        payload = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        print(f"unhealthy: {url} returned a non-JSON body: {e}", file=sys.stderr)
        return EXIT_UNHEALTHY

    code = payload.get("code")
    if code != 200:
        print(f"unhealthy: {url} reported code={code} "
              f"message={payload.get('message')!r}", file=sys.stderr)
        return EXIT_UNHEALTHY

    return EXIT_HEALTHY


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check whether the VIDEX server is healthy.")
    parser.add_argument("--host", type=str, default=DEFAULT_HOST,
                        help=f"Host to probe. Default: {DEFAULT_HOST}")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"Port the VIDEX server listens on. Default: {DEFAULT_PORT}")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                        help=f"Request timeout in seconds. Default: {DEFAULT_TIMEOUT}")
    parser.add_argument("--path", type=str, default=DEFAULT_PATH,
                        help=f"Health endpoint path. Default: {DEFAULT_PATH}")
    args = parser.parse_args(argv)
    return check(host=args.host, port=args.port, timeout=args.timeout, path=args.path)


if __name__ == "__main__":
    raise SystemExit(main())
