import os, sys, json, time
from google import genai

client = genai.Client(api_key=os.environ["GEMINI_KEY"])
PREFERRED = "gemini-3.8-flash"
BAD = ("image", "tts", "live", "audio", "embedding", "robotics", "computer")

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

def make(kind):
    length = "about 900 words" if kind == "long" else "about 120 words"
    prompt = f"""You run a YouTube channel called Cosmic Bits about
space and science facts. Pick a fresh, surprising topic and write
a {length} narration in English. Reply ONLY with JSON using these
keys: title, description, hashtags (list), script, keywords
(list of 3-6 stock footage search terms)."""
    models = get_models()
    for rnd in range(3):
        for model in models:
            try:
                r = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config={"response_mime_type": "application/json"},
                )
                data = json.loads(r.text)
                print("Riuscito con", model)
                return data
            except Exception as e:
                print(f"{model} fallito: {str(e)[:150]}")
                if "404" in str(e) or "NOT_FOUND" in str(e):
                    continue
                time.sleep(10)
        time.sleep(30 * (rnd + 1))
    raise SystemExit("Nessun modello Gemini disponibile")

if __name__ == "__main__":
    data = make(sys.argv[1])
    json.dump(data, open("out.json", "w"), indent=2)
    print(data["title"])
