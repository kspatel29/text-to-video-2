# Text-to-Video Pipeline

This project implements a pipeline that converts text into an educational video with narration. It uses Google's Gemini for storyboarding and content generation, Manim for creating animations, and Google Text-to-Speech (gTTS) for narration.

## Pipeline Overview

```
┌──────────────┐
│  User text   │
└─────┬────────┘
      │
      │ ① gemini-flash  ➜  storyboard + narration
      ▼
      🟡  Slide loop  (≤ 8 slides, retry ≤ 3)
            │
            │ ② gemini-flash  ➜  slide_i.py  (VoiceoverScene)
            │
            │ manim -pql slide_i.py           ← 720 p · 15 fps · quick-low
            │  ├─ Google TTS → wav
            │  ├─ Whisper timestamps
            │  └─ renders scene_i.mp4+audio
            ▼
ffmpeg -f concat -safe 0 -i list.txt -c copy  final_lesson.mp4   ✅
```

## Installation

1. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Make sure you have ffmpeg installed:
   ```bash
   # On Ubuntu/Debian
   sudo apt-get install ffmpeg
   
   # On macOS with Homebrew
   brew install ffmpeg
   ```

3. Create a `.env.local` file with your Gemini API key:
   ```
   GEMINI_API_KEY=your_api_key_here
   ```

## Usage

Run the pipeline with your input text:

```bash
python main.py "Your educational text content here"
```

The script will:
1. Generate a storyboard using Gemini
2. Create individual slide animations with Manim
3. Add narration using Google Text-to-Speech
4. Combine everything into a final video

## Configuration

- Edit `config.py` to modify voice settings or other Manim parameters
- For different language settings, modify the GTTSSpeechService parameters in `config.py`

## Speed Optimization

This pipeline is optimized for speed with the following settings:
- Quality flag: `-pql` (720p, 15fps) for faster rendering
- Whisper model: `tiny` for faster transcription
- Random seed: `42` for stable randomness across runs
- Retry cap: `3` to prevent infinite loops on bad code
