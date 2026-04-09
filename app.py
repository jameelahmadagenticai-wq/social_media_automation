# ══════════════════════════════════════════════════════════════
#  IMPORTS
# ══════════════════════════════════════════════════════════════

import datetime
import json
import os
import traceback

import requests
import telebot
from dotenv import load_dotenv
from gtts import gTTS
from moviepy.config import change_settings
from moviepy.editor import (
    AudioFileClip,
    CompositeVideoClip,
    TextClip,
    VideoFileClip,
)
from openai import OpenAI
from PIL import Image
from telebot import apihelper


# ══════════════════════════════════════════════════════════════
#  SYSTEM SETUP  (Windows / ImageMagick)
# ══════════════════════════════════════════════════════════════

IMAGEMAGICK_PATH = r"C:\Program Files\ImageMagick-7.1.2-Q16-HDRI\magick.exe"
os.environ["IMAGEMAGICK_BINARY"] = IMAGEMAGICK_PATH
change_settings({"IMAGEMAGICK_BINARY": IMAGEMAGICK_PATH})

# Pillow backwards-compat shim
if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.Resampling.LANCZOS


# ══════════════════════════════════════════════════════════════
#  ENVIRONMENT
# ══════════════════════════════════════════════════════════════

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
WEBHOOK_URL    = os.getenv("WEBHOOK_URL")          # optional — cloud upload
OUTPUT_DIR     = "output"
MAX_FILES      = int(os.getenv("MAX_OUTPUT_FILES", 20))

bot    = telebot.TeleBot(TELEGRAM_TOKEN)
client = OpenAI(api_key=OPENAI_API_KEY)

apihelper.CONNECT_TIMEOUT = 60
apihelper.READ_TIMEOUT    = 120


# ══════════════════════════════════════════════════════════════
#  BRAND SYSTEM
# ══════════════════════════════════════════════════════════════


with open("brands.json", "r", encoding="utf-8") as f:
    BRANDS: dict = json.load(f)

CURRENT_BRAND = "iv_clinic"          # changed at runtime via /set_brand


def _ensure_directories():
    """Create output/<brand> and assets/<brand> folders for every brand."""
    for brand_key in BRANDS:
        os.makedirs(os.path.join(OUTPUT_DIR, brand_key), exist_ok=True)
        os.makedirs(os.path.join("assets", brand_key), exist_ok=True)


_ensure_directories()


# ══════════════════════════════════════════════════════════════
#  FILE HELPERS
# ══════════════════════════════════════════════════════════════

def _ts() -> str:
    """Compact timestamp string for unique filenames."""
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def _brand_dir() -> str:
    """Absolute path to the current brand's output folder."""
    folder = os.path.join(OUTPUT_DIR, CURRENT_BRAND)
    os.makedirs(folder, exist_ok=True)
    return folder


def _path(filename: str) -> str:
    """Full path inside the current brand's output folder."""
    return os.path.join(_brand_dir(), filename)


def _save_text(filename: str, content: str):
    with open(_path(filename), "w", encoding="utf-8") as f:
        f.write(content)


def _load_text(filename: str) -> str:
    with open(_path(filename), "r", encoding="utf-8") as f:
        return f.read()


def _cleanup_output_folder():
    """Delete oldest .mp4 files when the brand folder exceeds MAX_FILES."""
    folder = _brand_dir()
    mp4_files = sorted(
        [os.path.join(folder, f) for f in os.listdir(folder) if f.endswith(".mp4")],
        key=os.path.getctime,
    )
    for old_file in mp4_files[:-MAX_FILES]:
        try:
            os.remove(old_file)
        except OSError:
            pass


# ══════════════════════════════════════════════════════════════
#  SESSION 1 — SCRIPT GENERATION
# ══════════════════════════════════════════════════════════════

def _build_system_prompt(brand_key: str) -> str:
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


def session_script(topic: str, brand_key: str) -> str:
    """
    Generate a voiceover script via GPT-4o.

    Returns: saved script filename (relative to brand output folder).
    """
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

    print(f"[script] Saved → {filename}")
    return filename


# ══════════════════════════════════════════════════════════════
#  SESSION 2 — AUDIO  (TTS + Whisper word timestamps)
# ══════════════════════════════════════════════════════════════

def session_audio(script_file: str) -> tuple[str, str]:
    """
    1. Convert script text → MP3 via gTTS.
    2. Run Whisper on the MP3 to obtain exact word-level timestamps.
    3. Save timestamps as a JSON sidecar.

    Returns: (audio_filename, timestamps_filename)
    """
    script_text    = _load_text(script_file)
    audio_filename = script_file.replace(".txt", ".mp3")
    audio_path     = _path(audio_filename)

    # — Text-to-Speech —
    gTTS(text=script_text).save(audio_path)
    print(f"[audio] TTS saved → {audio_filename}")

    # — Whisper word-level timestamps —
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

    ts_filename = script_file.replace(".txt", "_timestamps.json")
    _save_text(ts_filename, json.dumps(words, ensure_ascii=False, indent=2))
    print(f"[audio] Timestamps saved → {ts_filename}  ({len(words)} words)")

    return audio_filename, ts_filename


# ══════════════════════════════════════════════════════════════
#  SESSION 3 — BACKGROUND VIDEO
# ══════════════════════════════════════════════════════════════

def session_video(audio_file: str) -> str:
    """
    Crop & loop the brand's background video to match the audio duration.
    Target resolution: 720 × 1280  (vertical 9:16).

    Returns: background video filename.
    """
    brand      = BRANDS[CURRENT_BRAND]
    audio      = AudioFileClip(_path(audio_file))
    video      = VideoFileClip(brand["bg_video"]).resize(height=1280)

    # Crop to 720 px wide if wider than target
    if video.w > 720:
        video = video.crop(x_center=video.w / 2, width=720)

    # Loop or trim to exact audio length
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
        bitrate="1000k",
        verbose=False,
        logger=None,
    )

    audio.close()
    video.close()

    print(f"[video] Background video saved → {video_file}")
    return video_file


# ══════════════════════════════════════════════════════════════
#  SESSION 4 — SUBTITLE OVERLAY  (Whisper-synced)
# ══════════════════════════════════════════════════════════════

WORDS_PER_CHUNK = 5      # words shown at once — tune freely
FONT_SIZE       = 68     # subtitle font size (px)
TEXT_Y_RATIO    = 0.55   # vertical position (0.0 = top, 1.0 = bottom)


def session_text_overlay(video_file: str, timestamps_file: str) -> str:
    """
    Burn Whisper-synced subtitles onto the video.

    - Words are grouped into chunks of WORDS_PER_CHUNK.
    - Each chunk appears and disappears at the exact timestamps Whisper detected.
    - Soft crossfade-in / crossfade-out transition (60 ms) for polish.

    Returns: final video filename.
    """
    video  = VideoFileClip(_path(video_file))
    words  = json.loads(_load_text(timestamps_file))

    # — Group words into timed chunks —
    text_clips = []
    for i in range(0, len(words), WORDS_PER_CHUNK):
        group    = words[i : i + WORDS_PER_CHUNK]
        chunk    = " ".join(w["word"] for w in group)
        start    = group[0]["start"]
        duration = group[-1]["end"] - start

        if duration <= 0:
            continue

        clip = (
            TextClip(
                chunk,
                fontsize=FONT_SIZE,
                color="white",
                font="Arial-Bold",
                stroke_color="black",
                stroke_width=3,
                size=(int(video.w * 0.85), None),   # constrain width, auto-height
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
        bitrate="1000k",
        verbose=False,
        logger=None,
    )

    video.close()
    final.close()

    print(f"[subtitles] Final video saved → {final_file}")
    return final_file


# ══════════════════════════════════════════════════════════════
#  SESSION 5 — WEBHOOK UPLOAD  (cloud delivery)
# ══════════════════════════════════════════════════════════════

def session_webhook(final_file: str) -> bool:
    """
    Upload the finished video to WEBHOOK_URL as multipart/form-data.

    Returns True on HTTP 200, False on any error.
    Skipped automatically if WEBHOOK_URL is not set.
    """
    if not WEBHOOK_URL:
        print("[webhook] WEBHOOK_URL not set — skipping upload.")
        return False

    try:
        with open(_path(final_file), "rb") as f:
            response = requests.post(
                WEBHOOK_URL,
                files={"file": (final_file, f, "video/mp4")},
                timeout=120,
            )
        print(f"[webhook] {response.status_code} — {response.text}")
        return response.status_code == 200

    except Exception as exc:
        print(f"[webhook] Upload failed: {exc}")
        return False


# ══════════════════════════════════════════════════════════════
#  TELEGRAM COMMANDS
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
    bot.reply_to(
        message,
        f"✅ Switched to *{BRANDS[brand_id]['name']}*",
        parse_mode="Markdown",
    )


@bot.message_handler(commands=["brands"])
def cmd_list_brands(message):
    """List all available brands."""
    lines = [f"*Available Brands*\n"]
    for key, brand in BRANDS.items():
        active = " ← active" if key == CURRENT_BRAND else ""
        lines.append(f"  • `{key}` — {brand['name']}{active}")
    bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")


@bot.message_handler(commands=["generate_video"])
def cmd_generate_video(message):
    """
    Full pipeline: script → audio → video → subtitles → deliver → upload.
    Usage: /generate_video <topic>
    """
    try:
        parts = message.text.split(" ", 1)
        if len(parts) < 2 or not parts[1].strip():
            bot.reply_to(
                message,
                "❌ Please provide a topic.\nExample: `/generate_video hangover recovery`",
                parse_mode="Markdown",
            )
            return

        topic = parts[1].strip()

        _cleanup_output_folder()

        bot.reply_to(
            message,
            f"🎬 Processing your video…\n"
            f"*Brand:* {BRANDS[CURRENT_BRAND]['name']}\n"
            f"*Topic:* {topic}",
            parse_mode="Markdown",
        )

        # ── Pipeline ──────────────────────────────────────────
        script_file            = session_script(topic, CURRENT_BRAND)
        audio_file, ts_file    = session_audio(script_file)
        video_file             = session_video(audio_file)
        final_file             = session_text_overlay(video_file, ts_file)
        # ──────────────────────────────────────────────────────

        # Deliver video to user
        with open(_path(final_file), "rb") as v:
            bot.send_video(
                message.chat.id,
                v,
                caption=f"🔥 *{BRANDS[CURRENT_BRAND]['name']}* — {topic}",
                parse_mode="Markdown",
            )

        # Upload to cloud (silent — won't block delivery)
        if WEBHOOK_URL:
            success = session_webhook(final_file)
            if success:
                bot.send_message(message.chat.id, "☁️ Uploaded to cloud successfully.")

    except Exception:
        print(traceback.format_exc())
        bot.reply_to(message, "❌ Something went wrong. Please try again.")


# ══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("🚀 Bot running…")
    print(f"   Active brand : {CURRENT_BRAND} ({BRANDS[CURRENT_BRAND]['name']})")
    print(f"   Output dir   : {OUTPUT_DIR}/")
    print(f"   Webhook URL  : {WEBHOOK_URL or 'not set'}")
    bot.polling()