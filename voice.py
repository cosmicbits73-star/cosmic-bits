import sys, os, json, asyncio, subprocess, edge_tts

kind = sys.argv[1] if len(sys.argv) > 1 else "short"
PER = 3 if kind == "short" else 7
VOICE = "en-US-GuyNeural"
data = json.load(open("out.json"))
segs = data["segments"]

def ffdur(path):
    out = subprocess.check_output(["ffprobe", "-v", "error",
        "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", path])
    return float(out)

def ts(sec):
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"

def spread(tokens, start, dur):
    """Distribuisce il tempo tra le parole in base alla loro lunghezza."""
    total = sum(len(t) for t in tokens) or 1
    out, pos = [], start
    for t in tokens:
        d = dur * len(t) / total
        out.append((t, pos, pos + d))
        pos += d
    return out

async def tts_segment(text, path):
    """Genera la voce di una frase, con più tentativi se il servizio non risponde."""
    last = None
    for attempt in range(6):
        try:
            comm = edge_tts.Communicate(text, VOICE)
            bounds, got = [], 0
            with open(path, "wb") as f:
                async for ch in comm.stream():
                    if ch["type"] == "audio":
                        f.write(ch["data"])
                        got += len(ch["data"])
                    elif ch["type"] in ("WordBoundary", "SentenceBoundary"):
                        bounds.append(ch)
            if got > 0:
                return bounds
            raise RuntimeError("audio vuoto")
        except Exception as e:
            last = e
            print(f"  tentativo {attempt + 1} fallito: {str(e)[:100]}")
            await asyncio.sleep(2 * (attempt + 1))
    raise SystemExit(f"Voce non disponibile: {last}")

async def main():
    os.makedirs("voice_parts", exist_ok=True)
    words, timeline, files = [], [], []
    offset = 0.0
    for i, seg in enumerate(segs):
        text = seg["text"].strip()
        path = f"voice_parts/s{i}.mp3"
        bounds = await tts_segment(text, path)
        dur = ffdur(path)
        timeline.append({"keyword": seg["keyword"], "start": offset})
        seg_words = []
        for b in bounds:
            toks = b["text"].split()
            if toks:
                seg_words += spread(toks, b["offset"] / 1e7, b["duration"] / 1e7)
        if not seg_words:
            seg_words = spread(text.split(), 0.0, dur)
        for w, a, b2 in seg_words:
            words.append((w, offset + min(a, dur), offset + min(b2, dur)))
        files.append(f"s{i}.mp3")
        offset += dur
        if (i + 1) % 10 == 0 or i + 1 == len(segs):
            print(f"Voce: {i + 1}/{len(segs)} frasi")

    with open("voice_parts/list.txt", "w") as f:
        for name in files:
            f.write(f"file '{name}'\n")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", "voice_parts/list.txt", "-c:a", "libmp3lame", "-q:a", "4",
                    "voice.mp3"], check=True)

    # allinea i tempi alla durata reale del file finale
    real = ffdur("voice.mp3")
    k = real / offset if offset > 0 else 1.0
    if abs(real - offset) > 0.3:
        print(f"Correzione tempi: {offset:.1f}s -> {real:.1f}s")
    words = [(w, a * k, b * k) for w, a, b in words]
    for t in timeline:
        t["start"] *= k
    json.dump(timeline, open("timeline.json", "w"), indent=2)

    # sottotitoli
    lines, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) >= PER or w[0][-1] in ".!?":
            lines.append(cur)
            cur = []
    if cur:
        lines.append(cur)
    if lines:
        with open("subs.srt", "w", encoding="utf-8") as f:
            for n, ln in enumerate(lines, 1):
                text = " ".join(w[0] for w in ln)
                f.write(f"{n}\n{ts(ln[0][1])} --> {ts(ln[-1][2])}\n{text}\n\n")
    print("Durata voce:", round(real, 1), "s - righe di sottotitoli:", len(lines))

asyncio.run(main())
