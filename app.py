import datetime
import os
from dotenv import load_dotenv
from gtts import gTTS
import requests

os.environ["IMAGEMAGICK_BINARY"] = r"C:\Program Files\ImageMagick-7.1.2-Q16-HDRI\magick.exe"

from moviepy.editor import (
    AudioFileClip,
    CompositeVideoClip,
    TextClip,
    VideoFileClip,
)
from moviepy.config import change_settings
from openai import OpenAI
import telebot

load_dotenv()

change_settings({"IMAGEMAGICK_BINARY": r"C:\Program Files\ImageMagick-7.1.2-Q16-HDRI\magick.exe"})

bot = telebot.TeleBot(os.getenv("TELEGRAM_TOKEN"))
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# =============================================================================
# PROMPT
# =============================================================================

IV_CLINIC_PROMPT = """You are a world-class direct response copywriter specializing in high-end mobile IV therapy services.

Your task is to write a high-converting short-form video script (for TikTok, Instagram Reels, and YouTube Shorts) based on the user’s topic.

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

1. HOOK (first 2–3 seconds)
   - Grab attention immediately
   - Target pain points like fatigue, dehydration, hangover, burnout, low energy

2. PROBLEM
   - Explain why common solutions (water, rest, coffee) don’t work fast enough

3. SOLUTION
   - Introduce mobile IV therapy
   - Emphasize:
     • Fast absorption
     • Direct delivery into bloodstream
     • At-home convenience
     • Premium experience

4. BENEFITS
   - Energy boost
   - Hydration
   - Recovery
   - Wellness improvement

5. CALL TO ACTION (VERY IMPORTANT)
   - Clear and direct
   - Example: “Book now through the link in bio”

━━━━━━━━━━━━━━━━━━━
GOAL
━━━━━━━━━━━━━━━━━━━
- Make the viewer feel the pain
- Position the service as the fastest and most effective solution
- Drive immediate action and conversions

━━━━━━━━━━━━━━━━━━━
FINAL INSTRUCTION
━━━━━━━━━━━━━━━━━━━
Return ONLY the final voiceover script.
Do not add anything else."""

# =============================================================================
# 🔥 INTERNAL FUNCTIONS
# =============================================================================

def generate_script_internal(topic):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": IV_CLINIC_PROMPT},
            {"role": "user", "content": f"Write a script about: {topic}"},
        ],
    )

    script_content = response.choices[0].message.content

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_topic = topic.replace(" ", "_")[:20]
    filepath = f"output/script_{timestamp}_{safe_topic}.txt"

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(script_content)

    return os.path.basename(filepath)


def generate_voiceover_internal(script_filename):
    filepath = f"output/{script_filename}"

    with open(filepath, "r", encoding="utf-8") as f:
        script_text = f.read()

    tts = gTTS(text=script_text, lang="en", slow=False)
    mp3_path = filepath.replace(".txt", ".mp3")
    tts.save(mp3_path)

    return os.path.basename(mp3_path)


def create_video_internal(audio_filename):
    audio_path = f"output/{audio_filename}"
    bg_video_path = "assets/background.mp4"

    audio_clip = AudioFileClip(audio_path)
    video_clip = VideoFileClip(bg_video_path)

    if video_clip.duration < audio_clip.duration:
        video_clip = video_clip.loop(duration=audio_clip.duration)
    else:
        video_clip = video_clip.subclip(0, audio_clip.duration)

    final_clip = video_clip.set_audio(audio_clip)
    output_video_path = audio_path.replace(".mp3", ".mp4")

    final_clip.write_videofile(
        output_video_path,
        fps=24,
        codec="libx264",
        audio_codec="aac",
        verbose=False,
        logger=None,
    )

    final_clip.close()
    audio_clip.close()
    video_clip.close()

    return os.path.basename(output_video_path)


def add_text_internal(video_filename, script_filename):
    video_path = f"output/{video_filename}"
    script_path = f"output/{script_filename}"

    video_clip = VideoFileClip(video_path)

    with open(script_path, "r", encoding="utf-8") as f:
        script_text = f.read()

    sentences = [s.strip() for s in script_text.split(".") if s.strip()]
    total_duration = video_clip.duration

    char_counts = [len(s) for s in sentences]
    total_chars = sum(char_counts)
    durations = [(c / total_chars) * total_duration for c in char_counts]

    txt_clips = []
    start_time = 0

    for sentence, duration in zip(sentences, durations):
        txt_clip = TextClip(
            sentence,
            fontsize=60,
            color="white",
            font="Arial-Bold",
            stroke_color="black",
            stroke_width=2,
            size=(video_clip.w - 100, None),
            method="caption",
        )

        txt_clip = (
            txt_clip.set_position("center")
            .set_start(start_time)
            .set_duration(duration)
        )

        txt_clips.append(txt_clip)
        start_time += duration

    final_video = CompositeVideoClip([video_clip] + txt_clips)
    output_path = video_path.replace(".mp4", "_final.mp4")

    final_video.write_videofile(
        output_path,
        fps=24,
        codec="libx264",
        audio_codec="aac",
        verbose=False,
        logger=None,
    )

    final_video.close()
    video_clip.close()

    return os.path.basename(output_path)

# =============================================================================
# ☁️ N8N UPLOAD FUNCTION (NEW)
# =============================================================================

def upload_to_cloud(filepath):
    webhook_url = "http://localhost:5678/webhook/upload-video"

    with open(filepath, 'rb') as f:
        files = {
            'file': (os.path.basename(filepath), f, 'video/mp4')
        }
        # Use 'data' key if you parse JSON in n8n
        response = requests.post(webhook_url, files=files)

    print("Upload response:", response.status_code, response.text)
    return response.status_code, response.text

# =============================================================================
# 🚀 FULL PIPELINE COMMAND
# =============================================================================

@bot.message_handler(commands=["full_pipeline"])
def run_full_pipeline(message):
    try:
        topic = message.text.split(" ", 1)[1]

        bot.reply_to(
            message,
            f"🚀 Starting Full Pipeline for: *{topic}*\n(This will take 2-3 minutes)",
            parse_mode="Markdown",
        )

        # 1. Script
        script_filename = generate_script_internal(topic)

        # 2. Voice
        audio_filename = generate_voiceover_internal(script_filename)

        # 3. Video
        video_filename = create_video_internal(audio_filename)

        # 4. Captions
        final_output = add_text_internal(video_filename, script_filename)

        # 5. Send to Telegram
        with open(f"output/{final_output}", "rb") as video:
            bot.send_video(
                message.chat.id,
                video,
                caption="🔥 Your high-converting IV Clinic video is ready!",
            )

        # 6. Upload to n8n
        status, response_text = upload_to_cloud(f"output/{final_output}")

        bot.reply_to(
            message,
            f"☁️ Uploaded to n8n successfully ✅\nStatus: {status}"
        )

    except Exception as e:
        bot.reply_to(message, f"❌ Pipeline failed: {str(e)}")

# =============================================================================
# ENTRY
# =============================================================================

print("OpenClaw FULL PIPELINE + n8n is active ")
bot.polling()