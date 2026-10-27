import os, sys, json, requests
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

# Orari di uscita (ora italiana). Modificali qui se vuoi cambiarli.
SLOTS = {"long": ["08:00", "14:00", "20:00"],
         "short": ["11:00", "17:00", "22:00"]}
ROME = ZoneInfo("Europe/Rome")

def next_slot(kind, now=None):
    """Prossimo orario di uscita entro 3-90 minuti, altrimenti None."""
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(ROME)
    cands = []
    for add in (0, 1):
        day = (local + timedelta(days=add)).date()
        for hhmm in SLOTS[kind]:
            h, m = map(int, hhmm.split(":"))
            cands.append(datetime(day.year, day.month, day.day, h, m, tzinfo=ROME))
    for dt in sorted(cands):
        minutes = (dt - now).total_seconds() / 60
        if 3 <= minutes <= 90:
            return dt.astimezone(timezone.utc)
    return None

def build_meta(data, kind, privacy, publish_at):
    tags = [h.lstrip("#") for h in data["hashtags"]]
    hashtags = " ".join("#" + t for t in tags)
    if kind == "short":
        hashtags += " #Shorts"
    description = f'{data["description"]}\n\n{hashtags}'[:4900]
    status = {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}
    if publish_at:
        status["privacyStatus"] = "private"
        status["publishAt"] = publish_at.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return {
        "snippet": {
            "title": data["title"][:100],
            "description": description,
            "tags": tags,
            "categoryId": "28",
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "status": status,
    }

def main():
    kind = sys.argv[1]
    mode = sys.argv[2] if len(sys.argv) > 2 else "auto"
    data = json.load(open("out.json"))

    publish_at = None
    privacy = "public"
    if mode == "private":
        privacy = "private"
    elif mode == "auto":
        publish_at = next_slot(kind)
        if publish_at:
            print("Uscita programmata alle",
                  publish_at.astimezone(ROME).strftime("%d/%m %H:%M"), "(ora italiana)")
        else:
            print("Nessun orario vicino: pubblico subito")

    tok = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": os.environ["YT_CLIENT_ID"],
        "client_secret": os.environ["YT_CLIENT_SECRET"],
        "refresh_token": os.environ["YT_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }, timeout=30)
    if tok.status_code != 200:
        print(tok.text)
        tok.raise_for_status()
    access = tok.json()["access_token"]

    meta = build_meta(data, kind, privacy, publish_at)
    size = os.path.getsize("video.mp4")
    init = requests.post(
        "https://www.googleapis.com/upload/youtube/v3/videos"
        "?uploadType=resumable&part=snippet,status",
        headers={
            "Authorization": f"Bearer {access}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(size),
        },
        data=json.dumps(meta), timeout=60)
    if init.status_code != 200:
        print(init.text)
        init.raise_for_status()

    with open("video.mp4", "rb") as f:
        up = requests.put(init.headers["Location"],
                          headers={"Content-Type": "video/mp4"},
                          data=f, timeout=1800)
    if up.status_code not in (200, 201):
        print(up.text)
        up.raise_for_status()
    video_id = up.json()["id"]
    print("Caricato:", "https://youtu.be/" + video_id)

    # miniatura (solo video lunghi, se è stata creata)
    if os.path.exists("thumbnail.jpg"):
        with open("thumbnail.jpg", "rb") as f:
            th = requests.post(
                "https://www.googleapis.com/upload/youtube/v3/thumbnails/set",
                params={"videoId": video_id, "uploadType": "media"},
                headers={"Authorization": f"Bearer {access}",
                         "Content-Type": "image/jpeg"},
                data=f, timeout=120)
        if th.status_code == 200:
            print("Miniatura caricata")
        else:
            print("Miniatura non caricata:", th.status_code, th.text[:300])

if __name__ == "__main__":
    main()
