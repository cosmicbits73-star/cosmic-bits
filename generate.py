import os, sys, json, time
from google import genai

client = genai.Client(api_key=os.environ["GEMINI_KEY"])
MODEL = "gemini-3.8-flash"

def make(kind):
    length = "about 900 words" if kind == "long" else "about 120 words"
    prompt = f"""You run a YouTube channel called Cosmic Bits about
space and science facts. Pick a fresh, surprising topic and write
a {length} narration in English. Reply ONLY with JSON using these
keys: title, description, hashtags (list), script, keywords
(list of 3-6 stock footage search terms)."""
    for attempt in range(6):
        try:
            r = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config={"response_mime_type": "application/json"},
            )
            return json.loads(r.text)
        except Exception as e:
            print(f"Tentativo {attempt + 1} fallito: {e}")
            time.sleep(20 * (attempt + 1))
    raise SystemExit("Gemini non disponibile dopo 6 tentativi")

if __name__ == "__main__":
    data = make(sys.argv[1])
    json.dump(data, open("out.json", "w"), indent=2)
    print(data["title"])
