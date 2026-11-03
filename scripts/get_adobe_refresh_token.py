"""One-time helper: exchange an Adobe authorization code for a refresh token.

Prerequisites (done once in the Adobe Developer Console, console.adobe.io):
  1. Create a project, add the "Lightroom APIs" API.
  2. Choose an "OAuth Web App" credential.
  3. Set a default redirect URI, e.g. https://localhost/ (must be https,
     even for localhost).
  4. Note the generated Client ID (API key) and Client Secret.
  5. On the credential's "Scopes" tab, ensure these scopes are selected:
     openid, offline_access, lr_partner_apis, lr_partner_rendition_apis.

Authorization URL (open in a browser, log in with the same Adobe account
used by the Lightroom cloud app, approve access):
  https://ims-na1.adobelogin.com/ims/authorize/v2
    ?client_id=<CLIENT_ID>
    &redirect_uri=<REDIRECT_URI>
    &scope=openid,offline_access,lr_partner_apis,lr_partner_rendition_apis
    &response_type=code

After approving, you'll land on <REDIRECT_URI>?code=... - copy the code
value (it's single-use and expires quickly, run the command below promptly).

Usage:
    python scripts/get_adobe_refresh_token.py \
        <client_id> <client_secret> <redirect_uri> <authorization_code>

Prints the refresh token to store as the ADOBE_REFRESH_TOKEN secret.
"""

from __future__ import annotations

import sys

import requests

TOKEN_URL = "https://ims-na1.adobelogin.com/ims/token/v3"


def main() -> None:
    if len(sys.argv) != 5:
        print(__doc__)
        sys.exit(1)

    client_id, client_secret, redirect_uri, code = sys.argv[1:5]

    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    if "refresh_token" not in data:
        print("No refresh_token in response - was offline_access included in the scope?")
        print(data)
        sys.exit(1)

    print("\nADOBE_REFRESH_TOKEN=", data["refresh_token"], sep="")


if __name__ == "__main__":
    main()
