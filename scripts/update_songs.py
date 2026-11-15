"""Write songs.json: the videos on the New Heaviness: Latest playlist, in playlist order,
and the date new videos last arrived ("updated").

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


def fetch(key: str) -> list[dict]:
    songs, page = [], None
    while True:
        q = {"part": "snippet", "maxResults": 50, "playlistId": PLAYLIST_ID, "key": key}
        if page:
            q["pageToken"] = page
        with urllib.request.urlopen(f"{API}?{urllib.parse.urlencode(q)}", timeout=30) as r:
            data = json.load(r)
        for item in data.get("items", []):
            s = item["snippet"]
            if s.get("title") in ("Private video", "Deleted video"):
                continue
            artist, song = split_title(s["title"], s.get("videoOwnerChannelTitle", ""))
            songs.append({"id": s["resourceId"]["videoId"], "artist": artist, "song": song})
        page = data.get("nextPageToken")
        if not page:
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
