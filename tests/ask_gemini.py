import argparse, glob, json, os
from google import genai
from google.genai import types
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

MODEL = "gemini-3.8-flash"
EVENT = "Test cricket. The batter was bowled: the delivery hit the stumps and the stumps were disturbed."

ap = argparse.ArgumentParser()
ap.add_argument("--sheets", default="sheets")
ap.add_argument("--step", type=int, required=True)
ap.add_argument("--out", default="answer.json")
args = ap.parse_args()

paths = sorted(glob.glob(os.path.join(args.sheets, "*.jpg")))
imgs = [Image.open(p) for p in paths]
print("sending", len(imgs), "sheets:", [os.path.basename(p) for p in paths])

PROMPT = f"""You are analysing one cricket delivery from a broadcast camera behind the bowler.
Context: {EVENT}

The images are contact sheets, in time order. Each cell is one video frame with its frame number
printed in white on a black box at the top-left of the cell. Cells are {args.step} frame(s) apart.
Always answer with the frame number printed in a cell. Never invent numbers.

Find these moments. Each is defined by what is visible. Use the labelled frame closest to the moment.
- release: the first frame in which the ball has left the bowler's hand.
  If the ball is not visible, use the first frame in which the bowler's arm has completed its delivery swing.
- ball_at_batter: the first frame in which the ball is level with the batter's bat or pads.
- stumps_disturbed_visible: the first frame in which the stumps are visibly disturbed or a bail is in the air.
- camera_cuts: frames where the picture changes abruptly (a cut or a sudden jump in zoom or angle).

Rules:
- If a moment is not visible in any frame, set frame to null. Do not guess.
- confidence is between 0 and 1.
- evidence is one short sentence saying what you saw in that cell.

Return only JSON in this shape:
{{"moments": {{"release": {{"frame": 0, "confidence": 0.0, "evidence": ""}},
"ball_at_batter": {{"frame": 0, "confidence": 0.0, "evidence": ""}},
"stumps_disturbed_visible": {{"frame": 0, "confidence": 0.0, "evidence": ""}}}},
"camera_cuts": [], "notes": ""}}"""

client = genai.Client()   # reads GEMINI_API_KEY from the environment
resp = client.models.generate_content(
    model=MODEL,
    contents=[PROMPT] + imgs,
    config=types.GenerateContentConfig(temperature=0, response_mime_type="application/json"),
)
text = resp.text.strip()
with open(args.out, "w") as fh:
    fh.write(text)
print(text)

# order check
try:
    m = json.loads(text)["moments"]
    seq = [m[k]["frame"] for k in ("release", "ball_at_batter", "stumps_disturbed_visible")]
    known = [v for v in seq if v is not None]
    print("\nframes in order:", known == sorted(known), "->", seq)
except Exception as e:
    print("could not parse the answer:", e)