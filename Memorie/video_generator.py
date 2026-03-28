import os
import time
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image
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


VIDEO_MODEL = "veo-3.1-generate-preview"
VIDEO_MODEL_FAST = "veo-3.1-fast-generate-preview"
MUSIC_MODEL = "lyria-3-clip-preview"
IMAGE_MODEL = "nano-banana-pro-preview"


# ── Veo 3.1: Video Generation with Character Consistency + Extension ──

def _build_reference_images(image_paths: list[str] | None) -> list | None:
    """Load reference images from file paths for Veo character consistency."""
    if not image_paths:
        return None
    refs = []
    for img_path in image_paths[:3]:
        if os.path.exists(img_path):
            img = Image.open(img_path)
            refs.append(
                types.VideoGenerationReferenceImage(image=img, reference_type="asset")
            )
    return refs if refs else None


def _poll_video_operation(operation):
    """Poll a Veo operation until it completes, returning the operation."""
    c = get_client()
    while not operation.done:
        time.sleep(10)
        operation = c.operations.get(operation)
    return operation


def generate_scene(
    scene_prompt: str,
    reference_images: list[str] | None = None,
    aspect_ratio: str = "16:9",
    use_fast: bool = True,
) -> tuple:
    """Generate a single 8-second video scene with Veo 3.1.

    Returns (local_file_path, veo_video_object) — the veo_video_object is
    needed for subsequent extensions.
    """
    try:
        c = get_client()
        model = VIDEO_MODEL_FAST if use_fast else VIDEO_MODEL

        config_kwargs = {"aspect_ratio": aspect_ratio}
        ref_imgs = _build_reference_images(reference_images)
        if ref_imgs:
            config_kwargs["reference_images"] = ref_imgs

        config = types.GenerateVideosConfig(**config_kwargs)

        operation = c.models.generate_videos(
            model=model,
            prompt=scene_prompt,
            config=config,
        )

        operation = _poll_video_operation(operation)

        generated_video = operation.response.generated_videos[0]
        c.files.download(file=generated_video.video)

        video_path = tempfile.mktemp(suffix=".mp4")
        generated_video.video.save(video_path)
        return video_path, generated_video.video
    except Exception as e:
        print(f"Error generating scene: {e}")
        return None, None


def extend_video(
    previous_veo_video,
    extension_prompt: str,
) -> tuple:
    """Extend a Veo-generated video by ~7 seconds using a new prompt.

    The returned combined video includes the original + the extension.
    Extension is locked to 720p as per API limitation.
    """
    try:
        c = get_client()
        operation = c.models.generate_videos(
            model=VIDEO_MODEL,
            video=previous_veo_video,
            prompt=extension_prompt,
            config=types.GenerateVideosConfig(
                number_of_videos=1,
                resolution="720p",
            ),
        )

        operation = _poll_video_operation(operation)

        generated_video = operation.response.generated_videos[0]
        c.files.download(file=generated_video.video)

        video_path = tempfile.mktemp(suffix=".mp4")
        generated_video.video.save(video_path)
        return video_path, generated_video.video
    except Exception as e:
        print(f"Error extending video: {e}")
        return None, None


def generate_extended_video(
    scene_prompts: list[dict],
    reference_images: list[str] | None = None,
    aspect_ratio: str = "16:9",
    use_fast: bool = True,
    max_extensions: int = 3,
    progress_callback=None,
) -> str | None:
    """Generate initial scene, then extend it with subsequent scenes.

    Each extension adds ~7 seconds.  With 3 extensions you get ~8 + 21 = ~29 seconds.
    With max_extensions=5 you get ~8 + 35 = ~43 seconds, etc.

    Returns the path to the final combined video file.
    """
    if not scene_prompts:
        return None

    first_prompt = scene_prompts[0].get("description", str(scene_prompts[0]))
    if progress_callback:
        progress_callback("Filming Scene 1 (8 sec)...")

    video_path, veo_video = generate_scene(
        first_prompt, reference_images, aspect_ratio, use_fast
    )
    if not video_path or veo_video is None:
        return None

    remaining = scene_prompts[1 : 1 + max_extensions]
    for i, scene in enumerate(remaining):
        ext_prompt = scene.get("description", str(scene))
        if progress_callback:
            progress_callback(f"Extending with Scene {i + 2} (+7 sec)...")
        video_path, veo_video = extend_video(veo_video, ext_prompt)
        if video_path is None or veo_video is None:
            break

    return video_path


# ── Lyria 3: Music Generation ──

def generate_music(music_prompt: str, clip: bool = True) -> str | None:
    """Generate a soundtrack using Lyria 3.

    Args:
        music_prompt: Description of desired music mood, instruments, tempo
        clip: True for 30-sec clip, False for full-length (Pro)
    """
    try:
        model = MUSIC_MODEL
        full_prompt = (
            f"Create a cinematic soundtrack: {music_prompt}. "
            f"Make it emotional, evocative, and perfect for a personal memory video."
        )

        response = get_client().models.generate_content(
            model=model,
            contents=full_prompt,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO", "TEXT"],
            ),
        )

        for part in response.parts:
            if part.inline_data is not None:
                audio_path = tempfile.mktemp(suffix=".mp3")
                with open(audio_path, "wb") as f:
                    f.write(part.inline_data.data)
                return audio_path

        return None
    except Exception as e:
        print(f"Error generating music: {e}")
        return None


# ── Nano Banana: Style Reference & Cover Art ──

def generate_style_reference(description: str, style: str) -> str | None:
    """Generate a style reference image using Nano Banana."""
    try:
        style_prompts = {
            "anime": "Studio Ghibli anime style, cel-shaded, vibrant colors, soft lighting",
            "documentary": "Photorealistic, natural lighting, 35mm film grain, warm tones",
            "movie_trailer": "Cinematic, dramatic lighting, anamorphic lens, rich contrast",
            "studio_ghibli": "Miyazaki watercolor style, magical nature, warm golden glow",
            "cyberpunk": "Neon-lit cyberpunk, rain reflections, purple-blue holographic",
            "vlog": "Natural daylight, casual framing, warm and inviting, slightly overexposed",
        }

        style_desc = style_prompts.get(style, style_prompts["movie_trailer"])

        prompt = f"{style_desc}. {description}"

        response = get_client().models.generate_content(
            model=IMAGE_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
            ),
        )

        for part in response.parts:
            if part.inline_data is not None:
                img_path = tempfile.mktemp(suffix=".png")
                with open(img_path, "wb") as f:
                    f.write(part.inline_data.data)
                return img_path

        return None
    except Exception as e:
        print(f"Error generating style reference: {e}")
        return None


def generate_cover_thumbnail(memory_title: str, memory_summary: str, style: str) -> str | None:
    """Generate a cinematic cover/thumbnail for the memory."""
    try:
        prompt = (
            f"Cinematic movie poster style thumbnail for a personal memory titled '{memory_title}'. "
            f"Scene: {memory_summary}. "
            f"Style: {style}. Dramatic composition, emotional, beautiful. "
            f"No text overlays."
        )

        response = get_client().models.generate_content(
            model=IMAGE_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
            ),
        )

        for part in response.parts:
            if part.inline_data is not None:
                img_path = tempfile.mktemp(suffix=".png")
                with open(img_path, "wb") as f:
                    f.write(part.inline_data.data)
                return img_path

        return None
    except Exception as e:
        print(f"Error generating cover: {e}")
        return None


# ── Nano Banana: Comic / Manga Panel Generation ──

COMIC_STYLES = {
    "manga": "Black and white manga style, dramatic ink lines, screentone shading, expressive eyes, speed lines, Japanese manga aesthetic",
    "comic": "Full color American comic book style, bold outlines, dynamic poses, vibrant colors, halftone dots, speech bubble ready",
    "webtoon": "Korean webtoon style, soft cel-shading, pastel colors, clean lines, vertical scroll layout panel, emotional expressions",
    "graphic_novel": "Graphic novel style, muted watercolor palette, cinematic panels, detailed backgrounds, atmospheric lighting",
    "pop_art": "Pop art comic style, bright primary colors, Ben-Day dots, bold black outlines, Roy Lichtenstein inspired",
}


def generate_comic_panel(
    scene_prompt: str,
    caption: str = "",
    comic_style: str = "manga",
    panel_number: int = 1,
) -> str | None:
    """Generate a single comic/manga panel with narrative text using Nano Banana."""
    try:
        style_desc = COMIC_STYLES.get(comic_style, COMIC_STYLES["manga"])

        caption_instruction = ""
        if caption:
            caption_instruction = (
                f'Include a narration box at the {"top" if panel_number % 2 == 1 else "bottom"} '
                f'of the panel with this exact text in a clean readable font: "{caption}". '
                f"ALL text in the image MUST be in English only. Do NOT include any other language."
            )

        prompt = (
            f"{style_desc}. Comic panel {panel_number}. "
            f"Scene: {scene_prompt}. "
            f"Framed as a single comic book panel with dramatic composition. "
            f"All text, captions, labels, and lettering must be in English only. "
            f"{caption_instruction}"
        )

        response = get_client().models.generate_content(
            model=IMAGE_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
            ),
        )

        for part in response.parts:
            if part.inline_data is not None:
                img_path = tempfile.mktemp(suffix=".png")
                with open(img_path, "wb") as f:
                    f.write(part.inline_data.data)
                return img_path

        return None
    except Exception as e:
        print(f"Error generating comic panel {panel_number}: {e}")
        return None


def generate_comic_panels(
    scene_prompts: list[dict],
    comic_style: str = "manga",
    max_panels: int = 6,
    progress_callback=None,
) -> list[str]:
    """Generate all comic panels in parallel using Nano Banana."""
    panels = scene_prompts[:max_panels]
    results = [None] * len(panels)

    with ThreadPoolExecutor(max_workers=3) as executor:
        future_to_idx = {}
        for i, scene in enumerate(panels):
            prompt = scene.get("description", str(scene))
            caption = scene.get("caption", "")
            future = executor.submit(generate_comic_panel, prompt, caption, comic_style, i + 1)
            future_to_idx[future] = i

        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                result = future.result()
                results[idx] = result
                if progress_callback:
                    progress_callback(f"Panel {idx + 1}/{len(panels)} drawn")
            except Exception as e:
                print(f"Panel {idx} failed: {e}")

    return [r for r in results if r is not None]


def generate_memory_comic(
    memory: dict,
    comic_style: str = "manga",
    max_panels: int = 6,
    progress_callback=None,
) -> dict:
    """Full comic pipeline: panels (Nano Banana) + music (Lyria) + cover in parallel."""
    timings = {}
    total_start = time.time()

    scene_prompts = memory.get("scene_prompts", [])
    music_prompt = memory.get("music_prompt", "Emotional cinematic soundtrack, piano and strings")

    if not scene_prompts:
        scene_prompts = [
            {"description": f"Scene of: {memory.get('summary', 'a personal moment')}"}
        ]

    panel_paths = []
    music_path = None
    cover_path = None

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {}

        futures[executor.submit(
            generate_comic_panels, scene_prompts, comic_style, max_panels, progress_callback
        )] = "panels"

        futures[executor.submit(generate_music, music_prompt)] = "music"

        futures[executor.submit(
            generate_cover_thumbnail,
            memory.get("title", "Memory"),
            memory.get("summary", ""),
            comic_style,
        )] = "cover"

        for future in as_completed(futures):
            task = futures[future]
            try:
                elapsed = round(time.time() - total_start, 2)
                if task == "panels":
                    panel_paths = future.result()
                    timings["panels_generation"] = elapsed
                    if progress_callback:
                        progress_callback(f"{len(panel_paths)} panels drawn ({elapsed}s)")
                elif task == "music":
                    music_path = future.result()
                    timings["music_generation"] = elapsed
                    if progress_callback:
                        progress_callback(f"Music composed ({elapsed}s)")
                elif task == "cover":
                    cover_path = future.result()
                    timings["cover_generation"] = elapsed
                    if progress_callback:
                        progress_callback(f"Cover painted ({elapsed}s)")
            except Exception as e:
                print(f"Error in {task}: {e}")

    timings["total_time"] = round(time.time() - total_start, 2)

    return {
        "panel_paths": panel_paths,
        "music_path": music_path,
        "cover_path": cover_path,
        "timings": timings,
    }


# ── Full Pipeline ──

def generate_memory_video(
    memory: dict,
    reference_images: list[str] | None = None,
    style: str = "movie_trailer",
    max_extensions: int = 3,
    progress_callback=None,
) -> dict:
    """Full pipeline: extended video (Veo) + music (Lyria) + cover (Nano Banana).

    Veo generates an initial 8-sec scene then extends it with subsequent scenes
    (each extension adds ~7 sec).  Music and cover art generate in parallel with
    the initial scene; extensions run sequentially after.

    Returns dict with: video_path, music_path, cover_path, timings
    """
    timings = {}
    total_start = time.time()

    scene_prompts = memory.get("scene_prompts", [])
    music_prompt = memory.get("music_prompt", "Emotional cinematic soundtrack, piano and strings")

    if not scene_prompts:
        scene_prompts = [
            {"description": f"Cinematic scene of: {memory.get('summary', 'a personal moment')}"}
        ]

    # --- Phase A: first scene + music + cover in PARALLEL ---
    video_path = None
    veo_video = None
    music_path = None
    cover_path = None

    first_prompt = scene_prompts[0].get("description", str(scene_prompts[0]))

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {}

        futures[executor.submit(
            generate_scene, first_prompt, reference_images, "16:9", True,
        )] = "video"

        futures[executor.submit(generate_music, music_prompt)] = "music"

        futures[executor.submit(
            generate_cover_thumbnail,
            memory.get("title", "Memory"),
            memory.get("summary", ""),
            style,
        )] = "cover"

        for future in as_completed(futures):
            task = futures[future]
            try:
                elapsed = round(time.time() - total_start, 2)
                if task == "video":
                    video_path, veo_video = future.result()
                    timings["scene_1"] = elapsed
                    if progress_callback:
                        progress_callback(f"Scene 1 filmed ({elapsed}s)")
                elif task == "music":
                    music_path = future.result()
                    timings["music_generation"] = elapsed
                    if progress_callback:
                        progress_callback(f"Music composed ({elapsed}s)")
                elif task == "cover":
                    cover_path = future.result()
                    timings["cover_generation"] = elapsed
                    if progress_callback:
                        progress_callback(f"Cover art painted ({elapsed}s)")
            except Exception as e:
                print(f"Error in {task}: {e}")

    # --- Phase B: extend video with remaining scenes (sequential) ---
    needed_total = 1 + max_extensions
    while len(scene_prompts) < needed_total:
        idx = len(scene_prompts)
        scene_prompts.append({
            "description": (
                f"Continuation of the memory — scene {idx + 1}. "
                f"{scene_prompts[0].get('description', '')} "
                "Show a new angle or moment that naturally follows the previous scene."
            )
        })

    if veo_video is not None and max_extensions > 0:
        remaining = scene_prompts[1 : 1 + max_extensions]
        for i, scene in enumerate(remaining):
            ext_prompt = scene.get("description", str(scene))
            if progress_callback:
                progress_callback(f"Extending with Scene {i + 2} (+7 sec)...")
            new_path, new_veo = extend_video(veo_video, ext_prompt)
            if new_path and new_veo:
                video_path = new_path
                veo_video = new_veo
                timings[f"scene_{i + 2}"] = round(time.time() - total_start, 2)
                if progress_callback:
                    progress_callback(f"Scene {i + 2} added ({timings[f'scene_{i + 2}']}s)")
            else:
                if progress_callback:
                    progress_callback(f"Scene {i + 2} extension failed, stopping.")
                break

    timings["total_time"] = round(time.time() - total_start, 2)
    num_scenes = sum(1 for k in timings if k.startswith("scene_"))
    est_duration = 8 + max(0, num_scenes - 1) * 7
    timings["estimated_duration_sec"] = est_duration

    return {
        "video_path": video_path,
        "music_path": music_path,
        "cover_path": cover_path,
        "timings": timings,
    }
