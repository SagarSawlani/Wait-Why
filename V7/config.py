"""Paths and settings shared by the whole pipeline."""
import os
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(os.path.dirname(ROOT), ".env"))   # the project's existing API keys

CACHE_DIR = os.path.join(ROOT, "cache")
JOBS_DIR = os.path.join(ROOT, "jobs")
LIBRARY_PATH = os.path.join(ROOT, "library.json")      # the "Select from here" table
VIDEOS_DIR = os.path.join(os.path.dirname(ROOT), "videos")   # library "file" paths start here
FETCH_TIMEOUT = 180    # seconds to cut one library clip from YouTube

CALL_TIMEOUT = 60      # seconds; a Gemini call taking longer counts as a failed attempt

# Each model is tried this many times, in this order.
DETECT_CHAIN = [("gemini-3.6-flash", 2), ("gemini-3.5-flash", 2), ("gemini-3.8-flash", 1), ("gemini-3.5-flash-lite", 1)]
# Rule and caption text does not need vision, and this model has the larger free limit.
TEXT_CHAIN = [("gemini-3.1-flash-lite", 2), ("gemini-3.5-flash-lite", 1)]

DETECT_RUNS = 1        # the median of runs is used; each run costs one Gemini request
FRAME_STEP = 2         # every Nth frame goes on the sheets
MAX_CELLS = 120        # longer clips use a bigger step
REFINE_MARGIN = 6      # cells of context either side of the moments in the second, finer pass
SHEET_COLS = 4
SHEET_ROWS = 3
CELL_WIDTH = 480
MIN_CONFIDENCE = 0.3   # a moment below this is left out of the replay

MARK_MIN_SCORE = 0.5   # Jev's presence score needed before a marker is drawn
RING_MAX_AREA = 0.012  # share of the frame; a bigger box is not the small thing a ring is meant for
FEET_MAX_WIDTH = 1.5   # width over height of a 16:9 box; two players in contact still fit

SLOWDOWN = 2           # 2 = 0.5x replay
PAUSE_SECONDS = 3.0    # hold at each key moment
INTRO_SECONDS = 6.0
LEAD_SECONDS = 3.0     # clip time kept before the first moment
TAIL_SECONDS = 2.0     # clip time kept after the last moment
