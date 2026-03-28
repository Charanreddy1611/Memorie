"""
Memoire — Centralized Configuration
====================================
All configurable items for the Memoire application live here: model names,
API settings, style guides, comic style descriptors, emotion mappings,
OAuth scopes, database paths, and feature flags.

Changing a model version, adding a new visual style, or toggling dry-run
mode should require editing only this file.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ─── Feature Flags ────────────────────────────────────────────
DRY_RUN = os.getenv("MEMOIRE_DRY_RUN", "false").lower() in ("1", "true", "yes")

# ─── Google Gemini API ────────────────────────────────────────
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")

# ─── AI Model Names ──────────────────────────────────────────
GEMINI_MODEL = "gemini-2.5-flash"
VIDEO_MODEL = "veo-3.1-generate-preview"
VIDEO_MODEL_FAST = "veo-3.1-fast-generate-preview"
MUSIC_MODEL = "lyria-3-clip-preview"
IMAGE_MODEL = "nano-banana-pro-preview"

# ─── Generation Defaults ─────────────────────────────────────
DEFAULT_ASPECT_RATIO = "16:9"
DEFAULT_VIDEO_RESOLUTION = "720p"
DEFAULT_TEMPERATURE = 0.7
CREATIVE_TEMPERATURE = 0.8
MAX_REFERENCE_IMAGES = 3
MAX_COMIC_PANELS = 6
VIDEO_POLL_INTERVAL_SEC = 10

# ─── Visual Styles ───────────────────────────────────────────
VISUAL_STYLES = {
    "anime": "Anime",
    "documentary": "Documentary",
    "movie_trailer": "Movie Trailer",
    "studio_ghibli": "Studio Ghibli",
    "cyberpunk": "Cyberpunk",
    "vlog": "Vlog",
}

STYLE_CINEMATOGRAPHY = {
    "anime": "Studio Ghibli aesthetic, cel-shaded, vibrant colors, expressive faces, sakura petals, soft wind effects",
    "documentary": "35mm handheld, natural lighting, shallow depth of field, vérité style, muted color grading",
    "movie_trailer": "Epic cinematic wide shots, dramatic lighting, anamorphic lens flare, slow motion key moments",
    "studio_ghibli": "Watercolor backgrounds, magical realism, detailed nature, warm golden light, whimsical atmosphere",
    "cyberpunk": "Neon reflections, rain-slicked streets, purple-blue palette, holographic overlays, dystopian beauty",
    "vlog": "Eye-level POV, natural light, casual framing, warm color grading, jump cuts between moments",
}

STYLE_IMAGE_PROMPTS = {
    "anime": "Studio Ghibli anime style, cel-shaded, vibrant colors, soft lighting",
    "documentary": "Photorealistic, natural lighting, 35mm film grain, warm tones",
    "movie_trailer": "Cinematic, dramatic lighting, anamorphic lens, rich contrast",
    "studio_ghibli": "Miyazaki watercolor style, magical nature, warm golden glow",
    "cyberpunk": "Neon-lit cyberpunk, rain reflections, purple-blue holographic",
    "vlog": "Natural daylight, casual framing, warm and inviting, slightly overexposed",
}

# ─── Comic Styles ────────────────────────────────────────────
COMIC_STYLES = {
    "manga": "Black and white manga style, dramatic ink lines, screentone shading, expressive eyes, speed lines, Japanese manga aesthetic",
    "comic": "Full color American comic book style, bold outlines, dynamic poses, vibrant colors, halftone dots, speech bubble ready",
    "webtoon": "Korean webtoon style, soft cel-shading, pastel colors, clean lines, vertical scroll layout panel, emotional expressions",
    "graphic_novel": "Graphic novel style, muted watercolor palette, cinematic panels, detailed backgrounds, atmospheric lighting",
    "pop_art": "Pop art comic style, bright primary colors, Ben-Day dots, bold black outlines, Roy Lichtenstein inspired",
}

# ─── Emotions ────────────────────────────────────────────────
EMOTIONS = {
    "joy": "😊",
    "sadness": "😢",
    "excitement": "🤩",
    "calm": "😌",
    "nostalgia": "🥹",
    "love": "❤️",
    "gratitude": "🙏",
    "wonder": "✨",
}

# ─── Google OAuth / Calendar / Drive ─────────────────────────
OAUTH_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/drive.file",
]
CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")
TOKEN_PATH = "token.json"
DRIVE_FOLDER_NAME = "Memoire"
CALENDAR_TIMEZONE = "America/Los_Angeles"
CALENDAR_EVENT_PREFIX = "📹 Memory:"

# ─── Database ────────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(__file__), "memory_director.db")
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")

# ─── Logging ─────────────────────────────────────────────────
LOG_LEVEL = os.getenv("MEMOIRE_LOG_LEVEL", "INFO").upper()
LOG_FILE = os.getenv("MEMOIRE_LOG_FILE", "memoire.log")
