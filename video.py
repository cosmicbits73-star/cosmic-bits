import os, sys, json, subprocess, requests

kind = sys.argv[1]
W, H = (1080, 1920) if kind == "short" else (1920, 1080)
data = json.load(open("out.json"))
key = os.environ["PIXABAY_KEY"]
GENERIC = ["space", "galaxy", "science"]
MAXP = 6.0      # durata massima di una singola clip
LEAD = 0.3      # la clip cambia un attimo prima che la voce dica il nuovo argomento

def run(cmd):
    subprocess.run(cmd, check=True)

def duration(path):
    out = subprocess.check_output(["ffprobe", "-v", "error",
        "-show_entries", "format=duration", "-of",
        "default=nw=1:nk=1", path])
    return float(out)

voice_len = duration("voice.mp3") + 0.5
segs = data["segments"]

# --- istanti di inizio di ogni segmento
try:
    starts = [t["start"] for t in json.load(open("timeline.json"))]
    assert len(starts) == len(segs)
except Exception:
    counts = [len(s["text"].split()) for s in segs]
    tot, cum, starts = sum(counts), 0, []
    for c in counts:
        starts.append(voice_len * cum / tot)
        cum += c
bounds = [0.0]
for s in starts[1:]:
    bounds.append(max(bounds[-1], s - LEAD))
bounds.append(voice_len)

# --- ricerca e download delle clip
search_cache, raw_cache = {}, {}

def clip_url(h):
    v = h["videos"].get("medium") or h["videos"].get("small")
    return v["url"] if v and v.get("url") else None

def urls_for(q):
    if q in search_cache:
        return search_cache[q]
    def s(term):
        r = requests.get("https://pixabay.com/api/videos/",
            params={"key": key, "q": term, "per_page": 20, "safesearch": "true"},
            timeout=30)
        r.raise_for_status()
        return r.json().get("hits", [])
    try:
        hits = s(q)
        if not hits and " " in q:
            hits = s(q.split()[-1])
    except Exception as e:
        print("Ricerca fallita:", q, e)
        hits = []
    urls = [u for u in (clip_url(h) for h in hits) if u]
    search_cache[q] = urls
    return urls

def get_raw(u):
    if u in raw_cache:
        return raw_cache[u]
    path = f"clips/raw{len(raw_cache)}.mp4"
    resp = requests.get(u, timeout=60)
    resp.raise_for_status()
    with open(path, "wb") as f:
        f.write(resp.content)
    raw_cache[u] = (path, duration(path))
    return raw_cache[u]

def encode(raw, length, out, extra_vf=""):
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
          f"crop={W}:{H},fps=30,setsar=1{extra_vf}")
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-t", f"{length:.3f}",
         "-vf", vf, "-an", "-c:v", "libx264", "-preset", "veryfast",
         "-pix_fmt", "yuv420p", out])

os.makedirs("clips", exist_ok=True)
parts, used, produced, n = [], set(), 0.0, 0

for i, seg in enumerate(segs):
    target_end = bounds[i + 1]
    kw = seg["keyword"]
    own = urls_for(kw)
    generic = [u for g in GENERIC for u in urls_for(g)]
    order = ([u for u in own if u not in used]
             + [u for u in generic if u not in used]
             + own + list(raw_cache.keys()))
    print(f"[{i + 1}/{len(segs)}] {kw}: {len(own)} clip trovate")
    for u in order:
        remaining = target_end - produced
        if remaining <= 0.05:
            break
        try:
            raw, sd = get_raw(u)
            use = min(remaining, sd, MAXP)
            if remaining - use < 1.0 and sd >= remaining:
                use = remaining
            if use < 0.3:
                continue
            out = f"clips/p{n}.mp4"
            n += 1
            encode(raw, use, out)
            produced += duration(out)
            parts.append(out)
            used.add(u)
        except Exception as e:
            print("Clip saltata:", e)
    gap = target_end - produced
    if gap > 0.1 and parts:
        padded = f"clips/p{n}.mp4"
        n += 1
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", parts[-1],
             "-vf", f"tpad=stop_mode=clone:stop_duration={gap:.3f}",
             "-an", "-c:v", "libx264", "-preset", "veryfast",
             "-pix_fmt", "yuv420p", padded])
        produced += gap
        parts[-1] = padded

if not parts:
    raise SystemExit("Nessuna clip utilizzabile")
print("Clip usate:", len(parts), "- durata video:", round(produced, 1),
      "s - durata voce:", round(voice_len, 1), "s")

with open("list.txt", "w") as f:
    for p in parts:
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
