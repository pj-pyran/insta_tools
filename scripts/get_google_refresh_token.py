"""One-time helper: obtain a Google OAuth refresh token for Drive access.

Run locally (not in CI). Requires a Google Cloud OAuth client of type
"Desktop app" with the Drive API enabled on the project.

Usage:
    python scripts/get_google_refresh_token.py <client_id> <client_secret>

Prints the refresh token to store as the GOOGLE_REFRESH_TOKEN secret.
"""

from __future__ import annotations

import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/drive"]


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    client_id, client_secret = sys.argv[1], sys.argv[2]
    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=0)

    print("\nGOOGLE_REFRESH_TOKEN=", creds.refresh_token, sep="")


if __name__ == "__main__":
    main()
