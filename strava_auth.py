"""
Run once to get a Strava refresh token with activity:read_all scope.
Usage: py strava_auth.py
"""
import webbrowser
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from config import STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET

AUTH_CODE = None

class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        global AUTH_CODE
        params = parse_qs(urlparse(self.path).query)
        AUTH_CODE = params.get("code", [None])[0]
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"<h1>Authorized! You can close this tab.</h1>")

    def log_message(self, *args):
        pass


def main():
    url = (
        f"https://www.strava.com/oauth/authorize"
        f"?client_id={STRAVA_CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri=http://localhost:8765"
        f"&scope=activity:read_all"
    )
    print("Opening Strava authorization page...")
    webbrowser.open(url)
    print("Waiting for authorization...")

    server = HTTPServer(("localhost", 8765), _Handler)
    server.handle_request()

    if not AUTH_CODE:
        print("No code received. Try again.")
        return

    resp = requests.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": STRAVA_CLIENT_ID,
            "client_secret": STRAVA_CLIENT_SECRET,
            "code": AUTH_CODE,
            "grant_type": "authorization_code",
        },
    )
    data = resp.json()

    if "refresh_token" not in data:
        print(f"Error: {data}")
        return

    print("\n✅ Success! Add these to your .env:\n")
    print(f"STRAVA_REFRESH_TOKEN={data['refresh_token']}")
    print(f"\n(New access token expires: {data.get('expires_at', 'unknown')})")


if __name__ == "__main__":
    main()
