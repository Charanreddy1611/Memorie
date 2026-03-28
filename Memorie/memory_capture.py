import os
import re
import json
import base64
from datetime import date
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

_client = None


def get_client():
    global _client
    if _client is None:
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("Set GOOGLE_API_KEY in your .env file")
        _client = genai.Client(api_key=api_key)
    return _client


GEMINI_MODEL = "gemini-2.5-flash"


def _parse_json_safe(text: str) -> dict:
    """Parse JSON from Gemini output, handling common quirks."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()

    # Remove trailing commas before } or ] (most common Gemini JSON issue)
    text = re.sub(r",\s*([}\]])", r"\1", text)

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting the first JSON object from the text
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        candidate = match.group(0)
        candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse JSON from model output: {text[:200]}...")

EXTRACTION_PROMPT = """You are a memory extraction assistant. Analyze the user's input and extract a structured memory.

Return a valid JSON object with these fields:
{
  "date": "YYYY-MM-DD (use today if not mentioned)",
  "title": "A short, evocative title for this memory (max 10 words)",
  "summary": "A vivid 2-3 sentence summary capturing the emotional core",
  "people": ["list of people mentioned"],
  "location": "where it happened (or null)",
  "emotion": "one of: joy, sadness, excitement, calm, nostalgia, love, gratitude, wonder",
  "key_moments": ["3-5 specific visual moments that could be filmed as scenes"],
  "scene_prompts": [
    {
      "description": "Detailed visual description for video generation",
      "camera": "camera movement: dolly/pan/static/handheld/slow-zoom",
      "lighting": "lighting mood: golden-hour/soft/dramatic/neon/warm-indoor",
      "caption": "A short 1-2 sentence narrative caption IN ENGLISH ONLY for this scene, written like a comic book narration box. Poetic, evocative, first-person.",
      "duration": 8
    }
  ],
  "music_prompt": "Description of ideal soundtrack mood, tempo, instruments, genre"
}

Rules:
- key_moments should be concrete, visual, filmable moments (not abstract feelings)
- scene_prompts should have 3-6 entries, each describing an 8-second video scene
- music_prompt should match the emotion and be specific about instruments and mood
- If the input is too vague, still extract what you can and fill gaps creatively
- Always return valid JSON, nothing else
"""


def extract_memory_from_text(user_text: str) -> dict:
    """Extract structured memory from a text journal entry."""
    prompt = f"""{EXTRACTION_PROMPT}

Today's date: {date.today().isoformat()}

User's memory:
{user_text}

Return ONLY the JSON object, no markdown fences, no explanation."""

    response = get_client().models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.7,
            response_mime_type="application/json",
        ),
    )

    return _parse_json_safe(response.text)


def extract_memory_from_audio(audio_bytes: bytes, mime_type: str = "audio/wav") -> dict:
    """Process audio input and extract structured memory."""
    prompt = f"""{EXTRACTION_PROMPT}

Today's date: {date.today().isoformat()}

The user recorded an audio message about a memory. Listen to it and extract the memory.

Return ONLY the JSON object, no markdown fences, no explanation."""

    response = get_client().models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            types.Content(
                parts=[
                    types.Part.from_text(text=prompt),
                    types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
                ]
            )
        ],
        config=types.GenerateContentConfig(
            temperature=0.7,
            response_mime_type="application/json",
        ),
    )

    return _parse_json_safe(response.text)


def trigger_memory_from_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    """Analyze a photo of a physical object and extract associated memory context."""
    prompt = f"""You are a memory archaeologist. The user has shown you a physical object
(ticket stub, receipt, photo, souvenir, etc). Identify what it is, then imagine
and create a rich memory that could be associated with it.

{EXTRACTION_PROMPT}

Today's date: {date.today().isoformat()}

Analyze this image and create a memory based on what you see.

Return ONLY the JSON object, no markdown fences, no explanation."""

    response = get_client().models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            types.Content(
                parts=[
                    types.Part.from_text(text=prompt),
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                ]
            )
        ],
        config=types.GenerateContentConfig(
            temperature=0.8,
            response_mime_type="application/json",
        ),
    )

    return _parse_json_safe(response.text)


def enhance_scene_prompts(memory: dict, style: str, character_description: str = "") -> list[dict]:
    """Refine scene prompts with style-specific cinematography and character consistency."""
    style_guides = {
        "anime": "Studio Ghibli aesthetic, cel-shaded, vibrant colors, expressive faces, sakura petals, soft wind effects",
        "documentary": "35mm handheld, natural lighting, shallow depth of field, vérité style, muted color grading",
        "movie_trailer": "Epic cinematic wide shots, dramatic lighting, anamorphic lens flare, slow motion key moments",
        "studio_ghibli": "Watercolor backgrounds, magical realism, detailed nature, warm golden light, whimsical atmosphere",
        "cyberpunk": "Neon reflections, rain-slicked streets, purple-blue palette, holographic overlays, dystopian beauty",
        "vlog": "Eye-level POV, natural light, casual framing, warm color grading, jump cuts between moments",
    }

    style_desc = style_guides.get(style, style_guides["movie_trailer"])

    char_clause = ""
    if character_description:
        char_clause = f"\nCharacter anchor: Every scene must include this person: {character_description}. Keep their appearance perfectly consistent."

    prompt = f"""Refine these scene prompts for Veo 3.1 video generation.

Memory: {memory['summary']}
Key moments: {json.dumps(memory.get('key_moments', []))}
Style: {style} — {style_desc}
{char_clause}

Current scenes:
{json.dumps(memory.get('scene_prompts', []), indent=2)}

For each scene, return a refined prompt that:
1. Starts with the style keywords
2. Includes specific camera movement and framing
3. Describes lighting precisely
4. Includes dialogue or narration in quotes if appropriate (Veo generates native audio)
5. Keeps character identity anchors consistent across all scenes

Return a JSON array of objects with: description, camera, lighting, duration (always 8)
Return ONLY the JSON array."""

    response = get_client().models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.7,
            response_mime_type="application/json",
        ),
    )

    return _parse_json_safe(response.text)
