import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from get_data import get_youtube_client

load_dotenv()


def parse_iso_duration(iso: str) -> int:
    """Convert ISO 8601 duration (e.g. PT2H3M45S) to total seconds."""
    m = re.fullmatch(
        r'P(?:(\d+)D)?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?',
        iso,
    )
    if not m:
        return 0
    days, hours, minutes, seconds = (int(v or 0) for v in m.groups())
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def fetch_durations(youtube, video_ids: list[str]) -> dict[str, int]:
    """Fetch duration_seconds for up to 50 video IDs in one API call."""
    response = youtube.videos().list(
        part='contentDetails',
        id=','.join(video_ids),
        maxResults=50,
    ).execute()
    return {
        item['id']: parse_iso_duration(item['contentDetails']['duration'])
        for item in response.get('items', [])
    }


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'app'))
    from app import app, db, Concert

    youtube = get_youtube_client()

    with app.app_context():
        concerts = db.session.scalars(
            db.select(Concert).where(Concert.duration_seconds == None)  # noqa: E711
        ).all()

        if not concerts:
            print('All concerts already have durations.')
            return

        print(f'Fetching durations for {len(concerts)} concert(s)…')

        # Batch into groups of 50 (YouTube API limit)
        batch_size = 50
        updated = 0
        for i in range(0, len(concerts), batch_size):
            batch = concerts[i:i + batch_size]
            id_map = {c.youtube_id: c for c in batch}
            durations = fetch_durations(youtube, list(id_map.keys()))

            for youtube_id, secs in durations.items():
                if secs > 0:
                    id_map[youtube_id].duration_seconds = secs
                    updated += 1

            missing = set(id_map.keys()) - set(durations.keys())
            for youtube_id in missing:
                print(f'  WARNING: no data returned for {youtube_id} (private/deleted?)')

            db.session.commit()
            print(f'  Committed batch {i // batch_size + 1} ({min(i + batch_size, len(concerts))}/{len(concerts)})')

        print(f'Done. Updated {updated}/{len(concerts)} concert(s).')


if __name__ == '__main__':
    main()
