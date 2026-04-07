Perfect! Let’s update your **README.md** to reflect **everything you’ve done today**, including the **full pipeline command** (`/full_pipeline`) and **n8n integration**, plus instructions for Windows persistence. I’ll make it clean, modern, and ready for GitHub.

Here’s the updated version:

---

```markdown
# 🚀 OpenClaw AI Video Automation Bot

An end-to-end AI-powered Telegram bot that generates high-converting short-form videos — from script → voiceover → video → captions → cloud upload.

---

## 📌 Features

- ✍️ AI Script Generation (OpenAI GPT-4)  
- 🔊 Voiceover Creation (gTTS)  
- 🎬 Video Assembly (MoviePy + FFmpeg)  
- 📝 Auto Captions (ImageMagick + MoviePy)  
- ☁️ Cloud Upload to Google Drive (via n8n Webhook)  
- 🤖 Full Pipeline Command in Telegram  
- 🖥️ Background Service (Windows / PM2 or Task Scheduler)

---

## ⚙️ Tech Stack

- Python 3.11+  
- OpenAI API  
- Telegram Bot API (pyTelegramBotAPI)  
- gTTS (Google Text-to-Speech)  
- MoviePy & FFmpeg  
- ImageMagick  
- Requests (for n8n webhook)  

---

## 📂 Project Structure

```

D:\openclaw_bot
├── assets/
│   └── background.mp4
├── output/
│   ├── scripts (.txt)
│   ├── audio (.mp3)
│   └── videos (.mp4)
├── myvenv/
├── .env
├── app.py
├── tools.py
├── README.md

```

---

## 🔑 Environment Variables

Create a `.env` file in the root folder:

```

TELEGRAM_TOKEN=your_telegram_bot_token
OPENAI_API_KEY=your_openai_api_key

````

---

## 🛠️ Installation

### 1. Clone Repo
```bash
git clone https://github.com/your-username/openclaw-bot.git
cd openclaw-bot
````

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

[https://ffmpeg.org/download.html](https://ffmpeg.org/download.html)

### Install ImageMagick

[https://imagemagick.org/script/download.php](https://imagemagick.org/script/download.php)

Update path in `app.py` if needed:

```python
os.environ["IMAGEMAGICK_BINARY"] = "C:\\Program Files\\ImageMagick-7.1.2-Q16-HDRI\\magick.exe"
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

### Full Pipeline (All-in-One Command)

```
/full_pipeline Energy boost
```

> This automatically:
>
> 1. Generates the script
> 2. Converts it to voiceover
> 3. Creates the video
> 4. Adds captions
> 5. Sends the video to Telegram
> 6. Uploads the final video to n8n / Google Drive

---

## 🔄 Workflow

1. Generate Script → `/script <topic>`
2. Convert to Voiceover → `/voiceover <script.txt>`
3. Create Video → `/create_video <audio.mp3>`
4. Add Captions → `/add_text <video.mp4> <script.txt>`
5. Or just use **Full Pipeline** → `/full_pipeline <topic>`

---

## ☁️ n8n Integration

* The bot sends the final video to your n8n workflow using a webhook URL:

```python
http://localhost:5678/webhook/upload-video
```

* Make sure the workflow is active and the Google Drive node is configured.

---

## 🖥️ Windows Background Service

**Option 1: PM2**

```powershell
npm install -g pm2
pm2 start app.py --name "openclaw-bot" --interpreter "D:\openclaw_bot\myvenv\Scripts\python.exe" --cwd "D:\openclaw_bot"
pm2 save
```

**Option 2: Task Scheduler**

* Create a batch file (`start_openclaw.bat`) to run:

```batch
@echo off
D:\openclaw_bot\myvenv\Scripts\activate.bat
python D:\openclaw_bot\app.py
```

* Schedule the batch to run **at logon** in Windows Task Scheduler.

> Either method ensures the bot runs automatically in the background and restarts on boot.

---

## 📌 Example

```
/full_pipeline Energy boost
```

* The bot handles everything automatically.
* Output files are saved in `/output`.
* Final video also uploads to Google Drive via n8n.

---

## ⚡ Notes

* Keep `assets/background.mp4` ready
* Rendering depends on script length and TTS speed
* ImageMagick and FFmpeg must be correctly installed

---

## 🧠 Future Improvements

* Multiple background videos
* Better TTS voices (ElevenLabs / OpenAI Voice)
* Auto scene detection and editing
* Direct social media upload

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

This **README** is now fully updated for:

- `/full_pipeline` command  
- n8n integration  
