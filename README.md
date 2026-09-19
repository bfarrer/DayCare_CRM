# Red Fern Child Care — Enrollment CRM

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

```bash
# 1. Install dependencies into a local environment
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. Create your configuration file
cp .env.example .env

# 3. Generate a secret key and paste it into .env as SECRET_KEY=
python3 -c "import secrets; print(secrets.token_hex(32))"

# 4. Create the first staff account (this also creates the database)
export FLASK_APP=wsgi.py
.venv/bin/flask create-user

# 5. Start it
.venv/bin/python wsgi.py
```

Then open **http://127.0.0.1:5000** and sign in.

### Optional: load demo data

To see the funnel and reports populated before entering real families:

```bash
.venv/bin/flask seed-demo
```

This creates 12 fictional families and 25 students spread across every stage.
**Only run this on an empty database** — delete `instance/daycare_crm.sqlite3`
and start over when you're ready for real data.

### Adding your teammates

Sign in, go to **Team → Add team member**, and set a temporary password for each
person. Ask them to change it under **My account** after their first sign-in.
Everyone has the same permissions: all staff can view and edit every record.

---

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

## Going multi-user

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

Two things worth adding before real multi-user use, which this prototype
deliberately leaves out:

- **Database migrations** (Alembic / Flask-Migrate). Right now the schema is
  created with `db.create_all()`, which creates missing tables but does not alter
  existing ones. That is fine while the schema is settling; it is not fine once
  several people depend on the data.
- **Permission levels**, if you later decide not everyone should be able to
  delete records or manage accounts.

---

## Development

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest          # 39 tests
```

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

Colors follow the RFCC brand: primary red `#C81C22`, green `#93BD37`, neutrals
`#F2F2F2` / `#444444` / `#8C8D8E`. Headings use **Bebas Neue** and body text uses
**Poppins**, loaded from Google Fonts with system fallbacks, so the app still
reads correctly offline.

The red/green pairing used in charts was checked for color-vision deficiency
separation. Because the brand green is light against white, every chart bar is
directly labeled with its value and every chart is backed by a data table — no
figure depends on color alone.

To use the real logo, drop `RFCC_logo_transparent.png` into `app/static/img/` and
replace the `RF` circle in `app/templates/base.html`. Note the existing file is an
upscaled screengrab — get the original artwork for anything printed.
