import os, json, subprocess
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

data = json.load(open("out.json"))
text = (data.get("thumbnail_text") or " ".join(data["title"].split()[:4])).upper().strip()
W, H = 1280, 720
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# --- fotogramma di base (da una clip senza sottotitoli né logo)
src = "clips/p0.mp4" if os.path.exists("clips/p0.mp4") else "video.mp4"
for ss in ("1", "0"):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", ss, "-i", src,
                    "-frames:v", "1", "frame.png"])
    if os.path.exists("frame.png"):
        break

img = Image.open("frame.png").convert("RGB")
scale = max(W / img.width, H / img.height)
img = img.resize((int(img.width * scale) + 1, int(img.height * scale) + 1), Image.LANCZOS)
left, top = (img.width - W) // 2, (img.height - H) // 2
img = img.crop((left, top, left + W, top + H))
img = ImageEnhance.Color(img).enhance(1.25)
img = ImageEnhance.Contrast(img).enhance(1.12)

# --- sfumatura scura a sinistra per far leggere il testo
shade = Image.new("L", (W, H), 0)
sd = ImageDraw.Draw(shade)
for x in range(W):
    a = int(215 * max(0.0, 1 - x / (W * 0.80)))
    sd.line([(x, 0), (x, H)], fill=a)
img = Image.composite(Image.new("RGB", (W, H), (0, 0, 0)), img, shade)

d = ImageDraw.Draw(img)

def wrap(words, font, maxw):
    lines, cur = [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=font) <= maxw or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines

maxw = int(W * 0.62)
size = 190
while size > 60:
    font = ImageFont.truetype(FONT, size)
    lines = wrap(text.split(), font, maxw)
    lh = int(size * 1.12)
    if (len(lines) <= 3 and len(lines) * lh <= H * 0.72
            and all(d.textlength(l, font=font) <= maxw for l in lines)):
        break
    size -= 6

y = (H - len(lines) * lh) // 2
for i, line in enumerate(lines):
    color = (255, 214, 0) if i == len(lines) - 1 else (255, 255, 255)
    d.text((60, y), line, font=font, fill=color,
           stroke_width=max(6, size // 13), stroke_fill=(0, 0, 0))
    y += lh

# --- logo del canale
if os.path.exists("logo.png"):
    logo = Image.open("logo.png").convert("RGBA")
    lw = 200
    logo = logo.resize((lw, int(logo.height * lw / logo.width)), Image.LANCZOS)
    img.paste(logo, (W - lw - 30, H - logo.height - 30), logo)

img.save("thumbnail.jpg", quality=90)
print("Miniatura creata:", text, "-", os.path.getsize("thumbnail.jpg") // 1024, "KB")
