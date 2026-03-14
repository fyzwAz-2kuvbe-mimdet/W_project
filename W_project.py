# ============================================================
# W_project.py
# 초등학생 글짓기 서포트 프로그램
# 이스 이터널 스타일 NPC 대화 + 화이트/스카이블루 UI
# 레이아웃: 왼쪽=대화창(상단에 형식/문체 선택) / 오른쪽=선택창+입력창
# ============================================================

import streamlit as st
import random
import firebase_admin
from firebase_admin import credentials, firestore
from google import genai
import datetime

# ── 상수 ──────────────────────────────────────────────────────
GEMINI_MODEL = "gemini-2.0-flash"

TARGET_AGES = ["4~7세", "7~9세", "10~13세", "14~16세", "직접 입력"]

PLOT_TYPES = ["성장과 모험", "결점의 재발견", "반복과 확장", "부메랑 효과", "비밀공유와 들통"]

TARGET_LENGTHS = {
    "짧은 글 (약 3,000자)":  3000,
    "일반 글 (약 5,000자)":  5000,
    "긴 글 (약 7,500자)":    7500,
    "장편 (약 10,000자)":   10000,
}

# ── 외부 데이터 파일 로딩 ────────────────────────────────────
import json
from pathlib import Path

# Streamlit Cloud / 로컬 모두 동작하는 경로
DATA_DIR = Path(__file__).parent / "data"

# ── Firebase ──────────────────────────────────────────────────
@st.cache_resource
def init_firebase():
    if firebase_admin._apps:
        return firebase_admin.get_app()
    cfg = dict(st.secrets["firebase"])
    cfg["private_key"] = cfg["private_key"].replace("\\n", "\n")
    return firebase_admin.initialize_app(credentials.Certificate(cfg))

@st.cache_resource
def get_db():
    init_firebase()
    return firestore.client()

@st.cache_resource
def get_gemini_client():
    return genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

def save_to_firestore(session_id, stage, user_input, ai_response):
    try:
        get_db().collection("stories").document(session_id).set({
            "session_id": session_id,
            "last_updated": datetime.datetime.now(),
            "stage": stage,
            "history": firestore.ArrayUnion([{
                "stage": stage, "user": user_input,
                "ai": ai_response, "time": datetime.datetime.now().isoformat()
            }])
        }, merge=True)
    except Exception as e:
        st.warning(f"저장 오류: {e}")


def _load_json(filename):
    """JSON 파일 로딩 — 실패 시 예외를 그대로 올려서 원인을 노출"""
    path = DATA_DIR / filename
    if not path.exists():
        raise FileNotFoundError(
            f"[데이터 파일 없음] {path}\n"
            f"프로젝트 루트의 data/ 폴더에 {filename} 파일이 있어야 합니다."
        )
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def _load_all_data():
    """앱 시작 시 3개 파일을 모두 로딩"""
    import sys
    try:
        author_styles = _load_json("author_styles.json")
        npc_responses = _load_json("npc_responses.json")
        keywords      = _load_json("keywords.json")
        return author_styles, npc_responses, keywords
    except Exception as e:
        # Streamlit이 아직 초기화 전일 수 있으므로 print + st 둘 다 시도
        print(f"[DATA LOAD ERROR] {e}", file=sys.stderr)
        try:
            st.error(f"데이터 파일 로딩 실패: {e}")
            st.info(
                "💡 data/ 폴더에 3개 JSON 파일이 있는지 확인하세요.\n"
                "author_styles.json / npc_responses.json / keywords.json"
            )
            st.stop()
        except Exception:
            raise

# 앱 시작 시 로딩
_data = _load_all_data()
AUTHOR_STYLES  = _data[0] if _data else {}
NPC_RESPONSES  = _data[1] if _data else {}
KEYWORDS_POOL  = _data[2] if _data else {}

# ── UI 테마 ───────────────────────────────────────────────────
THEME = {
    "bg":         "#f0f8ff",
    "card":       "#ffffff",
    "card_bg":    "#e3f2fd",
    "border":     "#90caf9",
    "primary":    "#2196f3",
    "primary_dk": "#1565c0",
    "text":       "#1a237e",
    "text_muted": "#90caf9",
    "danger":     "#ef5350",
    "fire":       "#ff7043",
}

# ── 글쓰기 형식 ────────────────────────────────────────────────
WRITING_FORMATS = {
    "소설":     ("📖", "인물과 사건이 있는 이야기"),
    "에세이":   ("✏️", "내 생각과 경험을 솔직하게"),
    "시":       ("🌸", "짧고 아름다운 언어로"),
    "시나리오": ("🎬", "대사와 장면으로 표현"),
}

# ── 단계 정의 ─────────────────────────────────────────────────
STAGES       = ["기분탐색", "주제헌팅", "기", "승", "전", "결", "글생성", "완성"]
STAGE_ICONS  = ["💬", "🎯", "🌱", "🚀", "⚡", "🌈", "✨", "🌟"]
STAGE_LABELS = ["기분 탐색", "주제 헌팅", "기(起)", "승(承)", "전(轉)", "결(結)", "글 생성", "완성!"]

NPC_CHARACTERS = {
    "루나":   {"emoji": "🧝‍♀️", "color": "#2196f3", "role": "안내자"},
    "도토리": {"emoji": "🐿️",  "color": "#ff7043", "role": "응원단"},
    "글벌레": {"emoji": "📚",   "color": "#26a69a", "role": "박사"},
}

CHAR_LIMITS = {
    "기분탐색": 50, "주제헌팅": 30,
    "기": 100, "승": 150, "전": 150, "결": 100,
}

# ── 단계 질문 ─────────────────────────────────────────────────
STAGE_QUESTIONS = {
    "기": {"question": "주인공은 누구인가요? 🐰"},
    "승": {"question": "어떤 신나는 일이 생겼나요? 🚀"},
    "전": {"question": "갑자기 어떤 위기가 찾아왔나요? ⚡"},
    "결": {"question": "어떻게 문제를 해결했나요? 🌈"},
}


# 기본 fallback 응답 (JSON 파일 로딩 실패 또는 키 불일치 시 사용)
_FALLBACK_RESPONSES = {
    "기분탐색": [{"npc": "루나",   "message": "오늘 기분이 전해졌어! 😊",        "next_question": "어떤 이야기를 써볼까?"}],
    "주제헌팅": [{"npc": "글벌레", "message": "멋진 주제야! 📚",                  "next_question": "주인공은 누구인가요? 🐰"}],
    "기":       [{"npc": "도토리", "feedback": "이야기가 시작됐어! 🌱",           "next_question": "어떤 신나는 일이 생겼나요? 🚀"}],
    "승":       [{"npc": "글벌레", "feedback": "이야기가 펼쳐지네! 🚀",           "next_question": "갑자기 어떤 위기가 찾아왔나요? ⚡"}],
    "전":       [{"npc": "도토리", "feedback": "긴장감 넘쳐! ⚡",                 "next_question": "어떻게 문제를 해결했나요? 🌈"}],
    "결":       [{"npc": "루나",   "feedback": "완벽한 마무리야! 👏",             "full_review": "정말 대단해!", "badge": "글짓기 영웅"}],
}
_FALLBACK_KEYWORDS = {
    "기분탐색": [["오늘 있었던 일", "친구와의 순간", "떠오른 상상", "마음속 소원"]],
    "주제헌팅": [["토끼 소녀 달이", "용감한 소년 하늘이", "작은 마법사 별이", "강아지 뭉치"]],
    "기":       [["보물 지도 발견", "괴물이 나타남", "새 친구를 만남", "마법 문 발견"]],
    "승":       [["친구가 위험", "보물이 사라짐", "길을 잃음", "마법이 풀림"]],
    "전":       [["모두 힘을 합침", "마법의 힘으로", "용기를 냄", "친구의 도움"]],
    "결":       [["모두 행복하게", "새 모험 시작", "소중한 것 회복", "진짜 우정"]],
}

def get_stage_response(stage, user_input=None):
    """외부 JSON 파일에서 해당 단계의 NPC 응답과 키워드를 랜덤 선택"""
    responses = NPC_RESPONSES.get(stage) or _FALLBACK_RESPONSES.get(stage, [{"npc": "루나", "message": "잘 했어! 😊"}])
    kw_pool   = KEYWORDS_POOL.get(stage) or _FALLBACK_KEYWORDS.get(stage, [["계속해봐요"]])
    resp = random.choice(responses).copy()
    resp["keywords"] = random.choice(kw_pool) if kw_pool else []
    return resp


def build_writing_request(context):
    """Gemini API에 보낼 JSON 요청 객체를 반환"""
    fmt        = context.get("format", "소설")
    style      = context.get("style", "")
    age        = context.get("age", "")
    age_custom = context.get("age_custom", "")
    plot       = context.get("plot", "")
    length     = context.get("length", 3000)

    # 작가 스타일 정보 (장르별 딕셔너리에서 조회)
    style_info = AUTHOR_STYLES.get(fmt, {}).get(style, {})
    role       = style_info.get("role", "경험 많은 작가")
    tone       = style_info.get("tone", "")
    desc       = style_info.get("desc", "")
    style_line = f"- 작가 스타일: {style} / 역할: {role} / 톤: {tone} / 특징: {desc}" if style else ""

    # 대상 연령
    age_target = age_custom if age == "직접 입력" and age_custom else age
    age_line   = f"- 대상 독자: {age_target}" if age_target else "- 초등학생이 읽기 쉬운 언어 사용"

    # 플롯 유형
    plot_line  = f"- 플롯 유형: {plot}" if plot else ""

    prompt_text = (
        f"너는 {role}야.\n"
        f"아래 기승전결 메모를 바탕으로 {length}자 내외의 완성된 {fmt}을 써줘.\n\n"
        f"[주제] {context.get('topic', '')}\n"
        f"[기(起) - 발단] {context.get('ki', '')}\n"
        f"[승(承) - 전개] {context.get('seung', '')}\n"
        f"[전(轉) - 위기] {context.get('jeon', '')}\n"
        f"[결(結) - 결말] {context.get('gyeol', '')}\n\n"
        f"조건:\n"
        + (f"{style_line}\n" if style_line else "")
        + f"{age_line}\n"
        + (f"{plot_line}\n" if plot_line else "")
        + f"- {fmt} 형식에 맞게 작성\n"
        + f"- {length}자 내외"
    )

    request_body = {
        "model": GEMINI_MODEL,
        "contents": [{"parts": [{"text": prompt_text}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "object",
                "properties": {
                    "title":   {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["title", "content"],
            },
            "maxOutputTokens": max(4096, context.get("length", 3000) // 2),
        },
    }
    return request_body


def _show_request_expander(request_body, expanded=True):
    """오류 시 실제 API 요청 내용을 그대로 보여주는 UI"""
    import json
    with st.expander("📋 API 요청 내용 / Gemini에 직접 입력하기", expanded=expanded):
        c1 = THEME["primary_dk"]
        c2 = THEME["primary"]
        st.markdown(
            f'<div style="color:{c1};font-size:12px;margin-bottom:8px;">' +
            '아래는 실제로 전송된 API 요청이에요. 프롬프트 텍스트를 복사해서 ' +
            f'<a href="https://gemini.google.com" target="_blank" ' +
            f'style="color:{c2};font-weight:700;">gemini.google.com</a>' +
            ' 에 직접 붙여넣어 보세요! 🚀</div>',
            unsafe_allow_html=True
        )
        # 전체 요청 JSON
        st.markdown(f'<div style="color:{c1};font-size:11px;font-weight:600;margin-top:8px;">🔷 전체 요청 (JSON)</div>', unsafe_allow_html=True)
        st.code(json.dumps(request_body, ensure_ascii=False, indent=2), language="json")
        # 프롬프트 텍스트만 따로 표시
        try:
            prompt_text = request_body["contents"][0]["parts"][0]["text"]
            st.markdown(f'<div style="color:{c1};font-size:11px;font-weight:600;margin-top:8px;">🔶 프롬프트 텍스트만 보기</div>', unsafe_allow_html=True)
            st.code(prompt_text, language=None)
        except Exception:
            pass


def call_gemini_writing(request_body):
    import json
    try:
        prompt_text = request_body["contents"][0]["parts"][0]["text"]
        response = get_gemini_client().models.generate_content(
            model   = request_body["model"],
            contents= prompt_text,
            config  = {
                "response_mime_type": "application/json",
                "response_schema": request_body["generationConfig"]["responseSchema"],
                "max_output_tokens": request_body["generationConfig"]["maxOutputTokens"],
            },
        )
        usage = getattr(response, "usage_metadata", None)
        if usage:
            st.session_state.token_in  = st.session_state.get("token_in",  0) + getattr(usage, "prompt_token_count",     0)
            st.session_state.token_out = st.session_state.get("token_out", 0) + getattr(usage, "candidates_token_count", 0)

        data    = json.loads(response.text)
        title   = data.get("title", "")
        content = data.get("content", "")
        return f"# {title}\n\n{content}" if title else content

    except Exception as e:
        err_str = str(e)
        is_quota = "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower()

        if is_quota:
            st.error("⏱️ API 사용량 한도를 초과했어요. 아래 요청 내용을 확인하세요!")
        else:
            st.error(f"글 생성 오류: {e}")

        _show_request_expander(request_body, expanded=True)
        return ""


# ── Session State ─────────────────────────────────────────────
def init_session():
    defaults = {
        "stage_idx": 0,
        "chat_history": [],
        "context": {"format": "", "style": "", "age": "", "plot": "", "length": 3000},
        "suggested_keywords": [],
        "input_text": "",
        "session_id": datetime.datetime.now().strftime("%Y%m%d_%H%M%S"),
        "npc_intro_done": False,
        "writing_text": "",
        "writing_done": False,
        "setup_open": True,   # 설정 패널 열림/닫힘 상태
        "token_in": 0,        # 누적 입력 토큰
        "token_out": 0,       # 누적 출력 토큰
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def add_npc_message(npc_name, message, keywords=None, question=None):
    st.session_state.chat_history.append({
        "type": "npc", "npc": npc_name, "message": message,
        "keywords": keywords or [], "question": question or "",
    })
    if keywords:
        st.session_state.suggested_keywords = keywords


def add_player_message(text):
    st.session_state.chat_history.append({"type": "player", "message": text})


# ── 진행 바 ───────────────────────────────────────────────────
def render_progress_bar():
    idx      = st.session_state.stage_idx
    progress = min(min(idx, 6) / 6, 1.0)
    fmt      = st.session_state.context.get("format", "")
    style    = st.session_state.context.get("style", "")

    # 단계 라벨 (Python으로 생성해서 f-string 중첩 방지)
    label_parts = []
    display = list(zip(STAGE_ICONS[:6] + [STAGE_ICONS[7]], STAGE_LABELS[:6] + [STAGE_LABELS[7]]))
    for i, (icon, label) in enumerate(display):
        color = THEME["primary"] if idx >= i else "#b0bec5"
        label_parts.append(
            f'<span style="font-size:11px;color:{color};">{icon}{label}</span>'
        )
    labels_html = "".join(label_parts)

    # 형식/문체 뱃지 (Python 조건문으로 생성)
    badge_parts = []
    if fmt:
        fmt_icon = WRITING_FORMATS[fmt][0]
        badge_parts.append(
            f'<span style="background:{THEME["card_bg"]};color:{THEME["primary"]};'
            f'font-size:11px;padding:2px 10px;border-radius:20px;'
            f'border:1px solid {THEME["border"]};">{fmt_icon} {fmt}</span>'
        )
    if style:
        badge_parts.append(
            f'<span style="background:{THEME["card_bg"]};color:{THEME["primary_dk"]};'
            f'font-size:11px;padding:2px 10px;border-radius:20px;'
            f'border:1px solid {THEME["border"]};">✍️ {style}</span>'
        )
    badge_html = ""
    if badge_parts:
        inner = "".join(badge_parts)
        badge_html = (
            f'<div style="margin-top:6px;display:flex;gap:8px;flex-wrap:wrap;">'
            f'{inner}</div>'
        )

    st.markdown(
        f'<div style="background:#ffffff;padding:12px 16px;border-radius:12px;'
        f'margin-bottom:16px;border:1px solid {THEME["border"]};box-shadow:0 2px 8px #e3f2fd;">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">'
        f'<span style="color:{THEME["primary_dk"]};font-size:13px;font-weight:600;">✍️ 글짓기 여정</span>'
        f'<span style="color:{THEME["primary"]};font-size:13px;font-weight:700;">{int(progress*100)}%</span>'
        f'</div>'
        f'<div style="background:#e3f2fd;border-radius:8px;height:10px;overflow:hidden;">'
        f'<div style="background:linear-gradient(90deg,#64b5f6,#2196f3);'
        f'width:{progress*100}%;height:100%;border-radius:8px;"></div></div>'
        f'<div style="display:flex;justify-content:space-between;margin-top:8px;">'
        f'{labels_html}</div>'
        f'{badge_html}'
        f'</div>',
        unsafe_allow_html=True
    )


# ── 설정 패널 (오른쪽 컬럼 상단) ───────────────────────────
def render_setup_panel():
    ctx   = st.session_state.context
    fmt   = ctx.get("format", "")
    style = ctx.get("style", "")
    age   = ctx.get("age", "")
    plot  = ctx.get("plot", "")
    length_label = next((k for k, v in TARGET_LENGTHS.items() if v == ctx.get("length", 3000)), "")

    # expander 라벨
    if fmt:
        fmt_icon = WRITING_FORMATS[fmt][0]
        parts = [f"{fmt_icon} {fmt}"]
        if style: parts.append(style)
        if age:   parts.append(age)
        if plot:  parts.append(plot)
        label = "🎨 설정완료: " + " · ".join(parts)
    else:
        label = "🎨 글쓰기 설정을 해봐요"

    with st.expander(label, expanded=st.session_state.setup_open):

        # ── Step 1: 형식 ──────────────────────────────────────
        st.markdown(
            f'<div style="color:{THEME["primary"]};font-size:12px;font-weight:600;margin-bottom:6px;">📌 형식 선택</div>',
            unsafe_allow_html=True
        )
        fmt_cols = st.columns(4)
        for i, (f_name, (f_icon, f_desc)) in enumerate(WRITING_FORMATS.items()):
            with fmt_cols[i]:
                is_sel = fmt == f_name
                btn_label = f"{f_icon} {f_name} ✅" if is_sel else f"{f_icon} {f_name}"
                if st.button(btn_label, key=f"fmt_{f_name}", use_container_width=True):
                    ctx["format"] = f_name
                    ctx["style"]  = ""
                    st.session_state.setup_open = True
                    st.rerun()
                st.markdown(
                    f'<div style="text-align:center;color:{THEME["text_muted"]};font-size:10px;margin-top:-4px;">{f_desc}</div>',
                    unsafe_allow_html=True
                )

        # ── Step 2: 작가 스타일 (형식 선택 후 해당 장르 작가만 표시) ──
        st.markdown(
            f'<div style="color:{THEME["primary"]};font-size:12px;font-weight:600;margin-top:12px;margin-bottom:6px;">' +
            f'🖋️ 작가 스타일 <span style="color:{THEME["text_muted"]};font-size:10px;font-weight:400;">(선택 안 해도 됩니다)</span></div>',
            unsafe_allow_html=True
        )
        if fmt:
            genre_styles = AUTHOR_STYLES.get(fmt, {})
            if genre_styles:
                # 형식이 바뀌면 스타일 초기화
                if style and style not in genre_styles:
                    ctx["style"] = ""
                    style = ""
                s_cols = st.columns(4)
                for i, (s_name, info) in enumerate(genre_styles.items()):
                    with s_cols[i % 4]:
                        is_sel = style == s_name
                        btn_label = f"{s_name} ✅" if is_sel else s_name
                        if st.button(btn_label, key=f"sty_{fmt}_{s_name}", use_container_width=True):
                            ctx["style"] = "" if is_sel else s_name
                            st.session_state.setup_open = True
                            st.rerun()
                        st.markdown(
                            f'<div style="text-align:center;color:{THEME["text_muted"]};font-size:10px;margin-top:-4px;line-height:1.3;">{info["tone"]}</div>',
                            unsafe_allow_html=True
                        )
        else:
            st.markdown(
                f'<div style="color:{THEME["text_muted"]};font-size:11px;">📌 먼저 형식을 선택하면 해당 장르 작가가 표시돼요!</div>',
                unsafe_allow_html=True
            )

        # ── Step 3: 대상 연령 ─────────────────────────────────
        st.markdown(
            f'<div style="color:{THEME["primary"]};font-size:12px;font-weight:600;margin-top:12px;margin-bottom:6px;">👦 대상 연령</div>',
            unsafe_allow_html=True
        )
        age_cols = st.columns(5)
        for i, a in enumerate(TARGET_AGES):
            with age_cols[i]:
                is_sel = age == a
                if st.button(f"{a} ✅" if is_sel else a, key=f"age_{a}", use_container_width=True):
                    ctx["age"] = "" if is_sel else a
                    st.session_state.setup_open = True
                    st.rerun()
        # 직접 입력
        if age == "직접 입력":
            custom_age = st.text_input("연령 직접 입력", value=ctx.get("age_custom", ""), placeholder="예: 8세, 중학생", key="age_custom_input")
            if custom_age:
                ctx["age_custom"] = custom_age

        # ── Step 4: 플롯 유형 ─────────────────────────────────
        st.markdown(
            f'<div style="color:{THEME["primary"]};font-size:12px;font-weight:600;margin-top:12px;margin-bottom:6px;">📐 플롯 유형 <span style="color:{THEME["text_muted"]};font-size:10px;font-weight:400;">(선택 안 해도 됩니다)</span></div>',
            unsafe_allow_html=True
        )
        plot_cols = st.columns(5)
        for i, p in enumerate(PLOT_TYPES):
            with plot_cols[i]:
                is_sel = plot == p
                if st.button(f"{p} ✅" if is_sel else p, key=f"plot_{p}", use_container_width=True):
                    ctx["plot"] = "" if is_sel else p
                    st.session_state.setup_open = True
                    st.rerun()

        # ── Step 5: 글 길이 ───────────────────────────────────
        st.markdown(
            f'<div style="color:{THEME["primary"]};font-size:12px;font-weight:600;margin-top:12px;margin-bottom:6px;">📏 글 길이</div>',
            unsafe_allow_html=True
        )
        len_cols = st.columns(4)
        for i, (l_name, l_val) in enumerate(TARGET_LENGTHS.items()):
            with len_cols[i]:
                is_sel = ctx.get("length", 3000) == l_val
                if st.button(f"{l_name} ✅" if is_sel else l_name, key=f"len_{l_name}", use_container_width=True):
                    ctx["length"] = l_val
                    st.session_state.setup_open = True
                    st.rerun()

        # ── 확정 버튼 ─────────────────────────────────────────
        if fmt:
            st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
            fmt_icon = WRITING_FORMATS[fmt][0]
            btn_txt  = f"✅ {fmt_icon} {fmt}" + (f" · {style}" if style else "") + " 로 시작!"
            if st.button(btn_txt, use_container_width=True, type="primary", key="setup_confirm"):
                st.session_state.setup_open = False
                st.rerun()


# ── 대화창 ────────────────────────────────────────────────────
def render_one_message(msg):
    """메시지 하나를 렌더링하는 헬퍼"""
    if msg["type"] == "npc":
        npc = NPC_CHARACTERS.get(msg["npc"], NPC_CHARACTERS["루나"])
        q_html = (
            f'<div style="color:{THEME["primary"]};font-size:12px;'
            f'margin-top:6px;font-style:italic;">❓ {msg["question"]}</div>'
            if msg.get("question") else ""
        )
        st.markdown(
            f'<div style="background:#ffffff;border:1.5px solid {THEME["border"]};'
            f'border-radius:12px;padding:12px 14px;margin:6px 0;'
            f'box-shadow:0 1px 4px #e3f2fd;">'
            f'<div style="color:{THEME["primary"]};font-size:12px;'
            f'font-weight:700;margin-bottom:4px;">'
            f'{npc["emoji"]} {msg["npc"]} '
            f'<span style="font-size:10px;color:{THEME["text_muted"]};">({npc["role"]})</span>'
            f'</div>'
            f'<div style="color:{THEME["text"]};font-size:14px;line-height:1.6;">'
            f'{msg["message"]}</div>'
            f'{q_html}</div>',
            unsafe_allow_html=True
        )
    elif msg["type"] == "player":
        st.markdown(
            f'<div style="display:flex;justify-content:flex-end;margin:6px 0;">'
            f'<div style="background:#e3f2fd;border-radius:12px 12px 2px 12px;'
            f'padding:8px 12px;max-width:90%;border:1px solid {THEME["border"]};">'
            f'<div style="color:{THEME["primary"]};font-size:11px;'
            f'font-weight:600;margin-bottom:2px;">🧒 나</div>'
            f'<div style="color:{THEME["text"]};font-size:13px;">'
            f'{msg["message"]}</div></div></div>',
            unsafe_allow_html=True
        )


def render_chat_history():
    """
    최신 메시지가 항상 보이도록 역순으로 렌더링합니다.
    st.container(height=)는 위에서부터 채우므로,
    메시지를 뒤집어서 넣으면 최신 메시지가 맨 위(=화면에서 맨 아래)에 옵니다.
    CSS flex-direction:column-reverse 와 같은 효과입니다.
    """
    history = st.session_state.chat_history
    for msg in reversed(history):
        render_one_message(msg)


# ── 스탯 카드 ─────────────────────────────────────────────────
def render_stats_cards():
    stage       = STAGES[st.session_state.stage_idx]
    char_limit  = CHAR_LIMITS.get(stage, 100)
    current_len = len(st.session_state.input_text)
    streak      = len([m for m in st.session_state.chat_history if m["type"] == "player"])
    token_in    = st.session_state.get("token_in", 0)
    token_out   = st.session_state.get("token_out", 0)
    col1, col2  = st.columns(2)
    with col1:
        st.markdown(
            f'<div style="background:{THEME["card_bg"]};border-radius:10px;padding:10px;'
            f'text-align:center;border:1px solid {THEME["border"]};margin-bottom:8px;">'
            f'<div style="color:{THEME["text_muted"]};font-size:10px;">현재 단계</div>'
            f'<div style="color:{THEME["primary"]};font-size:16px;font-weight:700;">'
            f'{STAGE_ICONS[st.session_state.stage_idx]}</div>'
            f'<div style="color:{THEME["primary_dk"]};font-size:11px;">'
            f'{STAGE_LABELS[st.session_state.stage_idx]}</div></div>',
            unsafe_allow_html=True
        )
    with col2:
        color = THEME["danger"] if current_len > char_limit else THEME["primary"]
        st.markdown(
            f'<div style="background:{THEME["card_bg"]};border-radius:10px;padding:10px;'
            f'text-align:center;border:1px solid {THEME["border"]};margin-bottom:8px;">'
            f'<div style="color:{THEME["text_muted"]};font-size:10px;">글자 수 / 연속</div>'
            f'<div style="color:{color};font-size:16px;font-weight:700;">{current_len}자</div>'
            f'<div style="color:#b0bec5;font-size:11px;">/{char_limit}자 권장 · {streak}🔥</div>'
            f'</div>',
            unsafe_allow_html=True
        )
    # 토큰 사용량 카드 (2컬럼 전체 너비)
    total_token = token_in + token_out
    st.markdown(
        f'<div style="background:{THEME["card_bg"]};border-radius:10px;padding:8px 12px;'
        f'border:1px solid {THEME["border"]};margin-bottom:8px;'
        f'display:flex;justify-content:space-between;align-items:center;">'
        f'<span style="color:{THEME["text_muted"]};font-size:10px;">🔢 글 생성 토큰</span>'
        f'<span style="color:{THEME["primary"]};font-size:11px;font-weight:600;">'
        f'입력 {token_in:,} / 출력 {token_out:,} = 총 {total_token:,}</span>'
        f'</div>',
        unsafe_allow_html=True
    )


# ── 키워드 버튼 ───────────────────────────────────────────────
def render_keyword_buttons():
    if not st.session_state.suggested_keywords:
        return
    st.markdown(
        f'<div style="color:{THEME["primary"]};font-size:12px;margin:4px 0 6px;">'
        f'💡 눌러서 입력창에 추가해요!</div>',
        unsafe_allow_html=True
    )
    kws  = st.session_state.suggested_keywords[:4]
    row1 = st.columns(2)
    row2 = st.columns(2)
    grid = [row1[0], row1[1], row2[0], row2[1]]
    for i, kw in enumerate(kws):
        with grid[i]:
            if st.button(f"✨ {kw}", key=f"kw_{st.session_state.stage_idx}_{i}_{kw}", use_container_width=True):
                cur = st.session_state.input_text.strip()
                st.session_state.input_text = (cur + " " + kw) if cur else kw
                st.rerun()


# ── 단계 처리 ─────────────────────────────────────────────────
def process_stage(user_input):
    stage   = STAGES[st.session_state.stage_idx]
    context = st.session_state.context

    # 중간 단계: data 풀에서 즉시 선택 (API 호출 없음)
    result = get_stage_response(stage, user_input)

    stage_map = {"기분탐색": 1, "주제헌팅": 2, "기": 3, "승": 4, "전": 5, "결": 6}

    if stage == "기분탐색":
        context["mood"] = user_input
        add_npc_message(result.get("npc", "루나"), result.get("message", ""),
                        result.get("keywords", []), result.get("next_question", ""))
        st.session_state.stage_idx = 1

    elif stage == "주제헌팅":
        context["topic"] = user_input
        add_npc_message(result.get("npc", "글벌레"),
                        f"주제 확정! 『{user_input}』 {result.get('message', '')}",
                        result.get("keywords", []), result.get("next_question", ""))
        st.session_state.stage_idx = 2

    elif stage == "기":
        context["ki"] = user_input
        add_npc_message(result.get("npc", "도토리"), result.get("feedback", "기(起) 완성!"),
                        result.get("keywords", []), result.get("next_question", ""))
        st.session_state.stage_idx = 3

    elif stage == "승":
        context["seung"] = user_input
        add_npc_message(result.get("npc", "글벌레"), result.get("feedback", "승(承) 완성!"),
                        result.get("keywords", []), result.get("next_question", ""))
        st.session_state.stage_idx = 4

    elif stage == "전":
        context["jeon"] = user_input
        add_npc_message(result.get("npc", "도토리"), result.get("feedback", "전(轉) 완성!"),
                        result.get("keywords", []), result.get("next_question", ""))
        st.session_state.stage_idx = 5

    elif stage == "결":
        context["gyeol"] = user_input
        context["badge"] = result.get("badge", "글짓기 영웅")
        add_npc_message(result.get("npc", "루나"),
                        f"🎉 기승전결 완성! {result.get('full_review', '')}\n이제 AI가 글을 완성해줄게요! ✨")
        st.session_state.stage_idx = 6

    try:
        save_to_firestore(st.session_state.session_id, stage, user_input, str(result))
    except Exception:
        pass  # Firestore 저장 실패해도 진행 계속
    st.session_state.input_text = ""


def generate_writing():
    if st.session_state.writing_done:
        return
    fmt     = st.session_state.context.get("format", "소설")
    length  = st.session_state.context.get("length", 3000)
    request = build_writing_request(st.session_state.context)
    with st.spinner(f"📖 AI가 {length:,}자 {fmt}을 쓰고 있어요..."):
        text = call_gemini_writing(request)
    if text:
        st.session_state.writing_text = text
        st.session_state.writing_done = True
        save_to_firestore(st.session_state.session_id, "최종글", "자동생성", text[:500])
        st.session_state.stage_idx = 7
        st.rerun()
    else:
        # call_gemini_writing 내부에서 이미 오류 메시지+프롬프트 표시됨
        col_new, col_retry = st.columns(2)
        with col_new:
            if st.button("✏️ 새로운 글짓기", use_container_width=True):
                for k in list(st.session_state.keys()):
                    del st.session_state[k]
                st.rerun()
        with col_retry:
            if st.button("🔄 다시 시도하기", use_container_width=True, type="primary"):
                st.rerun()


# ── 완성 화면 ─────────────────────────────────────────────────
def render_completion():
    ctx   = st.session_state.context
    badge = ctx.get("badge","글짓기 영웅")
    text  = st.session_state.writing_text
    fmt   = ctx.get("format","소설")
    style = ctx.get("style","")
    fmt_icon = WRITING_FORMATS.get(fmt, ("📖",""))[0]

    # 뱃지 HTML (중첩 없이 Python으로 조립)
    badges = [
        f'<span style="background:#fff;border-radius:20px;padding:4px 14px;'
        f'border:1px solid {THEME["border"]};color:{THEME["primary"]};font-size:12px;">'
        f'{fmt_icon} {fmt}</span>'
    ]
    if style:
        badges.append(
            f'<span style="background:#fff;border-radius:20px;padding:4px 14px;'
            f'border:1px solid {THEME["border"]};color:{THEME["primary_dk"]};font-size:12px;">'
            f'✍️ {style}</span>'
        )
    badges.append(
        f'<span style="background:#fff;border-radius:20px;padding:4px 14px;'
        f'border:1px solid {THEME["border"]};color:{THEME["fire"]};font-size:12px;">'
        f'🏅 {badge}</span>'
    )
    badges_html = "".join(badges)

    st.markdown(
        f'<div style="background:linear-gradient(135deg,#e3f2fd,#bbdefb);border-radius:16px;'
        f'padding:20px;text-align:center;border:2px solid {THEME["primary"]};margin-bottom:16px;">'
        f'<div style="font-size:36px;margin-bottom:6px;">🌟</div>'
        f'<div style="color:{THEME["primary_dk"]};font-size:18px;font-weight:700;">글짓기 완성!</div>'
        f'<div style="display:flex;gap:8px;justify-content:center;margin-top:8px;flex-wrap:wrap;">'
        f'{badges_html}</div></div>',
        unsafe_allow_html=True
    )

    col_memo, col_writing = st.columns([1, 1.6])
    with col_memo:
        rows = [
            ("📌 주제",     "#26a69a",          ctx.get("topic","")),
            ("🌱 기(起)",   THEME["primary"],    ctx.get("ki","")),
            ("🚀 승(承)",   THEME["fire"],       ctx.get("seung","")),
            ("⚡ 전(轉)",   "#8e24aa",           ctx.get("jeon","")),
            ("🌈 결(結)",   THEME["primary_dk"], ctx.get("gyeol","")),
        ]
        rows_html = ""
        for label, color, val in rows:
            rows_html += (
                f'<div style="margin-bottom:10px;">'
                f'<span style="color:{color};font-weight:600;font-size:11px;">{label}</span>'
                f'<div style="color:{THEME["text"]};font-size:12px;margin-top:2px;line-height:1.5;">'
                f'{val}</div></div>'
            )
        st.markdown(
            f'<div style="background:#ffffff;border-radius:12px;padding:16px;'
            f'border:1px solid {THEME["border"]};">'
            f'<div style="color:{THEME["primary"]};font-weight:700;font-size:13px;margin-bottom:12px;">'
            f'📋 내 기승전결 메모</div>'
            f'{rows_html}</div>',
            unsafe_allow_html=True
        )

    with col_writing:
        st.markdown(
            f'<div style="background:#ffffff;border-radius:12px 12px 0 0;padding:12px 16px;'
            f'border:1.5px solid {THEME["primary"]};border-bottom:none;">'
            f'<span style="color:{THEME["primary"]};font-weight:700;font-size:13px;">'
            f'✨ AI가 완성한 {fmt} ({len(text)}자)</span></div>',
            unsafe_allow_html=True
        )
        with st.container(height=400):
            st.markdown(text)
        st.download_button(
            label=f"💾 {fmt} 다운로드 (.txt)",
            data=text.encode("utf-8"),
            file_name=f"나의{fmt}_{ctx.get('topic','작품')}.txt",
            mime="text/plain",
            use_container_width=True,
        )

    st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)
    if st.button("🔄 새로운 글짓기 시작하기", use_container_width=True):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()


# ── 메인 ─────────────────────────────────────────────────────
def main():
    st.set_page_config(
        page_title="글짓기 어드벤처 ✍️",
        page_icon="✍️",
        layout="wide",
        initial_sidebar_state="collapsed"
    )

    st.markdown(
        f'<style>'
        f'.stApp{{background-color:{THEME["bg"]};}}'
        f'.stButton>button{{background-color:{THEME["card"]};color:{THEME["primary"]};'
        f'border:1.5px solid {THEME["border"]};border-radius:10px;font-weight:600;transition:all 0.2s;}}'
        f'.stButton>button:hover{{background-color:{THEME["card_bg"]};'
        f'border-color:{THEME["primary"]};color:{THEME["primary_dk"]};}}'
        f'.stTextArea>div>div>textarea{{background-color:{THEME["card"]};color:{THEME["text"]};'
        f'border:1.5px solid {THEME["border"]};border-radius:10px;}}'
        f'.stTextArea>div>div>textarea:focus{{border-color:{THEME["primary"]};}}'
        f'div[data-testid="stMarkdownContainer"]{{color:{THEME["text"]};}}'
        f'.element-container{{margin-bottom:4px;}}'
        f'.block-container{{max-width:1100px;margin:auto;padding-top:1rem;}}'
        f'</style>',
        unsafe_allow_html=True
    )

    init_session()

    # 헤더
    st.markdown(
        f'<div style="text-align:center;padding:12px 0 8px;">'
        f'<div style="font-size:28px;">✍️</div>'
        f'<div style="color:{THEME["primary_dk"]};font-size:18px;font-weight:700;">글짓기 어드벤처</div>'
        f'<div style="color:{THEME["text_muted"]};font-size:12px;margin-top:2px;">'
        f'NPC 친구들과 함께 나만의 글을 써봐요!</div></div>',
        unsafe_allow_html=True
    )

    render_progress_bar()

    # 완성
    if st.session_state.stage_idx >= 7:
        render_completion()
        return

    # 글 자동 생성
    if st.session_state.stage_idx == 6:
        fmt = st.session_state.context.get("format","소설")
        st.markdown(
            f'<div style="background:#ffffff;border-radius:12px;padding:20px;text-align:center;'
            f'border:1.5px solid {THEME["primary"]};margin:16px 0;">'
            f'<div style="font-size:32px;margin-bottom:8px;">✨</div>'
            f'<div style="color:{THEME["primary_dk"]};font-size:15px;font-weight:700;margin-bottom:4px;">'
            f'기승전결 완성! {fmt}을 써줄게요</div>'
            f'<div style="color:{THEME["text"]};font-size:13px;">'
            f'주제: <b>{st.session_state.context.get("topic","")}</b></div></div>',
            unsafe_allow_html=True
        )
        generate_writing()
        return

    # 첫 NPC 인사
    if not st.session_state.npc_intro_done:
        fmt   = st.session_state.context.get("format","소설")
        style = st.session_state.context.get("style","")
        style_msg = f" {style}로" if style else ""
        length = st.session_state.context.get("length", 3000)
        add_npc_message(
            "루나",
            f"안녕! 나는 루나야 🧝‍♀️ 오늘 {fmt}을{style_msg} 함께 써보자! ({length:,}자)",
            ["오늘 정말 신났어요!", "좋은 일이 있었어요", "조금 피곤해요", "그냥 평범한 하루예요"],
            "오늘 기분이 어때? 또는 오늘 있었던 재미있는 일을 말해줘!"
        )
        st.session_state.npc_intro_done = True

    # ── 2컬럼 레이아웃 ────────────────────────────────────────
    col_left, col_right = st.columns([1, 1])

    # ══ 왼쪽 ════════════════════════════════════════════════════
    with col_left:
        st.markdown(
            f'<div style="color:{THEME["primary_dk"]};font-size:13px;'
            f'font-weight:600;margin-bottom:6px;">💬 NPC 대화</div>',
            unsafe_allow_html=True
        )
        # 대화창 — 고정 높이 스크롤, 새 메시지가 항상 아래에 표시됨
        with st.container(height=500):
            render_chat_history()

    # ══ 오른쪽 ══════════════════════════════════════════════════
    with col_right:
        st.markdown(
            f'<div style="color:{THEME["primary_dk"]};font-size:13px;'
            f'font-weight:600;margin-bottom:6px;">🎮 내 차례</div>',
            unsafe_allow_html=True
        )
        # 형식/문체 선택 패널 — 내 차례 상단
        render_setup_panel()
        render_stats_cards()
        render_keyword_buttons()

        st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)

        # ── API 연결 테스트 (오류 발생 시 진단용) ─────────────
        with st.expander("🔧 연결 진단", expanded=False):
            if st.button("Gemini API 연결 테스트", use_container_width=True, key="api_test"):
                try:
                    test_client = get_gemini_client()
                    test_resp = test_client.models.generate_content(
                        model=GEMINI_MODEL,
                        contents='연결 테스트. 숫자 1만 답해.'
                    )
                    st.success(f"✅ 연결 성공! 응답: {test_resp.text[:100]}")
                except Exception as e:
                    st.error(f"❌ 연결 실패: {e}")
            st.markdown(
                f'<div style="color:{THEME["text_muted"]};font-size:11px;">'
                f'모델: {GEMINI_MODEL}</div>',
                unsafe_allow_html=True
            )

        stage      = STAGES[st.session_state.stage_idx]
        char_limit = CHAR_LIMITS.get(stage, 100)
        placeholders = {
            "기분탐색": "오늘 기분이나 있었던 일을 써봐요!",
            "주제헌팅": "어떤 이야기를 쓰고 싶어요?",
            "기":       STAGE_QUESTIONS["기"]["question"],
            "승":       STAGE_QUESTIONS["승"]["question"],
            "전":       STAGE_QUESTIONS["전"]["question"],
            "결":       STAGE_QUESTIONS["결"]["question"],
        }

        user_input = st.text_area(
            label="내 이야기",
            value=st.session_state.input_text,
            placeholder=placeholders.get(stage, "여기에 써봐요!"),
            max_chars=char_limit,
            height=120,
            label_visibility="collapsed"
        )
        st.session_state.input_text = user_input

        col_send, col_clear = st.columns([4, 1])
        with col_send:
            send_label = "🚀 전송하기" if stage != "결" else "🎉 글 완성하기!"
            if st.button(send_label, use_container_width=True, type="primary"):
                cleaned = user_input.strip()
                if not st.session_state.context.get("format"):
                    st.warning("먼저 글쓰기 형식을 선택해줘요! 🎨")
                elif not cleaned:
                    st.warning("내용을 입력하거나 버튼을 눌러줘요! 💬")
                else:
                    add_player_message(cleaned)
                    process_stage(cleaned)
                    st.rerun()
        with col_clear:
            if st.button("🗑️", use_container_width=True, help="입력 내용 지우기"):
                st.session_state.input_text = ""
                st.rerun()

        st.markdown(
            f'<div style="text-align:center;color:{THEME["text_muted"]};'
            f'font-size:11px;margin-top:6px;">권장 {char_limit}자 이내</div>',
            unsafe_allow_html=True
        )


if __name__ == "__main__":
    main()


# ⚠️ [Firestore 보안 규칙 설정 안내]
# Firebase Console > Firestore Database > 규칙(Rules) 탭에서
# 프로덕션 배포 전 반드시 적절한 보안 규칙으로 변경하세요.
# rules_version = '2';
# service cloud.firestore {
#   match /databases/{database}/documents {
#     match /stories/{sessionId} {
#       allow write: if request.auth == null;
#       allow read: if false;
#     }
#   }
# }
