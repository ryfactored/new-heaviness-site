"""Write songs.json: the videos on the New Heaviness: Latest playlist, in playlist order,
and the date new videos last arrived ("updated").

Each song has the date it was added to the playlist ("added") and its views per day since
upload ("vpd"), which the home page uses for its New and Popular orders.

Run by .github/workflows/songs.yml. Needs YOUTUBE_API_KEY (a YouTube Data API v3 key).
"""
import datetime
import json
import os
import re
import urllib.parse
import urllib.request

PLAYLIST_ID = "PLQJf2JuUxsz0"
API = "https://www.googleapis.com/youtube/v3/playlistItems"
VIDEOS_API = "https://www.googleapis.com/youtube/v3/videos"

# Bracketed bits like "(Official Music Video)", "[4K]", "| Napalm Records".
NOISE = re.compile(
    r"\s*[\(\[][^\)\]]*\b(official|video|visuali[sz]er|lyric|lyrics|audio|hd|4k|uncensored|explicit)\b[^\)\]]*[\)\]]",
    re.I,
)
PIPE_TAIL = re.compile(r"\s*\|.*$")
# A trailing ' - Official Music Video', 'OFFICIAL VIDEO (Death Metal) ...' and the like.
DASH_TAIL = re.compile(r"\s*[-–—]?\s*\b(official\b|music video\b|visuali[sz]er\b|lyric video\b).*$", re.I)
# 'Silent Planet "fangs!!"' when a label's name came first.
QUOTED = re.compile(r'^(.+?)\s+["“](.+?)["”]?$')
DASH = re.compile(r"\s+[-–—]\s+")


def split_title(title: str, channel: str) -> tuple[str, str]:
    t = DASH_TAIL.sub("", PIPE_TAIL.sub("", NOISE.sub("", title))).strip()
    parts = DASH.split(t, maxsplit=1)
    if len(parts) == 2:
        artist, song = parts
    else:
        artist, song = re.sub(r"\s*-\s*Topic$", "", channel or ""), t
    artist, song = artist.strip(), song.strip()
    m = QUOTED.match(song)
    if artist.casefold() == (channel or "").casefold():
        # A label's channel put its own name first: 'Label - Band "Song"' or 'Label - Band -Song'.
        if m:
            artist, song = m.group(1), m.group(2)
        elif len(rest := re.split(r"\s+-\s*", song, maxsplit=1)) == 2:
            artist, song = rest
    return artist.strip(), song.strip("\"'“”‘’ ")


def get(url: str, query: dict) -> dict:
    with urllib.request.urlopen(f"{url}?{urllib.parse.urlencode(query)}", timeout=30) as r:
        return json.load(r)


def parse_time(value: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))


def views_per_day(key: str, songs: list[dict], uploaded: dict[str, str]) -> None:
    """Set each song's "vpd": views since upload divided by days since upload (at least 1)."""
    now = datetime.datetime.now(datetime.timezone.utc)
    for i in range(0, len(songs), 50):
        batch = songs[i:i + 50]
        data = get(VIDEOS_API, {"part": "statistics", "id": ",".join(s["id"] for s in batch), "key": key})
        views = {v["id"]: int(v.get("statistics", {}).get("viewCount", 0)) for v in data.get("items", [])}
        for s in batch:
            up = uploaded.get(s["id"])
            days = max(1.0, (now - parse_time(up)).total_seconds() / 86400) if up else 1.0
            s["vpd"] = round(views.get(s["id"], 0) / days)


def fetch(key: str) -> list[dict]:
    songs, uploaded, page = [], {}, None
    while True:
        q = {"part": "snippet,contentDetails", "maxResults": 50, "playlistId": PLAYLIST_ID, "key": key}
        if page:
            q["pageToken"] = page
        data = get(API, q)
        for item in data.get("items", []):
            s = item["snippet"]
            if s.get("title") in ("Private video", "Deleted video"):
                continue
            vid = s["resourceId"]["videoId"]
            artist, song = split_title(s["title"], s.get("videoOwnerChannelTitle", ""))
            # snippet.publishedAt on a playlist item is when it was added to the playlist.
            songs.append({"id": vid, "artist": artist, "song": song, "added": s["publishedAt"][:10]})
            if item.get("contentDetails", {}).get("videoPublishedAt"):
                uploaded[vid] = item["contentDetails"]["videoPublishedAt"]
        page = data.get("nextPageToken")
        if not page:
            break
    views_per_day(key, songs, uploaded)
    return songs


def main() -> None:
    songs = fetch(os.environ["YOUTUBE_API_KEY"])
    try:
        with open("songs.json", encoding="utf-8") as f:
            previous = json.load(f)
    except (OSError, ValueError):
        previous = {}
    seen = {s["id"] for s in previous.get("songs", [])}
    updated = previous.get("updated")
    # The date only moves when videos arrive, not when old ones are trimmed off Latest.
    if not updated or any(s["id"] not in seen for s in songs):
        updated = datetime.date.today().isoformat()
    with open("songs.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump({"playlist": PLAYLIST_ID, "updated": updated, "songs": songs}, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"{len(songs)} songs, updated {updated}")


if __name__ == "__main__":
    main()
