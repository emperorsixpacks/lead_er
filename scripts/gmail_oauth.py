"""One-time Gmail OAuth flow to get a refresh token for the Gmail API.

This lets lead_er send email from your Gmail over HTTPS (works on Render,
where SMTP is blocked), without ever storing your password.

Usage:
  python scripts/gmail_oauth.py

1. In Google Cloud Console: create a project, enable the "Gmail API".
2. OAuth consent screen -> add yourself as a test user.
3. Credentials -> Create credentials -> OAuth client ID -> "Desktop app".
4. Download the JSON and save it as `client_secret.json` in the repo root.
5. Run this script and complete the browser flow.

It prints the three env vars to add to .env / Render:
  GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN
"""
import json
import os
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def main() -> int:
    secret_path = os.path.join(os.getcwd(), "client_secret.json")
    if not os.path.exists(secret_path):
        print("Missing client_secret.json in the repo root.", file=sys.stderr)
        print("See the docstring above for how to create it.", file=sys.stderr)
        return 1

    with open(secret_path) as f:
        secret = json.load(f)["installed"]

    flow = InstalledAppFlow.from_client_secrets_file(secret_path, SCOPES)
    creds = flow.run_local_server(port=0)

    print("\nAdd these to your .env (and Render env):\n")
    print(f"GMAIL_CLIENT_ID={secret['client_id']}")
    print(f"GMAIL_CLIENT_SECRET={secret['client_secret']}")
    print(f"GMAIL_REFRESH_TOKEN={creds.refresh_token}")
    print("\nKeep the refresh token secret — it lets anything send as your Gmail.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
