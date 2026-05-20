import streamlit as st
import requests
import re

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

def clean_html(text):
    return re.sub(r"<.*?>", "", text)

def search_news(query):
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }
    params = {"query": query, "display": 5, "sort": "date"}
    response = requests.get(
        "https://openapi.naver.com/v1/search/news.json",
        headers=headers,
        params=params,
    )
    return response.json().get("items", [])

def summarize(article, prompt_instruction):
    prompt = f"""다음 기사를 요약해줘. 반드시 한국어만 사용해. 한자나 영어 절대 금지.

지시사항: {prompt_instruction}

기사:
{article}"""
    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
        },
    )
    return response.json()["choices"][0]["message"]["content"]

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

# --- 초기 세션 상태 ---
if "my_prompts" not in st.session_state:
    st.session_state["my_prompts"] = {}

# --- UI ---
st.set_page_config(page_title="AI 맞춤 기사 요약", page_icon="📰")
st.title("📰 AI 맞춤 기사 요약")
st.caption("나만의 말투로 뉴스를 읽다")

tab1, tab2, tab3 = st.tabs(["📰 뉴스 요약", "⚙️ 내 프롬프트 설정", "🏪 프롬프트 마켓"])

# ===== 탭 1: 뉴스 요약 =====
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
        selected_article = clean_html(
            st.session_state["news_items"][idx]["title"] + "\n" +
            st.session_state["news_items"][idx]["description"]
        )
        st.session_state["selected_article"] = selected_article

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

    if style in PRESET_PROMPTS:
        prompt_instruction = PRESET_PROMPTS[style]
    else:
        prompt_instruction = st.session_state["my_prompts"][style]

    st.caption(f"현재 프롬프트: _{prompt_instruction}_")

    if st.button("요약하기", type="primary"):
        if article.strip():
            with st.spinner("요약 중..."):
                result = summarize(article, prompt_instruction)
            st.success(result)
        else:
            st.warning("기사 내용을 먼저 입력해주세요.")

# ===== 탭 2: 내 프롬프트 설정 =====
with tab2:
    st.subheader("⚙️ 나만의 프롬프트 만들기")
    st.caption("AI에게 어떤 방식으로 요약할지 직접 지시해보세요.")

    with st.expander("💡 프롬프트 작성 예시"):
        st.markdown("""
- `드라마 해설사처럼 극적으로, 이모티콘 많이 써서 3줄 요약해줘.`
- `뉴스 앵커처럼 딱딱하고 공식적인 말투로 핵심만 2줄로 요약해줘.`
- `초등학생에게 설명하듯이 비유를 들어서 쉽게 3줄 요약해줘.`
        """)

    new_name = st.text_input("프롬프트 이름", placeholder="예: 드라마틱하게")
    new_prompt = st.text_area(
        "프롬프트 내용",
        placeholder="AI에게 내릴 지시를 자유롭게 작성하세요.",
        height=100,
    )

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
                if ok:
                    st.success("마켓에 공유됐어요! '프롬프트 마켓' 탭에서 확인하세요.")
                else:
                    st.error("공유 중 오류가 발생했습니다.")
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

# ===== 탭 3: 프롬프트 마켓 =====
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
