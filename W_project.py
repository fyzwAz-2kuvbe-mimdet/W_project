# ============================================================
# W_project.py
# 초등학생 글짓기 서포트 프로그램
# 이스 이터널 스타일 NPC 대화 + 화이트/스카이블루 UI
# 레이아웃: 왼쪽=대화창(상단에 형식/문체 선택) / 오른쪽=선택창+입력창
# ============================================================

import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
from google import genai
import datetime

# ── 상수 ──────────────────────────────────────────────────────
GEMINI_MODEL = "gemini-2.5-flash"
NOVEL_LENGTH = 3000

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

# ── 글쓰기 형식 & 문체 ────────────────────────────────────────
WRITING_FORMATS = {
    "소설":     ("📖", "인물과 사건이 있는 이야기"),
    "에세이":   ("✏️", "내 생각과 경험을 솔직하게"),
    "시":       ("🌸", "짧고 아름다운 언어로"),
    "시나리오": ("🎬", "대사와 장면으로 표현"),
}

WRITING_STYLES = {
    "소설": {
        "김영하 스타일":      "간결하고 도시적인 문체, 냉소적 유머",
        "이슬아 스타일":      "따뜻하고 일상적인 산문, 감성적 묘사",
        "제인 오스틴 스타일": "세밀한 심리 묘사와 위트 있는 대화",
        "생텍쥐페리 스타일":  "동화 같은 상상력, 철학적 여운",
    },
    "에세이": {
        "몽테뉴 스타일":          "자유롭고 솔직한 자기 성찰",
        "버지니아 울프 스타일":   "의식의 흐름, 섬세한 감각 묘사",
        "김훈 스타일":            "짧고 단호한 문장, 사물의 본질 탐구",
        "이어령 스타일":          "풍부한 비유와 통찰, 문화적 상상력",
    },
    "시": {
        "윤동주 스타일":          "순수하고 성찰적인 서정시",
        "김소월 스타일":          "한(恨)의 정서, 민요적 리듬",
        "에밀리 디킨슨 스타일":   "짧고 압축적, 독특한 구두점",
        "파블로 네루다 스타일":   "열정적이고 감각적인 이미지",
    },
    "시나리오": {
        "봉준호 스타일":          "장르 혼합, 예상 못한 반전",
        "노희경 스타일":          "인물 감정에 집중한 대화 중심",
        "크리스토퍼 놀란 스타일": "시간 구조 실험, 철학적 주제",
        "미야자키 하야오 스타일": "자연과 모험, 따뜻한 세계관",
    },
}

# ── 단계 정의 ─────────────────────────────────────────────────
STAGES       = ["기분탐색", "주제헌팅", "서론", "본론", "결론", "글생성", "완성"]
STAGE_ICONS  = ["💬", "🎯", "📖", "✍️", "🏁", "✨", "🌟"]
STAGE_LABELS = ["기분 탐색", "주제 헌팅", "서론 쓰기", "본론 쓰기", "결론 쓰기", "글 생성", "완성!"]

NPC_CHARACTERS = {
    "루나":   {"emoji": "🧝‍♀️", "color": "#2196f3", "role": "안내자"},
    "도토리": {"emoji": "🐿️",  "color": "#ff7043", "role": "응원단"},
    "글벌레": {"emoji": "📚",   "color": "#26a69a", "role": "박사"},
}

CHAR_LIMITS = {
    "기분탐색": 50, "주제헌팅": 30,
    "서론": 80, "본론": 120, "결론": 80,
}


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


# ── Gemini 프롬프트 ───────────────────────────────────────────
def build_prompt(stage, user_input, context):
    fmt   = context.get("format", "소설")
    style = context.get("style", "")
    style_hint = f" 문체 참고: {style}" if style else ""
    base = f"너는 초등학생 글짓기를 돕는 친절한 AI야. 글 형식은 {fmt}이야.{style_hint} 반드시 JSON으로만 답해. 설명 금지.\n"

    if stage == "기분탐색":
        return base + f"""
입력: "{user_input}"
keywords는 반드시 4개, 각 항목은 15자 이내 짧은 문장:
{{"npc":"루나","message":"공감 한 줄(20자 이내)","keywords":["문장1","문장2","문장3","문장4"],"next_question":"주제 헌팅 질문(30자 이내)"}}"""

    elif stage == "주제헌팅":
        return base + f"""
기분: "{context.get('mood','')}", 선택: "{user_input}"
JSON:
{{"npc":"글벌레","topic":"{fmt} 주제(20자 이내)","message":"칭찬 한 줄(20자 이내)","keywords":["서론 시작 문장1","서론 시작 문장2","서론 시작 문장3","서론 시작 문장4"],"next_question":"서론 질문(30자 이내)"}}"""

    elif stage == "서론":
        return base + f"""
주제: "{context.get('topic','')}", 서론: "{user_input}"
JSON:
{{"npc":"도토리","feedback":"서론 칭찬(20자 이내)","keywords":["본론 힌트1","본론 힌트2","본론 힌트3","본론 힌트4"],"next_question":"본론 질문(30자 이내)"}}"""

    elif stage == "본론":
        return base + f"""
주제: "{context.get('topic','')}", 서론요약: "{context.get('intro','')[:30]}", 본론: "{user_input}"
JSON:
{{"npc":"글벌레","feedback":"본론 칭찬(20자 이내)","keywords":["결론 힌트1","결론 힌트2","결론 힌트3","결론 힌트4"],"next_question":"결론 질문(30자 이내)"}}"""

    elif stage == "결론":
        return base + f"""
주제: "{context.get('topic','')}", 결론: "{user_input}"
JSON:
{{"npc":"루나","feedback":"결론 칭찬(20자 이내)","full_review":"전체 칭찬(30자 이내)","badge":"획득 칭호(10자 이내)"}}"""

    return base


def build_writing_prompt(context):
    fmt       = context.get("format", "소설")
    style     = context.get("style", "")
    style_desc = WRITING_STYLES.get(fmt, {}).get(style, "")
    style_line = f"\n- 문체: {style} — {style_desc}" if style_desc else ""
    return f"""너는 초등학생의 글쓰기 아이디어를 바탕으로 완성도 높은 {fmt}을 쓰는 작가야.
아래 기승전결 메모를 바탕으로 {NOVEL_LENGTH}자 내외의 완성된 {fmt}을 써줘.

[주제] {context.get('topic','')}
[서론] {context.get('intro','')}
[본론] {context.get('body','')}
[결론] {context.get('conclusion','')}

조건:
- 초등학생이 읽기 쉬운 언어 사용
- {fmt} 형식에 맞게 작성{style_line}
- 제목을 첫 줄에 붙여줘 (형식: # 제목)
- {NOVEL_LENGTH}자 내외 (너무 짧거나 길지 않게)
- JSON 없이 본문만 출력"""


def call_gemini(prompt):
    import json, re
    try:
        client = get_gemini_client()
        response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
        # 토큰 사용량 누적 저장
        usage = getattr(response, "usage_metadata", None)
        if usage:
            st.session_state.token_in  = st.session_state.get("token_in", 0)  + getattr(usage, "prompt_token_count", 0)
            st.session_state.token_out = st.session_state.get("token_out", 0) + getattr(usage, "candidates_token_count", 0)
        text = response.text.strip()
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group())
        else:
            # JSON 파싱 실패 — AI가 JSON 대신 다른 형식으로 답한 경우
            # 재시도: JSON만 달라고 다시 요청
            retry_prompt = prompt + "\n\n반드시 JSON만 출력하고 다른 텍스트는 절대 포함하지 마."
            response2 = client.models.generate_content(model=GEMINI_MODEL, contents=retry_prompt)
            text2 = response2.text.strip()
            match2 = re.search(r'\{.*\}', text2, re.DOTALL)
            if match2:
                return json.loads(match2.group())
            st.warning(f"⚠️ AI 응답 파싱 실패 (2회): {text2[:300]}")
    except Exception as e:
        err_str = str(e)
        if "API_KEY" in err_str or "api_key" in err_str or "INVALID" in err_str:
            st.error("🔑 Gemini API 키가 올바르지 않아요. Streamlit Cloud Secrets의 GEMINI_API_KEY를 확인해주세요.")
        elif "quota" in err_str.lower() or "429" in err_str:
            st.error("⏱️ API 사용량 한도 초과예요. 잠시 후 다시 시도해주세요.")
        elif "network" in err_str.lower() or "connect" in err_str.lower():
            st.error("🌐 네트워크 연결 문제예요. 인터넷 연결을 확인해주세요.")
        else:
            st.error(f"❌ AI 오류: {err_str}")
    return {}


def call_gemini_writing(prompt):
    try:
        response = get_gemini_client().models.generate_content(
            model=GEMINI_MODEL, contents=prompt,
            config={"max_output_tokens": 4096},
        )
        return response.text.strip()
    except Exception as e:
        st.error(f"글 생성 오류: {e}")
        return ""


# ── Session State ─────────────────────────────────────────────
def init_session():
    defaults = {
        "stage_idx": 0,
        "chat_history": [],
        "context": {"format": "", "style": ""},
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
    progress = min(min(idx, 5) / 5, 1.0)
    fmt      = st.session_state.context.get("format", "")
    style    = st.session_state.context.get("style", "")

    # 단계 라벨 (Python으로 생성해서 f-string 중첩 방지)
    label_parts = []
    display = list(zip(STAGE_ICONS[:5] + [STAGE_ICONS[6]], STAGE_LABELS[:5] + [STAGE_LABELS[6]]))
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


# ── 형식/문체 선택 패널 (오른쪽 컬럼 상단) ─────────────────
def render_setup_panel():
    """
    오른쪽 컬럼 '내 차례' 상단에 위치.
    setup_open=True 이면 펼쳐져 있고, 확정 버튼 누르면 접힘.
    형식/문체 선택 중에는 rerun해도 열린 상태 유지.
    """
    fmt   = st.session_state.context.get("format", "")
    style = st.session_state.context.get("style", "")

    # expander 라벨 — 선택 완료 여부에 따라 다르게 표시
    if fmt:
        fmt_icon = WRITING_FORMATS[fmt][0]
        label = f"🎨 설정완료: {fmt_icon} {fmt}" + (f" · {style}" if style else "")
    else:
        label = "🎨 글쓰기 형식과 문체를 선택해요"

    with st.expander(label, expanded=st.session_state.setup_open):

        # ── Step 1: 형식 ─────────────────────────────────────
        st.markdown(
            f'<div style="color:{THEME["primary"]};font-size:12px;'
            f'font-weight:600;margin-bottom:6px;">📌 형식 선택</div>',
            unsafe_allow_html=True
        )
        fmt_cols = st.columns(4)
        for i, (f_name, (f_icon, f_desc)) in enumerate(WRITING_FORMATS.items()):
            with fmt_cols[i]:
                is_sel = fmt == f_name
                btn_label = f"{f_icon} {f_name} ✅" if is_sel else f"{f_icon} {f_name}"
                if st.button(btn_label, key=f"fmt_{f_name}", use_container_width=True):
                    st.session_state.context["format"] = f_name
                    st.session_state.context["style"]  = ""
                    st.session_state.setup_open = True   # 형식 클릭 후에도 열린 상태 유지
                    st.rerun()
                st.markdown(
                    f'<div style="text-align:center;color:{THEME["text_muted"]};'
                    f'font-size:10px;margin-top:-4px;">{f_desc}</div>',
                    unsafe_allow_html=True
                )

        # ── Step 2: 문체 ─────────────────────────────────────
        if fmt:
            st.markdown(
                f'<div style="color:{THEME["primary"]};font-size:12px;font-weight:600;'
                f'margin-top:12px;margin-bottom:6px;">'
                f'🖋️ 문체 선택 '
                f'<span style="color:{THEME["text_muted"]};font-size:10px;font-weight:400;">'
                f'(선택 안 해도 됩니다)</span></div>',
                unsafe_allow_html=True
            )
            style_cols = st.columns(4)
            for i, (s_name, s_desc) in enumerate(WRITING_STYLES.get(fmt, {}).items()):
                with style_cols[i]:
                    is_sel = style == s_name
                    btn_label = f"{s_name} ✅" if is_sel else s_name
                    if st.button(btn_label, key=f"sty_{s_name}", use_container_width=True):
                        st.session_state.context["style"] = "" if is_sel else s_name
                        st.session_state.setup_open = True   # 문체 클릭 후에도 열린 상태 유지
                        st.rerun()
                    st.markdown(
                        f'<div style="text-align:center;color:{THEME["text_muted"]};'
                        f'font-size:10px;margin-top:-4px;line-height:1.3;">{s_desc}</div>',
                        unsafe_allow_html=True
                    )

        # ── 확정 버튼 ─────────────────────────────────────────
        if fmt:
            st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
            fmt_icon = WRITING_FORMATS[fmt][0]
            btn_txt  = f"✅ {fmt_icon} {fmt}" + (f" · {style}" if style else "") + " 로 시작!"
            if st.button(btn_txt, use_container_width=True, type="primary", key="setup_confirm"):
                st.session_state.setup_open = False  # 확정 버튼 누르면 닫힘
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
        f'<span style="color:{THEME["text_muted"]};font-size:10px;">🔢 토큰 사용량</span>'
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
    with st.spinner("✨ AI가 생각하는 중..."):
        result = call_gemini(build_prompt(stage, user_input, context))
    if not result:
        # 실패 시: 방금 추가한 player 메시지 제거 (중복 방지)
        if st.session_state.chat_history and st.session_state.chat_history[-1]["type"] == "player":
            st.session_state.chat_history.pop()
        # 입력창 복원
        st.session_state.input_text = user_input
        return

    if stage == "기분탐색":
        context["mood"] = user_input
        add_npc_message(result.get("npc","루나"), result.get("message",""),
                        result.get("keywords",[]), result.get("next_question",""))
        st.session_state.stage_idx = 1

    elif stage == "주제헌팅":
        topic = result.get("topic", user_input)
        context["topic"] = topic
        add_npc_message(result.get("npc","글벌레"),
                        f"주제 확정! 『{topic}』 {result.get('message','')}",
                        result.get("keywords",[]), result.get("next_question",""))
        st.session_state.stage_idx = 2

    elif stage == "서론":
        context["intro"] = user_input
        add_npc_message(result.get("npc","도토리"), result.get("feedback","서론 완성!"),
                        result.get("keywords",[]), result.get("next_question",""))
        st.session_state.stage_idx = 3

    elif stage == "본론":
        context["body"] = user_input
        add_npc_message(result.get("npc","글벌레"), result.get("feedback","본론 완성!"),
                        result.get("keywords",[]), result.get("next_question",""))
        st.session_state.stage_idx = 4

    elif stage == "결론":
        context["conclusion"] = user_input
        context["badge"] = result.get("badge","글짓기 영웅")
        add_npc_message(result.get("npc","루나"),
                        f"🎉 기승전결 완성! {result.get('full_review','')}\n이제 AI가 글을 완성해줄게요! ✨")
        st.session_state.stage_idx = 5

    save_to_firestore(st.session_state.session_id, stage, user_input, str(result))
    st.session_state.input_text = ""


def generate_writing():
    if st.session_state.writing_done:
        return
    fmt = st.session_state.context.get("format","소설")
    with st.spinner(f"📖 AI가 {NOVEL_LENGTH}자 {fmt}을 쓰고 있어요..."):
        text = call_gemini_writing(build_writing_prompt(st.session_state.context))
    if text:
        st.session_state.writing_text = text
        st.session_state.writing_done = True
        save_to_firestore(st.session_state.session_id, "최종글", "자동생성", text[:500])
        st.session_state.stage_idx = 6
        st.rerun()
    else:
        st.error("글 생성에 실패했어요. 잠시 후 다시 시도해요!")


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
            ("📌 주제", "#26a69a",        ctx.get("topic","")),
            ("📖 서론", THEME["primary"],  ctx.get("intro","")),
            ("✍️ 본론", THEME["fire"],     ctx.get("body","")),
            ("🏁 결론", THEME["primary_dk"], ctx.get("conclusion","")),
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
    if st.session_state.stage_idx >= 6:
        render_completion()
        return

    # 글 자동 생성
    if st.session_state.stage_idx == 5:
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
        add_npc_message(
            "루나",
            f"안녕! 나는 루나야 🧝‍♀️ 오늘 {fmt}을{style_msg} 함께 써보자!",
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
            "주제헌팅": "어떤 주제로 글을 쓰고 싶어요?",
            "서론":     "글의 시작을 써봐요!",
            "본론":     "본론에서 하고 싶은 이야기!",
            "결론":     "글을 어떻게 마무리할까요?",
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
            send_label = "🚀 전송하기" if stage != "결론" else "🎉 글 완성하기!"
            if st.button(send_label, use_container_width=True, type="primary"):
                cleaned = user_input.strip()
                if not cleaned:
                    st.warning("내용을 입력하거나 버튼을 눌러줘요! 💬")
                else:
                    add_player_message(cleaned)
                    process_stage(cleaned)
                    # process_stage 내부에서 실패 시 chat_history를 롤백했으므로
                    # 성공/실패 모두 rerun해서 화면 갱신
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
