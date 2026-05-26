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
    "친근하게": "친한 친구한테 말하듯 반말로, 쉽고 재미있게 3줄 요약해줘.",
    "전문적으로": "짧고 간결한 문어체로, 핵심 사실만 3줄 요약해줘.",
    "쉽게 설명": "중학생도 이해할 수 있도록 쉬운 단어로 3줄 요약해줘.",
}

SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

KST = timezone(timedelta(hours=9))

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
    return res.json()["choices"][0]["message"]["content"]

# ── 프롬프트 마켓 ──
def fetch_market_prompts():
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/prompts?select=*&order=likes.desc",
        headers=SUPABASE_HEADERS,
    )
    return res.json() if res.status_code == 200 else []

def upload_prompt(name, content):
    res = requests.post(
        f"{SUPABASE_URL}/rest/v1/prompts",
        headers={**SUPABASE_HEADERS, "Prefer": "return=representation"},
        json={"name": name, "content": content},
    )
    return res.status_code == 201

def like_prompt(prompt_id, current_likes):
    requests.patch(
        f"{SUPABASE_URL}/rest/v1/prompts?id=eq.{prompt_id}",
        headers=SUPABASE_HEADERS,
        json={"likes": current_likes + 1},
    )

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

# ───────────── UI ─────────────
st.set_page_config(page_title="AI 맞춤 기사 요약", page_icon="📰")
st.title("📰 AI 맞춤 기사 요약")
st.caption("나만의 말투로 뉴스를 읽다")

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
            with st.spinner("요약 중..."):
                result = summarize(article, prompt_instruction)
            st.session_state["last_summary"] = {"text": result, "style": style, "article": article}

            # ③ 자동 저장
            save_history(article[:40] + "...", result, style)
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
                    ok = upload_prompt(new_name, new_prompt)
                st.success("공유 완료!") if ok else st.error("공유 중 오류 발생.")
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
            with st.container(border=True):
                col_info, col_btn = st.columns([5, 2])
                with col_info:
                    st.markdown(f"**{p['name']}**")
                    st.caption(p["content"])
                with col_btn:
                    if st.button(f"👍 {p['likes']}", key=f"like_{p['id']}"):
                        like_prompt(p["id"], p["likes"])
                        st.session_state.pop("market_prompts", None)
                        st.rerun()
                    if st.button("내 목록에 추가", key=f"add_{p['id']}"):
                        st.session_state["my_prompts"][p["name"]] = p["content"]
                        st.success(f"'{p['name']}' 추가 완료!")

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
            st.markdown("**월 3,900원**")
            st.divider()
            st.markdown("✅ 무료 플랜의 모든 기능")
            st.markdown("🔒 요약 히스토리 **무제한**")
            st.markdown("🔒 기사 원문 **전체** 요약")
            st.markdown("🔒 요약 **길이 선택** (1줄/3줄/5줄)")
            st.markdown("🔒 광고 없이 이용")
            st.markdown("🔒 **프롬프트 자동 추천** AI")
            st.divider()
            st.button("💎 프리미엄 시작하기", type="primary", disabled=True)
            st.caption("준비 중입니다. 곧 오픈 예정!")

