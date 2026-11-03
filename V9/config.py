"""Paths and settings shared by the whole pipeline."""
import os
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(os.path.dirname(ROOT), ".env"))   # the project's existing API keys

CACHE_DIR = os.path.join(ROOT, "cache")
JOBS_DIR = os.path.join(ROOT, "jobs")
LIBRARY_PATH = os.path.join(ROOT, "library.json")      # the "Select from here" table
VIDEOS_DIR = os.environ.get("VIDEOS_DIR") or os.path.join(os.path.dirname(ROOT), "videos")   # library "file" paths start here
FETCH_TIMEOUT = 180    # seconds to cut one library clip from YouTube

# Online use. The Dockerfile sets PUBLIC=1, and then the app will not start without APP_PASSWORD.
PUBLIC = os.environ.get("PUBLIC") == "1"
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
SECRET_KEY = os.environ.get("SECRET_KEY", "")   # empty: a new random key, so logins end on restart
ALLOW_FETCH = os.environ.get("ALLOW_FETCH", "0" if PUBLIC else "1") == "1"   # YouTube blocks most cloud servers
MAX_UPLOAD_MB = 300
MAX_FRAME_GB = 6       # every full-size frame is held in memory during detection and the zoomed check; the free Space has 16 GB
MAX_PIXELS = 1920 * 1080
DAILY_JOBS = int(os.environ.get("DAILY_JOBS", "10"))        # all visitors together; keeps the free Gemini quota
VISITOR_DAILY_JOBS = int(os.environ.get("VISITOR_DAILY_JOBS", "3"))
MAX_WAITING = 3        # jobs queued or running at once
LOGIN_TRIES = 5        # wrong passwords per address before a 15 minute wait
JOB_HOURS = 24         # job folders older than this are deleted

CALL_TIMEOUT = 180     # seconds; a Gemini call taking longer counts as a failed attempt. Full-size sheets need the time

# Each model is tried this many times, in this order.
DETECT_CHAIN = [("gemini-3.6-flash", 2), ("gemini-3.5-flash", 2), ("gemini-3.5-flash-lite", 1), ("gemini-3.8-flash", 1)]
# Rule and caption text does not need vision, and this model has the larger free limit.
TEXT_CHAIN = [("gemini-3.1-flash-lite", 2), ("gemini-3.5-flash-lite", 1)]

DETECT_RUNS = 1        # the median of runs is used; each run costs one Gemini request
FRAME_STEP = 2         # every Nth frame goes on the sheets
MAX_CELLS = 120        # longer clips use a bigger step
REFINE_MARGIN = 6      # cells of context either side of the moments in the second, finer pass
SHEET_COLS = 4
SHEET_ROWS = 3
CELL_WIDTH = None     # frames go on the sheets at the clip's own size; small things like the ball need it
MIN_CONFIDENCE = 0.3   # a moment below this is left out of the replay

MARK_MIN_SCORE = 0.5   # Jev's presence score needed before a marker is drawn
RING_MAX_AREA = 0.012  # share of the frame; a bigger box is not the small thing a ring is meant for
FEET_MAX_WIDTH = 1.5   # width over height of a 16:9 box; two players in contact still fit

SLOWDOWN = 2           # 2 = 0.5x replay
PAUSE_SECONDS = 3.0    # hold at each key moment
INTRO_SECONDS = 6.0
LEAD_SECONDS = 3.0     # clip time kept before the first moment
TAIL_SECONDS = 2.0     # clip time kept after the last moment
