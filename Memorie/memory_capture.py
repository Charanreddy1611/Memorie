"""
Memory capture — Gemini-powered extraction and scene refinement
================================================================

This module is the text/audio/image front-end for turning raw user input into
structured "memories" that the rest of Memoire can render as video, comics, and
gallery entries. It talks to Google's Gemini model to:

  • Parse free-form journal text into a JSON memory (title, summary, people,
    emotion, key moments, Veo-oriented scene prompts, music direction).
  • Transcribe and interpret voice notes the same way, using multimodal input.
  • "Excavate" a plausible narrative from a photo of a memento (ticket,
    receipt, souvenir) when the user triggers capture from the camera.
  • Optionally refine scene prompts for a chosen visual style so downstream
    video generation gets consistent cinematography and character anchors.

Typical use cases: daily journaling with one-tap structure; hands-free memory
logging while walking; digitizing a box of keepsakes; and preparing the same
memory for different aesthetic pipelines (trailer vs. vlog vs. Ghibli-like)
without hand-editing every shot description.

When MEMOIRE_DRY_RUN is enabled in the environment (see config.DRY_RUN), all
Gemini calls are skipped and deterministic placeholder data is returned so UI
and storage flows can be tested without API usage or credentials.
"""

import json
import re
from datetime import date
from typing import Any

from google import genai
from google.genai import types

from config import (
    CREATIVE_TEMPERATURE,
    DEFAULT_TEMPERATURE,
    DRY_RUN,
    GEMINI_MODEL,
    GOOGLE_API_KEY,
    STYLE_CINEMATOGRAPHY,
)
from logger import get_logger, log_genai_call

log = get_logger(__name__)

_client = None


def get_client():
    """
    Return a singleton google.genai Client configured with GOOGLE_API_KEY.

    Lazily constructs the client on first use. Raises if the API key is missing.
    """
    log.info("get_client called")
    global _client
    if _client is None:
        api_key = GOOGLE_API_KEY
        if not api_key:
            raise ValueError("Set GOOGLE_API_KEY in your .env file")
        _client = genai.Client(api_key=api_key)
    return _client


def _dummy_memory_dict() -> dict:
    """
    Return a static memory dict used when DRY_RUN skips the Gemini API.

    Matches the EXTRACTION_PROMPT schema so downstream video, comic, and DB
    paths receive the same keys they expect from a real extraction response.
    """
    log.info("_dummy_memory_dict called")
    today = date.today().isoformat()
    return {
        "date": today,
        "title": "Dry run memory",
        "summary": "Placeholder summary for dry-run mode.",
        "people": [],
        "location": None,
        "emotion": "calm",
        "key_moments": [
            "A quiet moment at the window.",
            "Footsteps on the path.",
            "Sunset over the horizon.",
        ],
        "scene_prompts": [
            {
                "description": "Placeholder scene one for dry run.",
                "camera": "static",
                "lighting": "soft",
                "caption": "I remember the light falling just so.",
                "duration": 8,
            },
            {
                "description": "Placeholder scene two for dry run.",
                "camera": "slow-zoom",
                "lighting": "golden-hour",
                "caption": "The air felt still and full of possibility.",
                "duration": 8,
            },
        ],
        "music_prompt": "Soft piano, ambient pads, slow tempo, dry-run placeholder",
    }


def _sanitize_json_text(text: str) -> str:
    """Strip fences, trailing commas, and control chars that break json.loads."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
        text = text.strip()
    text = re.sub(r",\s*([}\]])", r"\1", text)
    text = re.sub(r"[\x00-\x09\x0b\x0c\x0e-\x1f]", " ", text)
    return text


def _try_close_truncated(text: str) -> str:
    """Attempt to close a truncated JSON object so it can still be parsed."""
    opens = text.count("{") - text.count("}")
    open_arr = text.count("[") - text.count("]")
    last_quote = text.rfind('"')
    quote_count = text.count('"')
    if quote_count % 2 != 0:
        text = text[:last_quote + 1] if last_quote > 0 else text + '"'
    text = text.rstrip(", \t\n")
    text += "]" * max(open_arr, 0)
    text += "}" * max(opens, 0)
    return text


def _parse_json_safe(text: str) -> Any:
    """
    Parse JSON from Gemini output, handling markdown fences, trailing commas,
    control characters, and truncated responses.

    Accepts either a JSON object or array (arrays are used for refined scene
    lists). Raises ValueError if no valid JSON can be recovered.
    """
    log.info("_parse_json_safe called text_len=%s", len(text))
    text = _sanitize_json_text(text)

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting the first JSON object from the text
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        candidate = _sanitize_json_text(match.group(0))
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # Handle truncated output: find the outermost { and try to close it
    brace_start = text.find("{")
    if brace_start >= 0:
        candidate = _try_close_truncated(text[brace_start:])
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
    log.info(
        "extract_memory_from_text called user_text_len=%s",
        len(user_text),
    )
    prompt = f"""{EXTRACTION_PROMPT}

Today's date: {date.today().isoformat()}

User's memory:
{user_text}

Return ONLY the JSON object, no markdown fences, no explanation."""

    gen_config = types.GenerateContentConfig(
        temperature=DEFAULT_TEMPERATURE,
        response_mime_type="application/json",
    )
    config_log = {
        "temperature": DEFAULT_TEMPERATURE,
        "response_mime_type": "application/json",
    }

    if DRY_RUN:
        dummy = json.dumps(_dummy_memory_dict())
        log_genai_call(
            log,
            model=GEMINI_MODEL,
            prompt=prompt,
            config=config_log,
            output=f"[DRY_RUN] {dummy}",
        )
        return _dummy_memory_dict()

    response = get_client().models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=gen_config,
    )
    log_genai_call(
        log,
        model=GEMINI_MODEL,
        prompt=prompt,
        config=config_log,
        output=response.text,
    )

    return _parse_json_safe(response.text)


def extract_memory_from_audio(audio_bytes: bytes, mime_type: str = "audio/wav") -> dict:
    """Process audio input and extract structured memory."""
    log.info(
        "extract_memory_from_audio called audio_bytes_len=%s mime_type=%s",
        len(audio_bytes),
        mime_type,
    )
    prompt = f"""{EXTRACTION_PROMPT}

Today's date: {date.today().isoformat()}

The user recorded an audio message about a memory. Listen to it and extract the memory.

Return ONLY the JSON object, no markdown fences, no explanation."""

    gen_config = types.GenerateContentConfig(
        temperature=DEFAULT_TEMPERATURE,
        response_mime_type="application/json",
    )
    config_log = {
        "temperature": DEFAULT_TEMPERATURE,
        "response_mime_type": "application/json",
    }
    contents = [
        types.Content(
            parts=[
                types.Part.from_text(text=prompt),
                types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
            ]
        )
    ]

    if DRY_RUN:
        dummy = json.dumps(_dummy_memory_dict())
        log_genai_call(
            log,
            model=GEMINI_MODEL,
            prompt=prompt,
            config={**config_log, "contents": "text+audio_bytes"},
            output=f"[DRY_RUN] {dummy}",
        )
        return _dummy_memory_dict()

    response = get_client().models.generate_content(
        model=GEMINI_MODEL,
        contents=contents,
        config=gen_config,
    )
    log_genai_call(
        log,
        model=GEMINI_MODEL,
        prompt=prompt,
        config={**config_log, "contents": "text+audio_bytes"},
        output=response.text,
    )

    return _parse_json_safe(response.text)


def trigger_memory_from_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    """Analyze a photo of a physical object and extract associated memory context."""
    log.info(
        "trigger_memory_from_image called image_bytes_len=%s mime_type=%s",
        len(image_bytes),
        mime_type,
    )
    prompt = f"""You are a memory archaeologist. The user has shown you a physical object
(ticket stub, receipt, photo, souvenir, etc). Identify what it is, then imagine
and create a rich memory that could be associated with it.

{EXTRACTION_PROMPT}

Today's date: {date.today().isoformat()}

Analyze this image and create a memory based on what you see.

Return ONLY the JSON object, no markdown fences, no explanation."""

    gen_config = types.GenerateContentConfig(
        temperature=CREATIVE_TEMPERATURE,
        response_mime_type="application/json",
    )
    config_log = {
        "temperature": CREATIVE_TEMPERATURE,
        "response_mime_type": "application/json",
    }
    contents = [
        types.Content(
            parts=[
                types.Part.from_text(text=prompt),
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            ]
        )
    ]

    if DRY_RUN:
        dummy = json.dumps(_dummy_memory_dict())
        log_genai_call(
            log,
            model=GEMINI_MODEL,
            prompt=prompt,
            config={**config_log, "contents": "text+image_bytes"},
            output=f"[DRY_RUN] {dummy}",
        )
        return _dummy_memory_dict()

    response = get_client().models.generate_content(
        model=GEMINI_MODEL,
        contents=contents,
        config=gen_config,
    )
    log_genai_call(
        log,
        model=GEMINI_MODEL,
        prompt=prompt,
        config={**config_log, "contents": "text+image_bytes"},
        output=response.text,
    )

    return _parse_json_safe(response.text)


def enhance_scene_prompts(memory: dict, style: str, character_description: str = "") -> list[dict]:
    """Refine scene prompts with style-specific cinematography and character consistency."""
    log.info(
        "enhance_scene_prompts called style=%s character_description_len=%s memory_keys=%s",
        style,
        len(character_description),
        list(memory.keys()) if isinstance(memory, dict) else None,
    )
    style_desc = STYLE_CINEMATOGRAPHY.get(style, STYLE_CINEMATOGRAPHY["movie_trailer"])

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

    gen_config = types.GenerateContentConfig(
        temperature=DEFAULT_TEMPERATURE,
        response_mime_type="application/json",
    )
    config_log = {
        "temperature": DEFAULT_TEMPERATURE,
        "response_mime_type": "application/json",
    }

    if DRY_RUN:
        existing = memory.get("scene_prompts") or []
        dummy_list = [
            {**dict(s), "duration": 8}
            if isinstance(s, dict)
            else {
                "description": str(s),
                "camera": "static",
                "lighting": "soft",
                "duration": 8,
            }
            for s in existing
        ]
        if not dummy_list:
            dummy_list = [
                {
                    "description": f"{style} dry-run placeholder scene",
                    "camera": "static",
                    "lighting": "soft",
                    "duration": 8,
                }
            ]
        dummy = json.dumps(dummy_list)
        log_genai_call(
            log,
            model=GEMINI_MODEL,
            prompt=prompt,
            config=config_log,
            output=f"[DRY_RUN] {dummy}",
        )
        return dummy_list

    response = get_client().models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=gen_config,
    )
    log_genai_call(
        log,
        model=GEMINI_MODEL,
        prompt=prompt,
        config=config_log,
        output=response.text,
    )

    return _parse_json_safe(response.text)
