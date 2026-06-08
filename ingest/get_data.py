from typing import Any


import os
from dotenv import load_dotenv
import googleapiclient.discovery
import google_auth_oauthlib.flow
import re

load_dotenv()

PLAYLIST_ID = os.getenv("PLAYLIST_ID")

scopes = ["https://www.googleapis.com/auth/youtube.readonly"]

def get_youtube_client():
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
    return youtube

def get_playlist_items(youtube, playlist_id):
    page_token = None
    while True:
        request = youtube.playlistItems().list(
            playlistId=playlist_id,
            part="snippet",
            maxResults=50,
            pageToken=page_token
        )
        response = request.execute()

        yield from response.get("items", [])
        page_token = response.get("nextPageToken")
        if not page_token:
            break

def get_descriptions(youtube, video_ids):
    descriptions = {}
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i+50]
        response = youtube.videos().list(
            part="snippet",
            id=",".join(batch),
        ).execute()
        for vid in response.get("items", []):
            vid_id = vid["id"]
            title = vid["snippet"]["title"]
            descriptions[(vid_id, title)] = vid["snippet"]["description"]
    return descriptions

def _is_song_entry(s: str) -> bool:
    """True if a line looks like an actual song list item (not commentary)."""
    if re.search(r'\d{1,2}:\d{2}\s+to\s+\d{1,2}:\d{2}', s, re.IGNORECASE):
        return False
    return bool(re.match(r'^\d', s))


def trim_description(desc):
    lines = desc.splitlines()

    first_idx = None
    last_idx = None
    for i, line in enumerate(lines):
        s = line.strip()
        if not re.search(r'\d{1,2}:\d{2}', s):
            continue
        if first_idx is None:
            if _is_song_entry(s):
                first_idx = i
                last_idx = i
        else:
            last_idx = i

    if first_idx is None:
        return desc

    return "\n".join(lines[first_idx : last_idx + 1])

_TS_PAT = re.compile(r'\[?\d{1,2}:\d{2}(?::\d{2})?\]?')
_ALAPANA_PAT = re.compile(r'\balaap?ana\b', re.IGNORECASE)
_RTP_PAT = re.compile(
    r'\bR\.?T\.?P\.?\b'
    r'|r[āa]?g[āa]?m[\s\W]*t[āa]?n[āa]?m[\s\W]*p[āa]?ll[āa]?v[iī]',
    re.IGNORECASE,
)
_RTP_SUB_PAT = re.compile(r'^\s*(ragam|tanam|pallavi)\b', re.IGNORECASE)


def _is_thani(s: str) -> bool:
    if re.search(r'\bthan[iy].*avarth?|\bavarth?.*than[iy]|\(w.*than[iy]', s, re.IGNORECASE):
        return True
    # Standalone "Thani" entry: bare label (after stripping number and timestamp) starts with thani/tani
    bare = _TS_PAT.sub('', s)
    bare = re.sub(r'^\s*\d+[\w]*[\s\.\-]+', '', bare).strip(' -:')
    return bool(re.match(r'than[iy]\b', bare, re.IGNORECASE))


def _strip_ab_prefix(s: str) -> str:
    """'2B. ' → '2. ', '10A-' → '10-'"""
    return re.sub(r'^(\s*\d+)[A-Za-z](\s*[\.\-])', r'\1\2', s)


def _normalize_rtp_line(s: str) -> str:
    s = re.sub(r'"[^"]*"', '', s)           # remove quoted lyrics
    s = re.sub(r'\([^)]{15,}\)', '', s)     # remove long parentheticals (likely lyrics)
    s = _RTP_PAT.sub('RTP', s)
    s = re.sub(r'\s*-\s*-\s*', ' - ', s)   # collapse double dashes left by removals
    s = re.sub(r'\s+', ' ', s).strip().rstrip(' -')
    return s


def normalize_description(text: str) -> str:
    lines = text.splitlines()
    result: list[str] = []
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if not s:
            i += 1
            continue

        # Multi-line RTP: header has RTP phrase but no timestamp
        if _RTP_PAT.search(s) and not _TS_PAT.search(s):
            num_m = re.match(r'^(\d+\w*[\.\-\s]+)', s)
            prefix = num_m.group(1).rstrip() if num_m else ''
            raga_text = _RTP_PAT.sub('', s).strip(' -:')
            raga = re.split(r'\s*[-:]\s*', raga_text)[0].strip()
            first_ts = None
            thani_in_rtp = False
            j = i + 1
            while j < len(lines):
                sub = lines[j].strip()
                if not sub:
                    j += 1
                    continue
                if _RTP_SUB_PAT.match(sub):
                    if first_ts is None:
                        m = _TS_PAT.search(sub)
                        if m:
                            first_ts = m.group()
                    j += 1
                elif _is_thani(sub):
                    thani_in_rtp = True
                    j += 1
                else:
                    break
            rtp_body = ' - '.join(['RTP'] + ([raga] if raga else []))
            if first_ts:
                rtp_body += f' {first_ts}'
            line_out = f'{prefix} {rtp_body}'.strip() if prefix else rtp_body
            if thani_in_rtp:
                line_out += ' (w/ thani)'
            result.append(line_out)
            i = j
            continue

        # Single-line RTP
        if _RTP_PAT.search(s):
            result.append(_normalize_rtp_line(s))
            i += 1
            # Skip continuation sub-lines (pallavi/ragam/tanam without a number prefix)
            while i < len(lines):
                sub = lines[i].strip()
                if not sub:
                    i += 1
                    continue
                if _RTP_SUB_PAT.match(sub) and not re.match(r'^\d', sub):
                    i += 1
                else:
                    break
            continue

        # Alapana: apply alapana's timestamp to the following song line
        if _ALAPANA_PAT.search(s):
            ts_m = _TS_PAT.search(s)
            if ts_m:
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j < len(lines):
                    next_s = lines[j].strip()
                    if not _ALAPANA_PAT.search(next_s) and not _is_thani(next_s):
                        if _TS_PAT.search(next_s):
                            merged = _TS_PAT.sub(ts_m.group(), next_s, count=1)
                        else:
                            merged = next_s + f' {ts_m.group()}'
                        result.append(_strip_ab_prefix(merged))
                        i = j + 1
                        continue
            i += 1
            continue

        # Thani avartanam: append marker to preceding song
        if _is_thani(s):
            if result:
                result[-1] = _strip_ab_prefix(result[-1]) + ' (w/ thani)'
            i += 1
            continue

        result.append(s)
        i += 1

    return '\n'.join(result)


def sort_descriptions(playlist_descs):
    desc_timestamps = {}
    comment_timestamps = {}

    for (vid, title), desc in playlist_descs.items():
        if re.search(r"(\d{1,2}:\d{2})", desc) is not None:
            desc_timestamps[(vid, title)] = normalize_description(trim_description(desc))
        else:
            comment_timestamps[(vid, title)] = desc
    return desc_timestamps, comment_timestamps

def main():
    youtube = get_youtube_client()
    
    playlist_items = list[Any](get_playlist_items(youtube, PLAYLIST_ID))
    video_ids = [i["snippet"]["resourceId"]["videoId"] for i in playlist_items]

    playlist_descs = get_descriptions(youtube, video_ids)
    desc_timestamps, comment_timestamps = sort_descriptions(playlist_descs)

    output_path = os.path.join(os.path.dirname(__file__), "desc_timestamps.txt")
    with open(output_path, "w", encoding="utf-8") as f:
        for (vid, title), desc in desc_timestamps.items():
            f.write(f"=== {vid} | {title} ===\n")
            f.write(desc)
            f.write("\n\n")
    print(f"Wrote {len(desc_timestamps)} descriptions to {output_path}")

if __name__ == "__main__":
    main()