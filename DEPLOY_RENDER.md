# Deploying Echo to Render

Render builds the `Dockerfile` at the repo root itself (it does not use any
image built locally) - it serves the frontend and the API from one FastAPI
process: the built frontend at `/`, the API under `/api`.

## 1. Push the code first

Render deploys from a GitHub branch. Make sure `main` is pushed before
starting the dashboard steps below.

## 2. Create the service

1. Render dashboard -> **New** -> **Web Service**.
2. Connect the `echo` GitHub repository, branch **main**.
3. Render should detect `render.yaml` at the repo root and offer to create
   the service from it ("Infrastructure as code" / Blueprint). Accept that -
   it sets the runtime to Docker, the health check path, and the persistent
   disk automatically. If it doesn't detect it, configure manually:
   - **Runtime**: Docker
   - **Dockerfile Path**: `./Dockerfile`
   - **Docker Build Context Directory**: `.`
   - **Health Check Path**: `/api/health`
4. **Instance type**: see the memory-test result below for the recommendation.
5. **Persistent Disk**: add one disk named `echo-data`, mounted at
   `/var/data`, size 1 GB (the sqlite file is small; this leaves headroom
   for years of attempt history). Without this, the database resets on
   every deploy/restart, since a plain Docker container's filesystem is
   wiped along with it.

## 3. Environment variables

Enter these in the service's **Environment** tab (`render.yaml` sets the
first two automatically if Render used the Blueprint; add them manually
otherwise):

| Key | Value | Why |
|---|---|---|
| `DATABASE_PATH` | `/var/data/speechpal.db` | Points sqlite at the persistent disk instead of the container's ephemeral filesystem (backend/db.py). |
| `DEBUG_KEEP_AUDIO` | `0` | Keeps the debug audio-capture path off in production (it's off by default in code either way - this just makes it explicit and un-forgettable). |

Do **not** set `USE_REAL_SCORER` or `USE_PHASE3_SCORER` - the app already
defaults to the Phase 3 scorer (`USE_PHASE3_SCORER=1`), which is what's
frozen and evaluated in `RESULTS.md`. `PORT` is provided by Render
automatically; the Dockerfile's `CMD` already binds to it.

No API keys, secrets, or external service credentials are needed - the
wav2vec2 model is baked into the image at build time (see the Dockerfile),
and everything else is self-contained.

## 4. First deploy

Render will build the image (expect the first build to take a while - the
frontend build, Python deps including torch, and the ~1.2GB model download
all happen during `docker build`, per the Dockerfile). The service won't
report healthy until:

1. The container starts and binds to `$PORT`.
2. The wav2vec2 model finishes loading and runs one dummy inference in the
   background (backend/main.py's lifespan warm-up) - `/api/health` returns
   HTTP 503 `{"status": "starting"}` until this finishes, then 200
   `{"status": "ok"}`. Watch the logs for `Warm-up complete - scorer is
   ready to serve requests.`

Render's own health check polls `/api/health` and won't mark the deploy
live until it sees a 200, so this is automatic - no action needed, just
expect a delay between "container running" and "service live" on first
boot.

## 5. Verify after deploy

- Open the service URL - the app itself should load at `/`.
- `curl https://<your-service>.onrender.com/api/health` should return
  `{"status":"ok","real_scorer":false}` once warm-up finishes.
- Log in with a fresh name and confirm a level loads and a recording scores
  (try it from both a Chromium browser and Safari - see the root
  README/RESULTS.md for the Safari audio/mp4 fix this deploy includes).
- The database starts empty on first deploy - that's expected per the
  persistent disk being newly created.

## 6. Redeploys later

Because `DATABASE_PATH` points at the persistent disk (not the container's
own filesystem), redeploys and restarts keep all existing users/attempts.
Only deleting the disk itself resets the data.
