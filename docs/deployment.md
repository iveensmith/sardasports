# Deploying SARDASPORTS: one server, Cloudflare in front

```
visitor ──▶ Cloudflare (DNS, CDN, DDoS, TLS) ──▶ tunnel ──▶ web (Next.js) ──▶ api (FastAPI) ──▶ SQLite on disk
```

One small server runs three containers (`docker-compose.prod.yml`):

| Container | What it is | Reachable from |
|---|---|---|
| `web` | the website (Next.js 16, standalone build) | the tunnel only |
| `api` | the prediction engine, its scheduler and its SQLite database | `web` only |
| `cloudflared` | a Cloudflare Tunnel: dials out to Cloudflare, so the server needs **no open inbound ports** | n/a |

Why this shape, and why not Cloudflare Workers for the engine: the engine keeps a 174 MB SQLite
file, a scheduler that must stay running, and about 0.5 GB of fitted models in memory. Workers
have 128 MB per request-isolate and no persistent disk, and Cloudflare Containers wipe their disk
whenever they sleep. The website *can* run on Workers (tested: Next 16.3.8 plus the OpenNext
adapter works), but it needs a paid plan and extra code, and gains little at this size. This setup
needs no code changes beyond the Next.js upgrade already made.

## What you need

- A server: Ubuntu 24.04, **4 GB RAM** (2 vCPU), 40 GB disk. A Hetzner CX22, a DigitalOcean 4 GB
  droplet or similar, about $5-10 a month. 2 GB is not enough: the engine alone is about 0.5 GB and
  the website build needs more.
- Your domain on Cloudflare (DNS managed there).
- The API-Football key (the same key serves the basketball feed).

## First-time setup

### 1. Prepare the server

```bash
# as root, once
adduser deploy && usermod -aG sudo deploy
ufw default deny incoming && ufw allow OpenSSH && ufw enable   # the tunnel needs no inbound port
curl -fsSL https://get.docker.com | sh && usermod -aG docker deploy
```

Log in as `deploy` from here on.

### 2. Get the code

```bash
sudo mkdir -p /opt/sardasports && sudo chown deploy /opt/sardasports
git clone https://github.com/iveensmith/sardasports.git /opt/sardasports
cd /opt/sardasports
```

### 3. Create the Cloudflare Tunnel

In the Cloudflare dashboard: **Zero Trust > Networks > Tunnels > Create a tunnel** > Cloudflared.

1. Name it `sardasports`. Choose **Docker** and copy the token from the command it shows
   (the long string after `--token`). You do not run that command; compose runs the connector.
2. Add a **Public hostname**: your domain (and `www`, if you use it), service type **HTTP**,
   URL **`web:3000`**.
3. Cloudflare creates the DNS record for you.

### 4. Configure

```bash
cp .env.production.example .env.production
nano .env.production          # fill in the tunnel token and your API key
```

Leave `NEXT_PUBLIC_SITE_URL` empty for now: while it is empty the site is `noindex` and
`robots.txt` disallows everything, so you can test on the live address without being indexed.

### 5. Upload the data

The engine's database, raw downloads and trained models are not in git. They go in once, from
your Windows machine. **Stop the local engine first** (so the files are not mid-write), then in
PowerShell from the project folder:

```powershell
# a consistent copy of the database (safe even while the engine runs)
.venv\Scripts\python.exe -m scripts.backup_db --out C:\temp\seed --keep 1

# on the server:  sudo mkdir -p /srv/sardasports/{data,models,chroma} && sudo chown -R deploy:deploy /srv/sardasports
scp C:\temp\seed\uniquepredict-*.db deploy@SERVER:/srv/sardasports/data/uniquepredict.db
scp -r data\raw data\processed deploy@SERVER:/srv/sardasports/data/
scp ml\models\* deploy@SERVER:/srv/sardasports/models/
```

(`data\processed` and `data\raw` are about 115 MB; the models about 56 MB; the database about
175 MB.) Then on the server, because the containers run as user id 1000:

```bash
sudo chown -R 1000:1000 /srv/sardasports
```

### 6. Start it

```bash
cd /opt/sardasports
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
docker compose -f docker-compose.prod.yml exec -T api alembic upgrade head   # a no-op if current
docker compose -f docker-compose.prod.yml ps                                 # all three "healthy"/"running"
```

The first build takes several minutes. The first request after a start is slow (the engine is
computing today's boards from cold; 20-40 seconds), then fast: the scheduler warms the caches
every 4 minutes.

### 7. Check it

Open your domain. The results strip should read "Recent strong tips" and the boards should
list fixtures. From the server:

```bash
docker compose -f docker-compose.prod.yml exec -T api curl -s localhost:8000/health
docker compose -f docker-compose.prod.yml logs --tail=50 api
```

## No domain yet? Test with a temporary address

Steps 3 and 4 (the named tunnel and `CLOUDFLARE_TUNNEL_TOKEN`) need a domain on Cloudflare. To
see the site running first, skip them and use the quick tunnel: a temporary
`https://....trycloudflare.com` address that needs no account and no domain.

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production --profile quick up -d --build api web quicktunnel
docker compose -f docker-compose.prod.yml logs quicktunnel | grep trycloudflare
```

The second command prints the address. Limits: it changes every time the container restarts, it
has no uptime promise, and Cloudflare provides it for testing, so do not give it to real
visitors. The site stays `noindex` because `NEXT_PUBLIC_SITE_URL` is empty.

When you have a domain, buy it through Cloudflare (Dashboard > Domain Registration; a `.com` is
about $10 a year at cost) or add an existing one, then follow steps 3 and 4 above and start with
the normal command. Stop the quick tunnel first:
`docker compose -f docker-compose.prod.yml stop quicktunnel`.

## Cloudflare settings worth turning on

- **SSL/TLS > Overview:** *Full* is fine; with a tunnel the origin leg is already encrypted.
  **Edge Certificates > Always Use HTTPS:** on.
- **Speed > Optimization:** leave **Rocket Loader** and **Auto Minify** *off*. They rewrite the
  page's JavaScript and can break React hydration.
- **Security > Bots:** *Bot Fight Mode* on.
- **Security > WAF > Rate limiting rules:** one rule on `POST /api/contact`, e.g. 5 requests per
  10 minutes per IP, so the contact form cannot be used to flood you.
- **Caching (once you have a domain):** Cloudflare caches the hashed `/_next/static/*` files by
  default but never HTML. The site sends `Cache-Control: public, s-maxage=60, stale-while-revalidate=600`
  on its pages, so add one rule to let Cloudflare keep them: **Caching > Cache Rules > Create rule**,
  *When* `Hostname` equals your domain **and** `URI Path` does not start with `/api`; *Then* **Eligible
  for cache**, Edge TTL **Use cache-control header if present**. Pages are then served from the
  nearest Cloudflare location for up to a minute (and stale for up to ten while refreshing), instead
  of travelling to your server each time. This does not work on the temporary `trycloudflare.com`
  address, which has no zone to put a rule on.
- **Email:** the Contact page stores messages in the engine's database (read them with
  `scripts/list_contact_messages.py`); nothing sends mail.

## Day-to-day

```bash
cd /opt/sardasports
git pull && docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build   # deploy an update
docker compose -f docker-compose.prod.yml logs -f api       # engine log (scheduler jobs show here)
docker compose -f docker-compose.prod.yml restart api       # restart the engine
```

After an update that changes the database (the commit message or `docs/roadmap.md` will say so),
run the migration once the containers are back up:

```bash
docker compose -f docker-compose.prod.yml exec -T api alembic upgrade head
```

A deploy rebuilds the images and restarts the containers; data lives in `/srv/sardasports` and is
untouched.

### Backups

The database is the one thing that cannot be rebuilt: the stored pre-kick-off predictions and the
live record are in it, and so are the members, blog posts, editor's picks and subscriptions.

**Nightly, automatic.** The engine takes a verified snapshot at 02:10 server time with SQLite's
own backup API (consistent while the engine is writing, checked with `integrity_check`) and writes
it to `/srv/sardasports/data/backups/uniquepredict-YYYYMMDD-HHMMSS.db`. The newest 14 are kept
(`BACKUP_KEEP` in `.env.production` changes that). It skips, and says so in `docker compose logs
api`, if the disk could not hold the copy twice over. No cron entry is needed. To take one now:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production exec -T api python -m scripts.backup_db --keep 14
```

**Get a copy off the server.** Those snapshots are on the same disk, so they protect against a bad
edit or a corrupt write, not against losing the server. Pull them to your own computer
(PowerShell on your PC; it copies only what is new, so run it weekly or daily):

```powershell
mkdir C:\backups\sardasports -Force
scp "deploy@YOUR_SERVER_IP:/srv/sardasports/data/backups/uniquepredict-*.db" C:\backups\sardasports\
scp -r "deploy@YOUR_SERVER_IP:/srv/sardasports/data/uploads" C:\backups\sardasports\
```

The second command copies the **blog images** (`/srv/sardasports/data/uploads`). They are files, not
rows, so the database snapshot does not contain them: restore the database without them and the
articles come back with broken pictures.

Hetzner's own paid server backups (a snapshot of the whole disk) are a second layer, if you want one.

**Restore.** Stop the api, put a snapshot at `/srv/sardasports/data/uniquepredict.db`,
`chown 1000:1000` it, delete any `uniquepredict.db-wal` and `uniquepredict.db-shm` beside it, and
start the api. Anything written after that snapshot (members who signed up since, picks settled
since) is gone, which is why the copy should be recent.

### What keeps itself current

The scheduler runs inside the `api` container: the daily data refresh (03:00), fixtures, odds,
results, match statistics, injuries, basketball and tennis feeds, and the weekly model retrain
(Monday 04:00). On start it also catches up on a missed refresh and on results that finished
while it was down. It only runs while the container runs, so keep the server up.

## Going live

1. Set `NEXT_PUBLIC_SITE_URL` (the real `https://` address), `NEXT_PUBLIC_OPERATOR_NAME` and
   `NEXT_PUBLIC_CONTACT_EMAIL` in `.env.production`.
2. Rebuild: `docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build web`.
3. Check `https://your-domain/robots.txt` allows crawling and lists the sitemap.

Do this only when the Privacy and Terms pages have been read by someone qualified: see
`docs/roadmap.md` and `docs/seo.md`.

## Rules this setup depends on

- **One `api` container, never two.** SQLite is a single-writer file, and the scheduler, the
  rate limiter and the caches are in-process. Running two copies would run every scheduled job
  twice and fight over the database. To scale, the engine first needs Postgres and a shared cache
  (the dev compose file has both); that is a separate piece of work.
- **The engine is never exposed.** It has no port published. Do not add one: its endpoints are
  unauthenticated by design because only the website talks to it.
- **Keep the server and the tunnel's token private.** Anyone with the tunnel token can route
  your hostname.

## Not yet tested

This was prepared on a Windows machine without Docker, so **the images were not built here**.
What was verified: the website builds in the same mode the Dockerfile uses
(`next build --experimental-build-mode compile`), the standalone server it produces runs and
serves every page against the live engine, the compose file parses, the backup script has tests,
and the engine runs from the same lockfile. The first `up --build` on the server is the real
test; if it fails, the likeliest places are the engine image's system libraries (the Dockerfile
installs `libgomp1` for XGBoost/LightGBM) and file ownership of `/srv/sardasports`.

## Memory: what froze the server on 12 Oct 2026, and the guard rails

The 4 GB box stopped answering SSH ("timed out during banner exchange"). The Hetzner console showed
the kernel's `Out of memory: Killed process (uvicorn) ... anon-rss:3059800kB`: the engine had grown to
about 3 GB, the container's cap was 3 GB on a 4 GB machine, and nothing was left for SSH, the web
server or the kernel. Its CPU sat at ~155% (the engine being killed, restarting and growing again).

**The cause, found afterwards:** the 12 Oct freeze was a Monday, and the scheduler's weekly retrain
(`retrain_models_job`, Mondays 04:00 UTC) trains about thirty models *inside the web engine's own
process*. The server's CPU graph sat at ~155% from about 04:00, and the process grew to 3 GB. That job
is now off unless `ENABLE_WEEKLY_RETRAIN=true`; train models on a development machine and upload them
(`ml/models/` to `/srv/sardasports/models`). The home page's extra board requests were not the cause.

What changed in response:
- The api container is capped at 2.3 GB and web at 512 MB (`docker-compose.prod.yml`), so a runaway
  restarts that container and not the box.
- `MALLOC_ARENA_MAX=2` for the api: threaded Python on glibc otherwise holds on to far more memory
  than it uses.
- The home page's featured picks read stored predictions only (`/sports/{sport}/board?stored_only=true`),
  so a page view never makes the engine load a sport's whole history.
- `/health` now returns `rss_mb`, the engine's resident memory. Check it from the server:
  `curl -s http://127.0.0.1:8000/health` inside the api container, or
  `docker compose ... exec -T api curl -s localhost:8000/health`. If it climbs steadily with no
  traffic, that is a leak and worth reporting with the timestamps.

Add swap once, as a cushion (on the server):

    sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
    sudo mkswap /swapfile && sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    free -h

Build the images with the api stopped on this size of box (`docker compose ... stop api`, build,
then `up -d`): a build and a running engine together are what pushed it over.

## Accounts, the admin dashboard and premium

**One-off, after pulling the code** (on the server, from `/opt/sardasports`):

```bash
# 1. add the new tables (safe to run twice)
docker compose -f docker-compose.prod.yml --env-file .env.production exec -T api alembic upgrade head

# 2. create your administrator account (it asks for a password; it is not shown or stored in
#    the clear). This one is interactive, so it has no -T:
docker compose -f docker-compose.prod.yml --env-file .env.production exec api python -m scripts.create_admin you@yourdomain.com
```

Then sign in at `/login` and open `/admin`.

**Mail.** Set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` and `SMTP_FROM` in
`.env.production` and restart the api. Until then every account e-mail is written to
`/admin/mail` and not sent. Authenticate the sending domain (SPF, DKIM, DMARC) with your mail
provider before launch, or confirmation mails will land in spam.

**Premium.**

1. Sign in, open `/admin/premium` and create a plan (the code `monthly`, the price you chose,
   the currency, "a month"), and switch it on. Nothing is pre-filled: the price is yours.
2. Add a payment provider's keys to `.env.production` and restart the api:
   - **Stripe:** `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET`. In the Stripe dashboard add a
     webhook endpoint `https://YOURDOMAIN/api/webhooks/stripe` listening for
     `checkout.session.completed`.
   - **Paystack:** `PAYSTACK_SECRET_KEY`. In the Paystack dashboard set the webhook URL to
     `https://YOURDOMAIN/api/webhooks/paystack`.
3. Test with the provider's **test keys** first: make a payment, confirm the member gets premium,
   repeat the same notification (it must not extend access twice), then switch to live keys.

Without a provider you can still grant premium by hand from `/admin/members`.

**What protects it:**
- A payment notification is accepted only with a valid signature from the provider, is applied
  once however many times it is sent, and buys access only if the amount is at least the plan's
  price. Card details never reach this server.
- A published pick cannot be edited, and can be deleted only until its match kicks off; a premium
  pick is visible to everyone from kick-off. See `app/services/content_service.py`.
- Passwords are stored as salted scrypt hashes and sessions and e-mail links as SHA-256 hashes.
  Sign-in, sign-up and reset requests are rate-limited.
- The session cookie is `sd_session` (HttpOnly, SameSite=Lax, Secure in production).

**Back up the database before launch and after.** It now holds members.

## The article editor

`/admin/posts/new` is a rich-text editor (title, category, tags, featured image, content). Notes:

- **The editor is CKEditor 4.22.1**, served from this site (`web/public/ckeditor`, copied out of
  `node_modules` by `web/scripts/copy-ckeditor.mjs` at build; nothing is loaded from a third
  party). 4.22.1 is the last release under its open-source licence and no longer receives
  security fixes. It is used only on the administrator-only page, and its output is never trusted:
  the engine rebuilds every article from an allow-list of tags, attributes and styles before
  storing it (`app/services/html_sanitize.py`, with tests). Do not loosen that list.
- **Buttons left off** the reference toolbar because they cannot work or would put unsafe or
  external things in a post: Save and PDF export (a cloud service), the form-field buttons, Flash,
  Iframe, and spell-check-as-you-type (it sends the text to a third party).
- **Images** are checked, resized (longest side 2000 px) and re-encoded on upload, then stored in
  `/srv/sardasports/data/uploads/blog` and served at `/media/<name>`. JPEG, PNG and WebP, up to
  6 MB. They are not in the database snapshot: back that folder up too (see Backups).
- **Categories** are a fixed list in `app/services/content_service.py` (`CATEGORIES`).
- After pulling this change run `alembic upgrade head` (it adds four columns to `posts`; articles
  written before it keep their old format and still display).
- To use the brand yellow for the main button instead of the reference's blue, change
  `--ae-accent` at the top of `web/components/admin/article-editor.css`.
