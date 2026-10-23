import sys, json, asyncio, edge_tts

kind = sys.argv[1] if len(sys.argv) > 1 else "short"
PER = 3 if kind == "short" else 7
data = json.load(open("out.json"))

def ts(sec):
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"

async def main():
    comm = edge_tts.Communicate(data["script"], "en-US-GuyNeural")
    bounds = []
    with open("voice.mp3", "wb") as f:
        async for ch in comm.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] in ("WordBoundary", "SentenceBoundary"):
                bounds.append(ch)

    words = []
    for b in bounds:
        toks = b["text"].split()
        if not toks:
            continue
        start = b["offset"] / 1e7
        dur = b["duration"] / 1e7
        total = sum(len(t) for t in toks)
        pos = start
        for t in toks:
            d = dur * len(t) / total
            words.append((t, pos, pos + d))
            pos += d

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
            for i, ln in enumerate(lines, 1):
                text = " ".join(w[0] for w in ln)
                f.write(f"{i}\n{ts(ln[0][1])} --> {ts(ln[-1][2])}\n{text}\n\n")
    print("Righe di sottotitoli:", len(lines))

asyncio.run(main())
