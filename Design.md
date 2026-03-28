# Memoire — Design Document

> *Your life, recut as a movie trailer.*

Memoire is an AI-powered memory preservation system that transforms personal
journal entries, voice recordings, and photographs into cinematic videos, comic
panels, and original soundtracks — then archives everything to Google Calendar
and Drive so memories resurface exactly when they matter.

---

## Architecture Overview

```
┌──────────────┐     ┌─────────────────┐     ┌────────────────────┐
│  Streamlit    │────▶│  memory_capture  │────▶│  Gemini 2.5 Flash  │
│  app.py       │     │  .py             │     │  (text/audio/image)│
│  (4 pages)    │     └─────────────────┘     └────────────────────┘
│               │
│               │     ┌─────────────────┐     ┌────────────────────┐
│               │────▶│  video_generator │────▶│  Veo 3.1           │
│               │     │  .py             │     │  Lyria 3 Clip      │
│               │     │                  │     │  Nano Banana Pro   │
│               │     └─────────────────┘     └────────────────────┘
│               │
│               │     ┌─────────────────┐     ┌────────────────────┐
│               │────▶│  calendar_service│────▶│  Google Calendar   │
│               │     │  .py             │     │  Google Drive      │
│               │     └─────────────────┘     └────────────────────┘
│               │
│               │     ┌─────────────────┐
│               │────▶│  database.py     │──▶ SQLite (WAL mode)
│               │     └─────────────────┘
│               │
│               │     ┌─────────────────┐
│               │────▶│  config.py       │  Centralized settings
│               │     │  logger.py       │  Structured logging
│               │     └─────────────────┘
└──────────────┘
```

---

## Features

### 1. Memory Capture (`memory_capture.py`)

Extracts structured memories from three input modalities using Gemini 2.5 Flash.

| Input Mode | Use Case |
|---|---|
| **Text** | Free-form journal writing — Gemini extracts date, people, emotions, filmable scene prompts |
| **Voice** | Audio recording up to 90 seconds — Gemini Live transcribes and structures the memory |
| **Camera** | Photograph of a physical artifact (ticket, receipt, souvenir) — Gemini identifies the object and imagines the associated memory |

**Outputs:** A structured JSON with `title`, `date`, `summary`, `people`, `location`, `emotion`, `key_moments`, `scene_prompts` (with camera/lighting/caption), and `music_prompt`.

**Scene Enhancement:** After extraction, `enhance_scene_prompts()` refines the raw prompts with style-specific cinematography keywords for Veo.

### 2. Cinematic Video Generation (`video_generator.py`)

Generates short-form cinematic videos using Google Veo 3.1 with multi-scene extension.

- **Initial Scene:** 8-second clip generated from the first scene prompt with optional character reference images for consistency.
- **Video Extension:** Each subsequent scene extends the video by ~7 seconds using Veo's extension API. A 3-scene video is ~22 seconds; 6 scenes ~43 seconds.
- **Character Consistency:** Upload 2-3 reference selfies in Settings; Veo uses them as asset-type reference images across all scenes.
- **Fast vs. Quality:** `veo-3.1-fast-generate-preview` for initial scenes (speed), `veo-3.1-generate-preview` for extensions (quality).

### 3. Comic Panel Generation (`video_generator.py`)

Generates styled comic/manga panels using Nano Banana Pro.

| Style | Description |
|---|---|
| Manga | B&W ink lines, screentone, speed lines |
| Comic | Full color American style, halftone dots |
| Webtoon | Korean style, soft cel-shading, pastels |
| Graphic Novel | Muted watercolors, cinematic panels |
| Pop Art | Roy Lichtenstein inspired, Ben-Day dots |

- Panels include English-only narrative captions positioned alternately at top/bottom.
- Up to 6 panels generated in parallel (3 workers).

### 4. Music Generation (`video_generator.py`)

Creates original soundtracks using Google Lyria 3 Clip.

- Input: Natural language description of mood, tempo, instruments, genre (auto-generated from the memory's `music_prompt`).
- Output: 30-second MP3 clip matching the memory's emotional tone.

### 5. Cover Art (`video_generator.py`)

Generates cinematic movie-poster-style thumbnails using Nano Banana Pro.

### 6. Google Calendar Integration (`calendar_service.py`)

- **OAuth 2.0** flow for Calendar + Drive scopes.
- **Event Creation:** All-day events with emotion, people, location, key moments, and Drive file links embedded in the description.
- **On This Day:** Surface memories from the same month/day in previous years.
- **Upcoming Events:** Query Calendar for future memory events.

### 7. Google Drive Integration (`calendar_service.py`)

- **Auto-upload:** Video, music, cover art, and comic panels to a `Memoire/` folder with per-memory subfolders.
- **Public sharing:** Each uploaded file gets a public viewer link.
- **Calendar linking:** Drive URLs are embedded in Calendar event descriptions.

### 8. Database (`database.py`)

SQLite with WAL mode for concurrent reads.

| Table | Purpose |
|---|---|
| `memories` | Full memory records with paths to generated media |
| `character_refs` | Reference selfies for Veo character consistency |
| `settings` | Key-value store for user preferences |

### 9. UI (`app.py`)

Streamlit application with 4 pages and a warm scrapbook aesthetic.

| Page | Purpose |
|---|---|
| **Capture** | Write / Speak / Camera input → extract → generate |
| **Gallery** | Browse all memories with video, panels, music players |
| **Calendar** | On This Day, date search, Google Calendar + Drive sync status |
| **Settings** | Character refs, default style, API status, models table |

---

## Configuration (`config.py`)

All tunable values are centralized:

- **Model names:** `GEMINI_MODEL`, `VIDEO_MODEL`, `VIDEO_MODEL_FAST`, `MUSIC_MODEL`, `IMAGE_MODEL`
- **Generation defaults:** Temperature, aspect ratio, resolution, poll interval, max panels
- **Style definitions:** `VISUAL_STYLES`, `STYLE_CINEMATOGRAPHY`, `STYLE_IMAGE_PROMPTS`, `COMIC_STYLES`
- **OAuth:** Scopes, credentials path, token path, Drive folder name, timezone
- **Feature flags:** `DRY_RUN` mode (env var `MEMOIRE_DRY_RUN=true`)

---

## Logging (`logger.py`)

Structured logging to console + file (`memoire.log`):

- All function calls logged at INFO with parameters.
- All GenAI API calls logged with model, prompt (truncated), config, and output.
- Inline binary data is never logged.
- Log level and file path configurable via `MEMOIRE_LOG_LEVEL` and `MEMOIRE_LOG_FILE` env vars.

---

## Dry-Run / Test Mode

Set `MEMOIRE_DRY_RUN=true` in `.env` or as an environment variable.

- **memory_capture:** Returns a realistic dummy memory dict without calling Gemini.
- **video_generator:** Returns dummy file paths (`dry_run_video.mp4`, etc.) without calling Veo/Lyria/Nano Banana.
- **calendar_service / database:** Operate normally (they don't call GenAI).

This allows full UI testing, pipeline validation, and demo rehearsal without consuming API quota.

---

## File Structure

```
Memoire/
├── app.py                 # Streamlit UI (4 pages)
├── config.py              # Centralized configuration
├── logger.py              # Logging setup
├── memory_capture.py      # Gemini-powered memory extraction
├── video_generator.py     # Veo + Lyria + Nano Banana generation
├── calendar_service.py    # Google Calendar + Drive integration
├── database.py            # SQLite persistence
├── story_generator.py     # Legacy story generator
├── requirements.txt       # Python dependencies
├── Design.md              # This document
├── .env.example           # Environment variable template
├── .gitignore             # Git exclusions
└── .streamlit/
    └── config.toml        # Streamlit theme configuration
```

---

## Google AI Models Used

| Model | SDK Name | Purpose |
|---|---|---|
| Gemini 2.5 Flash | `gemini-2.5-flash` | Memory extraction, scene refinement, function calling |
| Veo 3.1 | `veo-3.1-generate-preview` / `veo-3.1-fast-generate-preview` | Video generation + extension |
| Lyria 3 Clip | `lyria-3-clip-preview` | Music/soundtrack generation |
| Nano Banana Pro | `nano-banana-pro-preview` | Image generation (covers, comics, style references) |
