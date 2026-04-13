
# ══════════════════════════════════════════════════════════════
#  SECTION 1 — IMPORTS
# ══════════════════════════════════════════════════════════════

import datetime
import json
import logging
import os
import traceback
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
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


# ══════════════════════════════════════════════════════════════
#  SECTION 2 — LOGGING SETUP
# ══════════════════════════════════════════════════════════════

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

log_filename = os.path.join(LOG_DIR, f"bot_{datetime.date.today()}.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(log_filename, encoding="utf-8"),
        logging.StreamHandler(),  # also print to console
    ],
)

logger = logging.getLogger("VideoBot")


# ══════════════════════════════════════════════════════════════
#  SECTION 3 — ENVIRONMENT & CONFIGURATION
# ══════════════════════════════════════════════════════════════

load_dotenv()

# — Required credentials —
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# — Optional settings —
WEBHOOK_URL      = os.getenv("WEBHOOK_URL", "")
OUTPUT_DIR       = os.getenv("OUTPUT_DIR", "output")
MAX_FILES        = int(os.getenv("MAX_OUTPUT_FILES", 20))
IMAGEMAGICK_PATH = os.getenv("IMAGEMAGICK_PATH", r"C:\Program Files\ImageMagick-7.1.2-Q16-HDRI\magick.exe")

# — OpenAI TTS settings —
TTS_MODEL = os.getenv("TTS_MODEL", "tts-1")           # tts-1 | tts-1-hd
TTS_VOICE = os.getenv("TTS_VOICE", "alloy")           # alloy | echo | fable | onyx | nova | shimmer

# Validate required env vars at startup
for var_name, var_value in [("TELEGRAM_TOKEN", TELEGRAM_TOKEN), ("OPENAI_API_KEY", OPENAI_API_KEY)]:
    if not var_value:
        logger.critical(f"Missing required environment variable: {var_name}")
        raise EnvironmentError(f"{var_name} is not set in your .env file.")

# — ImageMagick setup (required by MoviePy for TextClip) —
os.environ["IMAGEMAGICK_BINARY"] = IMAGEMAGICK_PATH
change_settings({"IMAGEMAGICK_BINARY": IMAGEMAGICK_PATH})
logger.info(f"ImageMagick path set → {IMAGEMAGICK_PATH}")

# — Pillow backwards-compatibility shim —
if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.Resampling.LANCZOS

# — API clients —
bot    = telebot.TeleBot(TELEGRAM_TOKEN)
client = OpenAI(api_key=OPENAI_API_KEY)

# — Telegram timeout settings —
apihelper.CONNECT_TIMEOUT = 60
apihelper.READ_TIMEOUT    = 600


# ══════════════════════════════════════════════════════════════
#  SECTION 4 — BRAND SYSTEM
# ══════════════════════════════════════════════════════════════

with open("brands.json", "r", encoding="utf-8") as f:
    BRANDS: dict = json.load(f)

CURRENT_BRAND = "iv_clinic"   # updated at runtime via /set_brand


def _ensure_brand_directories():
    """Create output/<brand> and assets/<brand> folders for every brand."""
    for brand_key in BRANDS:
        os.makedirs(os.path.join(OUTPUT_DIR, brand_key), exist_ok=True)
        os.makedirs(os.path.join("assets", brand_key), exist_ok=True)
    logger.info(f"Brand directories verified for {len(BRANDS)} brand(s).")


_ensure_brand_directories()


# ══════════════════════════════════════════════════════════════
#  SECTION 5 — FILE HELPERS
# ══════════════════════════════════════════════════════════════

def _ts() -> str:
    """Compact timestamp string used to create unique filenames."""
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def _brand_dir() -> str:
    """Absolute path to the active brand's output folder."""
    folder = os.path.join(OUTPUT_DIR, CURRENT_BRAND)
    os.makedirs(folder, exist_ok=True)
    return folder


def _path(filename: str) -> str:
    """Full path for a file inside the active brand's output folder."""
    return os.path.join(_brand_dir(), filename)


def _save_text(filename: str, content: str):
    """Write text content to a file in the active brand's output folder."""
    with open(_path(filename), "w", encoding="utf-8") as f:
        f.write(content)


def _load_text(filename: str) -> str:
    """Read text content from a file in the active brand's output folder."""
    with open(_path(filename), "r", encoding="utf-8") as f:
        return f.read()


def _cleanup_output_folder():
    """
    Delete the oldest .mp4 files when the brand folder exceeds MAX_FILES.
    Prevents disk space issues during long-running sessions.
    """
    folder  = _brand_dir()
    mp4s    = sorted(
        [os.path.join(folder, f) for f in os.listdir(folder) if f.endswith(".mp4")],
        key=os.path.getctime,
    )
    to_delete = mp4s[:-MAX_FILES]
    for old_file in to_delete:
        try:
            os.remove(old_file)
            logger.info(f"[cleanup] Removed old file → {old_file}")
        except OSError as e:
            logger.warning(f"[cleanup] Could not remove {old_file}: {e}")


# ══════════════════════════════════════════════════════════════
#  SECTION 6 — SESSION 1: SCRIPT GENERATION
# ══════════════════════════════════════════════════════════════

def _build_system_prompt(brand_key: str) -> str:
    """Build the GPT system prompt using the brand's config."""
    brand = BRANDS[brand_key]
    return f"""You are a world-class direct response copywriter for {brand['name']}, \
a brand in the {brand['industry']} industry.

Tone: {brand['tone']}

Write a high-converting short-form video script (TikTok / Instagram Reels / YouTube Shorts).

SCRIPT STRUCTURE:
1. Hook        (2-3 seconds — grab attention instantly)
2. Problem     (pain point the viewer feels)
3. Solution    (how {brand['name']} solves it)
4. Benefits    (concrete outcomes / results)
5. Call to Action — use EXACTLY this CTA:
   {brand['cta']}

OUTPUT RULES:
- Return ONLY the voiceover script — no scene directions, brackets, labels, or emojis
- Short sentences, natural spoken language
- Under 60 seconds when spoken aloud
"""


@retry(
    retry=retry_if_exception_type(OpenAIError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def session_script(topic: str, brand_key: str) -> str:
    """
    SESSION 1 — Generate a voiceover script via GPT-4o.

    Retries up to 3 times on OpenAI API failures.

    Args:
        topic     : The video subject (e.g. "hangover recovery").
        brand_key : Key from brands.json (e.g. "iv_clinic").

    Returns:
        Saved script filename (relative to brand output folder).
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


# ══════════════════════════════════════════════════════════════
#  SECTION 7 — SESSION 2: AUDIO (OpenAI TTS + Whisper Timestamps)
# ══════════════════════════════════════════════════════════════

@retry(
    retry=retry_if_exception_type(OpenAIError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def session_audio(script_file: str) -> tuple[str, str]:
    """
    SESSION 2 — Convert script to audio and extract word-level timestamps.

    Steps:
        1. Synthesise speech via OpenAI TTS (configurable model & voice).
        2. Run Whisper on the MP3 for exact word-level timestamps.
        3. Save timestamps as a JSON sidecar file.

    Args:
        script_file : Filename of the saved script (from session_script).

    Returns:
        Tuple of (audio_filename, timestamps_filename).
    """
    script_text    = _load_text(script_file)
    audio_filename = script_file.replace(".txt", ".mp3")
    audio_path     = _path(audio_filename)

    # — Step 1: OpenAI TTS —
    logger.info(f"[audio] Generating TTS | model={TTS_MODEL} | voice={TTS_VOICE}")
    tts_response = client.audio.speech.create(
        model=TTS_MODEL,
        voice=TTS_VOICE,
        input=script_text,
    )
    tts_response.stream_to_file(audio_path)
    logger.info(f"[audio] TTS saved → {audio_filename}")

    # — Step 2: Whisper word-level timestamps —
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

    # — Step 3: Save timestamps JSON —
    ts_filename = script_file.replace(".txt", "_timestamps.json")
    _save_text(ts_filename, json.dumps(words, ensure_ascii=False, indent=2))
    logger.info(f"[audio] Timestamps saved → {ts_filename} ({len(words)} words)")

    return audio_filename, ts_filename


# ══════════════════════════════════════════════════════════════
#  SECTION 8 — SESSION 3: BACKGROUND VIDEO
# ══════════════════════════════════════════════════════════════

def session_video(audio_file: str) -> str:
    """
    SESSION 3 — Crop & loop the brand's background video to match audio duration.

    Target resolution: 720 × 1280 (vertical 9:16).

    Args:
        audio_file : Filename of the generated audio (from session_audio).

    Returns:
        Background video filename.
    """
    brand      = BRANDS[CURRENT_BRAND]
    audio_path = _path(audio_file)

    logger.info(f"[video] Building background video | bg={brand['bg_video']}")

    if not os.path.exists(brand["bg_video"]):
        raise FileNotFoundError(f"Background video not found: {brand['bg_video']}")

    audio = AudioFileClip(audio_path)
    video = VideoFileClip(brand["bg_video"]).resize(height=1280)

    # Crop to 720 px wide if source is wider than target
    if video.w > 720:
        video = video.crop(x_center=video.w / 2, width=720)

    # Loop short videos or trim long ones to match audio length
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


# ══════════════════════════════════════════════════════════════
#  SECTION 9 — SESSION 4: SUBTITLE OVERLAY (Whisper-Synced)
# ══════════════════════════════════════════════════════════════

WORDS_PER_CHUNK = 5      # number of words displayed per subtitle chunk
FONT_SIZE       = 68     # subtitle font size in pixels
TEXT_Y_RATIO    = 0.55   # vertical position (0.0 = top, 1.0 = bottom)


def session_text_overlay(video_file: str, timestamps_file: str) -> str:
    """
    SESSION 4 — Burn Whisper-synced subtitles onto the background video.

    - Words are grouped into chunks of WORDS_PER_CHUNK.
    - Each chunk appears/disappears at Whisper-detected timestamps.
    - Soft 60 ms crossfade-in / crossfade-out for a polished look.

    Args:
        video_file       : Filename of the background video (from session_video).
        timestamps_file  : Filename of the Whisper timestamps JSON (from session_audio).

    Returns:
        Final video filename.
    """
    logger.info(f"[subtitles] Overlaying subtitles | video={video_file}")

    video = VideoFileClip(_path(video_file))
    words = json.loads(_load_text(timestamps_file))

    # — Build one TextClip per word-chunk —
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
                size=(int(video.w * 0.85), None),  # constrain width, auto height
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

    # — Composite & export —
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


# ══════════════════════════════════════════════════════════════
#  SECTION 10 — SESSION 5: WEBHOOK UPLOAD (Cloud Delivery)
# ══════════════════════════════════════════════════════════════

@retry(
    retry=retry_if_exception_type(requests.RequestException),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def session_webhook(final_file: str) -> bool:
    """
    SESSION 5 — Upload the final video to a webhook/cloud endpoint.

    Retries up to 3 times on network failures.
    Skipped silently if WEBHOOK_URL is not configured.

    Args:
        final_file : Filename of the final video (from session_text_overlay).

    Returns:
        True if upload succeeded, False otherwise.
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


# ══════════════════════════════════════════════════════════════
#  SECTION 11 — PIPELINE ORCHESTRATOR (Threading)
# ══════════════════════════════════════════════════════════════
#
#  Pipeline with parallelism:
#
#    [Session 1: Script]
#         ↓
#    [Session 2: Audio + Timestamps]  ← runs first, produces both outputs
#         ↓
#    ┌────┴────────────────┐
#    │                     │
#    [Session 3: BG Video] [Nothing yet — timestamps already ready]
#         ↓
#    [Session 4: Subtitles]  ← waits for both video + timestamps
#         ↓
#    [Session 5: Webhook]
#
#  Sessions 3 & 4 are sequential by nature (4 needs 3's output).
#  However, if you have multiple topics queued, each full pipeline
#  runs in its own thread via the ThreadPoolExecutor below.
# ══════════════════════════════════════════════════════════════

def run_pipeline(topic: str, brand_key: str) -> str:
    """
    Execute the full video generation pipeline for a single topic.

    Steps (in order):
        1. Generate script
        2. Generate audio + timestamps (OpenAI TTS + Whisper)
        3. Build background video (runs after audio)
        4. Burn subtitles onto video
        5. Upload to webhook (if configured)

    Args:
        topic     : Subject of the video (e.g. "hangover recovery").
        brand_key : Active brand key.

    Returns:
        Full path to the final .mp4 file.

    Raises:
        Any exception from a failing session (caller handles it).
    """
    logger.info(f"[pipeline] START | brand={brand_key} | topic='{topic}'")
    t0 = datetime.datetime.now()

    script_file            = session_script(topic, brand_key)
    audio_file, ts_file    = session_audio(script_file)
    video_file             = session_video(audio_file)
    final_file             = session_text_overlay(video_file, ts_file)

    elapsed = (datetime.datetime.now() - t0).seconds
    logger.info(f"[pipeline] DONE in {elapsed}s → {final_file}")

    # Upload to cloud (non-blocking result — won't affect video delivery)
    if WEBHOOK_URL:
        try:
            session_webhook(final_file)
        except Exception as e:
            logger.error(f"[pipeline] Webhook upload failed after retries: {e}")

    return _path(final_file)


# ══════════════════════════════════════════════════════════════
#  SECTION 12 — TELEGRAM COMMANDS
# ══════════════════════════════════════════════════════════════

@bot.message_handler(commands=["set_brand"])
def cmd_set_brand(message):
    """
    Switch the active brand.
    Usage: /set_brand iv_clinic
    """
    global CURRENT_BRAND

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
    logger.info(f"[bot] Brand switched to: {brand_id}")
    bot.reply_to(
        message,
        f"✅ Switched to *{BRANDS[brand_id]['name']}*",
        parse_mode="Markdown",
    )


@bot.message_handler(commands=["brands"])
def cmd_list_brands(message):
    """List all configured brands and highlight the active one."""
    lines = ["*Available Brands*\n"]
    for key, brand in BRANDS.items():
        active = " ← active" if key == CURRENT_BRAND else ""
        lines.append(f"  • `{key}` — {brand['name']}{active}")
    bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")


@bot.message_handler(commands=["generate_video"])
def cmd_generate_video(message):
    """
    Run the full video generation pipeline and deliver the result.

    Usage: /generate_video <topic>
    Example: /generate_video hangover recovery

    The pipeline runs in a background thread so Telegram stays responsive.
    Multiple /generate_video calls can run concurrently.
    """
    parts = message.text.split(" ", 1)
    if len(parts) < 2 or not parts[1].strip():
        bot.reply_to(
            message,
            "❌ Please provide a topic.\nExample: `/generate_video hangover recovery`",
            parse_mode="Markdown",
        )
        return

    topic      = parts[1].strip()
    brand_key  = CURRENT_BRAND   # snapshot current brand (thread-safe read)

    _cleanup_output_folder()

    bot.reply_to(
        message,
        f"🎬 Processing your video…\n"
        f"*Brand:* {BRANDS[brand_key]['name']}\n"
        f"*Topic:* {topic}",
        parse_mode="Markdown",
    )

    logger.info(f"[bot] /generate_video | chat_id={message.chat.id} | topic='{topic}'")

    # — Run pipeline in a background thread so the bot stays responsive —
    with ThreadPoolExecutor(max_workers=4) as executor:
        future = executor.submit(run_pipeline, topic, brand_key)
        try:
            final_path = future.result()

            with open(final_path, "rb") as v:
                bot.send_video(
                    message.chat.id,
                    v,
                    caption=f"🔥 *{BRANDS[brand_key]['name']}* — {topic}",
                    parse_mode="Markdown",
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


# ══════════════════════════════════════════════════════════════
#  SECTION 13 — ENTRY POINT
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("🚀  VideoBot starting…")
    logger.info(f"   Active brand  : {CURRENT_BRAND} ({BRANDS[CURRENT_BRAND]['name']})")
    logger.info(f"   Output dir    : {OUTPUT_DIR}/")
    logger.info(f"   TTS model     : {TTS_MODEL} | voice: {TTS_VOICE}")
    logger.info(f"   Webhook URL   : {WEBHOOK_URL or 'not set'}")
    logger.info(f"   Log file      : {log_filename}")
    logger.info("=" * 60)

    bot.polling(none_stop=True, timeout=60)