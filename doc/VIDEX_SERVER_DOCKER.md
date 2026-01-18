## VIDEX-Server Docker Image Description

The latest public image is:

- `kangrongme/videx-server:0.2.0` (Docker Hub)

Make sure your environment can reach Docker Hub. If Docker Hub is not accessible but GHCR is, use:

- `ghcr.io/kr11/videx-server:0.2.0`

This image supports two entrypoint modes:

- `server` (default): start the VIDEX server
- `sync`: run a one-shot workflow to collect metadata from `--target`, then add metadata into `videx-server`, and create virtual tables in `--videx`

> Recommendation: prefer using a routable IP address (your host/server IP) instead of `localhost/127.0.0.1`, 
> to make sure `videx-server` (running in a container) can be reached by `videx-sync` and MariaDB-VIDEX (including `videx-plugin`).  
> This is especially important because MariaDB-VIDEX also needs to reach `videx-server`, e.g.:
>
> `SET SESSION VIDEX_SERVER_IP=<VIDEX_SERVER_IP>:<VIDEX_SERVER_PORT>;`

---

## Build image

Build locally from this repo and tag it as `videx-server:0.2.0`:

```bash
docker build -f build/Dockerfile.videxserver -t videx-server:0.2.0 .
```

---

## Quick start

Suppose your machine/server IP is `203.0.113.42` (example only).

### 1) Start the videx-server

Expose container port `5001` to a host port (choose any free host port, like 5001):

```bash
docker run -d --name videx-server \
  -p 5001:5001 \
  kangrongme/videx-server:0.2.0
```

Then open:

- `http://203.0.113.42:5001`
- `http://localhost:5001` (only if you are on the same machine)

---

### 2) Run sync (one-shot) against MariaDB (recommended: use host/server IP)

`sync` connects to `--target` (your MariaDB), collects metadata, writes metadata into `videx-server`, and creates virtual tables in `--videx`.

#### Command template

```bash
docker run --rm --name videx-sync \
  kangrongme/videx-server:0.2.0 sync \
  --target <TARGET_HOST>:<TARGET_PORT>:<TARGET_DB>:<TARGET_USER>:<TARGET_PASS> \
  [--videx <VIDEX_HOST>:<VIDEX_PORT>:<VIDEX_DB>:<VIDEX_USER>:<VIDEX_PASS>] \
  [--videx_server <VIDEX_SERVER_HOST>:<VIDEX_SERVER_PORT>]
```

#### Example (fake IP shown)

Suppose:

- Your machine/server IP is `203.0.113.42` (example only)
- MariaDB is reachable at `203.0.113.42:15508`
- Source database is `tpch_tiny`
- User/password: `videx` / `password`
- `videx-server` is reachable at `203.0.113.42:5001`

Run:

```bash
docker run --rm --name videx-sync \
  kangrongme/videx-server:0.2.0 sync \
  --target 203.0.113.42:15508:tpch_tiny:videx:password \
  --videx 203.0.113.42:15508:videx_tpch_tiny:videx:password \
  --videx_server 203.0.113.42:5001
```

#### Notes

1. If `--videx` is not specified, a default database `videx_{TARGET_DB}` will be created in `--target`.
2. If your videx-server is not the default `203.0.113.42:5001` , pass:
   - `--videx_server <VIDEX_SERVER_HOST>:<VIDEX_SERVER_PORT>`
3. Because MariaDB-VIDEX needs to call back into `videx-server`, you should configure a reachable server address, for example:
   ```sql
   SET SESSION VIDEX_SERVER_IP=<VIDEX_SERVER_IP>:<VIDEX_SERVER_PORT>;
   ```
   This is another reason why using a routable IP (not `localhost`) is recommended.

---

## FAQ

### Q1: I used `localhost` / `127.0.0.1` in `--target` and it failed. Why?

Inside a container, `localhost/127.0.0.1` refers to the container itself. If MariaDB runs on the Docker host (or elsewhere), the container cannot reach it via `localhost`.

**Linux (Docker Engine) quick fix: use `host.docker.internal` via `--add-host`**

```bash
docker run --rm --name videx-sync \
  --add-host=host.docker.internal:host-gateway \
  kangrongme/videx-server:0.2.0 sync \
  --target host.docker.internal:<PORT>:<DB>:<USER>:<PASS> \
  --videx host.docker.internal:<PORT>:<VIDEX_DB>:<VIDEX_USER>:<VIDEX_PASS> \
  --videx_server host.docker.internal:<VIDEX_SERVER_PORT>
```

However, you must ensure that MariaDB-VIDEX can still reach `videx-server`; 
things get tricky if MariaDB-VIDEX itself is also running inside a container. 
**In that case, using a routable IP is the most recommended way to ensure reachability.**
