import os, sys, json, subprocess, requests, textwrap

kind = sys.argv[1]
W, H = (1080, 1920) if kind == "short" else (1920, 1080)
data = json.load(open("out.json"))
key = os.environ["PIXABAY_KEY"]
GENERIC = ["space", "galaxy", "science"]
MAXP = 3.5 if kind == "short" else 5.0   # durata massima di una clip: più tagli = più ritmo
LEAD = 0.3           # la clip cambia un attimo prima che la voce dica il nuovo argomento
HOOK_SECONDS = 2.8   # per quanto resta la frase d'apertura (solo Shorts)
MUSIC_VOLUME = 0.18  # volume della musica di sottofondo (la voce è 1.0)
YELLOW = "&H00D7FF&"  # parola evidenziata
CYAN = "&HEBE100&"    # azzurro del logo
RED = "&H0000FF&"
GRAY = "&H3C3C3C&"

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
    # colori un po' più vivi per rendere le clip più accattivanti
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
          f"crop={W}:{H},fps=30,setsar=1,eq=saturation=1.15:contrast=1.05{extra_vf}")
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

# =====================================================================
# SCRITTE ANIMATE (sottotitoli a parola evidenziata, frase d'apertura,
# pulsante SUBSCRIBE animato, barra di avanzamento) in un unico file ASS
# =====================================================================
def ass_t(sec):
    cs = int(round(max(sec, 0) * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02}:{s:02}.{cs:02}"

def clean(t):
    return str(t).replace("{", "").replace("}", "").replace("\\", "").strip()

def group_lines(words):
    max_words, max_chars = (3, 15) if kind == "short" else (6, 36)
    lines, cur = [], []
    for w in words:
        cand = cur + [w]
        if cur and (len(cand) > max_words
                    or len(" ".join(x[0] for x in cand)) > max_chars):
            lines.append(cur)
            cur = []
        cur.append(w)
        if w[0][-1:] in ".!?":
            lines.append(cur)
            cur = []
    if cur:
        lines.append(cur)
    return lines

def rrect(w, h):
    r = h / 2
    return (f"m {r:.0f} 0 l {w - r:.0f} 0 b {w:.0f} 0 {w:.0f} {h:.0f} {w - r:.0f} {h:.0f} "
            f"l {r:.0f} {h:.0f} b 0 {h:.0f} 0 0 {r:.0f} 0")

CIRCLE = ("m 50 0 b 78 0 100 22 100 50 b 100 78 78 100 50 100 "
          "b 22 100 0 78 0 50 b 0 22 22 0 50 0")

def build_ass(words, total):
    if kind == "short":
        sub_fs, sub_out, sub_mv = 84, 8, 470
    else:
        sub_fs, sub_out, sub_mv = 58, 5, 55
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,DejaVu Sans,{sub_fs},&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,{sub_out},3,2,50,50,{sub_mv},1
Style: Hook,DejaVu Sans,88,&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,8,4,5,40,40,0,1
Style: Btn,DejaVu Sans,{64 if kind == "short" else 34},&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1
Style: Shape,DejaVu Sans,20,&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []

    # --- barra di avanzamento sottile in basso
    bar_h = 12
    ev.append(f"Dialogue: 0,{ass_t(0)},{ass_t(total)},Shape,,0,0,0,,"
              f"{{\\an7\\pos(0,{H - bar_h})\\p1\\bord0\\shad0\\1c{CYAN}\\fscx0"
              f"\\t(0,{int(total * 1000)},\\fscx100)}}m 0 0 l {W} 0 {W} {bar_h} 0 {bar_h}")

    # --- sottotitoli: parola evidenziata
    lines = group_lines(words)
    last_end = 0.0
    for li, ln in enumerate(lines):
        texts = [clean(w[0]) for w in ln]
        if kind == "short":
            texts = [t.upper() for t in texts]
        next_start = lines[li + 1][0][1] if li + 1 < len(lines) else total
        for i, w in enumerate(ln):
            start = max(w[1], last_end)
            if i + 1 < len(ln):
                end = ln[i + 1][1]
            else:
                end = min(w[2] + 0.15, next_start)
            end = max(end, start + 0.06)
            last_end = end
            shown = []
            for j, t in enumerate(texts):
                if j == i:
                    shown.append(f"{{\\c{YELLOW}}}{t}{{\\c&HFFFFFF&}}")
                else:
                    shown.append(t)
            ev.append(f"Dialogue: 1,{ass_t(start)},{ass_t(end)},Sub,,0,0,0,,{' '.join(shown)}")

    # --- frase d'apertura con effetto "pop" (solo Shorts)
    if kind == "short":
        hook_text = str(data.get("hook_text") or data.get("thumbnail_text") or "").strip().upper()
        hook_text = clean(hook_text)
        if hook_text:
            rows = textwrap.wrap(hook_text, 16)
            if len(rows) >= 2:
                rows[-1] = f"{{\\c{YELLOW}}}{rows[-1]}"
            txt = "\\N".join(rows)
            ev.append(f"Dialogue: 3,{ass_t(0)},{ass_t(HOOK_SECONDS)},Hook,,0,0,0,,"
                      f"{{\\an5\\pos({W // 2},{int(H * 0.27)})\\fad(80,250)\\fscx70\\fscy70"
                      f"\\t(0,200,\\fscx108\\fscy108)\\t(200,340,\\fscx100\\fscy100)}}{txt}")
            print("Frase d'apertura:", hook_text)

    # --- pulsante SUBSCRIBE animato: tocco, ondina e passaggio a "SUBSCRIBED"
    if kind == "short":
        cx, cy, h1 = W // 2, int(H * 0.30), 150
        w_red, w_gray = 520, 720
        times = [4.0, total - 5.5]
    else:
        h1 = 84
        w_red, w_gray = 290, 400
        cx, cy = 40 + w_gray // 2, 40 + h1 // 2
        times = [15.0, total * 0.5, total - 9.0]
    h2 = h1
    placed = []
    for t0 in times:
        if t0 < 1.0 or t0 + 3.6 > total or any(abs(t0 - p) < 6 for p in placed):
            continue
        placed.append(t0)
        a0, a1, a2 = ass_t(t0), ass_t(t0 + 1.5), ass_t(t0 + 3.5)
        pos = f"\\an5\\pos({cx},{cy})"
        pop = ("\\fscx0\\fscy0\\t(0,220,\\fscx112\\fscy112)\\t(220,380,\\fscx100\\fscy100)"
               "\\t(1120,1230,\\fscx90\\fscy90)")
        # fase 1: rosso "SUBSCRIBE"
        ev.append(f"Dialogue: 4,{a0},{a1},Shape,,0,0,0,,{{{pos}{pop}\\p1\\bord0\\shad0\\1c{RED}}}"
                  f"{rrect(w_red, h1)}")
        ev.append(f"Dialogue: 5,{a0},{a1},Btn,,0,0,0,,{{{pos}{pop}}}SUBSCRIBE")
        # fase 2: grigio "SUBSCRIBED ✓"
        back = ("\\fscx90\\fscy90\\t(0,160,\\fscx106\\fscy106)\\t(160,300,\\fscx100\\fscy100)"
                "\\fad(0,350)")
        ev.append(f"Dialogue: 4,{a1},{a2},Shape,,0,0,0,,{{{pos}{back}\\p1\\bord0\\shad0\\1c{GRAY}}}"
                  f"{rrect(w_gray, h2)}")
        ev.append(f"Dialogue: 5,{a1},{a2},Btn,,0,0,0,,{{{pos}{back}}}SUBSCRIBED \u2713")
        # ondina del "tocco"
        rx, ry = cx + int(w_red * 0.30), cy + int(h1 * 0.30)
        ev.append(f"Dialogue: 6,{ass_t(t0 + 1.15)},{ass_t(t0 + 1.75)},Shape,,0,0,0,,"
                  f"{{\\an5\\pos({rx},{ry})\\p1\\1a&HFF&\\3c&HFFFFFF&\\bord6\\shad0"
                  f"\\fscx30\\fscy30\\t(0,600,\\fscx200\\fscy200\\3a&HFF&)}}{CIRCLE}")
    path = "overlay.ass"
    with open(path, "w", encoding="utf-8") as f:
        f.write(head + "\n".join(ev) + "\n")
    return path

# --- scelta del tipo di scritte: ASS animato se ci sono i tempi delle parole
text_filter = None
try:
    words = json.load(open("words.json"))
    if words:
        text_filter = f"ass={build_ass(words, produced)}"
        print("Scritte animate: ok (", len(words), "parole )")
except Exception as e:
    print("Scritte animate non disponibili, uso i sottotitoli semplici:", e)
if text_filter is None and os.path.exists("subs.srt"):
    margin = 70 if kind == "short" else 15
    style = ("FontName=DejaVu Sans,Bold=1,FontSize=12,"
             "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
             f"BorderStyle=1,Outline=3,Shadow=0,Alignment=2,MarginV={margin}")
    text_filter = f"subtitles=subs.srt:force_style='{style}'"
vchain = text_filter or "null"

# --- montaggio finale: video + voce (+ musica) + logo
font = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
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
