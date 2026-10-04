# In a Tree ★

A **free, 18+ Texas dating web app**. No payments, no premium tiers, no paywalls — anywhere, ever.

Adults-only: every signup validates 18+, and an age gate covers the front door.

## Features

- **Accounts** — email + password signup/login, passwords hashed (Werkzeug), cookie sessions
- **Profiles** — display name, age (18+ enforced), gender, Texas city, bio, interests, "looking for", photo upload
- **Browse** — swipe-free card deck: Like / Pass
- **Matching** — mutual likes create a match
- **Messaging** — private chat only between matched users (polls every 3s)
- **Safety** — report any profile, block anyone, dedicated safety-tips page
- **Owner dashboard** — review open reports, dismiss them or ban users; basic site stats
- **Demo mode** — optional, off by default; seeds clearly-labeled `DEMO - …` profiles for testing. Never presented as real people.

## Stack

Python 3 + Flask + SQLite (stdlib) + plain HTML/CSS/JS. One dependency: Flask.

## Run it locally

```bash
cd texas-dating-app
pip install -r requirements.txt

# configure (optional but recommended)
cp .env.example .env
# then edit .env: set SECRET_KEY (generate with: python3 -c "import secrets; print(secrets.token_hex(32))")
# and ADMIN_EMAIL to the email you'll sign up with — that account becomes admin.

# load .env into your shell (or export the vars manually)
set -a; source .env; set +a

python app.py
```

Open http://localhost:5000. Sign up (age 18+ required), complete your profile, and browse.

To try it with sample data: `DEMO_MODE=true python app.py` — demo profiles are
labeled `DEMO PROFILE — not a real person` everywhere they appear.

## Deploy it (Render example)

1. Push this folder to a GitHub repo.
2. On [Render](https://render.com): **New → Web Service**, connect the repo.
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn app:app` (add `gunicorn` to requirements, or use `python app.py`)
   - Add a **persistent disk** mounted at `/data` and set env var `DATABASE_PATH=/data/dating.db`
     (otherwise your database wipes on every deploy/restart).
3. Set environment variables on Render: `SECRET_KEY` (long random string),
   `ADMIN_EMAIL` (your email), `DEMO_MODE=false`.
4. Same idea on [Railway](https://railway.app): new project from repo, add a
   volume for the SQLite file, set the same env vars.

Free tiers work fine for getting started.

## What it still needs before real users

- **A domain + HTTPS** — Render/Railway give you both on their free subdomains.
- **Moderation effort** — this is the real cost of a dating site. Review reports
  in the owner dashboard regularly, ban fakes fast.
- **Email verification** — currently anyone can sign up with any email. Add a
  verification step before launch to cut spam accounts.
- **Rate limiting / CAPTCHA** on signup and login to slow bots.
- **Photo moderation** — uploads are file-type checked but not content-checked.
- **Backups** — back up the SQLite file regularly (or move to Postgres later).
- **Legal basics** — a privacy policy and terms of service before you take real
  signups. Talk to a lawyer; this README isn't legal advice.

## Project layout

```
app.py               Flask app: pages + JSON API + SQLite
schema.sql           Database schema
requirements.txt     Flask only
.env.example         Copy to .env; secrets live in env vars, never in code
templates/           Jinja HTML pages (base, index, signup, login, browse,
                     profile, matches, chat, safety, admin)
static/css/style.css Dark, bold Texas theme
static/js/app.js     Shared fetch helpers, auth UI, age gate
static/uploads/      User photo uploads (created at runtime)
```

## API overview

`POST /api/signup` · `POST /api/login` · `POST /api/logout` · `GET /api/me`
`GET/PUT /api/profile` · `POST /api/profile/photo`
`GET /api/browse` · `POST /api/like` · `GET /api/matches`
`GET /api/matches/<id>` · `GET/POST /api/matches/<id>/messages`
`POST /api/report` · `POST /api/block` · `GET /api/blocks` · `DELETE /api/block/<id>`
`GET /api/admin/stats` · `GET /api/admin/reports` · `POST /api/admin/reports/<id>`
