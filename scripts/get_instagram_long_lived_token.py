"""One-time helper: exchange an Instagram authorization code for a long-lived token.

Prerequisites (done once in the Meta App Dashboard):
  1. Create an app, add the "Instagram API setup with Instagram login" product.
  2. Note the Instagram app ID and app secret, and register a redirect URI
     (e.g. https://localhost/ for manual copy-paste use).
  3. Send yourself to the authorization URL below, log in, and copy the
     "code" query param from the redirect URL you land on.

Authorization URL (open in a browser):
  https://www.instagram.com/oauth/authorize
    ?client_id=<IG_APP_ID>
    &redirect_uri=<REDIRECT_URI>
    &response_type=code
    &scope=instagram_business_basic,instagram_business_content_publish

Usage:
    python scripts/get_instagram_long_lived_token.py \
        <app_id> <app_secret> <redirect_uri> <authorization_code>

Prints the long-lived access token and the IG user id.
"""

from __future__ import annotations

import sys

import requests

SHORT_LIVED_TOKEN_URL = "https://api.instagram.com/oauth/access_token"
LONG_LIVED_TOKEN_URL = "https://graph.instagram.com/access_token"


def main() -> None:
    if len(sys.argv) != 5:
        print(__doc__)
        sys.exit(1)

    app_id, app_secret, redirect_uri, code = sys.argv[1:5]

    short_lived_resp = requests.post(
        SHORT_LIVED_TOKEN_URL,
        data={
            "client_id": app_id,
            "client_secret": app_secret,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "code": code,
        },
        timeout=30,
    )
    short_lived_resp.raise_for_status()
    short_lived_data = short_lived_resp.json()
    short_lived_token = short_lived_data["access_token"]
    ig_user_id = short_lived_data["user_id"]

    long_lived_resp = requests.get(
        LONG_LIVED_TOKEN_URL,
        params={
            "grant_type": "ig_exchange_token",
            "client_secret": app_secret,
            "access_token": short_lived_token,
        },
        timeout=30,
    )
    long_lived_resp.raise_for_status()
    long_lived_token = long_lived_resp.json()["access_token"]

    print("\nIG_USER_ID=", ig_user_id, sep="")
    print("IG_ACCESS_TOKEN=", long_lived_token, sep="")


if __name__ == "__main__":
    main()
