# ============================================================
# W_project.py
# 초등학생 글짓기 서포트 프로그램
# 이스 이터널 스타일 NPC 대화 + 화이트/스카이블루 UI
# ============================================================

import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
from google import genai
import datetime

# ── 상수 ──────────────────────────────────────────────────────
GEMINI_MODEL = "gemini-2.5-flash"

# ── UI 테마 설정 ───────────────────────────────────────────────
# 여기서 색상을 바꾸면 전체 UI에 반영됩니다
THEME = {
    "bg":         "#f0f8ff",   # 앱 전체 배경 (하늘빛 흰색)
    "card":       "#ffffff",   # 카드/대화창 배경
    "card_bg":    "#e3f2fd",   # 연한 카드 배경 (스탯 카드 등)
    "border":     "#90caf9",   # 테두리 색
    "primary":    "#2196f3",   # 메인 강조색 (버튼, 제목)
    "primary_dk": "#1565c0",   # 진한 강조색
    "text":       "#1a237e",   # 본문 텍스트
    "text_muted": "#90caf9",   # 흐린 텍스트
    "danger":     "#ef5350",   # 글자수 초과 경고색
    "fire":       "#ff7043",   # 연속작성 불꽃색
}

# 글짓기 단계 정의
STAGES = ["기분탐색", "주제헌팅", "서론", "본론", "결론", "완성"]
STAGE_ICONS = ["💬", "🎯", "📖", "✍️", "🏁", "🌟"]
STAGE_LABELS = ["기분 탐색", "주제 헌팅", "서론 쓰기", "본론 쓰기", "결론 쓰기", "완성!"]

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


def call_gemini(prompt: str) -> dict:
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
        "loading": False,
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


def render_progress_bar():
    stage_idx = st.session_state.stage_idx
    total = len(STAGES) - 1
    progress = min(stage_idx / total, 1.0)

    st.markdown(f"""
    <div style="background:#ffffff;padding:12px 16px;border-radius:12px;margin-bottom:16px;border:1px solid {THEME['border']};box-shadow:0 2px 8px #e3f2fd;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
            <span style="color:{THEME['primary_dk']};font-size:13px;font-weight:600;">✍️ 글짓기 여정</span>
            <span style="color:{THEME['primary']};font-size:13px;font-weight:700;">{int(progress*100)}%</span>
        </div>
        <div style="background:#e3f2fd;border-radius:8px;height:10px;overflow:hidden;">
            <div style="background:linear-gradient(90deg,#64b5f6,#2196f3);width:{progress*100}%;height:100%;border-radius:8px;transition:width 0.5s;"></div>
        </div>
        <div style="display:flex;justify-content:space-between;margin-top:8px;">
            {"".join([f'<span style="font-size:11px;color:{"#2196f3" if i <= stage_idx else "#b0bec5"};">{STAGE_ICONS[i]}{STAGE_LABELS[i]}</span>' for i in range(len(STAGES))])}
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_chat_history():
    for msg in st.session_state.chat_history:
        if msg["type"] == "npc":
            npc = NPC_CHARACTERS.get(msg["npc"], NPC_CHARACTERS["루나"])
            st.markdown(f"""
            <div style="background:#ffffff;border:1.5px solid {THEME['border']};border-radius:12px;padding:14px 16px;margin:8px 0;box-shadow:0 2px 6px #e3f2fd;">
                <div style="color:{THEME['primary']};font-size:13px;font-weight:700;margin-bottom:6px;">
                    {npc['emoji']} {msg['npc']} <span style="font-size:11px;color:{THEME['text_muted']};">({npc['role']})</span>
                </div>
                <div style="color:{THEME['text']};font-size:15px;line-height:1.6;">{msg['message']}</div>
                {f'<div style="color:{THEME["primary"]};font-size:13px;margin-top:8px;font-style:italic;">❓ {msg["question"]}</div>' if msg.get('question') else ''}
            </div>
            """, unsafe_allow_html=True)

        elif msg["type"] == "player":
            st.markdown(f"""
            <div style="display:flex;justify-content:flex-end;margin:8px 0;">
                <div style="background:#e3f2fd;border-radius:12px 12px 2px 12px;padding:10px 14px;max-width:80%;border:1px solid {THEME['border']};">
                    <div style="color:{THEME['primary']};font-size:13px;font-weight:600;margin-bottom:4px;">🧒 나</div>
                    <div style="color:{THEME['text']};font-size:14px;">{msg['message']}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)


def render_keyword_buttons():
    """NPC 추천 키워드를 2x2 버튼 그리드로 렌더링"""
    if not st.session_state.suggested_keywords:
        return

    st.markdown(f'<div style="color:{THEME["primary"]};font-size:13px;margin:8px 0 6px;">💡 아래 문장을 눌러 입력창에 추가해요!</div>', unsafe_allow_html=True)

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
                if current:
                    st.session_state.input_text = current + " " + kw
                else:
                    st.session_state.input_text = kw
                st.rerun()


def render_stats_cards():
    """다이어트 앱 스타일 스탯 카드"""
    stage = STAGES[st.session_state.stage_idx]
    char_limit = CHAR_LIMITS.get(stage, 100)
    current_len = len(st.session_state.input_text)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"""
        <div style="background:{THEME['card_bg']};border-radius:10px;padding:10px;text-align:center;border:1px solid {THEME['border']};">
            <div style="color:{THEME['text_muted']};font-size:11px;">현재 단계</div>
            <div style="color:{THEME['primary']};font-size:18px;font-weight:700;">{STAGE_ICONS[st.session_state.stage_idx]}</div>
            <div style="color:{THEME['primary_dk']};font-size:12px;">{STAGE_LABELS[st.session_state.stage_idx]}</div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        color = THEME['danger'] if current_len > char_limit else THEME['primary']
        st.markdown(f"""
        <div style="background:{THEME['card_bg']};border-radius:10px;padding:10px;text-align:center;border:1px solid {THEME['border']};">
            <div style="color:{THEME['text_muted']};font-size:11px;">글자 수</div>
            <div style="color:{color};font-size:18px;font-weight:700;">{current_len}</div>
            <div style="color:#b0bec5;font-size:12px;">/ {char_limit}자 권장</div>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        streak = len([m for m in st.session_state.chat_history if m["type"] == "player"])
        st.markdown(f"""
        <div style="background:{THEME['card_bg']};border-radius:10px;padding:10px;text-align:center;border:1px solid {THEME['border']};">
            <div style="color:{THEME['text_muted']};font-size:11px;">응답 횟수</div>
            <div style="color:{THEME['fire']};font-size:18px;font-weight:700;">{streak}🔥</div>
            <div style="color:#b0bec5;font-size:12px;">연속 작성</div>
        </div>
        """, unsafe_allow_html=True)


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
            f"🎉 완성! {result.get('full_review', '정말 훌륭한 글이에요!')}",
        )
        st.session_state.stage_idx = 5
        st.session_state.context["badge"] = badge

    save_story_to_firestore(
        st.session_state.session_id,
        stage,
        user_input,
        str(result)
    )

    # 입력창 초기화 (키워드는 add_npc_message에서 이미 저장됨)
    st.session_state.input_text = ""


# ── 완성 화면 ─────────────────────────────────────────────────
def render_completion():
    ctx = st.session_state.context
    badge = ctx.get("badge", "글짓기 영웅")

    st.markdown(f"""
    <div style="background:linear-gradient(135deg,#e3f2fd,#bbdefb);border-radius:16px;padding:28px;text-align:center;border:2px solid {THEME['primary']};margin:16px 0;">
        <div style="font-size:48px;margin-bottom:12px;">🌟</div>
        <div style="color:{THEME['primary_dk']};font-size:22px;font-weight:700;margin-bottom:8px;">글짓기 완성!</div>
        <div style="background:#ffffff;border-radius:20px;display:inline-block;padding:6px 20px;margin:8px 0;border:1px solid {THEME['border']};">
            <span style="color:{THEME['primary']};font-size:14px;font-weight:600;">🏅 {badge}</span>
        </div>
        <div style="color:{THEME['text']};font-size:13px;margin-top:12px;">오늘의 글짓기 여정을 모두 완료했어요!</div>
    </div>
    """, unsafe_allow_html=True)

    with st.expander("📖 내가 쓴 글 보기", expanded=True):
        topic = ctx.get("topic", "")
        intro = ctx.get("intro", "")
        body = ctx.get("body", "")
        conclusion = ctx.get("conclusion", "")

        st.markdown(f"""
        <div style="background:#ffffff;border-radius:12px;padding:20px;line-height:1.8;color:{THEME['text']};font-size:15px;border:1px solid {THEME['border']};">
            <div style="color:{THEME['primary']};font-weight:700;font-size:16px;margin-bottom:12px;">📌 주제: {topic}</div>
            <div style="margin-bottom:12px;"><span style="color:#26a69a;font-weight:600;">[서론]</span><br>{intro}</div>
            <div style="margin-bottom:12px;"><span style="color:{THEME['fire']};font-weight:600;">[본론]</span><br>{body}</div>
            <div><span style="color:{THEME['primary_dk']};font-weight:600;">[결론]</span><br>{conclusion}</div>
        </div>
        """, unsafe_allow_html=True)

    if st.button("🔄 새로운 글짓기 시작하기", use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()


# ── 메인 앱 ───────────────────────────────────────────────────
def main():
    st.set_page_config(
        page_title="글짓기 어드벤처 ✍️",
        page_icon="✍️",
        layout="centered",
        initial_sidebar_state="collapsed"
    )

    # 화이트 + 스카이블루 테마 스타일
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
    </style>
    """, unsafe_allow_html=True)

    # 세션 초기화
    init_session()

    # 헤더
    st.markdown(f"""
    <div style="text-align:center;padding:20px 0 10px;">
        <div style="font-size:32px;">✍️</div>
        <div style="color:{THEME['primary_dk']};font-size:20px;font-weight:700;">글짓기 어드벤처</div>
        <div style="color:{THEME['text_muted']};font-size:12px;margin-top:4px;">NPC 친구들과 함께 나만의 이야기를 써봐요!</div>
    </div>
    """, unsafe_allow_html=True)

    # 진행 바
    render_progress_bar()

    # 완성 단계
    if st.session_state.stage_idx >= len(STAGES) - 1:
        render_completion()
        return

    # 첫 NPC 인사
    if not st.session_state.npc_intro_done:
        add_npc_message(
            "루나",
            "안녕! 나는 루나야 🧝‍♀️ 오늘 글짓기 어드벤처를 함께할 거야!",
            ["오늘 정말 신났어요!", "좋은 일이 있었어요", "조금 피곤해요", "그냥 평범한 하루예요"],
            "오늘 기분이 어때? 또는 오늘 있었던 재미있는 일을 말해줘!"
        )
        st.session_state.npc_intro_done = True

    # 스탯 카드
    render_stats_cards()
    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

    # 대화창
    with st.container():
        render_chat_history()

    # 키워드 버튼
    render_keyword_buttons()

    # 입력창
    stage = STAGES[st.session_state.stage_idx]
    char_limit = CHAR_LIMITS.get(stage, 100)

    placeholders = {
        "기분탐색": "오늘 기분이나 있었던 일을 써봐요 (버튼을 눌러도 돼요!)",
        "주제헌팅": "어떤 주제로 글을 쓰고 싶어요?",
        "서론": "글의 시작을 써봐요! 어떻게 이야기를 열까요?",
        "본론": "본론에서 하고 싶은 이야기를 써봐요!",
        "결론": "글을 어떻게 마무리할까요?",
    }

    user_input = st.text_area(
        label="📝 내 이야기",
        value=st.session_state.input_text,
        placeholder=placeholders.get(stage, "여기에 써봐요!"),
        max_chars=char_limit,
        height=100,
        label_visibility="collapsed"
    )
    st.session_state.input_text = user_input

    # 전송/삭제 버튼
    col_send, col_clear = st.columns([4, 1])
    with col_send:
        send_label = "🚀 전송하기" if stage != "결론" else "🎉 완성하기"
        if st.button(send_label, use_container_width=True, type="primary"):
            cleaned = user_input.strip()
            if not cleaned:
                st.warning("먼저 내용을 입력하거나 버튼을 선택해줘요! 💬")
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
    <div style="text-align:center;color:{THEME['text_muted']};font-size:11px;margin-top:20px;padding-bottom:20px;">
        현재 단계: {STAGE_LABELS[st.session_state.stage_idx]} · 권장 {char_limit}자 이내
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
