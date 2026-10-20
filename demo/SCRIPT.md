# Demo video

The narration lives in [`narration.json`](narration.json), one line per scene, sized to that scene's footage.
Edit it there; nothing else holds a copy.

Rebuild the video (about 3.5 minutes):

1. Start Mailpit (`docker start waypoint-mailpit`, or `make mailpit`) and the demo server (launch config
   `waypoint-demo`, port 8100, fresh database).
2. `.venv/bin/python demo/record.py` records the real app with the live model (desktop, then phone).
3. `.venv/bin/python demo/cards.py` renders the title, evidence (from `results/results.json`) and end cards.
4. `.venv/bin/python demo/tts.py` voices the narration: with ElevenLabs when `ELEVENLABS_API_KEY` and
   `ELEVENLABS_VOICE_ID` are set (your own voice; `--speed` 0.7 to 1.2), else Azure AI Speech
   (`AZURE_SPEECH_KEY` or `AZURE_SPEECH_TOKEN`, plus `AZURE_SPEECH_REGION`).
5. `.venv/bin/python demo/edit.py` cuts it together: waits shortened, captions, narration, loudness to -16 LUFS.

Output: `demo/out/waypoint-demo.mp4` (gitignored).

The README's screenshots and slider GIF come from the same journey: with a fresh demo server running,
`.venv/bin/python demo/screens.py --base <server>` writes `docs/media/screens.jpg` and `docs/media/slider.gif`.

Everything on screen is simulated (a fictional tea chain, mocked WeBank data, simulated unit listings), and every
reply in the chat is written live by the model. Claims in the narration match `results/RESULTS.md`.
