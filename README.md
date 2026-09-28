# Daycare Enrollment CRM

A small web application for tracking the student acquisition funnel: who inquired,
whether they toured, whether they enrolled, when they started, when they graduated,
and — when they don't continue — whether they **declined** or **withdrew**, and why.

Built as a **local prototype**: it runs on one computer with a SQLite database file.
Everything is structured so that moving to a shared team database later is a
configuration change, not a rewrite. See [Going multi-user](#going-multi-user).

---

## The funnel

```
Inquiry → Contacted → Tour Scheduled → Tour Completed → Waitlist → Enrolled → Active → Graduated
                                                   ↘                    ↙
                                            Declined            Withdrew
                                         (reason + date)     (reason + date)
```

- **Waitlist** is an optional branch, not a required step. Conversion reporting
  skips over it so the numbers after it still read correctly.
- **Declined** = chose not to enroll. **Withdrew** = enrolled, then left. Both
  require a reason, and each keeps its own reason list, date, and notes.
- Stage dates are kept permanently. A family who toured and later declined still
  counts as having toured, so your tour-to-enrollment rate stays honest.
- Every stage change is written to an audit log with the date and who made it.

## What it tracks

| | |
|---|---|
| **Families** | Household name, address, how they heard about you, preferred contact method, notes |
| **Parents / guardians** | Name, relationship, email, phone, one designated primary contact per family |
| **Students** | Name, date of birth, program, classroom, desired start date, notes |
| **Funnel** | A date stamped for every stage reached, plus decline/withdraw reason and notes |
| **Contact log** | Calls, emails, texts, tours and notes, logged against a family or a specific student |
| **Team** | Staff accounts, all with equal permissions |

Student records hold **contact information only** — no medical, allergy, custody,
or financial fields. If you ever need those, they should be added deliberately,
with access controls and audit logging to match.

## Reports

The dashboard funnel covers the **current school year, April 1 through March 31**,
anchored on when each family first inquired. The window rolls over on its own --
on April 1 the funnel resets to the new year, and nothing is deleted.

A **year selector** on the funnel card switches between school years. It offers
every year from the earliest recorded inquiry through the current one, and the
stat tiles, the funnel, and the "Full reports" link all follow the selection.
The header says plainly when you are looking at a year other than the current one.

Two tiles deliberately ignore that window, because they answer "what is true right
now" rather than "how did this year go":

- **Open pipeline** — students in Inquiry, Contacted, Tour Scheduled, Tour
  Completed, or Waitlist. Enrolled and Active students are excluded; they are
  already won and are counted under *Currently enrolled* instead. A family who
  inquired last school year and is still touring is still live work, so they stay
  counted here after the year rolls over.
- **Currently enrolled** — students in Enrolled or Active.

To change when the school year starts, edit `SCHOOL_YEAR_START_MONTH` and
`SCHOOL_YEAR_START_DAY` in `app/constants.py`. To change which stages count as
open pipeline, edit `PROSPECT_STAGES` in the same file.

Everything else:

- Conversion funnel with step-by-step rates, and inquiry → enrolled overall
- Why families declined, and separately, why families withdrew
- Which referral sources actually produce enrollments
- Average days from first inquiry to enrollment
- Inquiries and enrollments by month
- Upcoming tours, and a "needs follow-up" list of pipeline families gone quiet
- CSV export of every student with all funnel dates

---

## Setup

You need Python 3.11 or newer.

### macOS / Linux

```bash
# 1. Install dependencies into a local environment
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. Create your configuration file
cp .env.example .env

# 3. Generate a secret key, then paste it into .env as SECRET_KEY=
python3 -c "import secrets; print(secrets.token_hex(32))"

# 4. Create the first staff account (this also creates the database)
export FLASK_APP=wsgi.py
.venv/bin/flask create-user

# 5. Start it
.venv/bin/python wsgi.py
```

### Windows (PowerShell)

Windows puts virtual-environment programs in `.venv\Scripts\`, not `.venv/bin/`.
Otherwise the steps are identical.

```powershell
# 1. Install dependencies into a local environment
py -3 -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt

# 2. Create your configuration file
Copy-Item .env.example .env

# 3. Generate a secret key, then paste it into .env as SECRET_KEY=
python -c "import secrets; print(secrets.token_hex(32))"

# 4. Create the first staff account (this also creates the database)
$env:FLASK_APP = "wsgi.py"
.\.venv\Scripts\flask create-user

# 5. Start it
.\.venv\Scripts\python wsgi.py
```

Notes for Windows:

- The `.\` prefix is required by PowerShell to run a program from the current folder.
- Calling the programs directly, as above, avoids needing `Activate.ps1`, which
  PowerShell's default execution policy blocks.
- If `py -3` is not recognized, use `python`. If that opens the Microsoft Store,
  Python is not installed -- install it from python.org and tick
  "Add Python to PATH".
- Dates display as `Mar 04, 2026` rather than `Mar 4, 2026`, because Windows does
  not support the day-without-padding format. Cosmetic only.

### Either platform

Then open **http://127.0.0.1:5000** and sign in with the account you just created.
Press `Ctrl+C` in the terminal to stop the server.

### Optional: load demo data

To see the funnel and reports populated before entering real families:

```bash
.venv/bin/flask seed-demo          # Windows: .\.venv\Scripts\flask seed-demo
```

This creates 12 fictional families and 25 students spread across every stage.
**Only run this on an empty database** — delete `instance/daycare_crm.sqlite3`
and start over when you're ready for real data.

### Adding your teammates

Sign in, go to **Team → Add team member**, and set a temporary password for each
person. Ask them to change it under **My account** after their first sign-in.
Everyone has the same permissions: all staff can view and edit every record.

---

## Keeping family data out of the repository

**This repository is public.** No family data has ever been committed to it, and
two things keep it that way:

1. **`.gitignore`** excludes the database, `.env`, CSV exports, and backups.
2. **A pre-commit hook** refuses any commit containing those files, including one
   forced past `.gitignore` with `git add -f`.

Enable the hook once per clone -- it is not automatic:

```bash
git config core.hooksPath .githooks
```

Check it is on with `git config core.hooksPath`, which should print `.githooks`.

If a database or CSV export is ever committed, treat the families in it as
published. Deleting the file in a later commit does not remove it from history,
and rewriting history does not reliably un-publish what others may already have
fetched or what search engines have indexed. Prevention is the only real control,
which is why the hook exists.

Two habits matter as much as the tooling: save CSV exports somewhere outside the
project folder, and keep database backups outside it too.

## Your data

The entire database is one file: **`instance/daycare_crm.sqlite3`**.

- **Back it up** by copying that file somewhere safe, on a schedule. There is no
  other copy. Copying it while the app is closed is safest.
- **It is not encrypted.** It contains names, addresses, phone numbers and emails
  of families and children. Keep it on a machine with full-disk encryption and a
  login password, and don't sync the folder to a personal cloud drive.
- `.gitignore` excludes `instance/` and `.env`, so real family data and your
  secret key are never committed to git. Keep it that way.

---

## Going to production

**See [DEPLOYMENT.md](DEPLOYMENT.md)** for the full click-by-click runbook:
the app on Render's free plan, the database on Neon's free plan, $0/month.

In short: `DATABASE_URL` points at PostgreSQL, Alembic migrations create and
update the schema, Gunicorn serves the app, and `DAYCARE_NAME` supplies the
daycare's name from the environment so it stays out of this public repository.

Two commands you will run from your own machine against the production
database, since Render's free plan provides no server shell:

```bash
DATABASE_URL="postgresql://...neon..." flask create-user   # add staff
DATABASE_URL="postgresql://...neon..." flask backup        # take a backup
```

### Database migrations

The local SQLite prototype creates its own tables on first run. Any PostgreSQL
database uses Alembic instead -- `db.create_all()` cannot alter existing
tables, so relying on it would silently skip every future schema change.

```bash
flask db migrate -m "what changed"   # generate, then READ the generated file
flask db upgrade                     # apply
```

Render runs `flask db upgrade` on every start, which is a no-op when the
database is already current.

### Backups

Neon's free plan has no managed backups, so take your own weekly and before
any deploy that changes the schema:

```bash
flask backup --output-dir ~/crm-backups   # every record, one JSON file
flask restore path/to/backup.json         # into an empty database
```

Restore refuses to run against a database that already holds records unless
passed `--force`. Backup files contain family data and password hashes -- keep
them outside the project folder and somewhere access-controlled.

On Windows, `scripts\backup.ps1` wraps this with verification, retention and
logging, and `scripts\Register-BackupTask.ps1` schedules it weekly. See
[DEPLOYMENT.md](DEPLOYMENT.md).

### The older notes on moving off SQLite

This prototype runs on one machine, so only one person can use it at a time.
When the team needs shared access, the change is:

1. **Stand up a Postgres database** — a managed one (Neon, Supabase, RDS) or on
   a server you control.
2. **Uncomment `psycopg[binary]`** in `requirements.txt` and install it.
3. **Point `DATABASE_URL` at Postgres** in `.env`:
   ```
   DATABASE_URL=postgresql+psycopg://crm_user:password@db-host:5432/daycare_crm
   ```
4. **Migrate the existing rows** across (the schema is created automatically on
   first start; the current data is small enough to move with the CSV export, or
   with a short script).
5. **Serve it properly** — run behind Gunicorn or similar rather than the built-in
   development server, and put it behind HTTPS. Once TLS is in place, set
   `SESSION_COOKIE_SECURE=1` in `.env`.

No application code needs to change. The models avoid SQLite-specific types
for exactly this reason.

One thing this deliberately still leaves out:

- **Permission levels.** Every signed-in user can view, edit, and delete every
  record, and can add teammates. That suits a small trusted team; revisit it if
  the staff list grows.

---

## Development

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest          # 55 tests

# Run the same suite against PostgreSQL, to catch anything SQLite tolerates:
TEST_DATABASE_URL="postgresql+psycopg://user:pw@localhost:5432/crm_test" \
  .venv/bin/python -m pytest
```

On Windows, substitute `.\.venv\Scripts\` for `.venv/bin/` throughout.

Layout:

```
app/
  constants.py     The funnel vocabulary: stages, order, reasons. Edit here to change the pipeline.
  models.py        Database tables
  services.py      Stage-change rules and the audit trail
  reporting.py     All read-only funnel analytics
  views/           One blueprint per area (auth, dashboard, families, children, reports, users)
  templates/       Jinja templates
  static/css/      Brand styling
wsgi.py            Entry point
tests/             Funnel logic and route tests
```

To change the pipeline stages, decline reasons, withdrawal reasons, or referral
sources, edit **`app/constants.py`** — the forms, board, and reports all read
from it.

## Branding

Colors follow the daycare brand: primary red `#C81C22`, green `#93BD37`, neutrals
`#F2F2F2` / `#444444` / `#8C8D8E`. Headings use **Bebas Neue** and body text uses
**Poppins**, loaded from Google Fonts with system fallbacks, so the app still
reads correctly offline.

The red/green pairing used in charts was checked for color-vision deficiency
separation. Because the brand green is light against white, every chart bar is
directly labeled with its value and every chart is backed by a data table — no
figure depends on color alone.

The daycare's name is **not** stored in the code. Set `DAYCARE_NAME` in `.env`
locally, and in the host's environment variables in production; it appears in the
header, page titles, and the sign-in screen. This keeps the name out of the
repository, which matters while the repository is public.

To use the real logo, drop the logo file into `app/static/img/` and replace the
initials circle in `app/templates/base.html`. If your source file is an upscaled
screengrab, get the original artwork before using it for anything printed.
