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
ALLOW_FETCH = os.environ.get("ALLOW_FETCH", "1") == "1"   # cut library clips from YouTube on first use
# Optional: the text of a cookies.txt from a spare YouTube login, for when YouTube asks a cloud server to sign in.
YT_COOKIES = os.environ.get("YT_COOKIES", "")
MAX_UPLOAD_MB = 300
MAX_CLIP_SECONDS = 120 # longer clips take too long and get a coarser frame step; frames are read as needed, so memory is not the limit
# Small hosts (about 0.5 GB): the video encoder uses 2 threads and no look-ahead, about half the memory, for a bigger file.
LOW_MEMORY = os.environ.get("LOW_MEMORY", "0") == "1"
X264_LOW_MEMORY = ["-threads", "2", "-tune", "zerolatency"]
OUTPUT_HEIGHT = 720    # with LOW_MEMORY, the explained video is rendered at this height at most
# x264 preset for the explained video. On a 0.1 CPU host ultrafast halves the encoding time (measured at 720p:
# 3.0 -> 1.6 s CPU for a 10 s clip) for a file about twice as big. The frozen clip itself keeps veryfast.
RENDER_PRESET_LOW_MEMORY = "ultrafast"
MAX_PIXELS = 1920 * 1080
DAILY_JOBS = int(os.environ.get("DAILY_JOBS", "10"))        # all visitors together; keeps the free Gemini quota
VISITOR_DAILY_JOBS = int(os.environ.get("VISITOR_DAILY_JOBS", "3"))
MAX_WAITING = 3        # jobs queued or running at once
LOGIN_TRIES = 5        # wrong passwords per address before a 15 minute wait
# Temporary files (on online by default): a visitor's selected clip, upload, output and job files are deleted when
# they refresh or leave the page, when the server stops, or TEMP_MINUTES after the output video is made.
TEMP_FILES = os.environ.get("TEMP_FILES", "1" if PUBLIC else "0") == "1"
TEMP_MINUTES = 30
SELECTED_DIR = os.path.join(ROOT, "selected")   # library clips downloaded for one visitor

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
