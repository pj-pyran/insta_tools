# insta_tools

Posts one photo per week from a Google Drive queue to an Instagram professional
account, running on a GitHub Actions schedule.

## How it works

Each run (`src/instagram_autoupload/main.py`):

1. Picks the next photo from a Google Drive folder (default: oldest first —
   see `selection.py` to change the strategy).
2. Downloads the photo and its matching `<name>.txt` caption file (optional).
3. Temporarily uploads the photo as a GitHub Release asset to get a public
   URL (required by the Instagram API, which fetches the image itself).
4. Creates an Instagram media container, polls until ready, and publishes it.
5. Deletes the temporary release/asset.
6. Moves the posted photo (and caption) into a `posted/` subfolder in Drive.
7. Refreshes the Instagram long-lived access token and rewrites the
   `IG_ACCESS_TOKEN` GitHub secret so it never expires between runs.

If the Drive queue is empty, or any step fails, the run exits non-zero and
shows up as a failed GitHub Actions run — no other notification is sent.

## One-time setup

### 1. Make the repo public

Required so `raw`/release asset URLs are fetchable by Instagram's servers
without auth.

### 2. Meta App Dashboard (Instagram)

1. Create an app at [developers.facebook.com](https://developers.facebook.com/apps).
2. Add the **Instagram API setup with Instagram login** product.
3. Note the Instagram **app ID** and **app secret**.
4. Add a redirect URI (e.g. `https://localhost/`) under that product's settings.
5. Visit this URL in a browser, log in with the Instagram professional account,
   and approve access:

   ```
   https://www.instagram.com/oauth/authorize
     ?client_id=<IG_APP_ID>
     &redirect_uri=<REDIRECT_URI>
     &response_type=code
     &scope=instagram_business_basic,instagram_business_content_publish
   ```

6. Copy the `code` query param from the URL you land on, then run:

   ```
   python scripts/get_instagram_long_lived_token.py <app_id> <app_secret> <redirect_uri> <code>
   ```

   This prints `IG_USER_ID` and `IG_ACCESS_TOKEN` — add both as GitHub repo
   secrets immediately (see "Adding secrets to GitHub" below). Never paste
   them into a tracked file — the authorization `code` is single-use and
   expires in 1 hour, so re-run the authorize URL if it fails.

### 3. Google Cloud (Drive)

1. Create a project, enable the **Google Drive API**.
2. Create an OAuth client of type **Desktop app**, note the client ID/secret.
3. Run:

   ```
   pip install google-auth-oauthlib
   python scripts/get_google_refresh_token.py <client_id> <client_secret>
   ```

   Complete the browser consent flow; it prints `GOOGLE_REFRESH_TOKEN`.
4. Create a Drive folder for the photo queue, note its folder ID (from the
   URL), and save it as `GDRIVE_FOLDER_ID`.
5. Populate the folder with `photo1.jpg` + `photo1.txt` (caption) pairs, etc.

### 4. GitHub secrets rotation token

The workflow rewrites `IG_ACCESS_TOKEN` each run, which the default
`GITHUB_TOKEN` cannot do. Create a fine-grained PAT scoped to this repo only,
with **Secrets: Read and write** permission, and save it as the
`GH_PAT_SECRETS` repo secret.

### 5. Repo secrets summary

| Secret | Description |
| --- | --- |
| `IG_USER_ID` | Instagram professional account ID |
| `IG_ACCESS_TOKEN` | Long-lived Instagram access token (auto-rotated) |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Drive OAuth client |
| `GOOGLE_REFRESH_TOKEN` | Drive OAuth refresh token |
| `GDRIVE_FOLDER_ID` | Drive folder holding the photo queue |
| `GH_PAT_SECRETS` | PAT used only to rotate `IG_ACCESS_TOKEN` |

`GITHUB_TOKEN` is provided automatically by Actions (used for the temporary
release upload).

### Adding secrets to GitHub

The repo must already exist on GitHub (push it first if you haven't).

1. On GitHub, go to the repo's **Settings → Secrets and variables → Actions**.
2. Under the **Secrets** tab, click **New repository secret** for each row in
   the table above, pasting in the name and value exactly.
3. Never commit these values to any file — only store them as repo secrets.
   If a value was ever pasted into a local file, delete that file afterward.

## Schedule

Runs Monday 05:00 UTC (`.github/workflows/weekly_post.yml`), based on
engagement research suggesting early Monday mornings perform best. Trigger a
manual test run any time from the Actions tab via "Run workflow".

## Local development

```
python -m venv .venv && source .venv/bin/activate
pip install -e .
export IG_USER_ID=... IG_ACCESS_TOKEN=... GOOGLE_CLIENT_ID=... \
       GOOGLE_CLIENT_SECRET=... GOOGLE_REFRESH_TOKEN=... GDRIVE_FOLDER_ID=... \
       GITHUB_TOKEN=... GH_PAT_SECRETS=... GITHUB_REPOSITORY=<owner>/<repo>
python -m instagram_autoupload.main
```
