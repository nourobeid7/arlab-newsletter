"""One-time: get a Gmail refresh token for the bot to send mail as you."""
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")

print("\n" + "=" * 60)
print("SAVE THESE THREE VALUES — you'll paste them into GitHub Secrets:")
print("=" * 60)
print(f"\nGMAIL_CLIENT_ID:\n{creds.client_id}")
print(f"\nGMAIL_CLIENT_SECRET:\n{creds.client_secret}")
print(f"\nGMAIL_REFRESH_TOKEN:\n{creds.refresh_token}")
print("\n" + "=" * 60)
