# Phase 0 Starter Checklist — Azureus

> Concrete, ordered actions to take the project from "planned" to "Day 1 of building." Estimated total time: 4 working days.
>
> **Do these in order.** Each item assumes the previous ones are done. If a step fails, fix it before moving on — accumulating skipped setup is the #1 way Phase 0 slides into Phase 1.
>
> Mark items off as you go (`- [x]` instead of `- [ ]`). Commit this file to the repo so progress is visible.

---

## Day 1 — Accounts, Repo, Local Toolchain

### Pre-flight (do this *before* you sit down to code)

- [ ] **Verify Bloomberg lab access for next 8 weeks.** Check the university lab schedule for closures during Phase 5 dates (~Days 45–55 from start). If lab will be closed, flag it now so we can reorder.
- [ ] **Verify your DigitalOcean GitHub Student Pack credit is active.** Log in to DO, check the credit balance. Should be ~$200. If expired or already used, plan for ~$30/month out of pocket from Day 1.
- [ ] **Verify domain DNS access.** Log in to wherever you bought `azureus.tech`. Make sure you can edit A records. We'll need this on Day 3.
- [ ] **Read `docs/ARCHITECTURE.md` end-to-end one more time.** Yes, even though you wrote it. Reading the final assembled document is different from incremental confirmation.

### Repo creation

- [ ] **Create the GitHub repo:** `azureus` (or `azureus-platform`). Public. MIT license selected at creation. Add a basic README placeholder. Initialize with `.gitignore` for Python.
- [ ] **Clone locally.** Verify `git remote -v` shows the right URL.
- [ ] **Commit `docs/ARCHITECTURE.md`** (the document you just downloaded). First real commit. Message: `docs: add architecture document v1.0`.
- [ ] **Commit `CLAUDE.md`** at repo root. Message: `chore: add Claude Code conventions`.
- [ ] **Commit this checklist** as `docs/PHASE_0_CHECKLIST.md`. Message: `docs: add Phase 0 starter checklist`.

### Local toolchain

- [ ] **Python 3.11 installed.** Verify: `python3 --version`. If on M2 Mac with Homebrew, `brew install python@3.11`.
- [ ] **uv installed** (modern Python package manager, faster than pip). `curl -LsSf https://astral.sh/uv/install.sh | sh`. Verify: `uv --version`.
- [ ] **Node 20+ and pnpm installed.** `brew install node pnpm` or via Volta. Verify: `node --version && pnpm --version`.
- [ ] **Docker Desktop installed and running.** Verify: `docker --version && docker compose version`. Make sure Docker Desktop is allocated at least 4GB RAM in preferences.
- [ ] **VS Code (or your editor of choice) with extensions:**
  - Python (Microsoft)
  - Pylance
  - Ruff
  - ESLint
  - Prettier
  - Tailwind CSS IntelliSense
  - Docker
  - GitLens
- [ ] **`gh` CLI installed and authenticated.** `brew install gh && gh auth login`. Will save you a lot of typing later.

### First real PR

- [ ] **Create `pyproject.toml`** at repo root with project metadata, Python version requirement, and empty dependency list. Use `uv init` to scaffold.
- [ ] **Create `.gitignore`** with comprehensive Python + Node + Docker + IDE patterns. Include `data/bloomberg/`, `.env`, `.env.production`, `*.db`, `mlflow_artifacts/`.
- [ ] **Create `.env.example`** at repo root with placeholder values for all env vars documented in `ARCHITECTURE.md` Section 7.3.
- [ ] **Open PR #1:** "chore: project scaffolding." Self-review. Squash-merge.
- [ ] **Tag `v0.0.1-scaffold`** on the merged commit. `git tag v0.0.1-scaffold && git push --tags`.

**End-of-Day-1 self-check:** Repo exists, public, MIT-licensed. ARCHITECTURE.md and CLAUDE.md are in it. You can clone fresh and `uv` and `pnpm` work. PR #1 is merged. First tag is pushed.

---

## Day 2 — Project Skeleton, CI, Local Compose

### Python package skeleton

- [ ] **Create directory structure** matching `CLAUDE.md` file layout. Empty `__init__.py` files where needed:
  - `azureus/`, `azureus/data/`, `azureus/features/`, `azureus/models/`, `azureus/strategies/`, `azureus/backtesting/`, `azureus/api/`, `azureus/worker/`, `azureus/pipelines/`, `azureus/utils/`
- [ ] **Configure `pyproject.toml`:**
  - Project name `azureus`, version `0.0.1`
  - Python >= 3.11
  - `[tool.ruff]` section with line-length 100, target-version py311, enabled rules (E, F, I, N, UP, B, A, C4, PT, SIM, ARG)
  - `[tool.mypy]` section with strict mode on `azureus/` package
  - `[tool.pytest.ini_options]` section pointing to `tests/`
- [ ] **Install initial dependencies:**
  ```
  uv add fastapi uvicorn sqlalchemy alembic asyncpg psycopg redis rq pydantic pydantic-settings pandera pandas numpy
  uv add --dev ruff mypy pytest pytest-asyncio pytest-cov httpx
  ```
- [ ] **Create a stub `azureus/__init__.py`** with `__version__ = "0.0.1"`.
- [ ] **Verify `uv run python -c "import azureus; print(azureus.__version__)"` works.**

### Frontend skeleton

- [ ] **Create frontend with Vite.** From repo root: `pnpm create vite frontend --template react-ts`. Then `cd frontend && pnpm install`.
- [ ] **Install frontend dependencies:**
  ```
  cd frontend
  pnpm add @tanstack/react-query @tanstack/react-router zustand
  pnpm add -D @types/node tailwindcss postcss autoprefixer eslint prettier
  ```
- [ ] **Initialize Tailwind:** `pnpm dlx tailwindcss init -p`. Configure `tailwind.config.js` content paths.
- [ ] **Install shadcn/ui:** `pnpm dlx shadcn@latest init`. Choose defaults; accept the New York style and Slate base color.
- [ ] **Verify dev server runs:** `pnpm dev`, open `localhost:5173`, see the Vite default page.
- [ ] **Replace App.tsx** with a minimal "Azureus — Coming Soon" placeholder. Style with Tailwind. Add Inter font via Google Fonts in `index.html`.

### Pre-commit hooks

- [ ] **Install pre-commit:** `uv tool install pre-commit` or `pip install pre-commit --user`.
- [ ] **Create `.pre-commit-config.yaml`** with hooks for ruff (format + check), mypy (fast mode), prettier, eslint.
- [ ] **Run `pre-commit install`** in the repo. Verify hooks fire on a dummy commit.

### GitHub Actions: CI

- [ ] **Create `.github/workflows/ci.yml`** with two jobs: `python-ci` and `frontend-ci`.
  - `python-ci`: checkout, set up uv, install, run ruff check, run ruff format check, run mypy on `azureus/`, run pytest with empty test placeholder
  - `frontend-ci`: checkout, set up pnpm, install, run lint, run typecheck (`pnpm tsc --noEmit`), build
- [ ] **Add a placeholder test:** `tests/test_smoke.py` with `def test_imports(): import azureus; assert azureus.__version__`.
- [ ] **Open PR #2:** "ci: initial CI pipeline." Verify CI runs and passes in GitHub Actions UI before merging. Squash-merge.
- [ ] **Add CI badge to README.md.**

### Docker Compose: local backend services only

- [ ] **Create `services/postgres/Dockerfile`** that extends `timescale/timescaledb:latest-pg16`.
- [ ] **Create `docker-compose.yml`** with services: `postgres`, `redis`. Use named volumes. Expose ports locally (5432, 6379) for direct access.
- [ ] **Create `docker-compose.override.yml`** (gitignored if needed, otherwise committed with local-only adjustments).
- [ ] **Start services:** `docker compose up -d`. Verify with `docker compose ps` that both are healthy.
- [ ] **Connect to Postgres locally** with `psql` or a GUI tool. Verify it's reachable on `localhost:5432`.
- [ ] **Open PR #3:** "feat: add Postgres + Redis local compose." Squash-merge.

**End-of-Day-2 self-check:** Project skeleton is committed. CI is green on every push. Local Docker Compose brings up Postgres + Redis. Frontend dev server shows a placeholder page. Pre-commit hooks block bad commits.

---

## ⏸ Days 3–4 deferred (2026-05-12)

Azure for Students region policy blocked VM provisioning in every region attempted (Southeast Asia, plus a second region; East US 2 not yet retried). Days 3–4 work is **paused, not cancelled** — the items below remain Phase 0 acceptance criteria and must be completed before the `v0.1.0-foundation` tag and Phase 0 sign-off. Local development continues into Phase 1; production deploy reopens once a cloud provider is selected (likely fallback: DigitalOcean droplet per the original plan, restoring `docs/ARCHITECTURE.md` §7 to its pre-Azure wording).

When you re-open this section, also revisit `CLAUDE.md` Stack table → `Deployment` row.

---

## Day 3 — Droplet, DNS, TLS, First Deployment

### Azure VM

- [ ] **Sign in to Azure Portal** at https://portal.azure.com using the Microsoft account registered for Azure for Students.
- [ ] **Create the VM** (Create a resource → Virtual machine → Create). Basics tab:
  - **Subscription:** Azure for Students
  - **Resource group:** Create new → `azureus-rg`
  - **Virtual machine name:** `azureus-prod`
  - **Region:** `(Asia Pacific) Southeast Asia` (Singapore — closest to HK)
  - **Availability options:** No infrastructure redundancy required
  - **Security type:** Standard
  - **Image:** `Ubuntu Server 24.04 LTS - x64 Gen2`
  - **VM architecture:** x64
  - **Size:** click "See all sizes", search `B1s`, select `Standard_B1s` (1 vCPU, 1 GiB RAM — free for 12 months under Azure for Students)
  - **Authentication type:** SSH public key
  - **Username:** `deploy`
  - **SSH public key source:** Use existing public key
  - **SSH public key:** paste the contents of `~/.ssh/id_ed25519.pub` (if it doesn't exist, run `ssh-keygen -t ed25519 -C "yelamanvalikhanovich@gmail.com"` first, accept defaults, then `cat ~/.ssh/id_ed25519.pub`)
  - **Public inbound ports:** Allow selected ports → check SSH (22), HTTP (80), HTTPS (443)
- [ ] **Disks tab:** OS disk type `Standard SSD (LRS)`, size 30 GiB (default). Defaults elsewhere.
- [ ] **Networking / Management / Monitoring / Advanced / Tags:** defaults are fine.
- [ ] **Review + create → Create.** Provisioning takes ~2 minutes.
- [ ] **Note the public IP** from the VM Overview page. Save it somewhere accessible (and tell me — I need it for DNS + deploy workflow).
- [ ] **SSH to the VM:** `ssh deploy@<public-ip>`. Accept the host key fingerprint on first connect.
- [ ] **Install Docker on the VM:**
  ```
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker deploy
  exit
  ```
  Reconnect (`ssh deploy@<public-ip>`) so the group change takes effect. Verify: `docker --version && docker compose version`.
- [ ] **Host firewall** (defense in depth on top of Azure NSG): `sudo ufw allow 22 && sudo ufw allow 80 && sudo ufw allow 443 && sudo ufw enable`.

### DNS (at get.tech)

- [ ] **Log in to get.tech** → My Domains → `azureus.tech` → Manage DNS / DNS Records.
- [ ] **Add an A record for apex:** Type `A`, Host `@` (or blank), Value `<VM public IP>`, TTL 300.
- [ ] **Add an A record for www:** Type `A`, Host `www`, Value `<VM public IP>`, TTL 300.
- [ ] **Verify propagation:** `dig azureus.tech +short` and `dig www.azureus.tech +short` from your laptop. Should print the VM IP. Allow 5–60 min.

### Caddy + initial production compose

- [ ] **Create `services/caddy/Caddyfile`** with `azureus.tech` block. Initially just serves a static file (we'll add reverse proxy later). Caddy auto-issues TLS.
- [ ] **Create `services/caddy/static/index.html`** with a placeholder "Azureus — Coming Soon" page.
- [ ] **Create `docker-compose.prod.yml`** with the `caddy` service. Mount `services/caddy/Caddyfile` and `services/caddy/static/`. Expose 80 and 443.
- [ ] **Create `/etc/azureus/.env.production` on the droplet** with placeholder values. `sudo mkdir /etc/azureus && sudo chown deploy:deploy /etc/azureus`. Set chmod 600 on the file.
- [ ] **Clone the repo to the droplet:** `git clone` into `/home/deploy/azureus`.
- [ ] **First manual deploy:** SSH to droplet, `cd /home/deploy/azureus`, `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d caddy`.
- [ ] **Verify HTTPS:** visit `https://azureus.tech` from your browser. Should see the "Coming Soon" page with a valid TLS certificate. **This is your first deployment.** Take a screenshot.

### GitHub Actions: deploy workflow

- [ ] **Generate a deploy SSH key** on your laptop, dedicated to GitHub Actions. Add the public key to `/home/deploy/.ssh/authorized_keys` on the droplet.
- [ ] **Add GitHub Secrets** (Settings → Secrets and variables → Actions):
  - `DEPLOY_SSH_KEY` (the private key)
  - `DEPLOY_HOST` (droplet IP)
  - `DEPLOY_USER` (`deploy`)
- [ ] **Create `.github/workflows/deploy.yml`** triggered on push to main. Steps: install SSH key, SSH to droplet, run `git pull && docker compose ... up -d`.
- [ ] **Test the workflow:** make a one-line change to `services/caddy/static/index.html` (e.g., change the page title), push to main, watch GHA run, then visit the site to confirm change appeared.
- [ ] **Take a second screenshot** showing the updated page.
- [ ] **Open PR #4:** "ci: deploy pipeline + initial production." Squash-merge.

**End-of-Day-3 self-check:** `https://azureus.tech` is live with TLS. CI passes. A push to main triggers an automatic deploy that takes <8 minutes. You can update the live site by editing a file and pushing.

---

## Day 4 — Hello World API + Frontend Wiring + Final Polish

### Minimal API

- [ ] **Create `azureus/api/main.py`** with a FastAPI app exposing two endpoints:
  - `GET /api/v1/health` → returns `{"status": "ok", "version": "0.0.1"}`
  - `GET /api/v1/version` → returns `{"version": "0.0.1", "git_sha": "<env var>", "build_time": "<env var>"}`
- [ ] **Add `services/base/Dockerfile`** — Python 3.11 base image with uv installed, project code copied, dependencies installed.
- [ ] **Add `services/api/Dockerfile`** — extends base, sets entrypoint to `uvicorn azureus.api.main:app --host 0.0.0.0 --port 8000`.
- [ ] **Add `api` service to `docker-compose.yml`.** Depends on postgres and redis.
- [ ] **Test locally:** `docker compose up -d api`, then `curl http://localhost:8000/api/v1/health`. Should return the JSON.

### Caddy reverse proxy

- [ ] **Update `Caddyfile`** to reverse-proxy `/api/*` requests to the `api` container.
- [ ] **Update `docker-compose.prod.yml`** to include `api` and have caddy depend on it.

### Frontend → API integration

- [ ] **Frontend: set up TanStack Query provider** in `main.tsx`. Wrap app with `QueryClientProvider`.
- [ ] **Frontend: create `src/api/client.ts`** with a base fetch wrapper. In dev, points to `http://localhost:8000`; in prod, uses relative `/api/v1`.
- [ ] **Frontend: create `src/api/health.ts`** with a `fetchHealth` function and `useHealth` hook (TanStack Query).
- [ ] **Frontend: update App.tsx** to call `useHealth()` and display the response (or error state). This proves end-to-end frontend → API works.
- [ ] **Frontend: set up Vite proxy config** in `vite.config.ts` so `/api/*` requests during dev are proxied to `http://localhost:8000`. This avoids CORS issues.
- [ ] **Frontend: build to static files.** `pnpm build`. Output goes to `frontend/dist/`.
- [ ] **Caddy: update `Caddyfile`** to serve `frontend/dist/` for non-API routes.
- [ ] **Update CI** to build the frontend and copy `frontend/dist/` into the deployment artifact.

### Production deploy

- [ ] **Update `deploy.yml`** to:
  1. Build frontend in CI
  2. SCP the `frontend/dist/` to the droplet
  3. Restart `api` and `caddy` containers
- [ ] **Push to main.** Watch the deploy.
- [ ] **Visit `https://azureus.tech`.** Should now see the React app (not the static "Coming Soon"). The health-status indicator on the page should show "ok" because the API is wired up.
- [ ] **Visit `https://azureus.tech/api/v1/health` directly.** Should see the JSON response.
- [ ] **Visit `https://azureus.tech/api/v1/docs`.** Should see Swagger UI auto-generated by FastAPI.
- [ ] **Take a celebratory screenshot.** This is Phase 0 complete.

### Final polish

- [ ] **Update README.md** with:
  - Project description (one paragraph from ARCHITECTURE.md Section 1.1)
  - Status badge for CI
  - Link to live site (`https://azureus.tech`)
  - Link to ARCHITECTURE.md
  - "WIP — in active development" notice
  - Quickstart for local dev (3 commands max)
- [ ] **Set up UptimeRobot:** create free account, add a monitor for `https://azureus.tech/api/v1/health`, set 5-minute interval, configure email alerts to your address.
- [ ] **Tag `v0.1.0-foundation`** on the deployed commit. This marks the end of Phase 0.
- [ ] **Open PR #5:** "feat(phase-0): foundation complete with deployed Hello World." Squash-merge.

---

## Phase 0 Exit Criteria — Binary Check

Before declaring Phase 0 done and starting Phase 1, verify *all* of these are true:

- [ ] A stranger visiting `https://azureus.tech` sees a working React page
- [ ] The page calls the real API and displays a real response
- [ ] TLS is valid (browser shows lock icon, no warnings)
- [ ] `/api/v1/health` returns `{"status": "ok"}`
- [ ] `/api/v1/docs` shows Swagger UI
- [ ] CI badge on GitHub is green
- [ ] Pushing a one-line change to main results in an automatic deploy within ~8 minutes
- [ ] Tag `v0.1.0-foundation` exists
- [ ] UptimeRobot is monitoring the site
- [ ] You have screenshots of: initial Caddy-only deploy, updated static deploy, final React+API deploy
- [ ] `docs/ARCHITECTURE.md`, `CLAUDE.md`, and `docs/PHASE_0_CHECKLIST.md` (this file, marked complete) are all in the repo

**If even one item is unchecked, Phase 0 is not done.** Do not start Phase 1 work (data layer, DataSource interface, ingestion flows). Going forward without completing the foundation will compound problems through the remaining phases.

---

## Time Budget Reality Check

If by end of Day 4 you've completed fewer than 75% of these items, **stop and reassess**:

- Are you procrastinating? (2-Day Rule: if stuck on one item >2 days, surface it for triage)
- Did you discover an unknown? (DNS issue, lab access blocked, Docker not working — these can eat a day each)
- Is the scope wrong? (Some items might be more than 1 day's work; tell me which)

Phase 0 sliding to 6 days is acceptable. Sliding to 10+ days means something fundamental needs adjustment before Phase 1.

---

## What Phase 1 Will Need on Day 5

You don't need to do these in Phase 0, but knowing they're coming helps:

- A complete list of HSI tickers in canonical format (we'll source/curate this on Day 5)
- yfinance ticker mapping (`0700.HK` for `700 HK`)
- Decision on whether to add `akshare` for HK fundamentals coverage (defer to actual ingestion testing)
- The first Alembic migration (creates the `tickers` table)
- The `DataSource` Protocol definition

Don't pre-build any of these in Phase 0. Just be mentally ready that Day 5 starts with data work.

---

**End of Phase 0 starter checklist. Good luck. Push hard.**
