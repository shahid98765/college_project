# Deploying to Vercel with Postgres (Neon)

## What changed
- `app.py` now reads the database connection from the `DATABASE_URL`
  environment variable. If it's not set, it falls back to a local SQLite
  file (for running on your own machine).
- Removed the SQLite-only `PRAGMA table_info` migration check so it also
  works on Postgres.
- `requirements.txt` now includes `psycopg2-binary` (the Postgres driver).
- Added `vercel.json` so Vercel actually knows how to build and route to
  `app.py` (this was missing before, which is likely part of why nothing
  deployed correctly).
- Upload folder now points at `/tmp/uploads` when running on Vercel, since
  the rest of the filesystem is read-only there. Note: files saved to
  `/tmp` still won't persist between deployments/invocations — fine for a
  college project, but not for real file storage.

## Steps to deploy

1. **Create a free Postgres database on Neon**
   - Go to https://neon.tech, sign up, create a new project.
   - Copy the connection string it gives you (starts with
     `postgres://` or `postgresql://`).

2. **Set environment variables in Vercel**
   - In your Vercel project → Settings → Environment Variables, add:
     - `DATABASE_URL` = the Neon connection string
     - `SECRET_KEY` = any random string (used for Flask sessions)

3. **Push this project to GitHub and import it into Vercel** (or run
   `vercel` from this folder with the Vercel CLI).

4. **First request creates the tables automatically** — `app.py` calls
   `db.create_all()` at startup, so the schema and default admin/cashier
   users are created the first time the app runs against the new database.
   Default admin login is still `admin@inventory.com` / `admin123` —
   change this after your first deploy.

## Local development
Just run it as before — with no `DATABASE_URL` set, it uses a local
SQLite file automatically:
```
pip install -r requirements.txt
python app.py
```

## Fix applied (static CSS/JS not loading on Vercel)

**Problem:** `vercel.json` used the legacy `builds`/`routes` config, which only
deploys the files needed to build `app.py` — Flask's `static/` folder was
never uploaded to Vercel, so `/static/css/style.css` 404'd and the page
rendered as unstyled HTML.

**Fix:**
1. Copied `static/css` and `static/js` into a new `public/static/` folder.
   Vercel automatically serves anything under `public/` as a static asset,
   independent of the Python function.
2. Replaced `vercel.json` with Vercel's zero-config format (no `builds`/`routes`).
   Vercel now auto-detects Flask and serves `public/` + routes everything
   else to `app.py`.
3. No template changes needed — `{{ url_for('static', filename='css/style.css') }}`
   still renders `/static/css/style.css`, which now resolves to
   `public/static/css/style.css`.
4. Kept the original `static/` folder too, so local `flask run` development
   is unaffected.

After pulling this zip, just `git add . && git commit -m "Fix Vercel static assets" && git push`.
