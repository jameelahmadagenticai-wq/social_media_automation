
# ┌──────────────────────────────────────────────────────────────────────────────┐
# │  SECTION 1 · IMPORTS                                                         │
# └──────────────────────────────────────────────────────────────────────────────┘

import datetime
import json
import logging
import os
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
import telebot
from dotenv import load_dotenv
from moviepy.config import change_settings
from moviepy.editor import (
    AudioFileClip,
    CompositeVideoClip,
    TextClip,
    VideoFileClip,
)
from openai import OpenAI, OpenAIError
from PIL import Image
from telebot import apihelper
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


# ┌──────────────────────────────────────────────────────────────────────────────┐
# │  SECTION 2 · LOGGING                                                         │
# └──────────────────────────────────────────────────────────────────────────────┘

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

_log_filename = os.path.join(LOG_DIR, f"bot_{datetime.date.today()}.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(_log_filename, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger("VideoBot")


# ┌──────────────────────────────────────────────────────────────────────────────┐
# │  SECTION 3 · ENVIRONMENT & CONFIGURATION                                     │
# └──────────────────────────────────────────────────────────────────────────────┘

load_dotenv()

# ── Required credentials ──────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# ── Optional settings ─────────────────────────────────────────────────────────
WEBHOOK_URL      = os.getenv("WEBHOOK_URL", "")
OUTPUT_DIR       = os.getenv("OUTPUT_DIR", "output")
MAX_FILES        = int(os.getenv("MAX_OUTPUT_FILES", 20))
IMAGEMAGICK_PATH = os.getenv(
    "IMAGEMAGICK_PATH",
    r"C:\Program Files\ImageMagick-7.1.2-Q16-HDRI\magick.exe",
)

# ── OpenAI TTS settings ───────────────────────────────────────────────────────
TTS_MODEL = os.getenv("TTS_MODEL", "tts-1")    # tts-1 | tts-1-hd
TTS_VOICE = os.getenv("TTS_VOICE", "alloy")    # alloy | echo | fable | onyx | nova | shimmer

# ── Validate required env vars at startup ────────────────────────────────────
for _var_name, _var_value in [
    ("TELEGRAM_TOKEN", TELEGRAM_TOKEN),
    ("OPENAI_API_KEY", OPENAI_API_KEY),
]:
    if not _var_value:
        logger.critical(f"Missing required environment variable: {_var_name}")
        raise EnvironmentError(f"{_var_name} is not set in your .env file.")

# ── ImageMagick (required by MoviePy for TextClip) ───────────────────────────
os.environ["IMAGEMAGICK_BINARY"] = IMAGEMAGICK_PATH
change_settings({"IMAGEMAGICK_BINARY": IMAGEMAGICK_PATH})
logger.info(f"ImageMagick path set → {IMAGEMAGICK_PATH}")

# ── Pillow backwards-compatibility shim ──────────────────────────────────────
if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.Resampling.LANCZOS

# ── API clients ───────────────────────────────────────────────────────────────
bot    = telebot.TeleBot(TELEGRAM_TOKEN)
client = OpenAI(api_key=OPENAI_API_KEY)

# ── Telegram timeout settings ─────────────────────────────────────────────────
apihelper.CONNECT_TIMEOUT = 60
apihelper.READ_TIMEOUT    = 600


# ┌──────────────────────────────────────────────────────────────────────────────┐
# │  SECTION 4 · BRAND SYSTEM                                                    │
# └──────────────────────────────────────────────────────────────────────────────┘

with open("brands.json", "r", encoding="utf-8") as _f:
    BRANDS: dict = json.load(_f)

CURRENT_BRAND = "iv_clinic"    # updated at runtime via /set_brand
PUBLISH_CACHE: dict = {}       # stores video path + social data per publish action


def _ensure_brand_directories() -> None:
    """Create output/<brand> and assets/<brand> folders for every brand."""
    for brand_key in BRANDS:
        os.makedirs(os.path.join(OUTPUT_DIR, brand_key), exist_ok=True)
        os.makedirs(os.path.join("assets", brand_key), exist_ok=True)
    logger.info(f"Brand directories verified for {len(BRANDS)} brand(s).")


_ensure_brand_directories()


# ┌──────────────────────────────────────────────────────────────────────────────┐
# │  SECTION 5 · FILE HELPERS                                                    │
# └──────────────────────────────────────────────────────────────────────────────┘

def _ts() -> str:
    """Return a compact timestamp string for unique filenames (e.g. 20240601_153045)."""
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def _brand_dir() -> str:
    """Return the absolute path to the active brand's output folder, creating it if needed."""
    folder = os.path.join(OUTPUT_DIR, CURRENT_BRAND)
    os.makedirs(folder, exist_ok=True)
    return folder


def _path(filename: str) -> str:
    """Build the full path for a file inside the active brand's output folder."""
    return os.path.join(_brand_dir(), filename)


def _save_text(filename: str, content: str) -> None:
    """Write text content to a file in the active brand's output folder."""
    with open(_path(filename), "w", encoding="utf-8") as f:
        f.write(content)


def _load_text(filename: str) -> str:
    """Read and return text content from a file in the active brand's output folder."""
    with open(_path(filename), "r", encoding="utf-8") as f:
        return f.read()


def _cleanup_output_folder() -> None:
    """
    Prune old .mp4 files when the brand folder exceeds MAX_FILES.

    Deletes the oldest files first to prevent disk exhaustion during long
    running sessions.
    """
    folder = _brand_dir()
    mp4s = sorted(
        [os.path.join(folder, f) for f in os.listdir(folder) if f.endswith(".mp4")],
        key=os.path.getctime,
    )
    for old_file in mp4s[:-MAX_FILES]:
        try:
            os.remove(old_file)
            logger.info(f"[cleanup] Removed old file → {old_file}")
        except OSError as e:
            logger.warning(f"[cleanup] Could not remove {old_file}: {e}")


# ┌──────────────────────────────────────────────────────────────────────────────┐
# │  SECTION 6 · SESSION 1 — SCRIPT GENERATION                                  │
# │                                                                              │
# │  Uses GPT-4o to write a short-form video voiceover script tailored to the   │
# │  active brand's tone, industry, and call-to-action.                          │
# └──────────────────────────────────────────────────────────────────────────────┘

def _build_system_prompt(brand_key: str) -> str:
    """
    Compose the GPT system prompt from the brand's configuration.

    Args:
        brand_key: Key from brands.json (e.g. "iv_clinic").

    Returns:
        Formatted system prompt string.
    """
    brand = BRANDS[brand_key]
    return (
        f"You are a world-class direct response copywriter for {brand['name']}, "
        f"a brand in the {brand['industry']} industry.\n\n"
        f"Tone: {brand['tone']}\n\n"
        "Write a high-converting short-form video script (TikTok / Instagram Reels / YouTube Shorts).\n\n"
        "SCRIPT STRUCTURE:\n"
        "1. Hook        (2-3 seconds — grab attention instantly)\n"
        "2. Problem     (pain point the viewer feels)\n"
        f"3. Solution    (how {brand['name']} solves it)\n"
        "4. Benefits    (concrete outcomes / results)\n"
        "5. Call to Action — use EXACTLY this CTA:\n"
        f"   {brand['cta']}\n\n"
        "OUTPUT RULES:\n"
        "- Return ONLY the voiceover script — no scene directions, brackets, labels, or emojis\n"
        "- Short sentences, natural spoken language\n"
        "- Under 60 seconds when spoken aloud\n"
    )


@retry(
    retry=retry_if_exception_type(OpenAIError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def session_script(topic: str, brand_key: str) -> str:
    """
    SESSION 1 — Generate a voiceover script via GPT-4o.

    Retries up to 3 times on transient OpenAI API failures.

    Args:
        topic:     Subject of the video (e.g. "hangover recovery").
        brand_key: Key from brands.json (e.g. "iv_clinic").

    Returns:
        Filename of the saved script (relative to the brand output folder).
    """
    logger.info(f"[script] Generating script | brand={brand_key} | topic={topic}")

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": _build_system_prompt(brand_key)},
            {"role": "user",   "content": f"Write about: {topic}"},
        ],
    )

    script_text = response.choices[0].message.content.strip()
    filename    = f"script_{_ts()}.txt"
    _save_text(filename, script_text)

    logger.info(f"[script] Saved → {filename}")
    return filename


# ┌──────────────────────────────────────────────────────────────────────────────┐
# │  SECTION 7 · SESSION 1b — SOCIAL MEDIA METADATA                             │
# │                                                                              │
# │  Generates an Instagram caption and five hashtags for the video topic using  │
# │  GPT-4.1-mini. Runs in parallel with the main pipeline setup.                │
# └──────────────────────────────────────────────────────────────────────────────┘

@retry(
    retry=retry_if_exception_type(OpenAIError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def session_social_metadata(topic: str, brand_key: str) -> dict:
    """
    SESSION 1b — Generate a social media caption and hashtag set via GPT.

    Args:
        topic:     Subject of the video.
        brand_key: Active brand key.

    Returns:
        Dictionary with keys:
            - "caption"      : 2-3 line Instagram caption.
            - "hashtags"     : Space-separated hashtag string.
            - "full_caption" : Caption + blank line + hashtags (ready to post).
    """
    brand = BRANDS[brand_key]
    logger.info(f"[social] Generating metadata | brand={brand_key} | topic={topic}")

    prompt = (
        "You are a social media expert.\n\n"
        "Generate an Instagram caption for:\n\n"
        f"Topic: {topic}\n"
        f"Brand: {brand['name']}\n"
        f"Tone:  {brand['tone']}\n\n"
        "Rules:\n"
        "- Caption should be 2-3 lines max\n"
        "- First line must be a strong hook\n"
        "- Include CTA at the end\n"
        "- Generate exactly 5 hashtags\n"
        "- Do NOT include hashtags inside the caption\n\n"
        "Return ONLY valid JSON:\n"
        '{\n  "caption": "...",\n  "hashtags": ["#tag1", "#tag2", "#tag3", "#tag4", "#tag5"]\n}'
    )

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": "You generate high-converting social media captions."},
            {"role": "user",   "content": prompt},
        ],
        temperature=0.7,
    )

    content = response.choices[0].message.content.strip()

    try:
        data          = json.loads(content)
        caption       = data.get("caption", "")
        hashtags      = " ".join(data.get("hashtags", []))
        logger.info("[social] Metadata generated successfully")
        return {
            "caption":      caption,
            "hashtags":     hashtags,
            "full_caption": f"{caption}\n\n{hashtags}",
        }
    except Exception as e:
        logger.error(f"[social] Failed to parse metadata JSON: {e}")
        return {"caption": "", "hashtags": "", "full_caption": ""}


# ┌──────────────────────────────────────────────────────────────────────────────┐
# │  SECTION 8 · SESSION 2 — AUDIO GENERATION & WORD TIMESTAMPS                 │
# │                                                                              │
# │  1. Synthesises speech from the script via OpenAI TTS.                       │
# │  2. Runs Whisper on the resulting MP3 to extract exact word-level timings.   │
# │  3. Saves timestamps as a JSON sidecar file for the subtitle session.        │
# └──────────────────────────────────────────────────────────────────────────────┘

@retry(
    retry=retry_if_exception_type(OpenAIError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def session_audio(script_file: str) -> tuple[str, str]:
    """
    SESSION 2 — Convert the script to audio and extract word-level timestamps.

    Args:
        script_file: Filename of the saved script (from session_script).

    Returns:
        Tuple of (audio_filename, timestamps_filename).
    """
    script_text    = _load_text(script_file)
    audio_filename = script_file.replace(".txt", ".mp3")
    audio_path     = _path(audio_filename)

    # ── Step 1: OpenAI TTS ────────────────────────────────────────────────────
    logger.info(f"[audio] Generating TTS | model={TTS_MODEL} | voice={TTS_VOICE}")
    tts_response = client.audio.speech.create(
        model=TTS_MODEL,
        voice=TTS_VOICE,
        input=script_text,
    )
    tts_response.stream_to_file(audio_path)
    logger.info(f"[audio] TTS saved → {audio_filename}")

    # ── Step 2: Whisper word-level timestamps ─────────────────────────────────
    logger.info("[audio] Running Whisper for word timestamps…")
    with open(audio_path, "rb") as f:
        whisper_result = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="verbose_json",
            timestamp_granularities=["word"],
        )

    words = [
        {"word": w.word.strip(), "start": w.start, "end": w.end}
        for w in whisper_result.words
        if w.word.strip()
    ]

    # ── Step 3: Save timestamps JSON ──────────────────────────────────────────
    ts_filename = script_file.replace(".txt", "_timestamps.json")
    _save_text(ts_filename, json.dumps(words, ensure_ascii=False, indent=2))
    logger.info(f"[audio] Timestamps saved → {ts_filename} ({len(words)} words)")

    return audio_filename, ts_filename


# ┌──────────────────────────────────────────────────────────────────────────────┐
# │  SECTION 9 · SESSION 3 — BACKGROUND VIDEO                                   │
# │                                                                              │
# │  Crops and loops the brand's background clip to match the audio duration.   │
# │  Target resolution: 720 × 1280 (vertical 9:16).                             │
# └──────────────────────────────────────────────────────────────────────────────┘

def session_video(audio_file: str) -> str:
    """
    SESSION 3 — Crop and loop the brand background video to match audio length.

    Args:
        audio_file: Filename of the generated audio (from session_audio).

    Returns:
        Filename of the assembled background video.

    Raises:
        FileNotFoundError: If the brand's background video asset is missing.
    """
    brand      = BRANDS[CURRENT_BRAND]
    audio_path = _path(audio_file)

    logger.info(f"[video] Building background video | bg={brand['bg_video']}")

    if not os.path.exists(brand["bg_video"]):
        raise FileNotFoundError(f"Background video not found: {brand['bg_video']}")

    audio = AudioFileClip(audio_path)
    video = VideoFileClip(brand["bg_video"]).resize(height=1280)

    # Crop to 720 px wide if the source is wider than the target
    if video.w > 720:
        video = video.crop(x_center=video.w / 2, width=720)

    # Loop short clips or trim long ones to match audio length exactly
    if video.duration < audio.duration:
        video = video.loop(duration=audio.duration)
    else:
        video = video.subclip(0, audio.duration)

    video = video.set_audio(audio)

    video_file = audio_file.replace(".mp3", "_bg.mp4")
    video.write_videofile(
        _path(video_file),
        fps=24,
        codec="libx264",
        audio_codec="aac",
        preset="ultrafast",
        threads=4,
        bitrate="600k",
        verbose=False,
        logger=None,
    )

    audio.close()
    video.close()

    logger.info(f"[video] Background video saved → {video_file}")
    return video_file


# ┌──────────────────────────────────────────────────────────────────────────────┐
# │  SECTION 10 · SESSION 4 — SUBTITLE OVERLAY (Whisper-Synced)                 │
# │                                                                              │
# │  Burns animated subtitles onto the background video using Whisper timings.  │
# │  Words are grouped into chunks with a 60 ms crossfade on entry and exit.    │
# └──────────────────────────────────────────────────────────────────────────────┘

# ── Subtitle constants ────────────────────────────────────────────────────────
WORDS_PER_CHUNK = 5      # words displayed per subtitle chunk
FONT_SIZE       = 68     # subtitle font size in pixels
TEXT_Y_RATIO    = 0.55   # vertical position (0.0 = top, 1.0 = bottom)


def session_text_overlay(video_file: str, timestamps_file: str) -> str:
    """
    SESSION 4 — Burn Whisper-synced subtitles onto the background video.

    Behaviour:
        - Words are grouped into chunks of WORDS_PER_CHUNK.
        - Each chunk fades in and out with a soft 60 ms crossfade.
        - Text is centred horizontally and positioned at TEXT_Y_RATIO.

    Args:
        video_file:      Filename of the background video (from session_video).
        timestamps_file: Filename of the Whisper timestamps JSON (from session_audio).

    Returns:
        Filename of the final video with subtitles burned in.
    """
    logger.info(f"[subtitles] Overlaying subtitles | video={video_file}")

    video = VideoFileClip(_path(video_file))
    words = json.loads(_load_text(timestamps_file))

    # ── Build one TextClip per word-chunk ─────────────────────────────────────
    text_clips = []
    for i in range(0, len(words), WORDS_PER_CHUNK):
        group    = words[i : i + WORDS_PER_CHUNK]
        chunk    = " ".join(w["word"] for w in group)
        start    = group[0]["start"]
        duration = group[-1]["end"] - start

        if duration <= 0:
            logger.warning(f"[subtitles] Skipped zero-duration chunk at index {i}: '{chunk}'")
            continue

        clip = (
            TextClip(
                chunk,
                fontsize=FONT_SIZE,
                color="white",
                font="Arial-Bold",
                stroke_color="black",
                stroke_width=3,
                size=(int(video.w * 0.85), None),   # constrain width, auto height
                method="caption",
                align="center",
            )
            .set_position(("center", video.h * TEXT_Y_RATIO))
            .set_start(start)
            .set_duration(duration)
            .crossfadein(0.06)
            .crossfadeout(0.06)
        )
        text_clips.append(clip)

    logger.info(f"[subtitles] Created {len(text_clips)} subtitle clips")

    # ── Composite and export ──────────────────────────────────────────────────
    final      = CompositeVideoClip([video] + text_clips)
    final_file = video_file.replace("_bg.mp4", "_final.mp4")

    final.write_videofile(
        _path(final_file),
        fps=24,
        codec="libx264",
        audio_codec="aac",
        preset="ultrafast",
        threads=4,
        bitrate="600k",
        verbose=False,
        logger=None,
    )

    video.close()
    final.close()

    logger.info(f"[subtitles] Final video saved → {final_file}")
    return final_file


# ┌──────────────────────────────────────────────────────────────────────────────┐
# │  SECTION 11 · SESSION 5 — WEBHOOK UPLOAD (Cloud Delivery)                   │
# │                                                                              │
# │  Posts the finished video to a configurable webhook endpoint.                │
# │  Silently skipped when WEBHOOK_URL is not set.                               │
# └──────────────────────────────────────────────────────────────────────────────┘

@retry(
    retry=retry_if_exception_type(requests.RequestException),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def session_webhook(final_file: str) -> bool:
    """
    SESSION 5 — Upload the final video to a webhook / cloud endpoint.

    Retries up to 3 times on network failures.
    Skipped silently if WEBHOOK_URL is not configured.

    Args:
        final_file: Filename of the finished video (from session_text_overlay).

    Returns:
        True if the upload returned HTTP 200, False otherwise.
    """
    if not WEBHOOK_URL:
        logger.info("[webhook] WEBHOOK_URL not set — skipping upload.")
        return False

    logger.info(f"[webhook] Uploading → {WEBHOOK_URL}")

    with open(_path(final_file), "rb") as f:
        response = requests.post(
            WEBHOOK_URL,
            data={"brand": CURRENT_BRAND},
            files={"file": (final_file, f, "video/mp4")},
            timeout=120,
        )

    logger.info(f"[webhook] Response: {response.status_code} — {response.text[:200]}")
    return response.status_code == 200


# ┌──────────────────────────────────────────────────────────────────────────────┐
# │  SECTION 12 · PIPELINE ORCHESTRATOR                                          │
# │                                                                              │
# │  Runs all five sessions in order for a single topic.  Each full pipeline     │
# │  executes inside its own thread so multiple /generate_video commands can     │
# │  run concurrently without blocking the Telegram event loop.                  │
# │                                                                              │
# │  Execution order:                                                            │
# │                                                                              │
# │    [1] Script  ──►  [1b] Social Metadata                                    │
# │                           │                                                 │
# │                    [2] Audio + Timestamps                                   │
# │                           │                                                 │
# │                    [3] Background Video                                     │
# │                           │                                                 │
# │                    [4] Subtitle Overlay                                     │
# │                           │                                                 │
# │                    [5] Webhook Upload  (non-blocking, best-effort)          │
# │                                                                              │
# └──────────────────────────────────────────────────────────────────────────────┘

def run_pipeline(topic: str, brand_key: str) -> dict:
    """
    Execute the full video generation pipeline for a single topic.

    Args:
        topic:     Subject of the video (e.g. "hangover recovery").
        brand_key: Active brand key at the time the request was received.

    Returns:
        Dictionary with keys:
            - "video_path"  : Absolute path to the final .mp4.
            - "social_data" : Caption + hashtags dict from session_social_metadata.

    Raises:
        Any exception propagated from a failing session (handled by the caller).
    """
    logger.info(f"[pipeline] ▶ START | brand={brand_key} | topic='{topic}'")
    t0 = datetime.datetime.now()

    script_file             = session_script(topic, brand_key)
    social_data             = session_social_metadata(topic, brand_key)
    audio_file, ts_file     = session_audio(script_file)
    video_file              = session_video(audio_file)
    final_file              = session_text_overlay(video_file, ts_file)

    elapsed = (datetime.datetime.now() - t0).seconds
    logger.info(f"[pipeline] ■ DONE in {elapsed}s → {final_file}")

    # Webhook upload is best-effort; a failure never blocks video delivery
    if WEBHOOK_URL:
        try:
            session_webhook(final_file)
        except Exception as e:
            logger.error(f"[pipeline] Webhook upload failed after retries: {e}")

    return {
        "video_path":  _path(final_file),
        "social_data": social_data,
    }


# ┌──────────────────────────────────────────────────────────────────────────────┐
# │  SECTION 13 · INLINE KEYBOARD HELPERS                                        │
# │                                                                              │
# │  Builds the "Publish to Facebook/IG" button attached to each delivered       │
# │  video message. Stores the required payload in PUBLISH_CACHE (capped at 50). │
# └──────────────────────────────────────────────────────────────────────────────┘

def get_publish_markup(
    video_path: str,
    brand_id: str,
    social_data: dict,
) -> InlineKeyboardMarkup:
    """
    Build an InlineKeyboardMarkup containing the publish button.

    Stores the video path and social metadata in PUBLISH_CACHE under a short UUID
    so the callback handler can retrieve them without hitting Telegram's 64-byte
    callback_data limit.

    Args:
        video_path:  Absolute path to the final .mp4.
        brand_id:    Active brand key.
        social_data: Caption + hashtags from session_social_metadata.

    Returns:
        InlineKeyboardMarkup with a single "🚀 Publish to Facebook/IG" button.
    """
    # Cap cache at 50 entries (FIFO eviction)
    if len(PUBLISH_CACHE) > 50:
        PUBLISH_CACHE.pop(next(iter(PUBLISH_CACHE)))

    publish_id = str(uuid.uuid4())[:8]
    PUBLISH_CACHE[publish_id] = {
        "video_path":  video_path,
        "brand_id":    brand_id,
        "social_data": social_data,
    }

    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton(
            text="🚀 Publish to Facebook/IG",
            callback_data=f"publish|{publish_id}",
        )
    )
    return markup


# ┌──────────────────────────────────────────────────────────────────────────────┐
# │  SECTION 14 · TELEGRAM COMMAND HANDLERS                                      │
# └──────────────────────────────────────────────────────────────────────────────┘

@bot.message_handler(commands=["set_brand"])
def cmd_set_brand(message) -> None:
    """
    Switch the active brand for the current session.

    Usage:   /set_brand <brand_id>
    Example: /set_brand iv_clinic
    """
    global CURRENT_BRAND, PUBLISH_CACHE

    PUBLISH_CACHE.clear()

    parts = message.text.split(" ", 1)
    if len(parts) < 2 or not parts[1].strip():
        available = "\n".join(
            f"  • `{k}` — {v['name']}" for k, v in BRANDS.items()
        )
        bot.reply_to(
            message,
            f"Usage: `/set_brand <brand_id>`\n\nAvailable brands:\n{available}",
            parse_mode="Markdown",
        )
        return

    brand_id = parts[1].strip()

    if brand_id not in BRANDS:
        bot.reply_to(message, f"❌ Brand `{brand_id}` not found.", parse_mode="Markdown")
        return

    CURRENT_BRAND = brand_id
    logger.info(f"[bot] Brand switched → {brand_id}")
    bot.reply_to(
        message,
        f"✅ Switched to *{BRANDS[brand_id]['name']}*",
        parse_mode="Markdown",
    )


@bot.message_handler(commands=["brands"])
def cmd_list_brands(message) -> None:
    """
    List all configured brands and highlight the currently active one.

    Usage: /brands
    """
    lines = ["*Available Brands*\n"]
    for key, brand in BRANDS.items():
        active = " ← active" if key == CURRENT_BRAND else ""
        lines.append(f"  • `{key}` — {brand['name']}{active}")
    bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")


@bot.message_handler(commands=["generate_video"])
def cmd_generate_video(message) -> None:
    """
    Kick off the full video generation pipeline for a given topic.

    The pipeline runs in a background thread so the bot stays responsive.
    Multiple calls can run concurrently (up to 4 workers).

    Usage:   /generate_video <topic>
    Example: /generate_video hangover recovery
    """
    parts = message.text.split(" ", 1)
    if len(parts) < 2 or not parts[1].strip():
        bot.reply_to(
            message,
            "❌ Please provide a topic.\nExample: `/generate_video hangover recovery`",
            parse_mode="Markdown",
        )
        return

    topic     = parts[1].strip()
    brand_key = CURRENT_BRAND   # snapshot at request time (thread-safe read)

    _cleanup_output_folder()

    bot.reply_to(
        message,
        f"🎬 Processing your video…\n"
        f"*Brand:* {BRANDS[brand_key]['name']}\n"
        f"*Topic:* {topic}",
        parse_mode="Markdown",
    )

    logger.info(f"[bot] /generate_video | chat_id={message.chat.id} | topic='{topic}'")

    with ThreadPoolExecutor(max_workers=4) as executor:
        future = executor.submit(run_pipeline, topic, brand_key)
        try:
            result      = future.result()
            final_path  = result["video_path"]
            social_data = result["social_data"]

            with open(final_path, "rb") as v:
                caption_text = (
                    social_data.get("full_caption")
                    or f"{BRANDS[brand_key]['name']} — {topic}"
                )
                bot.send_video(
                    message.chat.id,
                    v,
                    caption=caption_text,
                    parse_mode="Markdown",
                    reply_markup=get_publish_markup(final_path, brand_key, social_data),
                )
                logger.info(f"[bot] Video sent to chat_id={message.chat.id}")

        except FileNotFoundError as e:
            logger.error(f"[bot] Asset missing: {e}")
            bot.reply_to(message, f"❌ Asset not found: {e}")

        except OpenAIError as e:
            logger.error(f"[bot] OpenAI API error: {e}")
            bot.reply_to(message, "❌ OpenAI API failed after retries. Please try again later.")

        except requests.RequestException as e:
            logger.error(f"[bot] Network error: {e}")
            bot.reply_to(message, "❌ Network error during processing. Please try again.")

        except Exception:
            logger.error(f"[bot] Unexpected error:\n{traceback.format_exc()}")
            bot.reply_to(message, "❌ Something went wrong. Our team has been notified.")


# ┌──────────────────────────────────────────────────────────────────────────────┐
# │  SECTION 15 · CALLBACK QUERY HANDLERS                                        │
# └──────────────────────────────────────────────────────────────────────────────┘

@bot.callback_query_handler(func=lambda call: call.data.startswith("publish"))
def handle_publish_request(call) -> None:
    """
    Handle the "🚀 Publish to Facebook/IG" inline button press.

    Retrieves the cached video path and social data, then POSTs them to the
    configured N8N_SOCIAL_POST_URL webhook for downstream scheduling.
    """
    try:
        # ── Extract and validate publish ID ───────────────────────────────────
        _, publish_id = call.data.split("|")

        if publish_id not in PUBLISH_CACHE:
            bot.answer_callback_query(call.id, "❌ Data expired. Please regenerate the video.")
            return

        data        = PUBLISH_CACHE[publish_id]
        video_path  = data["video_path"]
        brand_id    = data["brand_id"]
        social_data = data["social_data"]

        bot.answer_callback_query(call.id, "🚀 Sending to Social Media Pipeline…")

        # ── Resolve and validate n8n webhook ──────────────────────────────────
        social_webhook = os.getenv("N8N_SOCIAL_POST_URL")
        if not social_webhook:
            bot.send_message(call.message.chat.id, "❌ N8N webhook not configured.")
            return

        # ── POST video + caption to n8n ───────────────────────────────────────
        with open(video_path, "rb") as f:
            response = requests.post(
                social_webhook,
                data={"brand": brand_id, "caption": social_data.get("full_caption", "")},
                files={"file": (os.path.basename(video_path), f, "video/mp4")},
                timeout=120,
            )

        # ── Reflect outcome back to the user ──────────────────────────────────
        if response.status_code == 200:
            bot.edit_message_caption(
                caption="✅ Sent to Social Media Queue!",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
            )
        else:
            bot.send_message(
                call.message.chat.id,
                f"❌ Failed to reach n8n. Status: {response.status_code}",
            )

    except Exception:
        logger.error(f"[callback] Publish error:\n{traceback.format_exc()}")
        bot.send_message(call.message.chat.id, "❌ Something went wrong during publishing.")


# ┌──────────────────────────────────────────────────────────────────────────────┐
# │  SECTION 16 · ENTRY POINT                                                    │
# └──────────────────────────────────────────────────────────────────────────────┘

if __name__ == "__main__":
    logger.info("=" * 70)
    logger.info("🚀  VideoBot starting…")
    logger.info(f"   Active brand  : {CURRENT_BRAND} ({BRANDS[CURRENT_BRAND]['name']})")
    logger.info(f"   Output dir    : {OUTPUT_DIR}/")
    logger.info(f"   TTS model     : {TTS_MODEL}  |  voice: {TTS_VOICE}")
    logger.info(f"   Webhook URL   : {WEBHOOK_URL or 'not configured'}")
    logger.info(f"   Log file      : {_log_filename}")
    logger.info("=" * 70)

    bot.polling(none_stop=True, timeout=60)