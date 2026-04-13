# 🚀 OpenClaw AI Video Automation Bot — v2.0

An end-to-end AI-powered Telegram bot that generates high-converting short-form videos —
fully automated from **Script → Voiceover → Video → Captions → Cloud Upload**.
Built with multi-brand support, structured logging, automatic retries, and threaded pipelines.

---

## 📌 What's New in v2.0

| Feature | v1.0 | v2.0 |
|---|---|---|
| TTS Engine | gTTS (Google) | ✅ OpenAI TTS (configurable model + voice) |
| ImageMagick Path | Hardcoded in code | ✅ Loaded from `.env` |
| Logging | `print()` statements | ✅ Structured file + console logging |
| API Failure Handling | None | ✅ Auto-retry with exponential backoff (tenacity) |
| Pipeline Execution | Sequential, blocking | ✅ Threaded — bot stays responsive |
| Error Messages | Generic | ✅ Specific per error type |

---

## 📌 Features

- ✍️ AI Script Generation (OpenAI GPT-4o)
- 🎯 Multi-Brand System (switch brands via Telegram command)
- 🔊 High-Quality Voiceover (OpenAI TTS — `tts-1` or `tts-1-hd`)
- 📝 Whisper-Synced Auto Captions
- 🎬 Video Assembly (MoviePy + FFmpeg)
- ☁️ Cloud Upload via Webhook (n8n / Google Drive)
- 🔁 Auto-Retry on API Failures (up to 3 attempts)
- 📋 Daily Rotating Log Files (`logs/bot_YYYY-MM-DD.log`)
- ⚡ Threaded Pipeline (multiple videos can process concurrently)

---

## ⚙️ Tech Stack

- Python 3.11+
- OpenAI API (GPT-4o + Whisper + TTS)
- Telegram Bot API (pyTelegramBotAPI)
- MoviePy & FFmpeg
- ImageMagick
- Tenacity (retry logic)
- Requests (webhook upload)

---

## 📂 Project Structure

```
D:\openclaw_bot
├── assets/
│   ├── iv_clinic/
│   │   └── background.mp4
│   └── <other_brand>/
│       └── background.mp4
├── output/
│   ├── iv_clinic/
│   │   ├── script_*.txt
│   │   ├── script_*.mp3
│   │   ├── script_*_timestamps.json
│   │   ├── script_*_bg.mp4
│   │   └── script_*_final.mp4
│   └── <other_brand>/
├── logs/
│   └── bot_YYYY-MM-DD.log
├── myvenv/
├── .env
├── brands.json
├── bot.py
├── requirements.txt
└── README.md
```

---

## 🔑 Environment Variables

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

```env
# ── Required ──────────────────────────────────────────────────
TELEGRAM_TOKEN=your_telegram_bot_token_here
OPENAI_API_KEY=your_openai_api_key_here

# ── ImageMagick (required by MoviePy for subtitle rendering) ──
IMAGEMAGICK_PATH=C:\Program Files\ImageMagick-7.1.2-Q16-HDRI\magick.exe

# ── OpenAI TTS Settings ───────────────────────────────────────
# Model : tts-1 (faster/cheaper) | tts-1-hd (studio quality)
# Voice : alloy | echo | fable | onyx | nova | shimmer
TTS_MODEL=tts-1
TTS_VOICE=alloy

# ── Optional ──────────────────────────────────────────────────
WEBHOOK_URL=https://your-webhook-endpoint.com/upload
OUTPUT_DIR=output
MAX_OUTPUT_FILES=20
```

> `WEBHOOK_URL` is optional. If not set, cloud upload is skipped automatically.

---

## 🏷️ Brand Configuration

Create a `brands.json` file in the root folder:

```json
{
  "iv_clinic": {
    "name": "IV Clinic",
    "industry": "Mobile IV Therapy",
    "tone": "confident, empathetic, premium",
    "cta": "Book now at ivclinic.com or DM us today.",
    "bg_video": "assets/iv_clinic/background.mp4"
  },
  "your_brand": {
    "name": "Your Brand Name",
    "industry": "Your Industry",
    "tone": "your tone here",
    "cta": "Your call to action here.",
    "bg_video": "assets/your_brand/background.mp4"
  }
}
```

> Each brand needs its own `background.mp4` inside `assets/<brand_key>/`.

---

## 🛠️ Installation

### 1. Clone the Repository

```bash
git clone https://github.com/sem-naq/Mobile-IV-Clinic.git
cd openclaw-bot
```

### 2. Create Virtual Environment

```bash
python -m venv myvenv
myvenv\Scripts\activate        # Windows
# source myvenv/bin/activate   # macOS / Linux
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Install FFmpeg

Download from https://ffmpeg.org/download.html and add it to your system `PATH`.

Verify installation:
```bash
ffmpeg -version
```

### 5. Install ImageMagick

Download from https://imagemagick.org/script/download.php.

Set the full path to `magick.exe` in your `.env` file:
```env
IMAGEMAGICK_PATH=C:\Program Files\ImageMagick-7.1.2-Q16-HDRI\magick.exe
```

### 6. Configure Environment

```bash
cp .env.example .env
# Edit .env with your tokens and settings
```

---

## 📦 requirements.txt

```
openai
pyTelegramBotAPI
python-dotenv
moviepy
Pillow
requests
tenacity
```

Install all at once:
```bash
pip install openai pyTelegramBotAPI python-dotenv moviepy Pillow requests tenacity
```

---

## 🤖 Pipeline Overview

Every `/generate_video` command runs these sessions in order:

```
[Session 1]  GPT-4o generates voiceover script
      ↓
[Session 2]  OpenAI TTS converts script → MP3
             Whisper extracts word-level timestamps → JSON
      ↓
[Session 3]  Brand background video is cropped, looped, synced to audio
      ↓
[Session 4]  Whisper-synced subtitles are burned onto the video
      ↓
[Session 5]  Final MP4 is sent to Telegram + uploaded to webhook (if set)
```

Each API-heavy session (Script, Audio, Webhook) automatically retries up to **3 times**
with exponential backoff on failure — so transient network issues don't break your video.

---

## ▶️ Telegram Commands Reference

### `/brands` — List All Configured Brands

```
/brands
```

**Response:**
```
Available Brands

  • iv_clinic — IV Clinic ← active
  • your_brand — Your Brand Name
```

---

### `/set_brand` — Switch Active Brand

```
/set_brand <brand_id>
```

**Example:**
```
/set_brand iv_clinic
```

**Response:**
```
✅ Switched to IV Clinic
```

> The active brand controls which GPT tone, CTA, and background video are used.

---

### `/generate_video` — Run the Full Pipeline

```
/generate_video <topic>
```

**Example:**
```
/generate_video hangover recovery
```

**What happens automatically:**
1. Generates a brand-specific GPT-4o script for the topic
2. Converts the script to speech via OpenAI TTS
3. Runs Whisper to get exact word timestamps
4. Builds the background video synced to the audio
5. Burns Whisper-synced captions onto the video
6. Sends the final `.mp4` directly to your Telegram chat
7. Uploads to cloud webhook (if `WEBHOOK_URL` is configured)

> The pipeline runs in a **background thread** — you can send more commands while it processes.

---

## 📋 Logging

All activity is logged to both the console and a daily rotating file:

```
logs/bot_2025-01-15.log
```

Log format:
```
2025-01-15 14:32:01 | INFO     | VideoBot | [script] Generating script | brand=iv_clinic | topic=hangover recovery
2025-01-15 14:32:04 | INFO     | VideoBot | [script] Saved → script_20250115_143204.txt
2025-01-15 14:32:04 | INFO     | VideoBot | [audio] Generating TTS | model=tts-1 | voice=alloy
...
2025-01-15 14:33:12 | INFO     | VideoBot | [pipeline] DONE in 68s → script_20250115_143204_final.mp4
```

To monitor logs in real time:
```bash
# Windows PowerShell
Get-Content logs\bot_2025-01-15.log -Wait

# macOS / Linux
tail -f logs/bot_$(date +%Y-%m-%d).log
```

---

## 🖥️ Running as a Windows Background Service

### Option 1: Windows Task Scheduler (Recommended)

Run once as **Administrator** to register the scheduled task:

```powershell
schtasks /create /tn "OpenclawBot" /tr "D:\openclaw_bot\myvenv\Scripts\python.exe D:\openclaw_bot\bot.py" /sc onlogon /rl highest /delay 0002:00 /f
```

> The 2-minute delay gives your VPN time to connect before the bot starts.

**Daily management commands** (regular PowerShell, no admin needed):

```powershell
# Start the bot manually
schtasks /run /tn "OpenclawBot"

# Stop the bot
schtasks /end /tn "OpenclawBot"

# Restart the bot
schtasks /end /tn "OpenclawBot"
schtasks /run /tn "OpenclawBot"

# Check if the bot process is running
Get-Process python
```

**Emergency / cleanup:**

```powershell
# Force kill all python processes (if bot is stuck)
Stop-Process -Name python -Force

# Remove the scheduled task entirely
schtasks /delete /tn "OpenclawBot" /f
```

---

### Option 2: Run Directly (Development / Testing)

```bash
# Activate virtual environment
myvenv\Scripts\activate

# Start the bot
python bot.py
```

---

### Option 3: Batch File Launcher

Create `start_openclaw.bat` in the project root:

```batch
@echo off
D:\openclaw_bot\myvenv\Scripts\activate.bat
python D:\openclaw_bot\bot.py
pause
```

Double-click to launch, or schedule via Task Scheduler.

> **Note:** Avoid PM2 on Windows — it can cause instability. Task Scheduler is the most reliable option.

---

## ☁️ n8n Webhook Integration

The bot POSTs the final video to your n8n workflow:

```
POST https://your-n8n-instance.com/webhook/upload-video

Body fields:
  brand  → active brand key (e.g. "iv_clinic")
  file   → the final .mp4 video (multipart/form-data)
```

Set `WEBHOOK_URL` in your `.env` to enable this. Leave it blank to skip upload silently.

---

## 📌 Example Workflow

```
/set_brand iv_clinic
/generate_video hangover recovery
```

**Bot responds:**
```
🎬 Processing your video…
Brand: IV Clinic
Topic: hangover recovery

[~60–90 seconds later]

🔥 IV Clinic — hangover recovery   [video attached]
☁️ Uploaded to cloud successfully.
```

---

## ⚡ Notes & Tips

- **Multiple requests:** You can send multiple `/generate_video` commands — each runs in its own thread (up to 4 concurrently).
- **File cleanup:** The bot automatically deletes the oldest `.mp4` files when the output folder exceeds `MAX_OUTPUT_FILES`.
- **TTS voices:** Change `TTS_VOICE` in `.env` to try different voices without touching code. Options: `alloy`, `echo`, `fable`, `onyx`, `nova`, `shimmer`.
- **Video quality:** Switch `TTS_MODEL=tts-1-hd` in `.env` for studio-quality audio (slightly slower).
- **Always connect VPN before starting the bot** if your API calls route through one.

---

## 🧠 Future Improvements

- ElevenLabs voice integration
- Multiple background videos per brand (random selection)
- Direct social media upload (TikTok, Instagram Reels)
- Scheduled auto-posting via cron / Task Scheduler
- Web dashboard for brand and video management

---

## 🤝 Contributing

Pull requests are welcome. Please open an issue first to discuss major changes.

---

## 📜 License

MIT License

---

## 👨‍💻 Author

**Jameel Ahmad**
OpenClaw AI Automation