# Deploying to production

App on **Render** (free), database on **Neon** (free). Total cost: $0/month.

Everything below is done from your browser and your own PowerShell window. You
do not need a terminal on the server -- Render's free plan does not provide one,
and nothing here requires it.

**Time:** about 30 minutes the first time.

---

## Why Neon rather than Render's database

Render offers a free PostgreSQL database. **Do not use it.** It expires 30 days
after creation and the data is deleted with it, which would take the daycare's
families along. Neon's free plan does not expire.

---

## Before you start

You need:

- The GitHub repository (you have it)
- An email address for two free accounts
- Your local clone working, with `.venv` installed

Your local `.venv` doubles as the admin tool for production: it is how you will
create staff accounts and take backups, by pointing `DATABASE_URL` at Neon for a
single command. That is why no server shell is needed.

---

## Step 1 — Create the database (Neon)

1. Go to **neon.com** and sign up (GitHub sign-in is fine).
2. Create a project. Name it anything; region closest to the daycare.
3. On the project dashboard, find **Connection string** and copy it. It looks
   like:

   ```
   postgresql://neondb_owner:PASSWORD@ep-something-123.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```

4. **Keep the whole string, including `?sslmode=require`.** Paste it somewhere
   safe for the next steps. It is a password -- do not put it in the repository,
   a commit, or a chat message.

Turn on **two-factor authentication** on this account. Anyone who signs in here
can read every family record.

---

## Step 2 — Create the web service (Render)

1. Go to **render.com** and sign up with GitHub.
2. **New → Web Service**, then connect your `DayCare_CRM` repository.
3. Set:

   | Field | Value |
   |---|---|
   | Name | your choice -- **this becomes the public URL** |
   | Branch | `claude/intelligent-dirac-c7l0mn` |
   | Runtime | Python 3 |
   | Build command | `pip install -r requirements.txt` |
   | Start command | `flask db upgrade && gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 60` |
   | Instance type | **Free** |
   | Health check path | `/healthz` |

   The service name becomes `your-name.onrender.com` and is publicly visible.
   Choose a neutral name if you would rather the daycare's name not appear in
   the URL.

4. Add these **environment variables**:

   | Key | Value |
   |---|---|
   | `DATABASE_URL` | the Neon connection string from Step 1 |
   | `DAYCARE_NAME` | the daycare's real name |
   | `SECRET_KEY` | click **Generate** |
   | `FLASK_APP` | `wsgi.py` |
   | `SESSION_COOKIE_SECURE` | `1` |
   | `BEHIND_PROXY` | `1` |
   | `PYTHON_VERSION` | `3.11.15` |

   `DAYCARE_NAME` and `DATABASE_URL` live only here. Neither is in the
   repository, which is why the repository can stay public.

5. **Create Web Service.** The first build takes a few minutes.

`render.yaml` in the repository describes this same setup if you prefer
Render's Blueprint flow. Either route produces the same service.

---

## Step 3 — Confirm it started

When the deploy finishes, open:

```
https://your-service-name.onrender.com/healthz
```

You should see `{"database":"ok","status":"ok"}`. That means the app started
**and** reached Neon.

If it says `database: unreachable`, `DATABASE_URL` is wrong -- check you copied
the whole string including `?sslmode=require`.

The deploy log should show the migration running:
`Running upgrade -> 5a5581a170d4, Initial schema`. That created the tables.

The main page will redirect you to a sign-in screen. You have no account yet.

---

## Step 4 — Create your staff account

From **your own PowerShell window**, pointed at the production database for one
command:

```powershell
cd D:\source\DayCare_CRM
$env:FLASK_APP = "wsgi.py"
$env:DATABASE_URL = "postgresql://...paste your Neon string..."
.\.venv\Scripts\flask create-user
Remove-Item Env:DATABASE_URL
```

That last line matters: it clears the production database out of your shell so
later local commands do not touch live data.

Now sign in at `https://your-service-name.onrender.com`.

**Do not run `seed-demo` against production.** It would mix fictional families
into real records.

---

## Step 5 — Add your team

Sign in, go to **Team → Add team member**, set a temporary password for each
person, and ask them to change it under **My account**.

Everyone has the same permissions: all staff can view, edit, and delete every
record.

---

## Living with the free tier

**The app sleeps after ~15 minutes idle.** The next visit takes roughly a
minute to wake. Staff will notice this first thing in the morning. Upgrading
the Render service to the paid instance (~$7/month) removes it, changes nothing
else, and can be done at any time.

**Neon allows 100 compute-hours per month** on the free plan, and scales to zero
when idle. Normal daycare use fits comfortably. If you exceed it, the database
suspends until the next cycle.

**Bandwidth is 5 GB/month** on Render's free workspace. This app serves text
pages, so that is not a practical limit.

---

## Backups -- your responsibility

Neon's free plan has no managed backups. Take your own, from your PowerShell
window:

```powershell
cd D:\source\DayCare_CRM
$env:FLASK_APP = "wsgi.py"
$env:DATABASE_URL = "postgresql://...your Neon string..."
.\.venv\Scripts\flask backup --output-dir "$env:USERPROFILE\Documents\crm-backups"
Remove-Item Env:DATABASE_URL
```

This writes one timestamped JSON file containing every record.

**Do weekly, and before any change to the app.** Set a calendar reminder; it
takes ten seconds.

The backup file **contains family data and password hashes**. Keep it out of the
project folder -- the command above writes to Documents for exactly that reason
-- and somewhere access-controlled.

To restore into an empty database:

```powershell
.\.venv\Scripts\flask restore "path\to\daycare-crm-backup-YYYYMMDD-HHMMSS.json"
```

Restore refuses to run against a database that already holds records unless you
pass `--force`, so it cannot quietly collide with live data.

---

## Deploying a change

Push to the branch. Render rebuilds and restarts automatically, running
`flask db upgrade` first, so schema changes apply themselves.

**Take a backup before deploying anything that changes the database.**

If a deploy breaks the site, Render's dashboard has **Rollback** to the previous
deploy. That rolls back *code*, not data -- a migration that changed the schema
stays applied, which is the other reason to back up first.

---

## Changing the schema later

Never edit tables by hand. After changing a model:

```powershell
$env:FLASK_APP = "wsgi.py"
.\.venv\Scripts\flask db migrate -m "what changed"
```

Read the generated file in `migrations\versions\` before committing it --
autogenerate is good, not perfect. Test locally, then push; Render applies it on
the next deploy.

---

## If something goes wrong

| Symptom | Cause |
|---|---|
| `/healthz` says `database: unreachable` | `DATABASE_URL` wrong or truncated; must include `?sslmode=require` |
| Deploy fails at `flask db upgrade` | `FLASK_APP` not set in Render's environment variables |
| Signed out on every visit | `SECRET_KEY` missing or changed |
| Everyone signed out after a deploy | `SECRET_KEY` was regenerated -- set it to a fixed value |
| First visit each morning is slow | Free plan sleeping; expected |
| Login page loads but sign-in fails silently | `SESSION_COOKIE_SECURE=1` without HTTPS, or `BEHIND_PROXY` not set |

Render's **Logs** tab shows application errors; `/healthz` distinguishes an
app-down problem from a database-down one.
