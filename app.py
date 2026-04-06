
import datetime
import os

# ── Third-Party Libraries ─────────────────────────────────────────────────────
from dotenv import load_dotenv
from gtts import gTTS
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

# ── Environment Configuration ─────────────────────────────────────────────────
load_dotenv()

# ── MoviePy ImageMagick Configuration ─────────────────────────────────────────
# Set path both via os.environ and MoviePy's own config to ensure it's picked up
change_settings({"IMAGEMAGICK_BINARY": r"C:\Program Files\ImageMagick-7.1.2-Q16-HDRI\magick.exe"})

# ── Client Initialization ─────────────────────────────────────────────────────
bot = telebot.TeleBot(os.getenv("TELEGRAM_TOKEN"))
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# =============================================================================
# SECTION 1 — SYSTEM PROMPT
# =============================================================================

IV_CLINIC_PROMPT = """
You are an expert copywriter for a high-end Mobile IV Clinic.
Write a high-converting, punchy short-form video script (TikTok/Reels) based on the user's topic.

IMPORTANT:
* Output ONLY clean voiceover text
* Do NOT include scene directions, brackets, narrator labels, or emojis
* Keep it under 60 seconds
* Use a natural, conversational, high-end tone
* Optimize for text-to-speech (TTS)

PACING & DELIVERY:
* Use short sentences for clarity
* Add line breaks to create natural pauses
* Use ellipses (...) for emotional or dramatic pauses
* Make it sound smooth, human, and premium (not robotic)

STRUCTURE:
1. Hook (attention-grabbing in first 3 seconds — fatigue, hangover, low energy)
2. Problem (why water/rest isn't enough)
3. Solution (Mobile IV therapy delivers nutrients directly into bloodstream at home)
4. CTA (clear instruction to click link in bio and book)

GOAL:
* Make the listener feel the problem
* Position the service as fast, premium, and convenient
* Drive immediate action

OUTPUT:
* Only the final voiceover script
* No extra explanations
"""


# =============================================================================
# SECTION 2 — BOT START / WELCOME
# =============================================================================

@bot.message_handler(commands=["start"])
def send_welcome(message):
    """
    Handle the /start command.

    Sends a welcome message to the user explaining how to use the bot
    and which commands are available.
    """
    bot.reply_to(
        message,
        "Welcome to OpenClaw Hub! 🦾\nUse `/script [Topic]` to generate a video script.",
        parse_mode="Markdown",
    )


# =============================================================================
# SECTION 3 — SCRIPT GENERATION
# =============================================================================

@bot.message_handler(commands=["script"])
def generate_script(message):
    """
    Handle the /script command to generate an AI-written voiceover script.

    Extracts the topic from the user's message, sends it to the OpenAI API
    using the IV Clinic system prompt, and saves the resulting script as a
    .txt file in the output/ directory. The script is also sent back to the
    user in Telegram.

    Usage:
        /script <topic>

    Example:
        /script Hangover cure
    """
    try:
        topic = message.text.split(" ", 1)[1]
    except IndexError:
        bot.reply_to(
            message,
            "❌ Please provide a topic. Example: `/script Hangover cure`",
            parse_mode="Markdown",
        )
        return

    bot.reply_to(message, f"⏳ Generating script for: *{topic}*...", parse_mode="Markdown")

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": IV_CLINIC_PROMPT},
                {"role": "user", "content": f"Write a script about: {topic}"},
            ],
        )

        script_content = response.choices[0].message.content

        # Build a timestamped filename and save the script locally
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_topic = topic.replace(" ", "_")[:20]
        filepath = f"output/script_{timestamp}_{safe_topic}.txt"

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(script_content)

        bot.reply_to(
            message,
            f"✅ *Script Generated & Saved!*\nFile: `{filepath}`\n\n{script_content}",
            parse_mode="Markdown",
        )

    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)}")


# =============================================================================
# SECTION 4 — VOICEOVER GENERATION
# =============================================================================

@bot.message_handler(commands=["voiceover"])
def generate_voiceover(message):
    """
    Handle the /voiceover command to convert a saved script into an MP3 audio file.

    Reads a previously generated .txt script from the output/ directory,
    converts its text to speech using Google TTS (gTTS), saves the result
    as an .mp3 file, and sends it back to the user on Telegram.

    Usage:
        /voiceover <filename.txt>

    Example:
        /voiceover script_20260403_120000_Fast_recovery.txt
    """
    try:
        filename = message.text.split(" ", 1)[1]
        filepath = f"output/{filename}"

        if not os.path.exists(filepath):
            bot.reply_to(
                message, "❌ File not found. Please double-check the filename."
            )
            return

        bot.reply_to(message, f"⏳ Reading `{filename}` and generating audio...")

        with open(filepath, "r", encoding="utf-8") as f:
            script_text = f.read()

        # Convert the script text to speech and save as MP3
        tts = gTTS(text=script_text, lang="en", slow=False)
        mp3_path = filepath.replace(".txt", ".mp3")
        tts.save(mp3_path)

        with open(mp3_path, "rb") as audio:
            bot.send_audio(
                message.chat.id,
                audio,
                title="Mobile IV Voiceover",
                caption=f"✅ Voiceover generated successfully!\nPath: `{mp3_path}`",
            )

    except IndexError:
        bot.reply_to(
            message,
            "❌ Please provide a filename. Example: `/voiceover script_20260403_120000_Fast_recovery.txt`",
            parse_mode="Markdown",
        )
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)}")


# =============================================================================
# SECTION 5 — VIDEO ASSEMBLY
# =============================================================================

@bot.message_handler(commands=["create_video"])
def create_video(message):
    """
    Handle the /create_video command to assemble a final video from audio and background footage.

    Loads a generated MP3 voiceover from the output/ directory and combines it
    with the background video at assets/background.mp4. If the background video
    is shorter than the audio it will be looped; if longer, it will be trimmed.
    The final rendered MP4 is sent back to the user on Telegram.

    Usage:
        /create_video <audio_filename.mp3>

    Example:
        /create_video script_20260403_120000_Fast_recovery.mp3
    """
    try:
        audio_filename = message.text.split(" ", 1)[1]
        audio_path = f"output/{audio_filename}"
        bg_video_path = "assets/background.mp4"

        if not os.path.exists(audio_path):
            bot.reply_to(
                message,
                f"❌ Audio file not found at `{audio_path}`. Please check the filename.",
                parse_mode="Markdown",
            )
            return

        if not os.path.exists(bg_video_path):
            bot.reply_to(
                message,
                "❌ Background video not found in `assets/background.mp4`. Please add one first.",
            )
            return

        bot.reply_to(
            message, "⏳ Assembling video and rendering (this may take a minute)..."
        )

        audio_clip = AudioFileClip(audio_path)
        video_clip = VideoFileClip(bg_video_path)

        # Loop the background if it's shorter than audio, otherwise trim it
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

        # Release memory after rendering
        final_clip.close()
        audio_clip.close()
        video_clip.close()

        with open(output_video_path, "rb") as video:
            bot.send_video(
                message.chat.id,
                video,
                caption=f"✅ Video assembled successfully!\nPath: `{output_video_path}`",
            )

    except IndexError:
        bot.reply_to(
            message,
            "❌ Please provide an audio filename. Example: `/create_video script_20260403_120000.mp3`",
            parse_mode="Markdown",
        )
    except Exception as e:
        bot.reply_to(message, f"❌ Error during rendering: {str(e)}")


# =============================================================================
# SECTION 6 — TEXT / CAPTION OVERLAY
# =============================================================================

@bot.message_handler(commands=["add_text"])
def add_text_overlays(message):
    """
    Handle the /add_text command to burn subtitle captions onto a video.

    Reads a script .txt file and splits it into sentences. Each sentence is
    rendered as a styled white-text caption and composited onto the corresponding
    segment of the provided video.

    Timing is proportional to character length — longer sentences stay on
    screen longer, closely matching how long the TTS voice spends on each
    sentence. This keeps captions in sync with the voiceover without needing
    audio waveform analysis.

    Requirements:
        ImageMagick must be installed and its path configured via the
        os.environ and change_settings calls at the top of this file.

    Usage:
        /add_text <video_filename.mp4> <script_filename.txt>

    Example:
        /add_text script_20260403_120000.mp4 script_20260403_120000.txt
    """
    try:
        args = message.text.split(" ", 2)
        video_filename = args[1]
        script_filename = args[2]

        video_path = f"output/{video_filename}"
        script_path = f"output/{script_filename}"

        if not os.path.exists(video_path) or not os.path.exists(script_path):
            bot.reply_to(
                message,
                "❌ One of the files was not found. Please verify both filenames.",
            )
            return

        bot.reply_to(message, "⏳ Processing video and burning in text captions...")

        video_clip = VideoFileClip(video_path)

        with open(script_path, "r", encoding="utf-8") as f:
            script_text = f.read()

        # Split into sentences, filter out any blank entries
        sentences = [s.strip() for s in script_text.split(".") if s.strip()]
        total_duration = video_clip.duration

        # ── Proportional timing by character length ───────────────────────────
        # Longer sentence = more spoken time = more screen time.
        # Each sentence's share of the total video duration is calculated as:
        #   (its character count / total characters) * total video duration
        char_counts = [len(s) for s in sentences]
        total_chars = sum(char_counts)
        durations = [(c / total_chars) * total_duration for c in char_counts]

        txt_clips = []
        start_time = 0

        for sentence, duration in zip(sentences, durations):
            txt_clip = TextClip(
                sentence,
                fontsize=40,
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
            start_time += duration  # advance by this sentence's proportional share

        # Composite all text clips on top of the video
        final_video = CompositeVideoClip([video_clip] + txt_clips)
        output_path = video_path.replace(".mp4", "_subtitled.mp4")

        final_video.write_videofile(
            output_path,
            fps=24,
            codec="libx264",
            audio_codec="aac",
            verbose=False,
            logger=None,
        )

        # Release memory after rendering
        final_video.close()
        video_clip.close()

        with open(output_path, "rb") as video:
            bot.send_video(
                message.chat.id,
                video,
                caption=f"✅ Captions added successfully!\nPath: `{output_path}`",
            )

    except IndexError:
        bot.reply_to(
            message,
            "❌ Please provide both filenames. Example: `/add_text video.mp4 script.txt`",
            parse_mode="Markdown",
        )
    except Exception as e:
        bot.reply_to(
            message,
            f"❌ Error during captioning: {str(e)}\nMake sure ImageMagick is correctly installed.",
        )


# =============================================================================
# ENTRY POINT
# =============================================================================

print("OpenClaw command layer is active...")
bot.polling()