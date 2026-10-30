import os, sys, json, subprocess, requests, textwrap

kind = sys.argv[1]
W, H = (1080, 1920) if kind == "short" else (1920, 1080)
data = json.load(open("out.json"))
key = os.environ["PIXABAY_KEY"]
GENERIC = ["space", "galaxy", "science"]
MAXP = 6.0           # durata massima di una singola clip
LEAD = 0.3           # la clip cambia un attimo prima che la voce dica il nuovo argomento
HOOK_SECONDS = 2.8   # per quanti secondi resta la frase d'apertura (solo Shorts)
MUSIC_VOLUME = 0.10  # volume della musica di sottofondo (la voce è 1.0)

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

# --- frase d'apertura a schermo (solo Shorts)
hook = None
if kind == "short":
    hook_text = str(data.get("hook_text") or data.get("thumbnail_text") or "").strip().upper()
    if hook_text:
        with open("hook.txt", "w", encoding="utf-8") as f:
            f.write(textwrap.fill(hook_text, 14))
        hook = (f"drawtext=fontfile={font}:textfile=hook.txt:expansion=none:"
                "fontcolor=white:fontsize=80:line_spacing=14:"
                "borderw=5:bordercolor=black:"
                "box=1:boxcolor=black@0.5:boxborderw=28:"
                "x=(w-text_w)/2:y=h*0.25:"
                f"enable='between(t,0,{HOOK_SECONDS})'")
        print("Frase d'apertura:", hook_text)

# --- scritta fissa per invitare a iscriversi
if kind == "short":
    cta_pos, cta_size = "x=w-text_w-40:y=200", 44
else:
    cta_pos, cta_size = "x=40:y=40", 38
cta = (f"drawtext=fontfile={font}:text='FOLLOW FOR MORE':"
       f"fontcolor=white:fontsize={cta_size}:borderw=4:bordercolor=black:{cta_pos}")

vchain = ",".join(x for x in (subs, hook, cta) if x)

# --- montaggio finale: video + voce (+ musica) + logo
has_logo = os.path.exists("logo.png")
has_music = os.path.exists("music.mp3")

cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
       "-i", "list.txt", "-i", "voice.mp3"]
idx = 2
fc = [f"[0:v]{vchain}[s]"]
if has_logo:
    cmd += ["-i", "logo.png"]
    lw = 250 if kind == "short" else 170
    pos = "40:150" if kind == "short" else "W-w-40:40"
    fc.append(f"[{idx}:v]scale={lw}:-1,format=rgba[lg]")
    fc.append(f"[s][lg]overlay={pos}[v]")
    idx += 1
else:
    brand = (f"drawtext=fontfile={font}:text='COSMIC BITS':"
             f"fontcolor=white:fontsize={H // 28}:borderw=3:x=w-tw-40:y=40")
    fc.append(f"[s]{brand}[v]")
amap = "1:a"
if has_music:
    print("Musica di sottofondo: music.mp3")
    cmd += ["-stream_loop", "-1", "-i", "music.mp3"]
    fc.append(f"[1:a]volume=1.0[va];[{idx}:a]volume={MUSIC_VOLUME}[ma];"
              "[va][ma]amix=inputs=2:duration=first:dropout_transition=0,volume=2[a]")
    amap = "[a]"
cmd += ["-filter_complex", ";".join(fc), "-map", "[v]", "-map", amap,
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", "video.mp4"]
run(cmd)
print("Video creato")
