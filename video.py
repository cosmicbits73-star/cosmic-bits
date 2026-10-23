import os, sys, json, subprocess, requests

kind = sys.argv[1]
W, H = (1080, 1920) if kind == "short" else (1920, 1080)
data = json.load(open("out.json"))
key = os.environ["PIXABAY_KEY"]
CLIP = 5
HITS = 3 if kind == "short" else 6

def run(cmd):
    subprocess.run(cmd, check=True)

def duration(path):
    out = subprocess.check_output(["ffprobe", "-v", "error",
        "-show_entries", "format=duration", "-of",
        "default=nw=1:nk=1", path])
    return float(out)

voice_len = duration("voice.mp3") + 0.5

def search(q):
    r = requests.get("https://pixabay.com/api/videos/",
        params={"key": key, "q": q, "per_page": 10}, timeout=30)
    r.raise_for_status()
    return r.json().get("hits", [])

urls = []
for kw in data["keywords"] + ["space", "galaxy", "science"]:
    for h in search(kw)[:HITS]:
        v = h["videos"].get("medium") or h["videos"]["small"]
        if v["url"] and v["url"] not in urls:
            urls.append(v["url"])

os.makedirs("clips", exist_ok=True)
parts, total = [], 0
for i, u in enumerate(urls):
    if total >= voice_len:
        break
    raw, out = f"clips/raw{i}.mp4", f"clips/c{i}.mp4"
    with open(raw, "wb") as f:
        f.write(requests.get(u, timeout=60).content)
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-t", str(CLIP),
         "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                f"crop={W}:{H},fps=30,setsar=1",
         "-an", "-c:v", "libx264", "-preset", "veryfast",
         "-pix_fmt", "yuv420p", out])
    parts.append(out)
    total += duration(out)

if not parts:
    raise SystemExit("Nessuna clip trovata")

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
if os.path.exists("assets/logo.png"):
    cmd += ["-i", "assets/logo.png"]
    first = f"[0:v]{subs}[s];" if subs else "[0:v]null[s];"
    cmd += ["-filter_complex",
            f"{first}[2:v]scale={W // 5}:-1[lg];[s][lg]overlay=W-w-30:30[v]",
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
