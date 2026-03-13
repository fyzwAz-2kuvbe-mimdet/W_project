# ============================================================
# W_project.py
# 초등학생 글짓기 서포트 프로그램
# 이스 이터널 스타일 NPC 대화 + 화이트/스카이블루 UI
# 레이아웃: 왼쪽=대화창 / 오른쪽=선택창+입력창
# ============================================================

import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
from google import genai
import datetime

# ── 상수 ──────────────────────────────────────────────────────
GEMINI_MODEL = "gemini-2.5-flash"
NOVEL_LENGTH = 3000  # 완성 소설 목표 글자수

# ── UI 테마 설정 ───────────────────────────────────────────────
# 여기서 색상을 바꾸면 전체 UI에 반영됩니다
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

# 글짓기 단계 정의
STAGES = ["기분탐색", "주제헌팅", "서론", "본론", "결론", "소설생성", "완성"]
STAGE_ICONS = ["💬", "🎯", "📖", "✍️", "🏁", "✨", "🌟"]
STAGE_LABELS = ["기분 탐색", "주제 헌팅", "서론 쓰기", "본론 쓰기", "결론 쓰기", "소설 생성", "완성!"]

# 진행바에 표시할 단계 (소설생성 제외 — 자동 처리)
PROGRESS_STAGES = [0, 1, 2, 3, 4, 6]  # 표시할 stage 인덱스

# NPC 캐릭터 설정
NPC_CHARACTERS = {
    "루나":   {"emoji": "🧝‍♀️", "color": "#2196f3", "role": "안내자"},
    "도토리": {"emoji": "🐿️",  "color": "#ff7043", "role": "응원단"},
    "글벌레": {"emoji": "📚",   "color": "#26a69a", "role": "박사"},
}

# 단계별 글자수 제한 (토큰 최소화)
CHAR_LIMITS = {
    "기분탐색": 50,
    "주제헌팅": 30,
    "서론": 80,
    "본론": 120,
    "결론": 80,
}


# ── Firebase 초기화 (캐시로 1회만 실행) ──────────────────────
@st.cache_resource
def init_firebase():
    if firebase_admin._apps:
        return firebase_admin.get_app()
    firebase_config = dict(st.secrets["firebase"])
    firebase_config["private_key"] = firebase_config["private_key"].replace("\\n", "\n")
    cred = credentials.Certificate(firebase_config)
    return firebase_admin.initialize_app(cred)


@st.cache_resource
def get_db():
    init_firebase()
    return firestore.client()


# ── Gemini 클라이언트 초기화 ──────────────────────────────────
@st.cache_resource
def get_gemini_client():
    return genai.Client(api_key=st.secrets["GEMINI_API_KEY"])


# ── Firestore 저장 ────────────────────────────────────────────
def save_story_to_firestore(session_id: str, stage: str, user_input: str, ai_response: str):
    try:
        db = get_db()
        doc_ref = db.collection("stories").document(session_id)
        doc_ref.set({
            "session_id": session_id,
            "last_updated": datetime.datetime.now(),
            "stage": stage,
            "history": firestore.ArrayUnion([{
                "stage": stage,
                "user": user_input,
                "ai": ai_response,
                "time": datetime.datetime.now().isoformat()
            }])
        }, merge=True)
    except Exception as e:
        st.warning(f"저장 중 오류가 발생했어요: {e}")


# ── Gemini 프롬프트 빌더 ──────────────────────────────────────
def build_prompt(stage: str, user_input: str, context: dict) -> str:
    base = "너는 초등학생 글짓기를 돕는 친절한 AI야. 반드시 JSON으로만 답해. 설명 금지.\n"

    if stage == "기분탐색":
        return base + f"""
입력: "{user_input}"
JSON 형식으로만 답해. keywords는 반드시 4개, 각 항목은 15자 이내 짧은 문장으로:
{{"npc":"루나","message":"공감 한 줄(20자 이내)","keywords":["문장1","문장2","문장3","문장4"],"next_question":"주제 헌팅 질문(30자 이내)"}}"""

    elif stage == "주제헌팅":
        mood = context.get("mood", "")
        return base + f"""
기분: "{mood}", 선택: "{user_input}"
JSON:
{{"npc":"글벌레","topic":"글 주제(20자 이내)","message":"칭찬 한 줄(20자 이내)","keywords":["서론 시작 문장1","서론 시작 문장2","서론 시작 문장3","서론 시작 문장4"],"next_question":"서론 질문(30자 이내)"}}"""

    elif stage == "서론":
        topic = context.get("topic", "")
        return base + f"""
주제: "{topic}", 서론: "{user_input}"
JSON:
{{"npc":"도토리","feedback":"서론 칭찬(20자 이내)","keywords":["본론 힌트 문장1","본론 힌트 문장2","본론 힌트 문장3","본론 힌트 문장4"],"next_question":"본론 질문(30자 이내)"}}"""

    elif stage == "본론":
        topic = context.get("topic", "")
        intro = context.get("intro", "")
        return base + f"""
주제: "{topic}", 서론요약: "{intro[:30]}", 본론: "{user_input}"
JSON:
{{"npc":"글벌레","feedback":"본론 칭찬(20자 이내)","keywords":["결론 힌트 문장1","결론 힌트 문장2","결론 힌트 문장3","결론 힌트 문장4"],"next_question":"결론 질문(30자 이내)"}}"""

    elif stage == "결론":
        topic = context.get("topic", "")
        return base + f"""
주제: "{topic}", 결론: "{user_input}"
JSON:
{{"npc":"루나","feedback":"결론 칭찬(20자 이내)","full_review":"전체 글 짧은 칭찬(30자 이내)","badge":"획득 칭호(10자 이내)"}}"""

    return base


def build_novel_prompt(context: dict) -> str:
    """
    기승전결이 모두 모인 context를 바탕으로
    Gemini에게 소설 작성을 요청하는 프롬프트를 생성합니다.
    """
    topic      = context.get("topic", "")
    intro      = context.get("intro", "")       # 서론
    body       = context.get("body", "")        # 본론
    conclusion = context.get("conclusion", "")  # 결론

    return f"""너는 초등학생의 글쓰기 아이디어를 바탕으로 재미있는 단편 소설을 쓰는 작가야.
아래의 기승전결 메모를 바탕으로 {NOVEL_LENGTH}자 내외의 완성된 단편 소설을 써줘.

[주제] {topic}
[서론] {intro}
[본론] {body}
[결론] {conclusion}

조건:
- 초등학생이 읽기 쉬운 문체로 작성
- 대화체와 묘사를 적절히 섞어서 생동감 있게
- 제목을 첫 줄에 붙여줘 (형식: # 제목)
- {NOVEL_LENGTH}자 내외로 작성 (너무 짧거나 길지 않게)
- 기승전결 구조가 자연스럽게 드러나도록
- JSON 형식 없이 소설 본문만 출력"""


def call_gemini(prompt: str) -> dict:
    """단계별 JSON 응답용 Gemini 호출"""
    import json, re
    client = get_gemini_client()
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        text = response.text.strip()
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception as e:
        st.error(f"AI 응답 오류: {e}")
    return {}


def call_gemini_novel(prompt: str) -> str:
    """소설 생성용 Gemini 호출 — 스트리밍으로 자연스럽게 출력"""
    client = get_gemini_client()
    try:
        # 소설은 긴 텍스트이므로 max_tokens를 넉넉하게
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config={"max_output_tokens": 4096},
        )
        return response.text.strip()
    except Exception as e:
        st.error(f"소설 생성 오류: {e}")
        return ""


# ── Session State 초기화 ──────────────────────────────────────
def init_session():
    defaults = {
        "stage_idx": 0,
        "chat_history": [],
        "context": {},
        "suggested_keywords": [],
        "input_text": "",
        "session_id": datetime.datetime.now().strftime("%Y%m%d_%H%M%S"),
        "npc_intro_done": False,
        "novel_text": "",        # 생성된 소설 전문
        "novel_done": False,     # 소설 생성 완료 여부
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ── UI 헬퍼 함수들 ────────────────────────────────────────────
def add_npc_message(npc_name: str, message: str, keywords: list = None, question: str = None):
    st.session_state.chat_history.append({
        "type": "npc",
        "npc": npc_name,
        "message": message,
        "keywords": keywords or [],
        "question": question or "",
    })
    if keywords:
        st.session_state.suggested_keywords = keywords


def add_player_message(text: str):
    st.session_state.chat_history.append({
        "type": "player",
        "message": text,
    })


# ── 진행 바 (상단 전체 너비) ──────────────────────────────────
def render_progress_bar():
    stage_idx = st.session_state.stage_idx
    # 소설생성(5) 단계는 진행바에서 완성(6)과 동일하게 표시
    display_idx = min(stage_idx, 5)
    total = 5  # 0~5 (완성 포함)
    progress = min(display_idx / total, 1.0)

    labels_html = ""
    display_stages = [
        (STAGE_ICONS[0], STAGE_LABELS[0], 0),
        (STAGE_ICONS[1], STAGE_LABELS[1], 1),
        (STAGE_ICONS[2], STAGE_LABELS[2], 2),
        (STAGE_ICONS[3], STAGE_LABELS[3], 3),
        (STAGE_ICONS[4], STAGE_LABELS[4], 4),
        (STAGE_ICONS[6], STAGE_LABELS[6], 6),
    ]
    for icon, label, idx in display_stages:
        active = stage_idx >= idx
        color = THEME['primary'] if active else "#b0bec5"
        labels_html += f'<span style="font-size:11px;color:{color};">{icon}{label}</span>'

    st.markdown(f"""
    <div style="background:#ffffff;padding:12px 16px;border-radius:12px;margin-bottom:16px;
                border:1px solid {THEME['border']};box-shadow:0 2px 8px #e3f2fd;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
            <span style="color:{THEME['primary_dk']};font-size:13px;font-weight:600;">✍️ 글짓기 여정</span>
            <span style="color:{THEME['primary']};font-size:13px;font-weight:700;">{int(progress*100)}%</span>
        </div>
        <div style="background:#e3f2fd;border-radius:8px;height:10px;overflow:hidden;">
            <div style="background:linear-gradient(90deg,#64b5f6,#2196f3);
                        width:{progress*100}%;height:100%;border-radius:8px;transition:width 0.5s;"></div>
        </div>
        <div style="display:flex;justify-content:space-between;margin-top:8px;">
            {labels_html}
        </div>
    </div>
    """, unsafe_allow_html=True)


# ── 왼쪽: 대화창 ──────────────────────────────────────────────
def render_chat_history():
    """
    왼쪽 패널에 NPC↔플레이어 대화 기록을 표시합니다.
    스크롤 가능한 고정 높이 박스 안에 렌더링합니다.
    """
    # 대화창 컨테이너 (스크롤 가능)
    chat_html = ""
    for msg in st.session_state.chat_history:
        if msg["type"] == "npc":
            npc = NPC_CHARACTERS.get(msg["npc"], NPC_CHARACTERS["루나"])
            question_html = (
                f'<div style="color:{THEME["primary"]};font-size:12px;'
                f'margin-top:6px;font-style:italic;">❓ {msg["question"]}</div>'
                if msg.get("question") else ""
            )
            chat_html += f"""
            <div style="background:#ffffff;border:1.5px solid {THEME['border']};
                        border-radius:12px;padding:12px 14px;margin:6px 0;
                        box-shadow:0 1px 4px #e3f2fd;">
                <div style="color:{THEME['primary']};font-size:12px;font-weight:700;margin-bottom:4px;">
                    {npc['emoji']} {msg['npc']}
                    <span style="font-size:10px;color:{THEME['text_muted']};">({npc['role']})</span>
                </div>
                <div style="color:{THEME['text']};font-size:14px;line-height:1.6;">{msg['message']}</div>
                {question_html}
            </div>"""

        elif msg["type"] == "player":
            chat_html += f"""
            <div style="display:flex;justify-content:flex-end;margin:6px 0;">
                <div style="background:#e3f2fd;border-radius:12px 12px 2px 12px;
                            padding:8px 12px;max-width:90%;border:1px solid {THEME['border']};">
                    <div style="color:{THEME['primary']};font-size:11px;font-weight:600;margin-bottom:2px;">🧒 나</div>
                    <div style="color:{THEME['text']};font-size:13px;">{msg['message']}</div>
                </div>
            </div>"""

    st.markdown(f"""
    <div style="height:480px;overflow-y:auto;padding:4px 2px;
                scrollbar-width:thin;scrollbar-color:{THEME['border']} transparent;">
        {chat_html}
        <div id="chat-bottom"></div>
    </div>
    <script>
        // 대화창 자동 스크롤
        var el = document.getElementById('chat-bottom');
        if(el) el.scrollIntoView({{behavior:'smooth'}});
    </script>
    """, unsafe_allow_html=True)


# ── 오른쪽: 스탯 카드 ─────────────────────────────────────────
def render_stats_cards():
    stage = STAGES[st.session_state.stage_idx]
    char_limit = CHAR_LIMITS.get(stage, 100)
    current_len = len(st.session_state.input_text)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"""
        <div style="background:{THEME['card_bg']};border-radius:10px;padding:10px;
                    text-align:center;border:1px solid {THEME['border']};margin-bottom:8px;">
            <div style="color:{THEME['text_muted']};font-size:10px;">현재 단계</div>
            <div style="color:{THEME['primary']};font-size:16px;font-weight:700;">
                {STAGE_ICONS[st.session_state.stage_idx]}
            </div>
            <div style="color:{THEME['primary_dk']};font-size:11px;">
                {STAGE_LABELS[st.session_state.stage_idx]}
            </div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        color = THEME['danger'] if current_len > char_limit else THEME['primary']
        streak = len([m for m in st.session_state.chat_history if m["type"] == "player"])
        st.markdown(f"""
        <div style="background:{THEME['card_bg']};border-radius:10px;padding:10px;
                    text-align:center;border:1px solid {THEME['border']};margin-bottom:8px;">
            <div style="color:{THEME['text_muted']};font-size:10px;">글자 수 / 연속</div>
            <div style="color:{color};font-size:16px;font-weight:700;">{current_len}자</div>
            <div style="color:#b0bec5;font-size:11px;">
                /{char_limit}자 권장 · {streak}🔥
            </div>
        </div>
        """, unsafe_allow_html=True)


# ── 오른쪽: 키워드 버튼 (2x2 그리드) ────────────────────────
def render_keyword_buttons():
    if not st.session_state.suggested_keywords:
        return

    st.markdown(
        f'<div style="color:{THEME["primary"]};font-size:12px;margin:4px 0 6px;">'
        f'💡 눌러서 입력창에 추가해요!</div>',
        unsafe_allow_html=True
    )

    keywords = st.session_state.suggested_keywords[:4]
    row1 = st.columns(2)
    row2 = st.columns(2)
    grid = [row1[0], row1[1], row2[0], row2[1]]

    for i, kw in enumerate(keywords):
        if i >= len(grid):
            break
        with grid[i]:
            if st.button(f"✨ {kw}", key=f"kw_{i}_{kw}", use_container_width=True):
                current = st.session_state.input_text.strip()
                st.session_state.input_text = (current + " " + kw) if current else kw
                st.rerun()


# ── 단계별 처리 로직 ──────────────────────────────────────────
def process_stage(user_input: str):
    stage = STAGES[st.session_state.stage_idx]
    context = st.session_state.context

    with st.spinner("✨ AI가 생각하는 중..."):
        prompt = build_prompt(stage, user_input, context)
        result = call_gemini(prompt)

    if not result:
        add_npc_message("루나", "앗, 잠깐 연결이 안 됐어요! 다시 한번 말해줄래요? 🙏")
        return

    if stage == "기분탐색":
        st.session_state.context["mood"] = user_input
        add_npc_message(
            result.get("npc", "루나"),
            result.get("message", "오늘 기분을 말해줬군요!"),
            result.get("keywords", []),
            result.get("next_question", "어떤 주제로 글을 써볼까요?")
        )
        st.session_state.stage_idx = 1

    elif stage == "주제헌팅":
        topic = result.get("topic", user_input)
        st.session_state.context["topic"] = topic
        add_npc_message(
            result.get("npc", "글벌레"),
            f"주제 확정! 『{topic}』 {result.get('message', '멋진 주제예요!')}",
            result.get("keywords", []),
            result.get("next_question", "서론을 어떻게 시작할까요?")
        )
        st.session_state.stage_idx = 2

    elif stage == "서론":
        st.session_state.context["intro"] = user_input
        add_npc_message(
            result.get("npc", "도토리"),
            result.get("feedback", "서론 완성!"),
            result.get("keywords", []),
            result.get("next_question", "본론에서는 무슨 이야기를 할까요?")
        )
        st.session_state.stage_idx = 3

    elif stage == "본론":
        st.session_state.context["body"] = user_input
        add_npc_message(
            result.get("npc", "글벌레"),
            result.get("feedback", "본론 완성!"),
            result.get("keywords", []),
            result.get("next_question", "어떻게 마무리할까요?")
        )
        st.session_state.stage_idx = 4

    elif stage == "결론":
        st.session_state.context["conclusion"] = user_input
        badge = result.get("badge", "글짓기 영웅")
        add_npc_message(
            result.get("npc", "루나"),
            f"🎉 기승전결 완성! {result.get('full_review', '정말 훌륭한 구성이에요!')}\n"
            f"이제 AI가 소설로 만들어줄게요! ✨",
        )
        st.session_state.context["badge"] = badge
        # 결론 완료 → 소설 생성 단계로
        st.session_state.stage_idx = 5

    save_story_to_firestore(
        st.session_state.session_id,
        stage,
        user_input,
        str(result)
    )
    st.session_state.input_text = ""


def generate_novel():
    """
    기승전결 context를 바탕으로 Gemini가 소설을 생성합니다.
    소설 생성 단계(stage_idx=5)에서 자동으로 호출됩니다.
    """
    if st.session_state.novel_done:
        return  # 이미 생성됨

    context = st.session_state.context
    prompt = build_novel_prompt(context)

    with st.spinner(f"📖 AI가 {NOVEL_LENGTH}자 소설을 쓰고 있어요... 잠깐만 기다려줘요!"):
        novel = call_gemini_novel(prompt)

    if novel:
        st.session_state.novel_text = novel
        st.session_state.novel_done = True
        # 소설 Firestore 저장
        save_story_to_firestore(
            st.session_state.session_id,
            "소설",
            "자동생성",
            novel[:500]  # 미리보기만 저장 (토큰 절약)
        )
        st.session_state.stage_idx = 6  # 완성 단계로
        st.rerun()
    else:
        st.error("소설 생성에 실패했어요. 다시 시도해볼게요!")


# ── 완성 화면 ─────────────────────────────────────────────────
def render_completion():
    ctx = st.session_state.context
    badge = ctx.get("badge", "글짓기 영웅")
    novel = st.session_state.novel_text

    # 완성 배너
    st.markdown(f"""
    <div style="background:linear-gradient(135deg,#e3f2fd,#bbdefb);border-radius:16px;
                padding:24px;text-align:center;border:2px solid {THEME['primary']};margin-bottom:16px;">
        <div style="font-size:40px;margin-bottom:8px;">🌟</div>
        <div style="color:{THEME['primary_dk']};font-size:20px;font-weight:700;margin-bottom:6px;">
            글짓기 어드벤처 완성!
        </div>
        <div style="background:#ffffff;border-radius:20px;display:inline-block;
                    padding:5px 18px;border:1px solid {THEME['border']};">
            <span style="color:{THEME['primary']};font-size:13px;font-weight:600;">🏅 {badge}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 두 컬럼 — 왼쪽: 기승전결 메모 / 오른쪽: 생성된 소설
    col_memo, col_novel = st.columns([1, 1.6])

    with col_memo:
        st.markdown(f"""
        <div style="background:#ffffff;border-radius:12px;padding:16px;
                    border:1px solid {THEME['border']};height:100%;">
            <div style="color:{THEME['primary']};font-weight:700;font-size:14px;margin-bottom:12px;">
                📋 내 기승전결 메모
            </div>
            <div style="margin-bottom:10px;">
                <span style="color:#26a69a;font-weight:600;font-size:12px;">📌 주제</span>
                <div style="color:{THEME['text']};font-size:13px;margin-top:2px;">
                    {ctx.get('topic','')}
                </div>
            </div>
            <div style="margin-bottom:10px;">
                <span style="color:{THEME['primary']};font-weight:600;font-size:12px;">📖 서론</span>
                <div style="color:{THEME['text']};font-size:13px;margin-top:2px;line-height:1.5;">
                    {ctx.get('intro','')}
                </div>
            </div>
            <div style="margin-bottom:10px;">
                <span style="color:{THEME['fire']};font-weight:600;font-size:12px;">✍️ 본론</span>
                <div style="color:{THEME['text']};font-size:13px;margin-top:2px;line-height:1.5;">
                    {ctx.get('body','')}
                </div>
            </div>
            <div>
                <span style="color:{THEME['primary_dk']};font-weight:600;font-size:12px;">🏁 결론</span>
                <div style="color:{THEME['text']};font-size:13px;margin-top:2px;line-height:1.5;">
                    {ctx.get('conclusion','')}
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col_novel:
        st.markdown(f"""
        <div style="background:#ffffff;border-radius:12px;padding:16px;
                    border:1.5px solid {THEME['primary']};">
            <div style="color:{THEME['primary']};font-weight:700;font-size:14px;margin-bottom:10px;">
                ✨ AI가 완성한 소설 ({len(novel)}자)
            </div>
        </div>
        """, unsafe_allow_html=True)

        # 소설 본문 — st.markdown으로 렌더링 (제목 # 포함)
        with st.container():
            st.markdown(f"""
            <div style="background:#f8fbff;border-radius:10px;padding:16px;
                        border:1px solid {THEME['border']};
                        max-height:500px;overflow-y:auto;
                        line-height:1.9;color:{THEME['text']};font-size:14px;
                        white-space:pre-wrap;">
{novel}
            </div>
            """, unsafe_allow_html=True)

        # 소설 다운로드 버튼
        st.download_button(
            label="💾 소설 다운로드 (.txt)",
            data=novel.encode("utf-8"),
            file_name=f"나의소설_{ctx.get('topic','작품')}.txt",
            mime="text/plain",
            use_container_width=True,
        )

    st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)

    if st.button("🔄 새로운 글짓기 시작하기", use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()


# ── 메인 앱 ───────────────────────────────────────────────────
def main():
    st.set_page_config(
        page_title="글짓기 어드벤처 ✍️",
        page_icon="✍️",
        layout="wide",               # 2컬럼 레이아웃을 위해 wide 모드
        initial_sidebar_state="collapsed"
    )

    # 화이트 + 스카이블루 테마
    st.markdown(f"""
    <style>
    .stApp {{ background-color: {THEME['bg']}; }}
    .stButton > button {{
        background-color: {THEME['card']};
        color: {THEME['primary']};
        border: 1.5px solid {THEME['border']};
        border-radius: 10px;
        font-weight: 600;
        transition: all 0.2s;
    }}
    .stButton > button:hover {{
        background-color: {THEME['card_bg']};
        border-color: {THEME['primary']};
        color: {THEME['primary_dk']};
    }}
    .stTextArea > div > div > textarea {{
        background-color: {THEME['card']};
        color: {THEME['text']};
        border: 1.5px solid {THEME['border']};
        border-radius: 10px;
    }}
    .stTextArea > div > div > textarea:focus {{
        border-color: {THEME['primary']};
    }}
    div[data-testid="stMarkdownContainer"] {{ color: {THEME['text']}; }}
    .element-container {{ margin-bottom: 4px; }}
    /* wide 모드에서 중앙 정렬 */
    .block-container {{ max-width: 1100px; margin: auto; padding-top: 1rem; }}
    </style>
    """, unsafe_allow_html=True)

    # 세션 초기화
    init_session()

    # ── 헤더 (전체 너비) ──────────────────────────────────────
    st.markdown(f"""
    <div style="text-align:center;padding:16px 0 8px;">
        <div style="font-size:28px;">✍️</div>
        <div style="color:{THEME['primary_dk']};font-size:18px;font-weight:700;">글짓기 어드벤처</div>
        <div style="color:{THEME['text_muted']};font-size:12px;margin-top:2px;">
            NPC 친구들과 함께 나만의 소설을 써봐요!
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── 진행 바 (전체 너비) ───────────────────────────────────
    render_progress_bar()

    # ── 완성 화면 ─────────────────────────────────────────────
    if st.session_state.stage_idx >= 6:
        render_completion()
        return

    # ── 소설 자동 생성 단계 (stage_idx == 5) ──────────────────
    if st.session_state.stage_idx == 5:
        st.markdown(f"""
        <div style="background:#ffffff;border-radius:12px;padding:20px;text-align:center;
                    border:1.5px solid {THEME['primary']};margin:16px 0;">
            <div style="font-size:36px;margin-bottom:8px;">✨</div>
            <div style="color:{THEME['primary_dk']};font-size:16px;font-weight:700;margin-bottom:6px;">
                기승전결 완성! 소설을 만들어볼게요
            </div>
            <div style="color:{THEME['text']};font-size:13px;">
                주제: <b>{st.session_state.context.get('topic','')}</b>
            </div>
        </div>
        """, unsafe_allow_html=True)
        generate_novel()  # 자동 실행
        return

    # ── 첫 NPC 인사 ───────────────────────────────────────────
    if not st.session_state.npc_intro_done:
        add_npc_message(
            "루나",
            "안녕! 나는 루나야 🧝‍♀️ 오늘 글짓기 어드벤처를 함께할 거야!",
            ["오늘 정말 신났어요!", "좋은 일이 있었어요", "조금 피곤해요", "그냥 평범한 하루예요"],
            "오늘 기분이 어때? 또는 오늘 있었던 재미있는 일을 말해줘!"
        )
        st.session_state.npc_intro_done = True

    # ── 2컬럼 레이아웃 ────────────────────────────────────────
    col_left, col_right = st.columns([1, 1])

    # ══ 왼쪽: 대화창 ════════════════════════════════════════════
    with col_left:
        st.markdown(f"""
        <div style="color:{THEME['primary_dk']};font-size:13px;font-weight:600;margin-bottom:6px;">
            💬 NPC 대화
        </div>
        """, unsafe_allow_html=True)
        render_chat_history()

    # ══ 오른쪽: 선택창 + 입력창 ═════════════════════════════════
    with col_right:
        st.markdown(f"""
        <div style="color:{THEME['primary_dk']};font-size:13px;font-weight:600;margin-bottom:6px;">
            🎮 내 차례
        </div>
        """, unsafe_allow_html=True)

        # 스탯 카드
        render_stats_cards()

        # 키워드 선택 버튼
        render_keyword_buttons()

        st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)

        # 입력창
        stage = STAGES[st.session_state.stage_idx]
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

        # 전송 / 삭제 버튼
        col_send, col_clear = st.columns([4, 1])
        with col_send:
            send_label = "🚀 전송하기" if stage != "결론" else "🎉 소설 만들기!"
            if st.button(send_label, use_container_width=True, type="primary"):
                cleaned = user_input.strip()
                if not cleaned:
                    st.warning("내용을 입력하거나 버튼을 눌러줘요! 💬")
                else:
                    add_player_message(cleaned)
                    process_stage(cleaned)
                    st.rerun()

        with col_clear:
            if st.button("🗑️", use_container_width=True, help="입력 내용 지우기"):
                st.session_state.input_text = ""
                st.rerun()

        # 하단 안내
        st.markdown(f"""
        <div style="text-align:center;color:{THEME['text_muted']};font-size:11px;margin-top:8px;">
            권장 {char_limit}자 이내
        </div>
        """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()


# ⚠️ [Firestore 보안 규칙 설정 안내]
# Firebase Console > Firestore Database > 규칙(Rules) 탭에서
# 프로덕션 배포 전 반드시 적절한 보안 규칙으로 변경하세요.
# 테스트 모드(allow read, write: if true)는 모든 접근을 허용하므로 위험합니다.
#
# 권장 규칙 예시:
# rules_version = '2';
# service cloud.firestore {
#   match /databases/{database}/documents {
#     match /stories/{sessionId} {
#       allow write: if request.auth == null;
#       allow read: if false;
#     }
#   }
# }
