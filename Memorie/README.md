# Memoire

**Your life, recut as a movie trailer.**

Memoire is an AI-powered memory preservation system that transforms journal entries, voice recordings, and photographs into cinematic videos, comic panels, and original soundtracks — then archives everything to Google Calendar and Drive so memories resurface exactly when they matter.

Built for **LA Hacks 2026** using the Google Gemini ecosystem.

---

## Features

- **Multi-modal Memory Capture** — Write, speak, or photograph a memory. Gemini 2.5 Flash extracts people, emotions, locations, and filmable scene prompts.
- **Cinematic Video Generation** — Veo 3.1 produces short cinematic clips (8–43 seconds) with multi-scene extension and character consistency via reference photos.
- **Comic Panel Generation** — Nano Banana Pro creates styled panels in Manga, Comic, Webtoon, Graphic Novel, or Pop Art styles with English captions.
- **Original Soundtrack** — Lyria 3 Clip composes a custom 30-second soundtrack matched to the memory's emotional tone.
- **Google Calendar + Drive Sync** — Generated media uploads to a dedicated Drive folder; all-day Calendar events resurface memories with embedded file links.
- **"On This Day" Resurfacing** — Memories from the same date in previous years appear automatically on the Calendar page.

---

## Tech Stack

| Component | Technology |
|---|---|
| Memory Extraction | **Gemini 2.5 Flash** |
| Video Generation | **Veo 3.1** (fast + quality modes) |
| Music Generation | **Lyria 3 Clip** |
| Image Generation | **Nano Banana Pro** |
| Voice Input | **Gemini Live API** |
| Cloud Storage | **Google Drive API** |
| Calendar Sync | **Google Calendar API** |
| Frontend | **Streamlit** (custom scrapbook UI) |
| Database | **SQLite** (WAL mode) |
| Auth | **OAuth 2.0** (Calendar + Drive scopes) |

---

## Getting Started

### Prerequisites

- Python 3.10+
- A Google Cloud project with Calendar and Drive APIs enabled
- A Gemini API key from [Google AI Studio](https://aistudio.google.com/)
- OAuth credentials (`credentials.json`) for Calendar/Drive

### Installation

```bash
git clone https://github.com/Charanreddy1611/Memorie.git
cd Memorie/Memorie
pip install -r requirements.txt
```

### Configuration

Create a `.env` file:

```
GOOGLE_API_KEY=your-gemini-api-key
```

Place your `credentials.json` in the project root for Calendar/Drive OAuth.

### Run

```bash
streamlit run app.py
```

The app opens at `http://localhost:8501`.

---

## Pages

| Page | What it does |
|---|---|
| **Capture** | Write, speak, or photograph a memory. Gemini extracts the story, then generate a cinematic video, comic panels, or both. |
| **Gallery** | Browse all saved memories with embedded video players, comic panel grids, and audio players. Upload to Drive and add to Calendar. |
| **Calendar** | "On This Day" resurfacing, date search, and Google Calendar + Drive sync status. |
| **Settings** | Upload character reference photos for Veo, set a default visual style, and view API connection status. |

---

## Project Structure

```
Memoire/
  app.py                 Streamlit UI (4 pages, scrapbook theme)
  config.py              Centralized configuration
  logger.py              Structured logging
  memory_capture.py      Gemini-powered memory extraction
  video_generator.py     Veo + Lyria + Nano Banana generation
  calendar_service.py    Google Calendar + Drive integration
  database.py            SQLite persistence
  requirements.txt       Python dependencies
  Design.md              Detailed architecture document
```

---

## Deployment

### Streamlit Community Cloud

1. Push to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io) and connect the repo
3. Set main file to `Memoire/app.py`
4. Add secrets:
   ```toml
   GOOGLE_API_KEY = "your-key"
   GOOGLE_TOKEN = '{"token": "...", "refresh_token": "...", ...}'
   ```

---

## Google AI Models

| Model | SDK Name | Purpose |
|---|---|---|
| Gemini 2.5 Flash | `gemini-2.5-flash` | Memory extraction, scene refinement |
| Veo 3.1 | `veo-3.1-generate-preview` | Video generation + extension |
| Lyria 3 Clip | `lyria-3-clip-preview` | Soundtrack composition |
| Nano Banana Pro | `nano-banana-pro-preview` | Cover art, comic panels, style references |
