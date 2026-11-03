# insta_tools

Posts one photo per week from a Google Drive queue to an Instagram professional
account, running on a GitHub Actions schedule.

## How it works

Each run (`src/instagram_autoupload/main.py`):

1. Looks in the Google Drive queue for a subfolder named after today's date
   (or `POST_DATE`, `YYYY-MM-DD`) and posts its photos together as one
   carousel (max 10). No such folder means nothing is posted.
   See "Queue layout" below.
2. Downloads the photos and the matching `<name>.txt` caption file (optional;
   the first photo in the post that has one is used).
3. Temporarily uploads the photos as GitHub Release assets to get public
   URLs (required by the Instagram API, which fetches the images itself).
4. Creates Instagram media container(s) (a carousel if several photos), polls
   until ready, and publishes.
5. Deletes the temporary release/asset.
6. Moves the posted photos (and caption) into `posted/<date>/` in Drive.
7. Refreshes the Instagram long-lived access token and rewrites the
   `IG_ACCESS_TOKEN` GitHub secret so it never expires between runs.

If any step fails, the run exits non-zero and
shows up as a failed GitHub Actions run — no other notification is sent.

### Queue layout

Both Lightroom exporters (cloud and Classic) put each photo in a subfolder of
the queue named by its planned post date, `YYYY-MM-DD/NNN-<original file name>.jpg`:

- Folder name = planned post date (defaults to the capture date, so everything
  shot on one day is one carousel). The upload job picks the folder by name.
- `NNN` – order of the photo within the post; the original file name is kept
  so you can match photos to the catalog.
- Photos with no capture date go in `undated/`, which is never posted until
  you rename it to a date.

To reschedule, rename the folder in Drive; to split or merge posts, move
photos (and their same-named `.txt` captions) between folders.

### Lightroom cloud export (optional, feeds the same queue)

A separate daily workflow (`src/instagram_autoupload/lightroom_cloud_main.py`,
`.github/workflows/lightroom_cloud_export.yml`) pulls photos from Lightroom's
cloud catalog (not Lightroom Classic) into the same Drive queue:

1. Tag photos for export by adding them to a Lightroom cloud album named
   **"for Instagram auto-export"** (create it once in the Lightroom mobile/web/
   desktop cloud app — the API has no per-photo keyword/tag field, so an
   album is the closest equivalent to the Classic plugin's `for_insta` keyword).
2. The script lists that album, skips anything already present in a second
   **"Instagram auto-exported"** album (the dedup mechanism, since the API
   can't remove a single asset from an album membership check), generates a
   JPEG export per new asset, crops/resizes it to Instagram's spec
   (`image_processing.py`, same constraints as the Classic plugin), and
   uploads the photo + a default caption `.txt` into the Drive queue folder.
3. Exported assets are added to "Instagram auto-exported" so they're never
   re-exported.
4. Adobe rotates the refresh token on every use, so the script writes the new
   one back to the `ADOBE_REFRESH_TOKEN` GitHub secret each run (same pattern
   as the Instagram token rotation).

**Caveat:** Adobe's standard OAuth app does not get a token that survives
indefinitely without additional Adobe approval for some capabilities (see
their docs) — if authentication ever starts failing, re-run the one-time
setup below to get a fresh refresh token.

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

### 5. Adobe Developer Console (Lightroom cloud export, optional)

1. Log into [console.adobe.io](https://console.adobe.io/), create a project,
   add the **Lightroom APIs** API.
2. Choose an **OAuth Web App** credential, set a default redirect URI (e.g.
   `https://localhost/`), note the **Client ID** and **Client Secret**.
3. On the credential's Scopes tab, ensure `openid`, `offline_access`,
   `lr_partner_apis`, and `lr_partner_rendition_apis` are selected.
4. Visit this URL, log in with the Adobe account tied to your Lightroom
   cloud catalog, and approve access:

   ```
   https://ims-na1.adobelogin.com/ims/authorize/v2
     ?client_id=<CLIENT_ID>
     &redirect_uri=<REDIRECT_URI>
     &scope=openid,offline_access,lr_partner_apis,lr_partner_rendition_apis
     &response_type=code
   ```

5. Copy the `code` query param from the URL you land on, then run promptly
   (codes are single-use and expire quickly):

   ```
   python scripts/get_adobe_refresh_token.py <client_id> <client_secret> <redirect_uri> <code>
   ```

   This prints `ADOBE_REFRESH_TOKEN` — add it, `ADOBE_CLIENT_ID`, and
   `ADOBE_CLIENT_SECRET` as GitHub repo secrets.
6. In the Lightroom cloud app (mobile/web/desktop), create an album named
   **"for Instagram auto-export"** and add photos to it when you want them
   picked up.

### 6. Repo secrets summary

| Secret | Description |
| --- | --- |
| `IG_USER_ID` | Instagram professional account ID |
| `IG_ACCESS_TOKEN` | Long-lived Instagram access token (auto-rotated) |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Drive OAuth client |
| `GOOGLE_REFRESH_TOKEN` | Drive OAuth refresh token |
| `GDRIVE_FOLDER_ID` | Drive folder holding the photo queue |
| `GH_PAT_SECRETS` | PAT used to rotate `IG_ACCESS_TOKEN` and `ADOBE_REFRESH_TOKEN` |
| `ADOBE_CLIENT_ID` / `ADOBE_CLIENT_SECRET` | Adobe OAuth Web App credential |
| `ADOBE_REFRESH_TOKEN` | Adobe refresh token (auto-rotated; optional, only for cloud export) |

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
