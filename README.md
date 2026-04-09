# 🚀 OpenClaw AI Video Automation Bot

An end-to-end AI-powered Telegram bot that generates high-converting short-form videos — from script → voiceover → video → captions → cloud upload. Now with **multi-brand support**.

---

## 📌 Features

- ✍️ AI Script Generation (OpenAI GPT-4o)
- 🎯 Multi-Brand System (switch brands via Telegram)
- 🔊 Voiceover Creation (gTTS)
- 📝 Whisper-Synced Auto Captions
- 🎬 Video Assembly (MoviePy + FFmpeg)
- ☁️ Cloud Upload via Webhook (n8n / Google Drive)
- 🤖 Full Pipeline Command in Telegram
- 🖥️ Background Service (Windows / PM2 or Task Scheduler)

---

## ⚙️ Tech Stack

- Python 3.11+
- OpenAI API (GPT-4o + Whisper)
- Telegram Bot API (pyTelegramBotAPI)
- gTTS (Google Text-to-Speech)
- MoviePy & FFmpeg
- ImageMagick
- Requests (for webhook upload)

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
│   │   ├── scripts (.txt)
│   │   ├── audio (.mp3)
│   │   └── videos (.mp4)
│   └── <other_brand>/
├── myvenv/
├── .env
├── brands.json
├── bot.py
└── README.md
```

---

## 🔑 Environment Variables

Create a `.env` file in the root folder:

```
TELEGRAM_TOKEN=your_telegram_bot_token
OPENAI_API_KEY=your_openai_api_key
WEBHOOK_URL=http://localhost:5678/webhook/upload-video
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

---

## 🛠️ Installation

### 1. Clone Repo
```bash
git clone https://github.com/sem-naq/Mobile-IV-Clinic.git
cd openclaw-bot
```

### 2. Create Virtual Environment
```bash
python -m venv myvenv
myvenv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

---

## ⚠️ Required Setup

### Install FFmpeg
https://ffmpeg.org/download.html

### Install ImageMagick
https://imagemagick.org/script/download.php

Update path in `bot.py` if needed:
```python
IMAGEMAGICK_PATH = r"C:\Program Files\ImageMagick-7.1.2-Q16-HDRI\magick.exe"
```

---

## ▶️ Telegram Commands

### List All Brands
```
/brands
```

### Switch Active Brand
```
/set_brand iv_clinic
```

### Generate Full Video (All-in-One)
```
/generate_video Hangover recovery
```

> This automatically:
> 1. Generates the script (GPT-4o, brand-specific tone + CTA)
> 2. Converts it to voiceover (gTTS)
> 3. Assembles the background video
> 4. Burns Whisper-synced captions
> 5. Sends the final video to Telegram
> 6. Uploads to cloud via webhook (if configured)

---

## ☁️ n8n Integration

The bot sends the final video to your n8n workflow via webhook:

```
http://localhost:5678/webhook/upload-video
```

Set this as `WEBHOOK_URL` in your `.env` file. Make sure the n8n workflow is active and the Google Drive node is configured.

---

## 🖥️ Windows Background Service

**Option 1: PM2**

```powershell
npm install -g pm2
pm2 start bot.py --name "openclaw-bot" --interpreter "D:\openclaw_bot\myvenv\Scripts\python.exe" --cwd "D:\openclaw_bot"
pm2 save
```

**Option 2: Task Scheduler**

Create a batch file `start_openclaw.bat`:

```batch
@echo off
D:\openclaw_bot\myvenv\Scripts\activate.bat
python D:\openclaw_bot\bot.py
```

Schedule it to run **at logon** in Windows Task Scheduler.

---

## 📌 Example Usage

```
/set_brand iv_clinic
/generate_video Hangover recovery
```

- Bot confirms brand and starts processing
- Final video is sent directly in Telegram chat
- Also uploaded to Google Drive via n8n (if configured)
- Output files saved in `output/iv_clinic/`

---

## ⚡ Notes

- Each brand needs its own `background.mp4` in `assets/<brand>/`
- Output files are auto-cleaned (keeps latest `MAX_OUTPUT_FILES` per brand)
- Rendering time depends on script length and machine speed
- ImageMagick and FFmpeg must be correctly installed

---

## 🧠 Future Improvements

- ElevenLabs / OpenAI Voice for better TTS
- Multiple background videos per brand
- Direct social media upload (TikTok, Instagram)
- Scheduled auto-posting

---

## 🤝 Contributing

Pull requests are welcome.

---

## 📜 License

MIT License

---

## 👨‍💻 Author

Jameel Ahmad
OpenClaw AI Automation