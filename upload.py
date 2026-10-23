import os, sys, json, requests

kind = sys.argv[1]
privacy = sys.argv[2] if len(sys.argv) > 2 else "private"
data = json.load(open("out.json"))

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

tags = [h.lstrip("#") for h in data["hashtags"]]
hashtags = " ".join("#" + t for t in tags)
if kind == "short":
    hashtags += " #Shorts"
description = f'{data["description"]}\n\n{hashtags}'[:4900]

meta = {
    "snippet": {
        "title": data["title"][:100],
        "description": description,
        "tags": tags,
        "categoryId": "28",
        "defaultLanguage": "en",
        "defaultAudioLanguage": "en",
    },
    "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
}

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
                      data=f, timeout=900)
if up.status_code not in (200, 201):
    print(up.text)
    up.raise_for_status()
print("Pubblicato:", "https://youtu.be/" + up.json()["id"])
