import streamlit as st
import time
import os
import json
import tempfile
from datetime import date, datetime
from concurrent.futures import ThreadPoolExecutor

# Bridge Streamlit Cloud secrets → env vars so all modules can use os.getenv()
try:
    for _k, _v in st.secrets.items():
        if isinstance(_v, str):
            os.environ.setdefault(_k, _v)
    if "GOOGLE_CREDENTIALS" in st.secrets and not os.path.exists("credentials.json"):
        with open("credentials.json", "w") as _f:
            _f.write(st.secrets["GOOGLE_CREDENTIALS"])
except Exception:
    pass

os.makedirs("assets", exist_ok=True)

import database as db
import memory_capture as capture
import video_generator as vgen
import calendar_service as cal

st.set_page_config(page_title="Memoire", page_icon="🎬", layout="wide", initial_sidebar_state="collapsed")

STYLES = {
    "anime": "Anime", "documentary": "Documentary", "movie_trailer": "Movie Trailer",
    "studio_ghibli": "Studio Ghibli", "cyberpunk": "Cyberpunk", "vlog": "Vlog",
}
EMOTIONS = {
    "joy": "😊", "sadness": "😢", "excitement": "🤩", "calm": "😌",
    "nostalgia": "🥹", "love": "❤️", "gratitude": "🙏", "wonder": "✨",
}

DIV = '<div style="text-align:center;margin:1.2rem 0;"><span style="display:inline-block;width:38%;height:1px;background:#D4C4A0;vertical-align:middle;"></span><span style="color:#D4C4A0;margin:0 10px;font-size:0.8rem;vertical-align:middle;">✦</span><span style="display:inline-block;width:38%;height:1px;background:#D4C4A0;vertical-align:middle;"></span></div>'

# ═══════════════ CSS ═══════════════
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,wght@0,300;0,400;0,500;0,600;0,700;1,300;1,400;1,500&family=Playfair+Display:ital,wght@0,400;0,600;0,700;1,400;1,600&display=swap');
:root{--bg:#F5F0E8;--side:#EDE4D3;--card:#FEFCF7;--accent:#D4A84B;--accent2:#C49438;--rose:#C9896A;--border:#D4C4A0;--text:#2C1810;--muted:#8B6F5E;--badge:#F5EDD8;--active:#F5EDD8}

/* ── base ── */
.main,.stApp{background-color:var(--bg)!important;background-image:url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.04'/%3E%3C/svg%3E")!important;background-blend-mode:multiply!important}
h1,h2,h3,h4{font-family:'Playfair Display',serif!important;color:var(--text)!important}
p,li,label,div{font-family:'DM Sans',sans-serif;color:var(--text)}
span{color:var(--text)}
[data-testid="stSidebar"] button[kind="header"] span,[data-testid="collapsedControl"] span,.material-symbols-outlined,.material-icons,[data-testid="stIconMaterial"]{font-family:'Material Symbols Rounded','Material Icons'!important;-webkit-text-fill-color:initial!important}

/* ── hero ── */
.hero{text-align:center;padding:2.5rem 0 1rem}
.hero-title{font-family:'Playfair Display',serif!important;font-size:2.8rem;font-weight:700;color:var(--text)!important;-webkit-text-fill-color:var(--text)!important;background:none!important;margin-bottom:.3rem}
.hero-sub{font-family:'DM Sans',sans-serif;font-size:1.05rem;color:var(--muted)!important;font-style:italic}

/* ── cards ── */
.card{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:1.5rem;margin-bottom:1rem;box-shadow:4px 6px 20px rgba(44,24,16,.10);transition:all .25s ease}
.card:hover{transform:translateY(-4px);box-shadow:6px 10px 30px rgba(44,24,16,.15)}
.card h4{margin:0 0 .75rem;font-size:1.1rem;font-family:'Playfair Display',serif!important;color:var(--text)!important}

/* ── stats ── */
.stat-card{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:1.2rem .8rem;text-align:center;box-shadow:4px 6px 20px rgba(44,24,16,.10);transition:all .25s ease}
.stat-card:hover{transform:translateY(-3px);box-shadow:6px 10px 28px rgba(44,24,16,.14)}
.stat-icon{font-size:1.4rem;margin-bottom:.3rem}
.stat-value{font-family:'Playfair Display',serif!important;font-size:2.2rem;font-weight:700;color:var(--text)!important;-webkit-text-fill-color:var(--text)!important;background:none!important}
.stat-label{color:var(--muted)!important;font-size:.78rem;font-family:'DM Sans',sans-serif}

/* ── badges ── */
.badge{display:inline-block;padding:3px 10px;border-radius:6px;font-size:.68rem;font-weight:500;font-family:'DM Sans',sans-serif;background:var(--badge);color:var(--muted);border:1px solid var(--border);margin:2px}

/* ── emotion tag ── */
.emotion-tag{display:inline-block;padding:4px 14px;border-radius:20px;font-size:.8rem;background:var(--badge);color:var(--text)!important;border:1px solid var(--border);font-family:'DM Sans',sans-serif}

/* ── status pills ── */
.pill{display:inline-block;padding:4px 14px;border-radius:20px;font-size:.78rem;font-family:'DM Sans',sans-serif;margin:3px 4px}
.pill-green{background:#E8F5E9;color:#2E7D32!important;border:1px solid #A5D6A7}
.pill-amber{background:var(--badge);color:var(--muted)!important;border:1px solid var(--border)}

/* ── polaroid caption ── */
.pol-cap{font-family:'Playfair Display',serif;font-style:italic;font-size:.75rem;color:var(--muted);text-align:center;margin-top:6px}

/* ── buttons ── */
.stButton>button{background:var(--accent)!important;color:var(--text)!important;border:none!important;border-radius:12px!important;font-weight:600!important;font-family:'DM Sans',sans-serif!important;padding:.6rem 1.5rem!important;transition:all .25s ease!important;box-shadow:0 2px 8px rgba(212,168,75,.3)!important}
.stButton>button p,.stButton>button span,.stButton>button div{color:var(--text)!important;font-family:'DM Sans',sans-serif!important}
.stButton>button:hover{background:var(--accent2)!important;transform:translateY(-2px)!important;box-shadow:0 4px 14px rgba(212,168,75,.4)!important}

/* ── inputs ── */
.stTextArea textarea,.stTextInput input{background:var(--card)!important;color:var(--text)!important;border:1px solid var(--border)!important;border-radius:12px!important;font-family:'DM Sans',sans-serif!important}
.stTextArea textarea:focus,.stTextInput input:focus{border-color:var(--accent)!important;box-shadow:0 0 0 3px rgba(212,168,75,.15)!important}
.stSelectbox>div>div,.stMultiSelect>div>div{background:var(--card)!important;border-color:var(--border)!important;border-radius:12px!important}
.stSelectbox>div>div:focus-within,.stMultiSelect>div>div:focus-within{border-color:var(--accent)!important;box-shadow:0 0 0 3px rgba(212,168,75,.15)!important}
.stDateInput>div>div>input{background:var(--card)!important;border:1px solid var(--border)!important;border-radius:12px!important;color:var(--text)!important;font-family:'DM Sans',sans-serif!important}
.stDateInput>div>div>input:focus{border-color:var(--accent)!important;box-shadow:0 0 0 3px rgba(212,168,75,.15)!important}

/* ── sidebar ── */
[data-testid="stSidebar"]{background:var(--side)!important;border-right:1px solid var(--border)!important;transform:none!important;visibility:visible!important;display:flex!important;transition:min-width .25s ease,max-width .25s ease!important;overflow:hidden!important}
[data-testid="stSidebar"]>div:first-child{background:var(--side)!important;transition:width .25s ease!important;overflow:hidden!important}
[data-testid="stSidebar"]>div:first-child::-webkit-scrollbar{display:none!important;width:0!important}
[data-testid="stSidebar"]>div:first-child{scrollbar-width:none!important;-ms-overflow-style:none!important}
[data-testid="stSidebar"] p,[data-testid="stSidebar"] span,[data-testid="stSidebar"] label,[data-testid="stSidebar"] div{color:var(--text)!important;font-family:'DM Sans',sans-serif}
[data-testid="collapsedControl"]{display:none!important;width:0!important;height:0!important;overflow:hidden!important}
[data-testid="stSidebarCollapsedControl"]{display:none!important;width:0!important;height:0!important}
[data-testid="stSidebar"] button[kind="header"]{display:none!important}
[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"]{display:none!important}
[data-testid="stSidebar"] [data-testid="stBaseButton-header"]{display:none!important}
button[title="Close sidebar"],button[title="Open sidebar"]{display:none!important}
.sb-title{font-family:'Playfair Display',serif!important;font-size:22px;font-weight:700;color:var(--text)!important}
.sb-tag{font-family:'DM Sans',sans-serif;font-size:12px;font-style:italic;color:var(--muted)!important;margin-top:-4px}

/* sidebar toggle button - subtle style */
[data-testid="stSidebar"] .stButton>button{
    background:transparent!important;border:1px solid var(--border)!important;
    border-radius:8px!important;padding:2px 10px!important;
    box-shadow:none!important;min-height:0!important}
[data-testid="stSidebar"] .stButton>button p,
[data-testid="stSidebar"] .stButton>button span{color:var(--muted)!important;font-size:14px!important}
[data-testid="stSidebar"] .stButton>button:hover{background:var(--badge)!important;transform:none!important;box-shadow:none!important}


/* sidebar radio nav override */
[data-testid="stSidebar"] .stRadio>div[role="radiogroup"]{gap:2px!important}
[data-testid="stSidebar"] .stRadio>div[role="radiogroup"] label{font-family:'DM Sans',sans-serif!important;font-size:15px!important;color:var(--muted)!important;padding:8px 12px!important;border-radius:12px!important;border-left:3px solid transparent!important;transition:all .2s ease!important;cursor:pointer;white-space:nowrap!important;overflow:visible!important}
[data-testid="stSidebar"] .stRadio>div[role="radiogroup"] label:hover{background:#F0E6D0!important}
[data-testid="stSidebar"] .stRadio>div[role="radiogroup"] label[data-checked="true"]{color:var(--text)!important;font-weight:700!important;background:var(--active)!important;border-left:3px solid var(--accent)!important}
[data-testid="stSidebar"] .stRadio>div[role="radiogroup"] label div[data-testid="stMarkdownContainer"] p{color:inherit!important}

/* ── tabs ── */
.stTabs [data-baseweb="tab-list"]{border-bottom:1px solid var(--border);gap:0}
.stTabs [data-baseweb="tab"]{font-family:'DM Sans',sans-serif!important;color:var(--muted)!important;border-bottom:2px solid transparent;padding:.5rem 1.2rem}
.stTabs [data-baseweb="tab"][aria-selected="true"]{color:var(--text)!important;font-weight:600!important;border-bottom:2px solid var(--accent)!important}
.stTabs [data-baseweb="tab-highlight"]{background-color:var(--accent)!important}

/* ── expander ── */
.stExpander{border:1px solid var(--border)!important;border-radius:16px!important;background:var(--card)!important;box-shadow:4px 6px 20px rgba(44,24,16,.08)!important}
.stExpander summary span{color:var(--accent)!important}

/* ── slider ── */
.stSlider>div>div>div>div{background:var(--accent)!important}

/* ── file uploader ── */
.stFileUploader>div{border:2px dashed var(--accent)!important;border-radius:16px!important;background:var(--badge)!important}

/* ── hide chrome ── */
#MainMenu,footer,header{display:none!important;height:0!important;margin:0!important;padding:0!important}
[data-testid="stHeader"]{display:none!important;height:0!important}
[data-testid="stSidebar"]>div:first-child{padding-top:.5rem!important}
[data-testid="stAppViewBlockContainer"]{padding-top:.5rem!important}
.block-container{padding-top:.5rem!important}
</style>""", unsafe_allow_html=True)


# ═══════════════ SESSION STATE ═══════════════
if "page" not in st.session_state:
    st.session_state.page = "capture"
    st.session_state.current_memory = None
    st.session_state.extracted = None
    st.session_state.generating = False
if "sb_open" not in st.session_state:
    st.session_state.sb_open = True

def _toggle_sb():
    st.session_state.sb_open = not st.session_state.sb_open

sb_open = st.session_state.sb_open
sb_w = 260 if sb_open else 60

_collapsed_radio_css = """
[data-testid="stSidebar"] .stRadio>div[role="radiogroup"] label>div:first-child{display:none!important}
[data-testid="stSidebar"] .stRadio>div[role="radiogroup"] label{justify-content:center!important;padding:10px 0!important;border-left:none!important}
[data-testid="stSidebar"] .stRadio>div[role="radiogroup"] label div[data-testid="stMarkdownContainer"] p{font-size:20px!important;text-align:center!important}
""" if not sb_open else ""
st.markdown(f"""<style>
[data-testid="stSidebar"]{{min-width:{sb_w}px!important;max-width:{sb_w}px!important}}
[data-testid="stSidebar"]>div:first-child{{width:{sb_w}px!important}}
{_collapsed_radio_css}
</style>""", unsafe_allow_html=True)


# ═══════════════ SIDEBAR ═══════════════
_NAV_FMT_EXPANDED = {"Capture": "✏️  Capture", "Gallery": "🎞️  Gallery", "Calendar": "📅  Calendar", "Settings": "⚙️  Settings"}
_NAV_FMT_COLLAPSED = {"Capture": "✏️", "Gallery": "🎞️", "Calendar": "📅", "Settings": "⚙️"}

with st.sidebar:
    toggle_label = "◀" if sb_open else "▶"
    st.button(toggle_label, key="sb_toggle", on_click=_toggle_sb)

    if sb_open:
        st.markdown('<div class="sb-title">Memoire</div>', unsafe_allow_html=True)
        st.markdown('<p class="sb-tag">Your life, recut as a movie trailer.</p>', unsafe_allow_html=True)
        st.markdown(DIV, unsafe_allow_html=True)

    fmt = _NAV_FMT_EXPANDED if sb_open else _NAV_FMT_COLLAPSED
    nav = st.radio(
        "Navigate",
        ["Capture", "Gallery", "Calendar", "Settings"],
        format_func=lambda x: fmt[x],
        label_visibility="collapsed",
    )
    st.session_state.page = {"Capture": "capture", "Gallery": "gallery", "Calendar": "calendar", "Settings": "settings"}[nav]

    if sb_open:
        st.markdown(DIV, unsafe_allow_html=True)
        st.markdown(
            '<span class="badge">Gemini</span><span class="badge">Veo 3.1</span>'
            '<span class="badge">Lyria 3</span><span class="badge">Nano Banana</span>'
            '<span class="badge">Calendar</span><span class="badge">Drive</span>',
            unsafe_allow_html=True,
        )


# ╔═══════════════════════════════════════════╗
# ║  PAGE 1 — CAPTURE                         ║
# ╚═══════════════════════════════════════════╝
if st.session_state.page == "capture":
    st.markdown('<div class="hero"><div class="hero-title">Capture a Memory</div><div class="hero-sub">Tell me what happened — I\'ll turn it into cinema.</div></div>', unsafe_allow_html=True)

    tab_text, tab_voice, tab_camera = st.tabs(["✏️ Write", "🎙️ Speak", "📷 Camera"])

    with tab_text:
        memory_text = st.text_area(
            "memory",
            placeholder="What happened today? Write freely — I'll find the story in it.",
            height=200,
            label_visibility="collapsed",
        )
        if st.button("🎬 Create My Memory", use_container_width=True, key="extract_text"):
            if memory_text.strip():
                with st.spinner("Gemini is reading your memory..."):
                    st.session_state.extracted = capture.extract_memory_from_text(memory_text)
            else:
                st.warning("Write something first!")

    with tab_voice:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<p style="font-style:italic;color:#8B6F5E;">Speak freely for up to 90 seconds.</p>', unsafe_allow_html=True)
        st.markdown('<p style="font-size:.85rem;color:#8B6F5E;">Gemini Live will listen and extract your story.</p>', unsafe_allow_html=True)
        audio_input = st.audio_input("Record", label_visibility="collapsed")
        st.markdown("</div>", unsafe_allow_html=True)
        if audio_input is not None:
            if st.button("🎬 Create from Voice", use_container_width=True, key="extract_voice"):
                with st.spinner("Gemini is listening..."):
                    st.session_state.extracted = capture.extract_memory_from_audio(audio_input.getvalue(), "audio/wav")

    with tab_camera:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<p style="font-style:italic;color:#8B6F5E;">Point your camera at something meaningful.</p>', unsafe_allow_html=True)
        st.markdown('<p style="font-size:.85rem;color:#8B6F5E;">Ticket stubs, receipts, photos, souvenirs — I\'ll recognize them.</p>', unsafe_allow_html=True)
        camera_input = st.camera_input("Photo", label_visibility="collapsed")
        st.markdown("</div>", unsafe_allow_html=True)
        if camera_input is not None:
            if st.button("🎬 Create from Photo", use_container_width=True, key="extract_camera"):
                with st.spinner("Gemini is analyzing..."):
                    st.session_state.extracted = capture.trigger_memory_from_image(camera_input.getvalue(), "image/jpeg")

    # ── extracted memory ──
    if st.session_state.extracted:
        mem = st.session_state.extracted
        st.markdown(DIV, unsafe_allow_html=True)
        st.markdown('<h3 style="font-family:\'Playfair Display\',serif;color:#2C1810;">Extracted Memory</h3>', unsafe_allow_html=True)
        col1, col2 = st.columns([3, 2], gap="large")

        with col1:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown(f"**{mem.get('title', 'Untitled')}**")
            st.markdown(f'<span style="font-family:\'Playfair Display\',serif;font-style:italic;font-size:.9rem;color:#8B6F5E;">{mem.get("date", date.today().isoformat())}</span>', unsafe_allow_html=True)
            emotion = mem.get("emotion", "")
            emoji = EMOTIONS.get(emotion, "")
            if emotion:
                st.markdown(f'<span class="emotion-tag">{emoji} {emotion.capitalize()}</span>', unsafe_allow_html=True)
            st.markdown(f"\n{mem.get('summary', '')}")
            people = mem.get("people", [])
            if people:
                st.markdown(f"**People:** {', '.join(people)}")
            if mem.get("location"):
                st.markdown(f"**Location:** {mem['location']}")
            moments = mem.get("key_moments", [])
            if moments:
                st.markdown("**Key Moments:**")
                for m in moments:
                    st.markdown(f"- {m}")
            st.markdown("</div>", unsafe_allow_html=True)

        with col2:
            st.markdown('<div class="card"><h4>Generation Settings</h4>', unsafe_allow_html=True)
            style = st.selectbox("Visual Style", list(STYLES.keys()), format_func=lambda x: STYLES[x])
            char_refs = db.get_character_refs()
            if char_refs:
                st.success(f"{len(char_refs)} reference image(s) loaded")
            else:
                st.info("Upload reference photos in Settings")
            output_mode = st.radio("Output format", ["Both", "Cinematic Video", "Comic Panels"], horizontal=True, help="Both = video + comic.")
            if output_mode in ("Cinematic Video", "Both"):
                max_ext = st.slider("Video length (scenes)", 1, 6, 3, help="1 scene ≈ 8 sec")
                st.caption(f"Estimated: ~{8 + max(0, max_ext - 1) * 7}s")
            if output_mode in ("Comic Panels", "Both"):
                comic_style = st.selectbox("Comic style", ["manga", "comic", "webtoon", "graphic_novel", "pop_art"], format_func=lambda x: x.replace("_", " ").title())
                max_panels = st.slider("Number of panels", 2, 6, 4)
            st.markdown("</div>", unsafe_allow_html=True)

            scenes = mem.get("scene_prompts", [])
            st.markdown(f'<div class="card"><h4>Scenes ({len(scenes)})</h4>', unsafe_allow_html=True)
            for i, s in enumerate(scenes[:4]):
                st.markdown(f"**Scene {i+1}:** {s.get('description', str(s))[:80]}...")
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown(DIV, unsafe_allow_html=True)
        col_gen, col_save = st.columns(2)
        with col_save:
            if st.button("Save Memory (text only)", use_container_width=True, key="save_text"):
                mem["style"] = style
                st.success(f"Saved! ID: {db.save_memory(mem)[:8]}...")
        with col_gen:
            gen_labels = {"Both": "🎬 Generate Video + Comic", "Cinematic Video": "🎬 Generate Cinematic Video", "Comic Panels": "🎬 Generate Comic Panels"}
            if st.button(gen_labels[output_mode], use_container_width=True, key="generate"):
                mem["style"] = style
                updates = {}
                do_video = output_mode in ("Cinematic Video", "Both")
                do_comic = output_mode in ("Comic Panels", "Both")
                with st.status("Preparing your memory...", expanded=True) as status:
                    st.write("Gemini is refining scene prompts...")
                    char_refs = db.get_character_refs()
                    try:
                        mem["scene_prompts"] = capture.enhance_scene_prompts(mem, style)
                    except Exception:
                        pass
                    if do_video:
                        st.write("Veo 3.1 filming… Lyria 3 composing… Nano Banana painting…")
                        vid_result = vgen.generate_memory_video(mem, reference_images=char_refs if char_refs else None, style=style, max_extensions=max_ext - 1)
                        if vid_result.get("video_path"):  updates["video_path"] = vid_result["video_path"]
                        if vid_result.get("music_path"):  updates["music_path"] = vid_result["music_path"]
                        if vid_result.get("cover_path"):  updates["cover_path"] = vid_result["cover_path"]; updates["thumbnail_path"] = vid_result["cover_path"]
                    if do_comic:
                        st.write(f"Nano Banana drawing {max_panels} {comic_style.replace('_',' ').title()} panels…")
                        if not do_video: st.write("Lyria 3 composing…")
                        comic_result = vgen.generate_memory_comic(mem, comic_style=comic_style, max_panels=max_panels)
                        if comic_result.get("panel_paths"):  updates["panel_paths"] = json.dumps(comic_result["panel_paths"])
                        if not updates.get("music_path") and comic_result.get("music_path"):  updates["music_path"] = comic_result["music_path"]
                        if not updates.get("cover_path") and comic_result.get("cover_path"):   updates["cover_path"] = comic_result["cover_path"]; updates["thumbnail_path"] = comic_result["cover_path"]
                    status.update(label="Memory complete!", state="complete")
                mem.update(updates)
                st.session_state.current_memory = db.save_memory(mem)
                st.session_state.page = "gallery"
                st.rerun()


# ╔═══════════════════════════════════════════╗
# ║  PAGE 2 — GALLERY                         ║
# ╚═══════════════════════════════════════════╝
elif st.session_state.page == "gallery":
    st.markdown('<div class="hero"><div class="hero-title">Memory Gallery</div><div class="hero-sub">Every memory, preserved as cinema.</div></div>', unsafe_allow_html=True)
    memories = db.get_all_memories()

    if not memories:
        st.markdown('<div class="card" style="text-align:center;padding:3rem;"><h4>No memories yet</h4><p style="color:#8B6F5E;font-style:italic;">Go to Capture to create your first memory.</p></div>', unsafe_allow_html=True)
    else:
        c0, c1, c2, c3 = st.columns(4)
        with c0:
            st.markdown(f'<div class="stat-card"><div class="stat-icon">🎞️</div><div class="stat-value">{len(memories)}</div><div class="stat-label">Memories</div></div>', unsafe_allow_html=True)
        with c1:
            ppl = set()
            for m in memories: ppl.update(m.get("people", []))
            st.markdown(f'<div class="stat-card"><div class="stat-icon">👥</div><div class="stat-value">{len(ppl)}</div><div class="stat-label">People</div></div>', unsafe_allow_html=True)
        with c2:
            vc = sum(1 for m in memories if m.get("video_path"))
            cc = sum(1 for m in memories if m.get("panel_paths"))
            st.markdown(f'<div class="stat-card"><div class="stat-icon">🎬</div><div class="stat-value">{vc}/{cc}</div><div class="stat-label">Videos / Comics</div></div>', unsafe_allow_html=True)
        with c3:
            cal_c = sum(1 for m in memories if m.get("calendar_event_id"))
            st.markdown(f'<div class="stat-card"><div class="stat-icon">📅</div><div class="stat-value">{cal_c}</div><div class="stat-label">On Calendar</div></div>', unsafe_allow_html=True)

        st.markdown(DIV, unsafe_allow_html=True)

        for mem in memories:
            emotion = mem.get("emotion", "")
            emoji = EMOTIONS.get(emotion, "🎬")
            title = mem.get("title", "Untitled")
            mem_date = mem.get("date", "")
            with st.expander(f"{emoji} **{title}** — {mem_date}", expanded=(mem.get("id") == st.session_state.get("current_memory"))):
                col_media, col_info = st.columns([3, 2], gap="large")
                with col_media:
                    panel_list = []
                    raw = mem.get("panel_paths")
                    if raw:
                        try: panel_list = json.loads(raw)
                        except: panel_list = []
                        panel_list = [p for p in panel_list if p and os.path.exists(p)]
                    if panel_list:
                        st.markdown('<p style="font-weight:600;font-variant:small-caps;color:#2C1810;">Comic Panels</p>', unsafe_allow_html=True)
                        pc = st.columns(min(len(panel_list), 3))
                        for ip, pp in enumerate(panel_list):
                            with pc[ip % min(len(panel_list), 3)]:
                                st.image(pp, use_container_width=True)
                                st.markdown(f'<p class="pol-cap">Panel {ip+1}</p>', unsafe_allow_html=True)
                    if mem.get("video_path") and os.path.exists(mem["video_path"]):
                        st.markdown('<p style="font-weight:600;font-variant:small-caps;color:#2C1810;">Cinematic Video</p>', unsafe_allow_html=True)
                        st.video(mem["video_path"])
                    elif not panel_list:
                        if mem.get("cover_path") and os.path.exists(mem["cover_path"]):
                            st.image(mem["cover_path"], use_container_width=True)
                        else:
                            st.info("No video or panels generated yet.")
                    if mem.get("music_path") and os.path.exists(mem["music_path"]):
                        st.markdown('<p style="font-weight:600;font-variant:small-caps;color:#2C1810;">Original Soundtrack</p>', unsafe_allow_html=True)
                        with open(mem["music_path"], "rb") as f:
                            st.audio(f, format="audio/mp3")
                with col_info:
                    st.markdown(f"**{mem.get('summary', '')}**")
                    if mem.get("people"):  st.markdown(f"**People:** {', '.join(mem['people'])}")
                    if mem.get("location"): st.markdown(f"**Location:** {mem['location']}")
                    if emotion: st.markdown(f'<span class="emotion-tag">{emoji} {emotion.capitalize()}</span>', unsafe_allow_html=True)
                    moments = mem.get("key_moments", [])
                    if moments:
                        st.markdown("**Key Moments:**")
                        for m in moments: st.markdown(f"- {m}")
                    st.markdown(DIV, unsafe_allow_html=True)
                    ca, cb = st.columns(2)
                    with ca:
                        has = any([mem.get("video_path"), mem.get("music_path"), mem.get("cover_path"), mem.get("panel_paths")])
                        bl = "Upload to Drive & Calendar" if has else "Add to Calendar"
                        if st.button(bl, key=f"cal_{mem['id']}", use_container_width=True):
                            try:
                                dl = None
                                if has:
                                    with st.spinner("Uploading to Drive..."): dl = cal.upload_memory_to_drive(mem)
                                eid = cal.add_memory_event(mem, drive_links=dl)
                                if eid:
                                    db.update_memory(mem["id"], {"calendar_event_id": eid})
                                    if dl and dl.get("folder_link"): st.success(f"Saved! [Open folder]({dl['folder_link']})")
                                    else: st.success("Added to Calendar!")
                                else: st.error("Connect calendar in Settings first.")
                            except Exception as e: st.error(f"Error: {e}")
                    with cb:
                        if st.button("Delete", key=f"del_{mem['id']}", use_container_width=True):
                            db.delete_memory(mem["id"]); st.rerun()


# ╔═══════════════════════════════════════════╗
# ║  PAGE 3 — CALENDAR                        ║
# ╚═══════════════════════════════════════════╝
elif st.session_state.page == "calendar":
    st.markdown('<div class="hero"><div class="hero-title">Memory Calendar</div><div class="hero-sub">Memories resurface exactly when they matter.</div></div>', unsafe_allow_html=True)
    col_l, col_r = st.columns(2, gap="large")

    with col_l:
        st.markdown('<div class="card"><h4>📮 On This Day</h4>', unsafe_allow_html=True)
        today = date.today()
        otd = db.get_on_this_day(today.month, today.day)
        if otd:
            for mem in otd:
                emo = EMOTIONS.get(mem.get("emotion", ""), "🎬")
                st.markdown(f"**{emo} {mem.get('title')}** ({mem.get('date')})")
                st.markdown(f"*{mem.get('summary', '')}*")
                if mem.get("cover_path") and os.path.exists(mem["cover_path"]): st.image(mem["cover_path"], width=300)
                st.markdown(DIV, unsafe_allow_html=True)
        else:
            st.markdown('<p style="font-family:\'Playfair Display\',serif;font-style:italic;color:#8B6F5E;">This page is waiting for its story...</p><div style="text-align:center;opacity:.2;font-size:3rem;margin:1rem 0;">🎞️</div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with col_r:
        st.markdown('<div class="card"><h4>Find a Memory</h4>', unsafe_allow_html=True)
        st.markdown('<p style="font-style:italic;font-size:.85rem;color:#8B6F5E;">Pick a date</p>', unsafe_allow_html=True)
        ld = st.date_input("date", value=date.today(), label_visibility="collapsed")
        if st.button("Search", key="date_search", use_container_width=True):
            res = db.get_memories_for_date(ld.isoformat())
            if res:
                for mem in res:
                    st.markdown(f"**{EMOTIONS.get(mem.get('emotion',''),'🎬')} {mem.get('title')}**")
                    st.markdown(f"*{mem.get('summary', '')}*")
            else: st.info(f"No memories for {ld.isoformat()}")
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(DIV, unsafe_allow_html=True)

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown('<h4>📅 Google Calendar + 💾 Drive Sync</h4>', unsafe_allow_html=True)
    st.markdown('<p style="font-size:.85rem;font-style:italic;color:#8B6F5E;">Your memories are automatically added to Google Calendar and backed up to Drive.</p>', unsafe_allow_html=True)
    if cal.is_calendar_connected():
        st.markdown('<span class="pill pill-green">📅 Calendar: Connected</span><span class="pill pill-green">💾 Drive: Connected</span>', unsafe_allow_html=True)
        evts = cal.get_upcoming_memory_events(5)
        if evts:
            st.markdown("**Upcoming:**")
            for ev in evts: st.markdown(f"- {ev.get('summary','Event')} — {ev.get('start',{}).get('date','')}")
        else: st.markdown('<p style="font-style:italic;color:#8B6F5E;">No upcoming memory events.</p>', unsafe_allow_html=True)
        if st.button("Re-authenticate", key="reauth_cal"):
            if os.path.exists("token.json"): os.remove("token.json")
            try: cal.connect_calendar(); st.success("Re-authenticated!"); st.rerun()
            except Exception as e: st.error(f"OAuth failed: {e}")
    else:
        st.markdown('<span class="pill pill-amber">📅 Calendar: Not connected</span><span class="pill pill-amber">💾 Drive: Not connected</span>', unsafe_allow_html=True)
        if st.button("Connect Google Calendar + Drive", key="connect_cal", use_container_width=True):
            try: cal.connect_calendar(); st.success("Connected!"); st.rerun()
            except FileNotFoundError as e: st.error(str(e))
            except Exception as e: st.error(f"OAuth failed: {e}")
    st.markdown("</div>", unsafe_allow_html=True)


# ╔═══════════════════════════════════════════╗
# ║  PAGE 4 — SETTINGS                        ║
# ╚═══════════════════════════════════════════╝
elif st.session_state.page == "settings":
    st.markdown('<div class="hero"><div class="hero-title">Settings</div><div class="hero-sub">Configure your Memoire.</div></div>', unsafe_allow_html=True)
    col_l, col_r = st.columns(2, gap="large")

    with col_l:
        st.markdown('<div class="card"><h4>Character Reference Photos</h4>', unsafe_allow_html=True)
        st.markdown('<p style="font-style:italic;font-size:.9rem;color:#8B6F5E;">Upload 2–3 selfies so Veo can keep you consistent across all scenes.</p>', unsafe_allow_html=True)
        current_refs = db.get_character_refs()
        if current_refs:
            st.success(f"{len(current_refs)} reference image(s) loaded")
            rc = st.columns(len(current_refs))
            for i, rp in enumerate(current_refs):
                if os.path.exists(rp):
                    with rc[i]: st.image(rp, width=120)
            if st.button("Clear References", key="clear_refs"): db.clear_character_refs(); st.rerun()
        uploaded = st.file_uploader("Upload reference photos", type=["jpg", "jpeg", "png"], accept_multiple_files=True, key="ref_upload")
        if uploaded:
            for f in uploaded[:3]:
                sp = os.path.join("assets", f"ref_{f.name}")
                with open(sp, "wb") as out: out.write(f.getvalue())
                db.save_character_ref(sp)
            st.success(f"Saved {len(uploaded[:3])} image(s)"); st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    with col_r:
        st.markdown('<div class="card"><h4>Default Style</h4>', unsafe_allow_html=True)
        st.markdown('<p style="font-style:italic;font-size:.85rem;color:#8B6F5E;">Default visual style</p>', unsafe_allow_html=True)
        cs = db.get_setting("default_style", "movie_trailer")
        ns = st.selectbox("style", list(STYLES.keys()), format_func=lambda x: STYLES[x], index=list(STYLES.keys()).index(cs), label_visibility="collapsed")
        if ns != cs: db.set_setting("default_style", ns); st.success(f"Set to {STYLES[ns]}")
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="card"><h4>API Status</h4>', unsafe_allow_html=True)
        ak = os.getenv("GOOGLE_API_KEY")
        if ak: st.markdown(f'<span class="pill pill-amber">🔑 API Key: ...{ak[-6:]}</span>', unsafe_allow_html=True)
        else: st.error("GOOGLE_API_KEY not found in .env")
        conn = cal.is_calendar_connected()
        st.markdown(f'<span class="pill {"pill-green" if conn else "pill-amber"}">📅 Calendar + Drive: {"Connected" if conn else "Not connected"}</span>', unsafe_allow_html=True)
        st.markdown('<span class="pill pill-green">🤖 Gemini Live: Active</span>', unsafe_allow_html=True)
        st.markdown(f'<p style="margin-top:.8rem;font-size:.85rem;color:#8B6F5E;"><b>Character Refs:</b> {len(current_refs)} loaded</p>', unsafe_allow_html=True)
        st.markdown(f'<p style="font-size:.85rem;color:#8B6F5E;"><b>Total Memories:</b> {len(db.get_all_memories())}</p>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="card"><h4>Models Used</h4>', unsafe_allow_html=True)
        st.markdown("""
| Model | Purpose |
|-------|---------|
| **Gemini 2.5 Flash** | Memory extraction, scene writing |
| **Veo 3.1** | Cinematic video with character consistency |
| **Lyria 3 Clip** | Custom soundtrack composition |
| **Nano Banana** | Cover art & style references |
| **Gemini Live API** | Voice memory capture |
""")
        st.markdown("</div>", unsafe_allow_html=True)
