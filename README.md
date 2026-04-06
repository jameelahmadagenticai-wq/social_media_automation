Here’s your **clean copy-paste README.md** 👇

```markdown
# 🚀 OpenClaw AI Video Automation Bot

An end-to-end AI-powered Telegram bot that generates high-converting short-form videos — from script → voiceover → video → captions.

---

## 📌 Features

- ✍️ AI Script Generation (OpenAI)
- 🔊 Voiceover Creation (gTTS)
- 🎬 Video Assembly (MoviePy)
- 📝 Auto Captions (ImageMagick + MoviePy)
- 🤖 Telegram Bot Control

---

## ⚙️ Tech Stack

- Python
- OpenAI API
- Telegram Bot API (pyTelegramBotAPI)
- gTTS
- MoviePy
- ImageMagick
- FFmpeg

---

## 📂 Project Structure

```

├── assets/
│   └── background.mp4
├── output/
│   ├── scripts (.txt)
│   ├── audio (.mp3)
│   └── videos (.mp4)
├── .env
├── main.py
└── README.md

```

---

## 🔑 Environment Variables

Create a `.env` file:

```

TELEGRAM_TOKEN=your_telegram_bot_token
OPENAI_API_KEY=your_openai_api_key

```

---

## 🛠️ Installation

### 1. Clone Repo
```

git clone [https://github.com/your-username/openclaw-bot.git](https://github.com/your-username/openclaw-bot.git)
cd openclaw-bot

```

### 2. Create Virtual Environment
```

python -m venv venv
venv\Scripts\activate

```

### 3. Install Dependencies
```

pip install -r requirements.txt

```

---

## ⚠️ Required Setup

### Install FFmpeg
https://ffmpeg.org/download.html

### Install ImageMagick
https://imagemagick.org/script/download.php

Update path in code if needed:
```

os.environ["IMAGEMAGICK_BINARY"] = "your_path_here"

```

---

## ▶️ Usage (Telegram Commands)

### Start Bot
```

/start

```

### Generate Script
```

/script Hangover cure

```

### Generate Voiceover
```

/voiceover script_filename.txt

```

### Create Video
```

/create_video audio_filename.mp3

```

### Add Captions
```

/add_text video.mp4 script.txt

```

---

## 🔄 Workflow

1. Generate Script  
2. Convert to Voiceover  
3. Create Video  
4. Add Captions  

---

## 📌 Example

```

/script Energy boost
/voiceover script_20260406_120000_Energy_boost.txt
/create_video script_20260406_120000_Energy_boost.mp3
/add_text script_20260406_120000_Energy_boost.mp4 script_20260406_120000_Energy_boost.txt

```

---

## ⚡ Notes

- Keep `assets/background.mp4` ready
- Output files are saved in `/output`
- Rendering time depends on script length
- ImageMagick must be properly configured

---

## 🧠 Future Improvements

- Multiple background videos
- Better TTS (ElevenLabs / OpenAI Voice)
- Auto scene detection
- Direct social media upload

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
```

---

