"""Finds what a model rejects: sends small requests, adding one thing at a time.
Run: python gemma_probe.py gemma-4-31b-it runs_gemma/clip3/sheets
Uses about 13 requests, and prints OK or the error for each. Compare the FAILs with the OKs."""
import glob, io, os, sys, time
from PIL import Image
from google import genai
from google.genai import types
from dotenv import load_dotenv
from gemini_keyframes import SYSTEM_PROMPT, MOMENT_DEFS, SHAPE

load_dotenv()
model, sheet_dir = sys.argv[1], sys.argv[2]
client = genai.Client()
paths = sorted(glob.glob(os.path.join(sheet_dir, "*.jpg")))
print(f"model {model}, {len(paths)} sheets in {sheet_dir}")


def scaled(path, width):
    img = Image.open(path).convert("RGB")
    return img.resize((width, img.height * width // img.width))


def jpeg_part(img):
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg")


full_prompt = f"{SYSTEM_PROMPT}\n\nCells are 2 frame(s) apart.\n\n{MOMENT_DEFS}\n\n{SHAPE}"
sheet = paths[0]
tests = [
    ("text only, short", ["Say OK."]),
    ("text only, full prompt", [full_prompt]),
    ("short text + 256px image (PIL)", ["Describe this image in five words.", scaled(sheet, 256)]),
    ("short text + 256px image (JPEG bytes)", ["Describe this image in five words.", jpeg_part(scaled(sheet, 256))]),
    ("short text + 1024px image", ["Describe this image in five words.", jpeg_part(scaled(sheet, 1024))]),
    ("short text + 2400px sheet", ["Describe this image in five words.", jpeg_part(Image.open(sheet).convert("RGB"))]),
    ("full prompt + 1024px image", [full_prompt, jpeg_part(scaled(sheet, 1024))]),
    ("full prompt + 2 images 1024px", [full_prompt] + [jpeg_part(scaled(p, 1024)) for p in paths[:2]]),
    ("full prompt + all sheets 1024px", [full_prompt] + [jpeg_part(scaled(p, 1024)) for p in paths]),
    # Google's Gemma docs put the image before the text, and upload it with the Files API
    ("image first, 1024px", [jpeg_part(scaled(sheet, 1024)), "Describe this image in five words."]),
    ("all sheets first, full prompt", [jpeg_part(Image.open(p).convert("RGB")) for p in paths] + [full_prompt]),
]
try:
    uploaded = [client.files.upload(file=p) for p in paths]
    tests += [
        ("Files API, one sheet first", [uploaded[0], "Describe this image in five words."]),
        ("Files API, all sheets first, full prompt", uploaded + [full_prompt]),
    ]
except Exception as e:
    print(f"FAIL  Files API upload: {str(e)[:110]}")

for name, contents in tests:
    try:
        resp = client.models.generate_content(model=model, contents=contents)
        print(f"OK    {name}: {(resp.text or '').strip()[:70]!r}")
    except Exception as e:
        print(f"FAIL  {name}: {str(e)[:110]}")
    time.sleep(5)   # stays under 15 requests per minute
