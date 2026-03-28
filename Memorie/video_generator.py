"""
Memoire — Video, music, and image generation (Google GenAI)

This module is the media pipeline for turning structured “memory” data into
deliverable assets used elsewhere in the app:

**Veo 3.1 (video)** — Generates an initial ~8 second scene from a text prompt,
optionally grounded with up to a few reference images for character or setting
consistency. The same model family can *extend* an existing Veo output with a
follow-up prompt (~7 seconds per extension), so multi-beat stories become one
longer clip. Typical uses: cinematic recap videos, narrative montages, and any
flow that needs motion + continuity across scenes.

**Lyria 3 (music)** — Produces short soundtrack audio from a mood/instrument
prompt, suited for underscoring memory videos or comics without manual music
editing.

**Nano Banana / image models** — Generates stills: style references for a chosen
visual look, poster-like cover thumbnails for a memory, and sequential comic or
manga panels with optional English narration captions. Typical uses: covers,
social previews, printable/shareable comic strips, and style previews before
committing to video.

**Orchestration** — Higher-level helpers run parallel work (e.g. first video
scene + music + cover) then sequential video extensions, or parallel comic panels
+ music + cover, returning local file paths and timing metadata for the UI or
export step.

**Configuration & dry-run** — Model names, defaults, style dictionaries, and
`DRY_RUN` live in `config.py`. When `DRY_RUN` is true, no API calls are made;
dummy paths are returned so the rest of the application can be exercised
offline (tests, demos, CI) without credentials or quota.

Environment variables and API keys are loaded via `config.py` (not this module).
"""

from __future__ import annotations

import os
import time
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed

from PIL import Image
from google import genai
from google.genai import types

from config import (
    COMIC_STYLES,
    DEFAULT_ASPECT_RATIO,
    DEFAULT_VIDEO_RESOLUTION,
    DRY_RUN,
    GOOGLE_API_KEY,
    IMAGE_MODEL,
    MAX_REFERENCE_IMAGES,
    MUSIC_MODEL,
    STYLE_IMAGE_PROMPTS,
    VIDEO_MODEL,
    VIDEO_MODEL_FAST,
    VIDEO_POLL_INTERVAL_SEC,
)
from logger import get_logger, log_genai_call

log = get_logger(__name__)

_client = None

# Placeholder object for the second element of (path, veo_video) in DRY_RUN so
# extension loops can run without a real API video handle.
_DRY_VEO_VIDEO = object()


def get_client():
    """Return a singleton `genai.Client` configured with `GOOGLE_API_KEY` from config."""
    global _client
    log.info(
        "get_client()  (reusing_singleton=%s)",
        _client is not None,
    )
    if _client is None:
        api_key = GOOGLE_API_KEY
        if not api_key:
            raise ValueError("Set GOOGLE_API_KEY in your .env file")
        _client = genai.Client(api_key=api_key)
    return _client


def _build_reference_images(image_paths: list[str] | None) -> list | None:
    """Load up to `MAX_REFERENCE_IMAGES` image files as Veo reference assets."""
    log.info(
        "_build_reference_images(image_paths=%r)",
        image_paths,
    )
    if not image_paths:
        return None
    refs = []
    for img_path in image_paths[:MAX_REFERENCE_IMAGES]:
        if os.path.exists(img_path):
            img = Image.open(img_path)
            refs.append(
                types.VideoGenerationReferenceImage(image=img, reference_type="asset")
            )
    return refs if refs else None


def _poll_video_operation(operation):
    """Poll a Veo long-running operation until complete; return the final operation."""
    log.info("_poll_video_operation(operation=%r)", operation)
    c = get_client()
    while not operation.done:
        time.sleep(VIDEO_POLL_INTERVAL_SEC)
        operation = c.operations.get(operation)
    return operation


def generate_scene(
    scene_prompt: str,
    reference_images: list[str] | None = None,
    aspect_ratio: str = DEFAULT_ASPECT_RATIO,
    use_fast: bool = True,
) -> tuple:
    """Generate a single ~8 second video scene with Veo 3.1.

    Returns ``(local_file_path, veo_video_object)``. The video object is required
    for subsequent `extend_video` calls. On failure returns ``(None, None)``.
    """
    log.info(
        "generate_scene(scene_prompt=%r, reference_images=%r, aspect_ratio=%r, use_fast=%r)",
        scene_prompt,
        reference_images,
        aspect_ratio,
        use_fast,
    )
    if DRY_RUN:
        log_genai_call(
            log,
            model=VIDEO_MODEL_FAST if use_fast else VIDEO_MODEL,
            prompt=scene_prompt,
            config={
                "aspect_ratio": aspect_ratio,
                "reference_images": reference_images,
                "use_fast": use_fast,
                "dry_run": True,
            },
            output="dry_run_video.mp4 + sentinel veo handle",
        )
        return "dry_run_video.mp4", _DRY_VEO_VIDEO

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
        log_genai_call(
            log,
            model=model,
            prompt=scene_prompt,
            config=dict(config_kwargs, reference_image_count=len(ref_imgs or [])),
            output=f"saved_video_path={video_path}",
        )
        return video_path, generated_video.video
    except Exception as e:
        log.error("Error generating scene: %s", e)
        return None, None


def extend_video(
    previous_veo_video,
    extension_prompt: str,
) -> tuple:
    """Extend a Veo-generated video by ~7 seconds using a new prompt.

    Uses ``DEFAULT_VIDEO_RESOLUTION`` in the API config (typically 720p).
    Returns ``(path, new_veo_video_object)`` or ``(None, None)`` on failure.
    """
    log.info(
        "extend_video(previous_veo_video=%r, extension_prompt=%r)",
        previous_veo_video,
        extension_prompt,
    )
    if DRY_RUN:
        log_genai_call(
            log,
            model=VIDEO_MODEL,
            prompt=extension_prompt,
            config={
                "number_of_videos": 1,
                "resolution": DEFAULT_VIDEO_RESOLUTION,
                "dry_run": True,
            },
            output="dry_run_video.mp4 + sentinel veo handle",
        )
        return "dry_run_video.mp4", _DRY_VEO_VIDEO

    try:
        c = get_client()
        config = types.GenerateVideosConfig(
            number_of_videos=1,
            resolution=DEFAULT_VIDEO_RESOLUTION,
        )
        operation = c.models.generate_videos(
            model=VIDEO_MODEL,
            video=previous_veo_video,
            prompt=extension_prompt,
            config=config,
        )

        operation = _poll_video_operation(operation)

        generated_video = operation.response.generated_videos[0]
        c.files.download(file=generated_video.video)

        video_path = tempfile.mktemp(suffix=".mp4")
        generated_video.video.save(video_path)
        log_genai_call(
            log,
            model=VIDEO_MODEL,
            prompt=extension_prompt,
            config={"number_of_videos": 1, "resolution": DEFAULT_VIDEO_RESOLUTION},
            output=f"saved_video_path={video_path}",
        )
        return video_path, generated_video.video
    except Exception as e:
        log.error("Error extending video: %s", e)
        return None, None


def generate_extended_video(
    scene_prompts: list[dict],
    reference_images: list[str] | None = None,
    aspect_ratio: str = DEFAULT_ASPECT_RATIO,
    use_fast: bool = True,
    max_extensions: int = 3,
    progress_callback=None,
) -> str | None:
    """Generate an initial scene then chain Veo extensions for subsequent beats.

    Returns the path to the final combined video file, or ``None`` if the first
    scene cannot be generated.
    """
    log.info(
        "generate_extended_video(scene_prompts=%r, reference_images=%r, "
        "aspect_ratio=%r, use_fast=%r, max_extensions=%r, progress_callback=%r)",
        scene_prompts,
        reference_images,
        aspect_ratio,
        use_fast,
        max_extensions,
        progress_callback,
    )
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


def generate_music(music_prompt: str, clip: bool = True) -> str | None:
    """Generate a soundtrack clip using Lyria 3 via `generate_content` with audio modality."""
    log.info("generate_music(music_prompt=%r, clip=%r)", music_prompt, clip)
    model = MUSIC_MODEL
    full_prompt = (
        f"Create a cinematic soundtrack: {music_prompt}. "
        f"Make it emotional, evocative, and perfect for a personal memory video."
    )
    gen_config = types.GenerateContentConfig(
        response_modalities=["AUDIO", "TEXT"],
    )
    config_dict = {"response_modalities": ["AUDIO", "TEXT"], "clip": clip}

    if DRY_RUN:
        log_genai_call(
            log,
            model=model,
            prompt=full_prompt,
            config=config_dict,
            output="dry_run_music.mp3",
        )
        return "dry_run_music.mp3"

    try:
        response = get_client().models.generate_content(
            model=model,
            contents=full_prompt,
            config=gen_config,
        )

        for part in response.parts:
            if part.inline_data is not None:
                audio_path = tempfile.mktemp(suffix=".mp3")
                with open(audio_path, "wb") as f:
                    f.write(part.inline_data.data)
                log_genai_call(
                    log,
                    model=model,
                    prompt=full_prompt,
                    config=config_dict,
                    output=f"audio_path={audio_path}",
                )
                return audio_path

        log_genai_call(
            log,
            model=model,
            prompt=full_prompt,
            config=config_dict,
            output="no inline audio in response",
        )
        return None
    except Exception as e:
        log.error("Error generating music: %s", e)
        return None


def generate_style_reference(description: str, style: str) -> str | None:
    """Generate a single style-reference still using `STYLE_IMAGE_PROMPTS` and Nano Banana."""
    log.info("generate_style_reference(description=%r, style=%r)", description, style)
    style_desc = STYLE_IMAGE_PROMPTS.get(style, STYLE_IMAGE_PROMPTS["movie_trailer"])
    prompt = f"{style_desc}. {description}"
    gen_config = types.GenerateContentConfig(
        response_modalities=["IMAGE", "TEXT"],
    )
    config_dict = {"response_modalities": ["IMAGE", "TEXT"], "style": style}

    if DRY_RUN:
        log_genai_call(
            log,
            model=IMAGE_MODEL,
            prompt=prompt,
            config=config_dict,
            output="dry_run_image.png",
        )
        return "dry_run_image.png"

    try:
        response = get_client().models.generate_content(
            model=IMAGE_MODEL,
            contents=prompt,
            config=gen_config,
        )

        for part in response.parts:
            if part.inline_data is not None:
                img_path = tempfile.mktemp(suffix=".png")
                with open(img_path, "wb") as f:
                    f.write(part.inline_data.data)
                log_genai_call(
                    log,
                    model=IMAGE_MODEL,
                    prompt=prompt,
                    config=config_dict,
                    output=f"image_path={img_path}",
                )
                return img_path

        log_genai_call(
            log,
            model=IMAGE_MODEL,
            prompt=prompt,
            config=config_dict,
            output="no inline image in response",
        )
        return None
    except Exception as e:
        log.error("Error generating style reference: %s", e)
        return None


def generate_cover_thumbnail(memory_title: str, memory_summary: str, style: str) -> str | None:
    """Generate a cinematic cover/thumbnail image for a memory (no text overlays)."""
    log.info(
        "generate_cover_thumbnail(memory_title=%r, memory_summary=%r, style=%r)",
        memory_title,
        memory_summary,
        style,
    )
    prompt = (
        f"Cinematic movie poster style thumbnail for a personal memory titled '{memory_title}'. "
        f"Scene: {memory_summary}. "
        f"Style: {style}. Dramatic composition, emotional, beautiful. "
        f"No text overlays."
    )
    gen_config = types.GenerateContentConfig(
        response_modalities=["IMAGE", "TEXT"],
    )
    config_dict = {"response_modalities": ["IMAGE", "TEXT"]}

    if DRY_RUN:
        log_genai_call(
            log,
            model=IMAGE_MODEL,
            prompt=prompt,
            config=config_dict,
            output="dry_run_image.png",
        )
        return "dry_run_image.png"

    try:
        response = get_client().models.generate_content(
            model=IMAGE_MODEL,
            contents=prompt,
            config=gen_config,
        )

        for part in response.parts:
            if part.inline_data is not None:
                img_path = tempfile.mktemp(suffix=".png")
                with open(img_path, "wb") as f:
                    f.write(part.inline_data.data)
                log_genai_call(
                    log,
                    model=IMAGE_MODEL,
                    prompt=prompt,
                    config=config_dict,
                    output=f"image_path={img_path}",
                )
                return img_path

        log_genai_call(
            log,
            model=IMAGE_MODEL,
            prompt=prompt,
            config=config_dict,
            output="no inline image in response",
        )
        return None
    except Exception as e:
        log.error("Error generating cover: %s", e)
        return None


def generate_comic_panel(
    scene_prompt: str,
    caption: str = "",
    comic_style: str = "manga",
    panel_number: int = 1,
) -> str | None:
    """Generate one comic/manga panel with optional English narration caption."""
    log.info(
        "generate_comic_panel(scene_prompt=%r, caption=%r, comic_style=%r, panel_number=%r)",
        scene_prompt,
        caption,
        comic_style,
        panel_number,
    )
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
    gen_config = types.GenerateContentConfig(
        response_modalities=["IMAGE", "TEXT"],
    )
    config_dict = {"response_modalities": ["IMAGE", "TEXT"], "comic_style": comic_style}

    dummy_path = f"dry_run_panel_{panel_number}.png"
    if DRY_RUN:
        log_genai_call(
            log,
            model=IMAGE_MODEL,
            prompt=prompt,
            config=config_dict,
            output=dummy_path,
        )
        return dummy_path

    try:
        response = get_client().models.generate_content(
            model=IMAGE_MODEL,
            contents=prompt,
            config=gen_config,
        )

        for part in response.parts:
            if part.inline_data is not None:
                img_path = tempfile.mktemp(suffix=".png")
                with open(img_path, "wb") as f:
                    f.write(part.inline_data.data)
                log_genai_call(
                    log,
                    model=IMAGE_MODEL,
                    prompt=prompt,
                    config=config_dict,
                    output=f"image_path={img_path}",
                )
                return img_path

        log_genai_call(
            log,
            model=IMAGE_MODEL,
            prompt=prompt,
            config=config_dict,
            output="no inline image in response",
        )
        return None
    except Exception as e:
        log.error("Error generating comic panel %s: %s", panel_number, e)
        return None


def generate_comic_panels(
    scene_prompts: list[dict],
    comic_style: str = "manga",
    max_panels: int = 6,
    progress_callback=None,
) -> list[str]:
    """Generate up to `max_panels` comic panels in parallel (thread pool)."""
    log.info(
        "generate_comic_panels(scene_prompts=%r, comic_style=%r, max_panels=%r, progress_callback=%r)",
        scene_prompts,
        comic_style,
        max_panels,
        progress_callback,
    )
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
                log.error("Panel %s failed: %s", idx, e)

    return [r for r in results if r is not None]


def generate_memory_comic(
    memory: dict,
    comic_style: str = "manga",
    max_panels: int = 6,
    progress_callback=None,
) -> dict:
    """Run comic pipeline: parallel comic panels, music, and cover; return paths and timings."""
    log.info(
        "generate_memory_comic(memory=%r, comic_style=%r, max_panels=%r, progress_callback=%r)",
        memory,
        comic_style,
        max_panels,
        progress_callback,
    )
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
                log.error("Error in %s: %s", task, e)

    timings["total_time"] = round(time.time() - total_start, 2)

    return {
        "panel_paths": panel_paths,
        "music_path": music_path,
        "cover_path": cover_path,
        "timings": timings,
    }


def generate_memory_video(
    memory: dict,
    reference_images: list[str] | None = None,
    style: str = "movie_trailer",
    max_extensions: int = 3,
    progress_callback=None,
) -> dict:
    """Full pipeline: first Veo scene + parallel music/cover, then optional extensions."""
    log.info(
        "generate_memory_video(memory=%r, reference_images=%r, style=%r, "
        "max_extensions=%r, progress_callback=%r)",
        memory,
        reference_images,
        style,
        max_extensions,
        progress_callback,
    )
    timings = {}
    total_start = time.time()

    scene_prompts = memory.get("scene_prompts", [])
    music_prompt = memory.get("music_prompt", "Emotional cinematic soundtrack, piano and strings")

    if not scene_prompts:
        scene_prompts = [
            {"description": f"Cinematic scene of: {memory.get('summary', 'a personal moment')}"}
        ]

    video_path = None
    veo_video = None
    music_path = None
    cover_path = None

    first_prompt = scene_prompts[0].get("description", str(scene_prompts[0]))

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {}

        futures[executor.submit(
            generate_scene, first_prompt, reference_images, DEFAULT_ASPECT_RATIO, True,
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
                log.error("Error in %s: %s", task, e)

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
