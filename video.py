import os, sys, json, math, subprocess, requests

kind = sys.argv[1]
W, H = (1080, 1920) if kind == "short" else (1920, 1080)
data = json.load(open("out.json"))
key = os.environ["PIXABAY_KEY"]
CLIP = 5
GENERIC = ["space", "galaxy", "science"]

def run(cmd):
    subprocess.run(cmd, check=True)

def duration(path):
    out = subprocess.check_output(["ffprobe", "-v", "error",
        "-show_entries", "format=duration", "-of",
        "default=nw=1:nk=1", path])
    return float(out)

voice_len = duration("voice.mp3") + 0.5
need = math.ceil(voice_len / CLIP)

def search(q):
    r = requests.get("https://pixabay.com/api/videos/",
        params={"key": key, "q": q, "per_page": 20, "safesearch": "true"},
        timeout=30)
    r.raise_for_status()
    return r.json().get("hits", [])

def clip_url(h):
    v = h["videos"].get("medium") or h["videos"].get("small")
    return v["url"] if v and v.get("url") else None

def pick(q, count, seen):
    hits = search(q)
    if not hits and " " in q:
        hits = search(q.split()[-1])
    got = []
    for h in hits:
        u = clip_url(h)
        if u and u not in seen:
            seen.add(u)
            got.append(u)
            if len(got) >= count:
                break
    return got

kws = [k.strip() for k in data["keywords"] if k.strip()] or GENERIC
per = max(1, math.ceil(need / len(kws)))
seen, urls = set(), []
for kw in kws:
    found = pick(kw, per, seen)
    print(f"{kw}: {len(found)} clip")
    urls += found
for kw in GENERIC:
    if len(urls) >= need:
        break
    urls += pick(kw, need - len(urls), seen)
print("Clip trovate:", len(urls), "su", need, "necessarie")

os.makedirs("clips", exist_ok=True)
parts = []
for i, u in enumerate(urls[:need]):
    raw, out = f"clips/raw{i}.mp4", f"clips/c{i}.mp4"
    try:
        resp = requests.get(u, timeout=60)
        resp.raise_for_status()
        with open(raw, "wb") as f:
            f.write(resp.content)
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-t", str(CLIP),
             "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                    f"crop={W}:{H},fps=30,setsar=1",
             "-an", "-c:v", "libx264", "-preset", "veryfast",
             "-pix_fmt", "yuv420p", out])
        parts.append(out)
    except Exception as e:
        print("Clip saltata:", e)

if not parts:
    raise SystemExit("Nessuna clip utilizzabile")

seq, t, j = [], 0, 0
while t < voice_len:
    p = parts[j % len(parts)]
    seq.append(p)
    t += duration(p)
    j += 1
with open("list.txt", "w") as f:
    for p in seq:
        f.write(f"file '{p}'\n")

margin = 70 if kind == "short" else 15
style = ("FontName=DejaVu Sans,Bold=1,FontSize=12,"
         "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
         f"BorderStyle=1,Outline=3,Shadow=0,Alignment=2,MarginV={margin}")
subs = f"subtitles=subs.srt:force_style='{style}'" if os.path.exists("subs.srt") else None
font = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
       "-i", "list.txt", "-i", "voice.mp3"]
if os.path.exists("logo.png"):
    lw = 250 if kind == "short" else 170
    pos = "40:150" if kind == "short" else "W-w-40:40"
    first = f"[0:v]{subs}[s]" if subs else "[0:v]null[s]"
    cmd += ["-i", "logo.png", "-filter_complex",
            f"{first};[2:v]scale={lw}:-1,format=rgba[lg];[s][lg]overlay={pos}[v]",
            "-map", "[v]", "-map", "1:a"]
else:
    brand = (f"drawtext=fontfile={font}:text='COSMIC BITS':"
             f"fontcolor=white:fontsize={H // 28}:borderw=3:x=w-tw-40:y=40")
    vf = f"{subs},{brand}" if subs else brand
    cmd += ["-vf", vf, "-map", "0:v", "-map", "1:a"]
cmd += ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", "video.mp4"]
run(cmd)
print("Video creato")
