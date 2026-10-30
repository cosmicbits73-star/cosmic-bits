import os, sys, json, time, random
from google import genai

client = genai.Client(api_key=os.environ["GEMINI_KEY"])
PREFERRED = "gemini-3.8-flash"
BAD = ("image", "tts", "live", "audio", "embedding", "robotics", "computer")
HISTORY = "topics.json"
MIN_WORDS = {"long": 700, "short": 80}

# (argomento, peso): più alto = esce più spesso
CATEGORIES = [
    ("animals with surprising abilities", 4),
    ("extreme animals and how they survive", 3),
    ("deep ocean creatures and mysteries", 3),
    ("famous scientists and their wild discoveries", 3),
    ("famous astronauts, explorers and inventors", 2),
    ("the human body", 2),
    ("the human brain and sleep", 2),
    ("dinosaurs and ancient Earth", 2),
    ("strange chemistry and materials", 2),
    ("alien life and exoplanets", 2),
    ("space missions and astronauts", 2),
    ("planets and moons of our solar system", 1),
    ("black holes and extreme gravity", 1),
    ("stars, supernovae and galaxies", 1),
    ("physics paradoxes", 1),
    ("time, light and relativity", 1),
    ("the origin and fate of the universe", 1),
    ("deep ocean and Earth science", 1),
]
# (angolo, peso)
ANGLES = [
    ("a common myth that is wrong", 4),
    ("a what-if scenario", 4),
    ("something that sounds fake but is true", 3),
    ("a shocking number or scale", 2),
    ("a mystery nobody has solved yet", 2),
    ("a comparison that blows the mind", 2),
    ("a recent scientific discovery", 1),
]

def pick(options):
    names = [o[0] for o in options]
    weights = [o[1] for o in options]
    return random.choices(names, weights=weights, k=1)[0]

def load_history():
    try:
        return json.load(open(HISTORY))
    except Exception:
        return []

def get_models():
    names = [PREFERRED]
    try:
        for m in client.models.list():
            n = m.name.replace("models/", "")
            actions = getattr(m, "supported_actions", None) or []
            ok = not actions or "generateContent" in actions
            if "flash" in n and ok and not any(b in n for b in BAD) and n not in names:
                names.append(n)
    except Exception as e:
        print("Elenco modelli non disponibile:", e)
    print("Modelli che proverò:", names)
    return names

def accept(data, kind, history):
    data.setdefault("topic", data.get("title", "senza titolo"))
    history.append({"topic": data["topic"], "kind": kind})
    json.dump(history[-300:], open(HISTORY, "w"), indent=2)
    return data

def make(kind):
    history = load_history()
    past = [h["topic"] for h in history][-80:]
    category = pick(CATEGORIES)
    angle = pick(ANGLES)
    print("Categoria:", category, "- Angolo:", angle)
    if kind == "long":
        length = "between 850 and 950 words in total (never fewer than 800)"
        seg_rule = "Use at least 45 segments."
        mid_rule = ("- Around the middle of the narration, add ONE short, natural "
                    "sentence inviting viewers to subscribe, for example "
                    "\"If you're enjoying this, subscribe to Cosmic Bits.\"\n")
    else:
        length = "about 120 words in total"
        seg_rule = "Use 7 to 9 segments."
        mid_rule = ""
    avoid = "; ".join(past) if past else "none yet"
    prompt = f"""You run a YouTube channel called Cosmic Bits about
space and science facts. Write a narration in English, {length}.

Topic area: {category}. Angle: {angle}.
Topics already covered, DO NOT repeat or closely resemble any of them: {avoid}.

Rules for the narration:
- The FIRST sentence must be a powerful hook that grabs attention in
  under 3 seconds (a shocking claim or an intriguing question).
- The LAST sentence must be a memorable punchline or mind-blowing
  closing thought, followed by a short call to action such as
  "Follow Cosmic Bits for more cosmic secrets."
{mid_rule}- Keep the middle fast-paced and easy to understand.
- Every fact must be real and accurate.

Reply ONLY with JSON using these keys: topic (3-8 words naming the
specific subject), title, description, hashtags (list), thumbnail_text,
hook_text, segments.

"thumbnail_text" is a teaser for the video thumbnail: 2 to 4 WORDS in
capital letters that trigger curiosity (for example "IT SHOULDN'T EXIST"),
not a copy of the title.

"hook_text" is a line written on screen during the first 3 seconds of the
video, to stop people from scrolling away: 3 to 7 WORDS in capital letters,
a surprising fact or a curious question about the topic (for example
"ELECTRIC EELS SHOCK 600 VOLTS"). Only letters, numbers, ? and !, no quotes.

"segments" is the whole narration split into consecutive parts, in
order. {seg_rule} Each part is an object {{"text": "...", "keyword": "..."}}.
- "text" is one or two COMPLETE sentences (about 12 to 25 words).
- "keyword" is 1 or 2 simple English words naming something that can be
  FILMED or ANIMATED, common in free stock video libraries, and that
  matches exactly what that text is talking about. Good examples:
  galaxy, nebula, astronaut, rocket launch, microscope, ocean waves,
  volcano, human brain, lightning, earth from space, laboratory,
  jellyfish. Never use rare scientific names or abstract ideas (use
  "microscope" instead of "tardigrade").
Read together, the texts form the complete narration."""
    models = get_models()
    best = None
    for rnd in range(3):
        for model in models:
            try:
                r = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config={"response_mime_type": "application/json"},
                )
                data = json.loads(r.text)
                segs = [s for s in (data.get("segments") or [])
                        if isinstance(s, dict)
                        and str(s.get("text", "")).strip()
                        and str(s.get("keyword", "")).strip()]
                if len(segs) < 2:
                    print("Segmenti mancanti, riprovo")
                    continue
                data["segments"] = segs
                data["script"] = " ".join(s["text"].strip() for s in segs)
                data["keywords"] = [s["keyword"].strip() for s in segs]
                data["thumbnail_text"] = str(
                    data.get("thumbnail_text")
                    or " ".join(str(data.get("title", "")).split()[:4])).strip()
                data["hook_text"] = str(
                    data.get("hook_text") or data["thumbnail_text"]).strip()
                nwords = len(data["script"].split())
                if nwords < MIN_WORDS[kind]:
                    print(f"Testo troppo corto ({nwords} parole), riprovo")
                    if best is None or nwords > best[0]:
                        best = (nwords, data)
                    continue
                if data.get("topic", "").strip().lower() in [p.lower() for p in past]:
                    print("Argomento già usato, riprovo")
                    continue
                print("Riuscito con", model, "-", nwords, "parole")
                return accept(data, kind, history)
            except Exception as e:
                print(f"{model} fallito: {str(e)[:150]}")
                if "404" in str(e) or "NOT_FOUND" in str(e):
                    continue
                time.sleep(10)
        time.sleep(15 * (rnd + 1))
    if best:
        print("Uso il testo più lungo ottenuto:", best[0], "parole")
        return accept(best[1], kind, history)
    raise SystemExit("Nessun modello Gemini disponibile")

if __name__ == "__main__":
    data = make(sys.argv[1])
    json.dump(data, open("out.json", "w"), indent=2)
    print(data["title"])
    print("Frase d'apertura:", data["hook_text"])
    print("Segmenti:", len(data["segments"]), "- parole:", len(data["script"].split()))
