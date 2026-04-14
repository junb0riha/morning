import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '').strip()
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '').strip()
NEWS_API_KEY = os.environ.get('NEWS_API_KEY', '').strip()
GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '').strip()
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '').strip()
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '').strip()

print(f"GROQ_API_KEY 길이: {len(GROQ_API_KEY)}")

def build_prompt(articles_text, market):
    if market == "us":
        return f"""당신은 한국의 시니어 매크로 애널리스트입니다. 아래 미국 증시 뉴스를 바탕으로 전일 뉴욕 증시 매크로 시황을 요약해주세요.

[작성 규칙]
- 반드시 한국어로만 작성 (영어, 일본어, 중국어 절대 금지)
- 200자 내외로 작성
- 개별 종목 언급 금지
- 아래 항목 중심으로 서술:
  1. 주요 지수 흐름 (S&P500, 나스닥, 다우)
  2. 핵심 매크로 원인 (연준 정책, 금리, 유가, 지정학적 리스크 등)
  3. 투자자 심리 및 시장 분위기
- 자연스러운 문어체 한국어 문장으로 작성
- 요약문만 출력 (제목, 설명, 부연 없이)

뉴스:
{articles_text}"""
    else:
        return f"""당신은 한국의 시니어 매크로 애널리스트입니다. 아래 한국 증시 뉴스를 바탕으로 당일 한국 증시 매크로 시황을 요약해주세요.

[작성 규칙]
- 반드시 한국어로만 작성 (영어, 일본어, 중국어 절대 금지)
- 200자 내외로 작성
- 개별 종목 언급 금지
- 아래 항목 중심으로 서술:
  1. 주요 지수 흐름 (코스피, 코스닥)
  2. 핵심 매크로 원인 (환율, 외국인 수급, 유가, 지정학적 리스크 등)
  3. 투자자 심리 및 시장 분위기
- 자연스러운 문어체 한국어 문장으로 작성
- 요약문만 출력 (제목, 설명, 부연 없이)

뉴스:
{articles_text}"""

def summarize_with_groq(articles_text, market):
    if not GROQ_API_KEY:
        return None
    try:
        res = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {
                        "role": "system",
                        "content": "당신은 한국의 시니어 매크로 애널리스트입니다. 반드시 한국어로만 답변하세요."
                    },
                    {
                        "role": "user",
                        "content": build_prompt(articles_text, market)
                    }
                ],
                "max_tokens": 400,
                "temperature": 0.3
            }
        )
        data = res.json()
        print(f"Groq 응답: {data}")
        if 'choices' in data:
            return data['choices'][0]['message']['content'].strip()
        return None
    except Exception as e:
        print(f"Groq 오류: {e}")
        return None

def summarize_with_gpt(articles_text, market):
    if not OPENAI_API_KEY:
        return None
    try:
        res = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {
                        "role": "system",
                        "content": "당신은 한국의 시니어 매크로 애널리스트입니다. 반드시 한국어로만 답변하세요."
                    },
                    {
                        "role": "user",
                        "content": build_prompt(articles_text, market)
                    }
                ],
                "max_tokens": 400,
                "temperature": 0.3
            }
        )
        data = res.json()
        print(f"GPT 응답: {data}")
        if 'choices' in data:
            return data['choices'][0]['message']['content'].strip()
        return None
    except Exception as e:
        print(f"GPT 오류: {e}")
        return None

def summarize_with_gemini(articles_text, market):
    if not GEMINI_API_KEY:
        return None
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
        res = requests.post(url, json={
            "contents": [{"parts": [{"text": build_prompt(articles_text, market)}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 400}
        })
        data = res.json()
        print(f"Gemini 응답: {data}")
        if 'candidates' in data:
            return data['candidates'][0]['content']['parts'][0]['text'].strip()
        return None
    except Exception as e:
        print(f"Gemini 오류: {e}")
        return None

def summarize(articles_text, market):
    print("Groq로 요약 시도...")
    result = summarize_with_groq(articles_text, market)
    if result:
        print("Groq 요약 성공!")
        return result
    print("Groq 실패, GPT로 시도...")
    result = summarize_with_gpt(articles_text, market)
    if result:
        print("GPT 요약 성공!")
        return result
    print("GPT 실패, Gemini로 시도...")
    result = summarize_with_gemini(articles_text, market)
    if result:
        print("Gemini 요약 성공!")
        return result
    return "요약 실패"

def get_us_news():
    rss_urls = [
        "https://feeds.finance.yahoo.com/rss/2.0/headline?s=%5EGSPC&region=US&lang=en-US",
        "https://news.google.com/rss/search?q=NYSE+Nasdaq+stock+market&hl=en-US&gl=US&ceid=US:en",
    ]
    articles = []
    for rss_url in rss_urls:
        try:
            res = requests.get(rss_url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
            root = ET.fromstring(res.content)
            for item in root.findall('.//item')[:5]:
                title = item.findtext('title', '').strip()
                description = item.findtext('description', '').strip()
                if title:
                    articles.append(f"- {title}: {description}")
            if len(articles) >= 5:
                break
        except Exception as e:
            print(f"미국 RSS 오류: {e}")

    if not articles:
        url = (
            f"https://newsapi.org/v2/top-headlines"
            f"?category=business&language=en&country=us"
            f"&apiKey={NEWS_API_KEY}&pageSize=5"
        )
        res = requests.get(url).json()
        for a in res.get('articles', []):
            title = a.get('title', '').split(' - ')[0]
            desc = a.get('description', '')
            articles.append(f"- {title}: {desc}")

    articles_text = "\n".join(articles[:5])
    print(f"미국 뉴스 수집: {len(articles)}건")
    summary = summarize(articles_text, "us")
    return f"🇺🇸 *미국 증시 (전일)*\n{summary}"

def get_kr_news():
    rss_urls = [
        "https://www.yna.co.kr/rss/economy.xml",
        "https://news.kbs.co.kr/rss/rss_economy.xml",
    ]
    articles = []
    for rss_url in rss_urls:
        try:
            res = requests.get(rss_url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
            print(f"한국 RSS 상태코드: {res.status_code} ({rss_url})")
            root = ET.fromstring(res.content)
            for item in root.findall('.//item')[:5]:
                title = item.findtext('title', '').strip()
                description = item.findtext('description', '').strip()
                if title:
                    articles.append(f"- {title}: {description}")
            if len(articles) >= 5:
                break
        except Exception as e:
            print(f"한국 RSS 오류: {e}")

    if not articles:
        print("한국 뉴스 수집 실패")
        return "🇰🇷 *한국 증시 (당일)*\n뉴스 수집 실패"

    articles_text = "\n".join(articles[:5])
    print(f"한국 뉴스 수집: {len(articles)}건")
    summary = summarize(articles_text, "kr")
    return f"🇰🇷 *한국 증시 (당일)*\n{summary}"

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    res = requests.post(url, json=payload)
    print("텔레그램 응답:", res.json())

if __name__ == "__main__":
    now_kst = datetime.utcnow() + timedelta(hours=9)
    header = f"📰 *모닝 브리프* — {now_kst.strftime('%Y년 %m월 %d일 %H:%M')} KST\n"
    us_news = get_us_news()
    kr_news = get_kr_news()
    full_message = header + "\n" + us_news + "\n\n" + kr_news
    send_telegram(full_message)
    print("전송 완료!")
