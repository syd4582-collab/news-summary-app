import streamlit as st
import requests

API_KEY = "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"

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
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}]
        }
    )
    return response.json()["choices"][0]["message"]["content"]

# --- UI ---
st.set_page_config(page_title="AI 맞춤 기사 요약", page_icon="📰")
st.title("📰 AI 맞춤 기사 요약")
st.caption("나만의 말투로 뉴스를 읽다")

article = st.text_area("기사 내용을 붙여넣으세요", height=200,
                        placeholder="뉴스 기사 본문을 여기에 붙여넣으세요...")

style = st.radio(
    "요약 스타일 선택",
    ["친근하게", "전문적으로", "쉽게 설명"],
    horizontal=True
)

if st.button("요약하기", type="primary"):
    if article.strip():
        with st.spinner("요약 중..."):
            result = summarize(article, style)
        st.success(result)
    else:
        st.warning("기사 내용을 먼저 입력해주세요.")
