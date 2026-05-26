import streamlit as st
import requests
import re
from datetime import datetime, timezone, timedelta

GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
NAVER_CLIENT_ID = st.secrets["NAVER_CLIENT_ID"]
NAVER_CLIENT_SECRET = st.secrets["NAVER_CLIENT_SECRET"]
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

PRESET_PROMPTS = {
    "친근하게": (
        "너는 친한 친구에게 오늘 뉴스를 재미있게 전해주는 사람이야. "
        "딱딱한 표현은 쓰지 말고 자연스러운 반말로 얘기해줘. "
        "어려운 용어가 나오면 일상적인 말로 바꿔서 설명하고, "
        "이모티콘을 1~2개 섞어서 읽는 재미를 더해줘. "
        "4줄로, 핵심 내용과 '그래서 나한테 뭐가 중요한지'까지 포함해서 요약해줘."
    ),
    "전문적으로": (
        "너는 10년 경력의 시니어 경제 전문 기자야. "
        "육하원칙 기반의 간결한 문어체로, 핵심 수치와 사실만 담아줘. "
        "불필요한 수식어와 감정적 표현은 철저히 배제하고, "
        "독자가 스스로 판단할 수 있도록 배경 맥락도 한 문장 포함해줘. "
        "4줄로 정리하되, 각 줄이 독립적인 핵심 정보를 담도록 구성해줘."
    ),
    "쉽게 설명": (
        "너는 복잡한 뉴스를 누구나 이해하게 풀어주는 선생님이야. "
        "처음 이 뉴스를 접하는 사람도 이해할 수 있도록 쉬운 단어만 사용하고, "
        "어려운 개념은 반드시 친숙한 비유나 예시로 바꿔서 설명해줘. "
        "'왜 이 뉴스가 중요한지', '내 생활에 어떤 영향을 주는지'도 포함해줘. "
        "4줄로 요약하되, 마지막 줄은 핵심 한 문장 정리로 마무리해줘."
    ),
}

SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

KST = timezone(timedelta(hours=9))

DAILY_KEYWORDS = [k.strip() for k in st.secrets.get("DAILY_KEYWORDS", "경제,인공지능,정치").split(",")]
DAILY_STYLE    = st.secrets.get("DAILY_STYLE", "쉽게 설명")

# ───────────── 유틸 함수 ─────────────

def clean_html(text):
    return re.sub(r"<.*?>", "", text)

def search_news(query):
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }
    params = {"query": query, "display": 5, "sort": "date"}
    res = requests.get(
        "https://openapi.naver.com/v1/search/news.json",
        headers=headers, params=params,
    )
    return res.json().get("items", [])

def summarize(article, prompt_instruction):
    prompt = f"""다음 기사를 요약해줘. 반드시 한국어만 사용해. 한자나 영어 절대 금지.

지시사항: {prompt_instruction}

기사:
{article}"""
    res = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={"model": "llama-3.3-70b-versatile",
              "messages": [{"role": "user", "content": prompt}]},
    )
    data = res.json()
    if "choices" not in data:
        error_msg = data.get("error", {}).get("message", str(data))
        raise ValueError(f"API 오류: {error_msg}")
    return data["choices"][0]["message"]["content"]

# ── 프롬프트 마켓 ──
def fetch_market_prompts():
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/prompts?select=*&order=likes.desc",
        headers=SUPABASE_HEADERS,
    )
    return res.json() if res.status_code == 200 else []

def upload_prompt(name, content):
    """업로드 성공 시 생성된 id 반환, 실패 시 None 반환"""
    res = requests.post(
        f"{SUPABASE_URL}/rest/v1/prompts",
        headers={**SUPABASE_HEADERS, "Prefer": "return=representation"},
        json={"name": name, "content": content},
    )
    if res.status_code == 201:
        data = res.json()
        return data[0]["id"] if data else None
    return None

def like_prompt(prompt_id, current_likes):
    requests.patch(
        f"{SUPABASE_URL}/rest/v1/prompts?id=eq.{prompt_id}",
        headers=SUPABASE_HEADERS,
        json={"likes": current_likes + 1},
    )

def delete_prompt(prompt_id):
    res = requests.delete(
        f"{SUPABASE_URL}/rest/v1/prompts?id=eq.{prompt_id}",
        headers=SUPABASE_HEADERS,
    )
    return res.status_code in (200, 204)

# ── 오늘의 브리핑 ──
def fetch_daily_feed():
    """오늘 날짜의 브리핑이 Supabase에 있으면 바로 반환, 없으면 생성 후 반환"""
    today = datetime.now(KST).strftime("%Y-%m-%d")
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/daily_feed?feed_date=eq.{today}&select=*&order=id.asc",
        headers=SUPABASE_HEADERS,
    )
    if res.status_code == 200 and res.json():
        return res.json(), False   # (데이터, 새로 생성 여부)

    # 오늘 데이터 없음 → 새로 생성
    instruction = PRESET_PROMPTS.get(DAILY_STYLE, PRESET_PROMPTS["쉽게 설명"])
    feed_items = []
    for keyword in DAILY_KEYWORDS:
        try:
            items = search_news(keyword)
            if not items:
                continue
            article_text = clean_html(items[0]["title"] + "\n" + items[0]["description"])
            summary_text = summarize(article_text, instruction)
            row = {
                "keyword":       keyword,
                "article_title": clean_html(items[0]["title"]),
                "summary":       summary_text,
                "style":         DAILY_STYLE,
                "feed_date":     today,
            }
            requests.post(
                f"{SUPABASE_URL}/rest/v1/daily_feed",
                headers={**SUPABASE_HEADERS, "Prefer": "return=minimal"},
                json=row,
            )
            feed_items.append(row)
        except Exception:
            continue
    return feed_items, True

# ── ③ 요약 히스토리 ──
def save_history(article_preview, summary, style):
    requests.post(
        f"{SUPABASE_URL}/rest/v1/history",
        headers={**SUPABASE_HEADERS, "Prefer": "return=minimal"},
        json={"article_preview": article_preview,
              "summary": summary,
              "style": style},
    )

def fetch_history():
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/history?select=*&order=created_at.desc&limit=20",
        headers=SUPABASE_HEADERS,
    )
    return res.json() if res.status_code == 200 else []

# ───────────── 세션 초기화 ─────────────
if "my_prompts" not in st.session_state:
    st.session_state["my_prompts"] = {}
if "last_summary" not in st.session_state:
    st.session_state["last_summary"] = None
if "liked_ids" not in st.session_state:
    st.session_state["liked_ids"] = set()       # 이번 세션에서 좋아요한 id
if "my_uploaded_ids" not in st.session_state:
    st.session_state["my_uploaded_ids"] = set() # 이번 세션에서 올린 프롬프트 id

# ───────────── UI ─────────────
st.set_page_config(
    page_title="AI 맞춤 기사 요약",
    page_icon="📰",
    layout="wide",
)

# ── CSS 주입 ──
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&display=swap');

html, body, [class*="css"] {
    font-family: 'Noto Sans KR', sans-serif;
}

/* 상단 햄버거 메뉴·푸터 숨김 */
#MainMenu {visibility: hidden;}
footer     {visibility: hidden;}

/* 메인 여백 */
.main .block-container {
    padding-top: 1.5rem;
    padding-bottom: 2rem;
}

/* 탭 스타일 */
.stTabs [data-baseweb="tab-list"] {
    gap: 6px;
    background: #eff0f7;
    border-radius: 14px;
    padding: 5px;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 10px;
    padding: 8px 18px;
    font-weight: 600;
    color: #6b7280;
}
.stTabs [aria-selected="true"] {
    background: white !important;
    color: #5b4fe9 !important;
    box-shadow: 0 2px 10px rgba(91,79,233,0.15);
}

/* Primary 버튼 */
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border: none;
    border-radius: 12px;
    font-weight: 700;
    letter-spacing: 0.3px;
    transition: transform .15s, box-shadow .15s;
}
.stButton > button[kind="primary"]:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(102,126,234,0.45);
}

/* Secondary 버튼 */
.stButton > button[kind="secondary"] {
    border-radius: 12px;
    border: 1.5px solid #667eea;
    color: #667eea;
    font-weight: 600;
}

/* 입력창 */
.stTextInput  > div > div > input,
.stTextArea   > div > div > textarea {
    border-radius: 10px;
    border: 1.5px solid #e2e8f0;
    transition: border-color .2s, box-shadow .2s;
}
.stTextInput  > div > div > input:focus,
.stTextArea   > div > div > textarea:focus {
    border-color: #667eea;
    box-shadow: 0 0 0 3px rgba(102,126,234,0.15);
}

/* 알림 박스 둥글게 */
.stSuccess, .stWarning, .stError, .stInfo {
    border-radius: 12px;
}

/* 사이드바 다크 그라디언트 */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg,#1a1a2e 0%,#16213e 55%,#0f3460 100%) !important;
}
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] div {
    color: #e2e8f0 !important;
}
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
    color: #ffffff !important;
}
[data-testid="stSidebar"] hr {
    border-color: rgba(255,255,255,0.15) !important;
}
</style>
""", unsafe_allow_html=True)

# ── 히어로 헤더 ──
st.markdown("""
<div style="
    background: linear-gradient(135deg,#667eea 0%,#764ba2 100%);
    padding: 2rem 2.5rem;
    border-radius: 20px;
    margin-bottom: 1.5rem;
    color: white;
">
    <h1 style="margin:0; font-size:2rem; font-weight:900; letter-spacing:-0.5px;">
        📰 AI 맞춤 기사 요약
    </h1>
    <p style="margin:0.4rem 0 0; font-size:1rem; opacity:0.88;">
        나만의 말투와 스타일로 뉴스를 읽다
    </p>
</div>
""", unsafe_allow_html=True)

# ── 사이드바 ──
with st.sidebar:
    st.markdown("## 📰 AI 뉴스 요약")
    st.caption("나만의 말투로 뉴스를 읽다")
    st.divider()

    st.markdown("### 🚀 빠른 사용법")
    st.markdown("""
1. **뉴스 요약** 탭에서 검색
2. 기사 선택 후 스타일 선택
3. **요약하기** 클릭
4. 결과 복사 후 공유!
    """)
    st.divider()

    # 통계
    st.markdown("### 📊 서비스 현황")
    market_count = len(fetch_market_prompts())
    st.metric("공유된 프롬프트", f"{market_count}개")
    st.divider()

    # ── 광고란 ──
    st.markdown("### 📢 광고")
    st.markdown("""
<div style="
    background: linear-gradient(135deg,#ffecd2,#fcb69f);
    border-radius: 14px;
    padding: 14px;
    text-align: center;
    margin-bottom: 10px;
">
    <p style="font-size:9px; color:#b45309; margin:0 0 6px; font-weight:700;
              letter-spacing:1px;">ADVERTISEMENT</p>
    <div style="
        background: rgba(255,255,255,0.6);
        border-radius: 10px;
        height: 160px;
        display: flex;
        align-items: center;
        justify-content: center;
        flex-direction: column;
        gap: 6px;
    ">
        <p style="font-size:1.5rem; margin:0;">🛍️</p>
        <p style="color:#92400e; font-weight:700; margin:0; font-size:0.85rem;">
            광고 영역
        </p>
        <p style="color:#b45309; font-size:0.7rem; margin:0;">240 × 160</p>
    </div>
</div>

<div style="
    background: linear-gradient(135deg,#d4fc79,#96e6a1);
    border-radius: 14px;
    padding: 14px;
    text-align: center;
">
    <p style="font-size:9px; color:#166534; margin:0 0 6px; font-weight:700;
              letter-spacing:1px;">ADVERTISEMENT</p>
    <div style="
        background: rgba(255,255,255,0.6);
        border-radius: 10px;
        height: 80px;
        display: flex;
        align-items: center;
        justify-content: center;
        flex-direction: column;
        gap: 4px;
    ">
        <p style="color:#14532d; font-weight:700; margin:0; font-size:0.85rem;">
            배너 광고 영역
        </p>
        <p style="color:#166534; font-size:0.7rem; margin:0;">240 × 80</p>
    </div>
</div>
    """, unsafe_allow_html=True)

# ── 오늘의 브리핑 섹션 ──
today_label = datetime.now(KST).strftime("%Y년 %m월 %d일")

st.markdown(f"""
<div style="
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 0.8rem;
">
    <span style="
        font-size: 1.3rem;
        font-weight: 900;
        color: #2d3748;
    ">📅 오늘의 뉴스 브리핑</span>
    <span style="
        background: #ede9fe;
        color: #6d28d9;
        font-size: 0.75rem;
        font-weight: 700;
        padding: 3px 10px;
        border-radius: 999px;
    ">{today_label}</span>
    <span style="
        background: #f0fdf4;
        color: #15803d;
        font-size: 0.75rem;
        font-weight: 700;
        padding: 3px 10px;
        border-radius: 999px;
    ">✨ {DAILY_STYLE} 스타일</span>
</div>
""", unsafe_allow_html=True)

if "daily_feed" not in st.session_state:
    with st.spinner("오늘의 기사를 요약하는 중입니다... (첫 방문 시 최대 20초 소요)"):
        st.session_state["daily_feed"], is_new = fetch_daily_feed()

feed = st.session_state["daily_feed"]

if feed:
    cols = st.columns(len(feed))
    for col, item in zip(cols, feed):
        with col:
            st.markdown(f"""
<div style="
    background: white;
    border-radius: 16px;
    padding: 1.2rem 1.4rem;
    box-shadow: 0 2px 16px rgba(91,79,233,0.10);
    border-top: 4px solid #667eea;
    height: 100%;
    min-height: 180px;
">
    <span style="
        background: #ede9fe;
        color: #6d28d9;
        font-size: 0.7rem;
        font-weight: 800;
        padding: 2px 10px;
        border-radius: 999px;
        letter-spacing: 0.5px;
    ">#{item['keyword']}</span>
    <p style="
        font-size: 0.85rem;
        font-weight: 700;
        color: #374151;
        margin: 0.6rem 0 0.4rem;
        line-height: 1.4;
    ">{item['article_title'][:40]}{'...' if len(item['article_title']) > 40 else ''}</p>
    <p style="
        font-size: 0.82rem;
        color: #6b7280;
        line-height: 1.6;
        margin: 0;
    ">{item['summary']}</p>
</div>
            """, unsafe_allow_html=True)
else:
    st.info("오늘의 브리핑을 불러오지 못했습니다. 잠시 후 새로고침해주세요.")

st.markdown("<div style='margin-bottom:1.5rem'></div>", unsafe_allow_html=True)

# ── 탭 ──
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📰 뉴스 요약",
    "⚙️ 내 프롬프트 설정",
    "🏪 프롬프트 마켓",
    "📚 요약 히스토리",
    "💎 프리미엄",
])

# ══════════════════════════════════════
# 탭 1 — 뉴스 요약
# ══════════════════════════════════════
with tab1:
    st.subheader("🔍 뉴스 검색")
    query = st.text_input("검색어를 입력하세요", placeholder="예: 금리, 반도체, 대선")

    if st.button("검색"):
        if query.strip():
            with st.spinner("기사 검색 중..."):
                items = search_news(query)
            if items:
                st.session_state["news_items"] = items
            else:
                st.warning("검색 결과가 없습니다.")

    if "news_items" in st.session_state:
        titles = [clean_html(item["title"]) for item in st.session_state["news_items"]]
        selected = st.radio("기사를 선택하세요", titles)
        idx = titles.index(selected)
        st.session_state["selected_article"] = clean_html(
            st.session_state["news_items"][idx]["title"] + "\n" +
            st.session_state["news_items"][idx]["description"]
        )

    st.divider()
    st.subheader("📝 기사 요약")

    article = st.text_area(
        "기사 내용 (검색 후 자동 입력되거나 직접 붙여넣기 가능)",
        value=st.session_state.get("selected_article", ""),
        height=150,
    )

    my_prompt_names = list(st.session_state["my_prompts"].keys())
    all_styles = list(PRESET_PROMPTS.keys()) + my_prompt_names
    style = st.radio("요약 스타일 선택", all_styles, horizontal=True)
    prompt_instruction = PRESET_PROMPTS.get(style, st.session_state["my_prompts"].get(style, ""))
    st.caption(f"현재 프롬프트: _{prompt_instruction}_")

    if st.button("요약하기", type="primary"):
        if article.strip():
            try:
                with st.spinner("요약 중..."):
                    result = summarize(article, prompt_instruction)
                st.session_state["last_summary"] = {"text": result, "style": style, "article": article}
                save_history(article[:40] + "...", result, style)
            except ValueError as e:
                st.error(str(e))
        else:
            st.warning("기사 내용을 먼저 입력해주세요.")

    # 요약 결과 표시
    if st.session_state["last_summary"]:
        data = st.session_state["last_summary"]
        st.success("✅ 요약 완료!")
        st.markdown(f"**스타일:** {data['style']}")
        st.markdown(data["text"])

        # ② 공유 버튼
        st.divider()
        col_copy, col_kakao = st.columns(2)
        with col_copy:
            st.code(data["text"], language=None)   # 우상단 복사 아이콘 자동 생성
            st.caption("⬆️ 우상단 아이콘으로 복사")
        with col_kakao:
            st.info("📤 복사 후 카카오톡·SNS에 바로 공유하세요!")

# ══════════════════════════════════════
# 탭 2 — 내 프롬프트 설정
# ══════════════════════════════════════
with tab2:
    st.subheader("⚙️ 나만의 프롬프트 만들기")
    st.caption("AI에게 어떤 방식으로 요약할지 직접 지시해보세요.")

    with st.expander("💡 프롬프트 작성 예시"):
        st.markdown("""
- `드라마 해설사처럼 극적으로, 이모티콘 많이 써서 3줄 요약해줘.`
- `뉴스 앵커처럼 딱딱하고 공식적인 말투로 핵심만 2줄로 요약해줘.`
- `초등학생에게 설명하듯이 비유를 들어서 쉽게 3줄 요약해줘.`
        """)

    new_name   = st.text_input("프롬프트 이름", placeholder="예: 드라마틱하게")
    new_prompt = st.text_area("프롬프트 내용",
                              placeholder="AI에게 내릴 지시를 자유롭게 작성하세요.", height=100)

    col_save, col_share = st.columns(2)
    with col_save:
        if st.button("내 목록에 저장", type="primary"):
            if new_name.strip() and new_prompt.strip():
                st.session_state["my_prompts"][new_name] = new_prompt
                st.success(f"'{new_name}' 저장 완료!")
            else:
                st.warning("이름과 내용을 모두 입력해주세요.")
    with col_share:
        if st.button("마켓에 공유하기"):
            if new_name.strip() and new_prompt.strip():
                with st.spinner("공유 중..."):
                    new_id = upload_prompt(new_name, new_prompt)
                if new_id:
                    st.session_state["my_uploaded_ids"].add(new_id)
                    st.session_state.pop("market_prompts", None)  # 마켓 캐시 초기화
                    st.success("공유 완료! '프롬프트 마켓' 탭에서 확인하세요.")
                else:
                    st.error("공유 중 오류 발생.")
            else:
                st.warning("이름과 내용을 모두 입력해주세요.")

    if st.session_state["my_prompts"]:
        st.divider()
        st.subheader("📋 저장된 내 프롬프트")
        for name, content in list(st.session_state["my_prompts"].items()):
            col1, col2 = st.columns([4, 1])
            col1.markdown(f"**{name}**: {content}")
            if col2.button("삭제", key=f"del_{name}"):
                del st.session_state["my_prompts"][name]
                st.rerun()

# ══════════════════════════════════════
# 탭 3 — 프롬프트 마켓
# ══════════════════════════════════════
with tab3:
    st.subheader("🏪 프롬프트 마켓")
    st.caption("다른 사용자가 공유한 프롬프트를 탐색하고 내 목록에 추가하세요.")

    if st.button("새로고침"):
        st.session_state.pop("market_prompts", None)

    if "market_prompts" not in st.session_state:
        with st.spinner("불러오는 중..."):
            st.session_state["market_prompts"] = fetch_market_prompts()

    market_prompts = st.session_state["market_prompts"]

    if not market_prompts:
        st.info("아직 공유된 프롬프트가 없어요. 첫 번째로 공유해보세요!")
    else:
        for p in market_prompts:
            pid = p["id"]
            already_liked = pid in st.session_state["liked_ids"]
            is_mine       = pid in st.session_state["my_uploaded_ids"]

            with st.container(border=True):
                col_info, col_btn = st.columns([5, 2])
                with col_info:
                    label = f"**{p['name']}**"
                    if is_mine:
                        label += "  🙋 내가 올린 프롬프트"
                    st.markdown(label)
                    st.caption(p["content"])
                with col_btn:
                    # 좋아요 — 이미 눌렀으면 비활성화
                    like_label = f"👍 {p['likes']}" if not already_liked else f"✅ {p['likes']}"
                    if st.button(like_label, key=f"like_{pid}", disabled=already_liked):
                        like_prompt(pid, p["likes"])
                        st.session_state["liked_ids"].add(pid)
                        st.session_state.pop("market_prompts", None)
                        st.rerun()

                    # 내 목록에 추가
                    if st.button("내 목록에 추가", key=f"add_{pid}"):
                        st.session_state["my_prompts"][p["name"]] = p["content"]
                        st.success(f"'{p['name']}' 추가 완료!")

                    # 삭제 — 본인 프롬프트만 표시
                    if is_mine:
                        if st.button("🗑️ 삭제", key=f"del_market_{pid}", type="secondary"):
                            with st.spinner("삭제 중..."):
                                ok = delete_prompt(pid)
                            if ok:
                                st.session_state["my_uploaded_ids"].discard(pid)
                                st.session_state.pop("market_prompts", None)
                                st.success("삭제됐어요.")
                                st.rerun()
                            else:
                                st.error("삭제 중 오류 발생.")

# ══════════════════════════════════════
# 탭 4 — ③ 요약 히스토리
# ══════════════════════════════════════
with tab4:
    st.subheader("📚 요약 히스토리")
    st.caption("최근 요약한 기사 20건을 모아볼 수 있어요.")

    if st.button("새로고침", key="refresh_history"):
        st.session_state.pop("history_data", None)

    if "history_data" not in st.session_state:
        with st.spinner("불러오는 중..."):
            st.session_state["history_data"] = fetch_history()

    history = st.session_state["history_data"]

    if not history:
        st.info("아직 요약한 기사가 없어요. '뉴스 요약' 탭에서 요약해보세요!")
    else:
        for item in history:
            with st.container(border=True):
                # 시간 변환 (UTC → KST)
                try:
                    dt_utc = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
                    dt_kst = dt_utc.astimezone(KST).strftime("%Y.%m.%d %H:%M")
                except Exception:
                    dt_kst = item["created_at"][:16]

                col_meta, col_style = st.columns([4, 1])
                col_meta.markdown(f"**{item['article_preview']}**")
                col_style.markdown(f"`{item['style']}`")
                st.caption(f"🕐 {dt_kst}")
                st.markdown(item["summary"])

# ══════════════════════════════════════
# 탭 5 — ④ 프리미엄
# ══════════════════════════════════════
with tab5:
    st.subheader("💎 프리미엄 플랜")

    col_free, col_premium = st.columns(2)

    with col_free:
        with st.container(border=True):
            st.markdown("### 🆓 무료 플랜")
            st.markdown("**현재 이용 중**")
            st.divider()
            st.markdown("✅ 뉴스 검색 및 요약")
            st.markdown("✅ 프리셋 스타일 3종")
            st.markdown("✅ 커스텀 프롬프트 제작")
            st.markdown("✅ 프롬프트 마켓 이용")
            st.markdown("✅ 요약 히스토리 20건")
            st.divider()
            st.markdown("### 무료")

    with col_premium:
        with st.container(border=True):
            st.markdown("### 💎 프리미엄 플랜")
            st.markdown("**월 4,900원**")
            st.divider()
            st.markdown("✅ 무료 플랜의 모든 기능")
            st.markdown("🔒 요약 히스토리 **무제한**")
            st.markdown("🔒 기사 원문 **전체** 요약")
            st.markdown("🔒 요약 **길이 선택** (1줄/3줄/4줄)")
            st.markdown("🔒 광고 없이 이용")
            st.markdown("🔒 **프롬프트 자동 추천** AI")
            st.divider()
            st.button("💎 프리미엄 시작하기", type="primary", disabled=True)
            st.caption("준비 중입니다. 곧 오픈 예정!")

