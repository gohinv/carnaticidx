import json
import os

import googleapiclient.discovery
import google_auth_oauthlib.flow


scopes = ["https://www.googleapis.com/auth/youtube.readonly"]

def main():
    # Disable OAuthlib's HTTPS verification when running locally.
    # *DO NOT* leave this option enabled in production.
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

    api_service_name = "youtube"
    api_version = "v3"
    client_secrets_file = "credentials-desktop.json"

    # Get credentials and create an API client
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
        client_secrets_file, scopes)
    credentials = flow.run_local_server(port=0)
    youtube = googleapiclient.discovery.build(
        api_service_name, api_version, credentials=credentials)

    request = youtube.playlists().list(
        part="snippet,contentDetails",
        maxResults=25,
        mine=True
    )
    response = request.execute()

    for playlist in response.get("items", []):
        snippet = playlist["snippet"]
        print(json.dumps({
            "id": playlist["id"],
            "title": snippet["title"],
            "itemCount": playlist["contentDetails"]["itemCount"],
        }, indent=2, ensure_ascii=False))
        print()

if __name__ == "__main__":
    main()








