import json, asyncio, edge_tts

data = json.load(open("out.json"))

async def main():
    tts = edge_tts.Communicate(data["script"], "en-US-GuyNeural")
    await tts.save("voice.mp3")

asyncio.run(main())
