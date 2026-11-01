"""Lists the models your GEMINI_API_KEY can call. Optional filter: python list_models.py gemma"""
import sys
from google import genai
from dotenv import load_dotenv

load_dotenv()

word = sys.argv[1].lower() if len(sys.argv) > 1 else ""
client = genai.Client()   # reads GEMINI_API_KEY from the environment
found = 0
for m in client.models.list():
    actions = getattr(m, "supported_actions", None) or []
    name = m.name.replace("models/", "")
    if "generateContent" in actions and word in name.lower():
        print(name)
        found += 1
if not found:
    print(f"No models found{' matching ' + repr(word) if word else ''}.")