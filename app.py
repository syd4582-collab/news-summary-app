import streamlit as st
import requests
import re

GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
NAVER_CLIENT_ID = st.secrets["NAVER_CLIENT_ID"]
NAVER_CLIENT_SECRET = st.secrets["NAVER_CLIENT_SECRET"]

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

def summarize(article, style):
    prompt = f"""다음 기사를 아래 스타일로 3줄 요약해줘.
반드시 한국어만 사용해. 한자나 영어 절대 금지.

스타일: {style}
- 친근하게: 친한 친구한테 말하듯 반말로, 쉽고 재미있게
- 전문적으로: 짧고 간결한 문어체, 핵심만
- 쉽게 설명: 중학생도 이해할 수 있도록 쉬운 단어로

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

# --- UI ---
st.set_page_config(page_title="AI 맞춤 기사 요약", page_icon="📰")
st.title("📰 AI 맞춤 기사 요약")
st.caption("나만의 말투로 뉴스를 읽다")

# --- 뉴스 검색 ---
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

# --- 요약 ---
st.subheader("📝 기사 요약")
article = st.text_area(
    "기사 내용 (검색 후 자동 입력되거나 직접 붙여넣기 가능)",
    value=st.session_state.get("selected_article", ""),
    height=150,
)

style = st.radio(
    "요약 스타일 선택",
    ["친근하게", "전문적으로", "쉽게 설명"],
    horizontal=True,
)

if st.button("요약하기", type="primary"):
    if article.strip():
        with st.spinner("요약 중..."):
            result = summarize(article, style)
        st.success(result)
    else:
        st.warning("기사 내용을 먼저 입력해주세요.")
