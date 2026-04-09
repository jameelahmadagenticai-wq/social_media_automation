import datetime
import os
import traceback
import json
from dotenv import load_dotenv
from gtts import gTTS
from PIL import Image
from openai import OpenAI
import telebot
from telebot import apihelper

# ─────────────────────────────────────────
#  MoviePy / ImageMagick
# ─────────────────────────────────────────
IMAGEMAGICK_PATH = r"C:\Program Files\ImageMagick-7.1.2-Q16-HDRI\magick.exe"
os.environ["IMAGEMAGICK_BINARY"] = IMAGEMAGICK_PATH

from moviepy.editor import AudioFileClip, CompositeVideoClip, TextClip, VideoFileClip
from moviepy.config import change_settings

change_settings({"IMAGEMAGICK_BINARY": IMAGEMAGICK_PATH})

# ─────────────────────────────────────────
#  Pillow compatibility shim
# ─────────────────────────────────────────
if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.Resampling.LANCZOS


# ══════════════════════════════════════════════════════════════
#  ENVIRONMENT
# ══════════════════════════════════════════════════════════════

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
WEBHOOK_URL    = os.getenv("WEBHOOK_URL")
OUTPUT_DIR     = "output"
MAX_FILES      = int(os.getenv("MAX_OUTPUT_FILES", 20))

bot    = telebot.TeleBot(TELEGRAM_TOKEN)
client = OpenAI(api_key=OPENAI_API_KEY)

apihelper.CONNECT_TIMEOUT = 60
apihelper.READ_TIMEOUT    = 120


# ══════════════════════════════════════════════════════════════
#  SESSION 1 — SCRIPT GENERATION
# ══════════════════════════════════════════════════════════════

IV_CLINIC_PROMPT = """You are a world-class direct response copywriter specializing in high-end mobile IV therapy services.

Your task is to write a high-converting short-form video script (for TikTok, Instagram Reels, and YouTube Shorts) based on the user's topic.

━━━━━━━━━━━━━━━━━━━
OUTPUT RULES (STRICT)
━━━━━━━━━━━━━━━━━━━
- Output ONLY the voiceover script
- Do NOT include scene directions, brackets, labels, or emojis
- Do NOT include titles or explanations
- Keep it under 60 seconds
- Use clean, natural spoken language (optimized for text-to-speech)

━━━━━━━━━━━━━━━━━━━
TONE & STYLE
━━━━━━━━━━━━━━━━━━━
- Premium, luxury, and trustworthy
- Conversational and human (not robotic)
- Emotionally engaging but not exaggerated
- Confident and persuasive
- Clear and easy to understand

━━━━━━━━━━━━━━━━━━━
PACING & DELIVERY
━━━━━━━━━━━━━━━━━━━
- Use short sentences
- Break lines frequently for natural pauses
- Use ellipses (...) to create emotional pauses
- Make it sound smooth when spoken aloud

━━━━━━━━━━━━━━━━━━━
SCRIPT STRUCTURE
━━━━━━━━━━━━━━━━━━━
1. HOOK (first 2-3 seconds)
2. PROBLEM
3. SOLUTION
4. BENEFITS
5. CALL TO ACTION

━━━━━━━━━━━━━━━━━━━
FINAL INSTRUCTION
━━━━━━━━━━━━━━━━━━━
Return ONLY the final voiceover script.
Do not add anything else.
"""

def session_script(topic: str) -> str:
    """Generate script via GPT-4o. Returns saved filename."""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": IV_CLINIC_PROMPT},
            {"role": "user",   "content": f"Write about: {topic}"},
        ]
    )

    script_text = response.choices[0].message.content.strip()
    filename    = f"script_{_ts()}.txt"
    _save_text(filename, script_text)

    return filename


# ══════════════════════════════════════════════════════════════
#  SESSION 2 — AUDIO (TTS + Whisper word timestamps)
# ══════════════════════════════════════════════════════════════

def session_audio(script_file: str) -> tuple[str, str]:
    """
    1. Convert script → MP3 via gTTS
    2. Run Whisper on the MP3 to get word-level timestamps
    3. Save timestamps as a JSON sidecar file

    Returns (audio_filename, timestamps_filename)
    """

    script_text = _load_text(script_file)

    # — TTS —
    audio_filename = script_file.replace(".txt", ".mp3")
    audio_path     = _path(audio_filename)
    gTTS(text=script_text).save(audio_path)

    # — Whisper word timestamps —
    with open(audio_path, "rb") as f:
        whisper_result = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="verbose_json",
            timestamp_granularities=["word"],
        )

    # whisper_result.words = list of {"word", "start", "end"}
    words = [
        {"word": w.word.strip(), "start": w.start, "end": w.end}
        for w in whisper_result.words
        if w.word.strip()
    ]

    ts_filename = script_file.replace(".txt", "_timestamps.json")
    _save_text(ts_filename, json.dumps(words, ensure_ascii=False, indent=2))

    return audio_filename, ts_filename


# ══════════════════════════════════════════════════════════════
#  SESSION 3 — VIDEO (background loop)
# ══════════════════════════════════════════════════════════════

def session_video(audio_file: str) -> str:
    """Loop background.mp4 to match audio duration. Returns video filename."""

    audio = AudioFileClip(_path(audio_file))
    video = VideoFileClip("assets/background.mp4")

    # Crop to vertical 9:16 (720 × 1280)
    video = video.resize(height=1280)
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
        fps=24, codec="libx264", audio_codec="aac",
        preset="ultrafast", threads=4, bitrate="1000k",
        verbose=False, logger=None,
    )

    audio.close()
    video.close()

    return video_file


# ══════════════════════════════════════════════════════════════
#  SESSION 4 — TEXT OVERLAY  (100% Whisper-synced)
# ══════════════════════════════════════════════════════════════

WORDS_PER_CHUNK = 5        # words shown at once — tune freely
FONT_SIZE       = 68
TEXT_Y_RATIO    = 0.55     # vertical position (0 = top, 1 = bottom)


def session_text_overlay(video_file: str, timestamps_file: str) -> str:
    """
    Burn subtitles onto the video using exact Whisper timestamps.
    Words are grouped into chunks; each chunk appears/disappears
    at the exact millisecond Whisper detected them in the audio.

    Returns final video filename.
    """

    video = VideoFileClip(_path(video_file))
    words = json.loads(_load_text(timestamps_file))

    # — Group words into chunks of WORDS_PER_CHUNK —
    chunks = []
    for i in range(0, len(words), WORDS_PER_CHUNK):
        group  = words[i : i + WORDS_PER_CHUNK]
        text   = " ".join(w["word"] for w in group)
        start  = group[0]["start"]
        end    = group[-1]["end"]
        chunks.append({"text": text, "start": start, "end": end})

    # — Build TextClips from chunks —
    text_clips = []
    for chunk in chunks:
        duration = chunk["end"] - chunk["start"]
        if duration <= 0:
            continue

        clip = (
            TextClip(
                chunk["text"],
                fontsize=FONT_SIZE,
                color="white",
                font="Arial-Bold",
                stroke_color="black",
                stroke_width=3,
                size=(int(video.w * 0.85), None),
                method="caption",
                align="center",
            )
            .set_position(("center", video.h * TEXT_Y_RATIO))
            .set_start(chunk["start"])
            .set_duration(duration)
            .crossfadein(0.06)
            .crossfadeout(0.06)
        )
        text_clips.append(clip)

    # — Composite & export —
    final = CompositeVideoClip([video] + text_clips)

    final_file = video_file.replace("_bg.mp4", "_final.mp4")
    final.write_videofile(
        _path(final_file),
        fps=24, codec="libx264", audio_codec="aac",
        preset="ultrafast", threads=4, bitrate="1000k",
        verbose=False, logger=None,
    )

    video.close()
    final.close()

    return final_file


# ══════════════════════════════════════════════════════════════
#  SESSION 5 — WEBHOOK UPLOAD
# ══════════════════════════════════════════════════════════════

def session_webhook(final_file: str) -> bool:
    """Upload finished video to webhook. Returns True on success."""

    import requests

    try:
        with open(_path(final_file), "rb") as f:
            res = requests.post(
                WEBHOOK_URL,
                files={"file": (final_file, f, "video/mp4")},
                timeout=120,
            )
        print(f"[webhook] {res.status_code} — {res.text}")
        return res.status_code == 200
    except Exception as e:
        print(f"[webhook] Upload failed: {e}")
        return False


# ══════════════════════════════════════════════════════════════
#  PIPELINE  — ties all sessions together
# ══════════════════════════════════════════════════════════════

@bot.message_handler(commands=["generate_video"])
def pipeline(message):
    try:
        _cleanup_output_folder()

        parts = message.text.split(" ", 1)
        if len(parts) < 2 or not parts[1].strip():
            bot.reply_to(message, "❌ Please provide a topic.\nExample: /generate_video hangover recovery")
            return

        topic = parts[1].strip()

        bot.reply_to(
            message,
            f"🎬 Your video is being processed…\n_Topic: {topic}_",
            parse_mode="Markdown",
        )

        # Run all sessions silently
        script_file            = session_script(topic)
        audio_file, ts_file    = session_audio(script_file)
        video_file             = session_video(audio_file)
        final_file             = session_text_overlay(video_file, ts_file)

        # Deliver video
        with open(_path(final_file), "rb") as v:
            bot.send_video(message.chat.id, v, caption="🔥 Your video is ready!")

        # Session 5 — Webhook (silent)
        if WEBHOOK_URL:
            session_webhook(final_file)
            bot.send_message(message.chat.id, "☁️ Uploaded to cloud successfully.")

    except Exception:
        print(traceback.format_exc())
        bot.reply_to(message, "❌ Something went wrong. Please try again.")


# ══════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════

def _ts() -> str:
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def _path(filename: str) -> str:
    return os.path.join(OUTPUT_DIR, filename)


def _save_text(filename: str, content: str):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(_path(filename), "w", encoding="utf-8") as f:
        f.write(content)


def _load_text(filename: str) -> str:
    with open(_path(filename), "r", encoding="utf-8") as f:
        return f.read()


def _cleanup_output_folder():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    files = sorted(
        [_path(f) for f in os.listdir(OUTPUT_DIR)],
        key=os.path.getctime,
    )
    for old_file in files[:-MAX_FILES]:
        try:
            os.remove(old_file)
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("🚀 Bot running…")
    bot.polling()