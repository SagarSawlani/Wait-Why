"""Paths and settings shared by the whole pipeline."""
import os
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(os.path.dirname(ROOT), ".env"))   # the project's existing API keys

CACHE_DIR = os.path.join(ROOT, "cache")
JOBS_DIR = os.path.join(ROOT, "jobs")

CALL_TIMEOUT = 60      # seconds; a Gemini call taking longer counts as a failed attempt

# Each model is tried this many times, in this order.
# 3.8 and 3.6 are skipped for now because their free daily limit is used up.
DETECT_CHAIN = [("gemini-3.5-flash-lite", 2)]
# Rule and caption text does not need vision, and this model has the larger free limit.
TEXT_CHAIN = [("gemini-3.1-flash-lite", 2), ("gemini-3.5-flash-lite", 1)]

DETECT_RUNS = 1        # the median of runs is used; each run costs one Gemini request
FRAME_STEP = 2         # every Nth frame goes on the sheets
MAX_CELLS = 120        # longer clips use a bigger step
SHEET_COLS = 4
SHEET_ROWS = 3
CELL_WIDTH = 480
MIN_CONFIDENCE = 0.3   # a moment below this is left out of the replay

SLOWDOWN = 2           # 2 = 0.5x replay
PAUSE_SECONDS = 3.0    # hold at each key moment
INTRO_SECONDS = 6.0
