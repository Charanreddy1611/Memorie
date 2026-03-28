import os
import time
import tempfile
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
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

STORY_MODEL = "gemini-2.5-flash-preview-05-20"
VIDEO_MODEL = "veo-3.1-generate-preview"
MUSIC_MODEL = "lyria-3-clip-preview"
IMAGE_MODEL = "gemini-2.0-flash-preview-image-generation"


def generate_story(story_topic: str, story_length: str = "short", child_name: str = "") -> dict:
    """Use Gemini to write the bedtime story AND craft prompts for Veo/Lyria."""
    main_character = child_name if child_name.strip() else "the main character"
    length_desc = "2-3 minutes" if story_length == "short" else "5-7 minutes"

    prompt = f"""You are a children's bedtime story writer AND a creative director.

TASK 1 — Write a gentle bedtime story for children aged 3-5 about: {story_topic}
Story length: {story_length.upper()} ({length_desc})
{'Make ' + main_character + ' the main character.' if child_name.strip() else ''}

Story rules:
- Calm, bedtime-appropriate, no violence or scary elements
- Simple words, short sentences, 2-3 main characters
- Peaceful settings (bedroom, garden, starry sky)
- Include gentle sound effects and interactive moments
- End with characters feeling sleepy and peaceful

TASK 2 — Write a VIDEO SCENE PROMPT for Veo to animate this story.
The prompt should describe ONE cinematic 8-second scene that captures the heart of the story.
Include visual style (warm, soft lighting, children's animation style), characters, setting, and a key moment.
Include dialogue or narration that should be spoken in the video.

TASK 3 — Write a MUSIC PROMPT for Lyria to compose a 30-second background score.
Describe the mood, tempo, instruments, and feeling (e.g. "gentle lullaby with soft piano and celesta, warm and dreamy, 70 BPM").

Return your response in EXACTLY this format with these exact headers:

---STORY---
[The complete bedtime story here]

---VIDEO_PROMPT---
[The Veo scene description here]

---MUSIC_PROMPT---
[The Lyria music description here]

---COVER_PROMPT---
[A prompt for generating a beautiful cover illustration for this story, children's book style, warm colors, whimsical]
"""

    response = get_client().models.generate_content(
        model=STORY_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.8),
    )

    text = response.text.strip()

    sections = {"story": "", "video_prompt": "", "music_prompt": "", "cover_prompt": ""}
    current_section = None
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped == "---STORY---":
            current_section = "story"
            continue
        elif stripped == "---VIDEO_PROMPT---":
            current_section = "video_prompt"
            continue
        elif stripped == "---MUSIC_PROMPT---":
            current_section = "music_prompt"
            continue
        elif stripped == "---COVER_PROMPT---":
            current_section = "cover_prompt"
            continue

        if current_section:
            sections[current_section] += line + "\n"

    for key in sections:
        sections[key] = sections[key].strip()

    if not sections["story"]:
        sections["story"] = text

    return sections


def generate_video(video_prompt: str) -> str | None:
    """Use Veo 3.1 to generate an 8-second animated story video."""
    try:
        styled_prompt = (
            f"Children's bedtime animation style, soft warm lighting, "
            f"gentle and whimsical, safe for young children. "
            f"{video_prompt}"
        )

        c = get_client()
        operation = c.models.generate_videos(
            model=VIDEO_MODEL,
            prompt=styled_prompt,
        )

        while not operation.done:
            time.sleep(10)
            operation = c.operations.get(operation)

        generated_video = operation.response.generated_videos[0]
        c.files.download(file=generated_video.video)

        video_path = tempfile.mktemp(suffix=".mp4")
        generated_video.video.save(video_path)
        return video_path
    except Exception as e:
        print(f"Error generating video: {e}")
        return None


def generate_music(music_prompt: str) -> str | None:
    """Use Lyria 3 Clip to generate a 30-second background score."""
    try:
        full_prompt = (
            f"Create a 30-second bedtime lullaby: {music_prompt}. "
            f"Keep it gentle, soothing, and perfect for children falling asleep."
        )

        response = get_client().models.generate_content(
            model=MUSIC_MODEL,
            contents=full_prompt,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO", "TEXT"],
            ),
        )

        for part in response.parts:
            if part.inline_data is not None:
                temp_audio = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
                temp_audio.write(part.inline_data.data)
                temp_audio.close()
                return temp_audio.name

        return None
    except Exception as e:
        print(f"Error generating music: {e}")
        return None


def generate_cover_art(cover_prompt: str) -> str | None:
    """Use Nano Banana (Gemini Flash Image) to generate cover art."""
    try:
        full_prompt = (
            f"Children's book cover illustration, vibrant and warm, "
            f"whimsical art style, suitable for young children: {cover_prompt}"
        )

        response = get_client().models.generate_content(
            model=IMAGE_MODEL,
            contents=full_prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
            ),
        )

        for part in response.parts:
            if part.inline_data is not None:
                temp_img = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
                temp_img.write(part.inline_data.data)
                temp_img.close()
                return temp_img.name

        return None
    except Exception as e:
        print(f"Error generating cover art: {e}")
        return None


def generate_story_complete(story_topic: str, story_length: str = "short", child_name: str = "") -> dict:
    """
    Full pipeline: Gemini writes story + prompts, then Veo/Lyria/NanoBanana run in PARALLEL.
    """
    timings = {}
    total_start = time.time()

    # Step 1: Gemini generates story + all creative prompts
    story_start = time.time()
    sections = generate_story(story_topic, story_length, child_name)
    timings["story_generation"] = round(time.time() - story_start, 2)

    if not sections["story"] or "Sorry, I cannot create a story" in sections["story"]:
        timings["total_time"] = round(time.time() - total_start, 2)
        return {
            "story": sections.get("story", "Sorry, I cannot create a story on this topic."),
            "video": None,
            "music": None,
            "cover_art": None,
            "timings": timings,
        }

    # Step 2: Run Veo + Lyria + Nano Banana in PARALLEL
    video_path = None
    music_path = None
    cover_path = None

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {}

        if sections.get("video_prompt"):
            futures[executor.submit(generate_video, sections["video_prompt"])] = "video"

        if sections.get("music_prompt"):
            futures[executor.submit(generate_music, sections["music_prompt"])] = "music"

        if sections.get("cover_prompt"):
            futures[executor.submit(generate_cover_art, sections["cover_prompt"])] = "cover"

        for future in as_completed(futures):
            task_name = futures[future]
            task_start = time.time()
            try:
                result = future.result()
                if task_name == "video":
                    video_path = result
                    timings["video_generation"] = round(time.time() - story_start - timings["story_generation"], 2)
                elif task_name == "music":
                    music_path = result
                    timings["music_generation"] = round(time.time() - story_start - timings["story_generation"], 2)
                elif task_name == "cover":
                    cover_path = result
                    timings["cover_generation"] = round(time.time() - story_start - timings["story_generation"], 2)
            except Exception as e:
                print(f"Error in {task_name}: {e}")

    timings["total_time"] = round(time.time() - total_start, 2)

    print("=" * 60)
    print("STORYFORGE GENERATION COMPLETE")
    print("=" * 60)
    for key, val in timings.items():
        print(f"  {key}: {val}s")
    print("=" * 60)

    return {
        "story": sections["story"],
        "video": video_path,
        "music": music_path,
        "cover_art": cover_path,
        "timings": timings,
    }
