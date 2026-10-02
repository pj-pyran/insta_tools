# Auto Insta Export — Lightroom Classic plugin

Watches your catalog for photos tagged `for_export`, exports them as
Instagram-ready JPEGs straight into the Google Drive sync folder used by
`instagram_autoupload`, writes a caption `.txt` per photo, and tags exported
photos `auto-exported` so they're never exported twice.

## How it works

- Runs a background task inside Lightroom (started automatically whenever
  Lightroom is open) that checks every 2 minutes (configurable) for photos
  with the `for_export` keyword that don't already have `auto-exported`.
- For each match: exports a full-quality JPEG, crops/resizes it to fit
  Instagram's supported aspect ratio range (4:5 to 1.91:1) at up to
  1080×1350px, writes a same-named caption `.txt`, and tags the photo
  `auto-exported` in the catalog (both keywords are kept permanently).
- You can also trigger a pass manually any time via
  **Library → Plug-in Extras → Auto Insta Export: Run Now**.
- There's no "drive connected" trigger — you open Lightroom to tag photos
  anyway, so the background task catches it from there automatically.

## One-time setup

### 1. Install the Lightroom Classic SDK (for development/debugging only)

You don't need the SDK to *run* the plugin — only if you want to edit it or
view its debug log more conveniently.

1. Download the SDK from Adobe's developer site (search "Lightroom Classic
   SDK download" — Adobe doesn't keep a stable direct link across versions).
2. It's a documentation + sample-plugins bundle; no installer step is
   required, it's just reference material.
3. For live debugging, the easier path is tailing the plugin's own log file
   (see Troubleshooting below) rather than using the SDK tooling directly.

### 2. Install the plugin into Lightroom

1. Open Lightroom Classic → **File → Plug-in Manager**.
2. Click **Add**, navigate to and select the
   `lightroom_plugin/AutoInstaExport.lrplugin` folder from this repo.
3. Confirm it shows as **Installed and running** with no errors.

### 3. Configure the export folder / keywords

Edit `AutoInstaExport.lrplugin/Config.lua` if any of these differ for you:

| Setting | Default |
| --- | --- |
| `exportFolder` | Your Google Drive sync path for `_insta_auto` |
| `forExportKeywordName` | `for_export` |
| `autoExportedKeywordName` | `auto-exported` |
| `captionText` | Default caption appended to every export |
| `pollIntervalSeconds` | `120` |

Reload the plugin (Plug-in Manager → select it → **Reload Plug-in**) after
editing `Config.lua`.

### 4. Tag and export photos

1. In Lightroom, select photos and add the `for_export` keyword (create it
   once via the Keywording panel if it doesn't exist yet).
2. Wait up to `pollIntervalSeconds`, or trigger immediately via
   **Library → Plug-in Extras → Auto Insta Export: Run Now**.
3. Exported JPEGs + caption `.txt` files land in the configured folder, which
   syncs automatically via Google Drive for Desktop — no Drive API/OAuth
   needed for this half of the pipeline.
4. The `instagram_autoupload` GitHub Actions workflow picks them up from
   there on its own weekly schedule.

## Troubleshooting

- The plugin logs to Lightroom's standard plugin log file. Enable logging by
  keeping `logger:enable('logfile')` (already set) and find the output at:
  `~/Library/Logs/Adobe/Lightroom/LrClassicLogs/AutoInstaExport.log`
  (macOS) — tail it while testing:
  ```
  tail -f ~/Library/Logs/Adobe/Lightroom/LrClassicLogs/AutoInstaExport.log
  ```
- If no photos export, confirm the `for_export` keyword name matches exactly
  (case-sensitive) and that the photos don't already have `auto-exported`.
- If cropping/resizing looks wrong, the plugin shells out to macOS's built-in
  `sips` tool — confirm `sips -g pixelWidth <file>` works from a terminal.
- Aspect-ratio handling: photos are **cropped** (not padded) to fit between
  4:5 and 1.91:1 before resizing, matching what Instagram would otherwise
  crop automatically.
