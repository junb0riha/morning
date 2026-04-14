import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import time

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '').strip()
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '').strip()
NEWS_API_KEY = os.environ.get('NEWS_API_KEY', '').strip()
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '').strip()
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '').strip()

print(f"OPENAI_API_KEY 길이: {len(OPENAI_API_KEY)}")
print(f"GEMINI_API_KEY 길이: {len(GEMINI_API_KEY)}")

def summarize_with_gpt(articles_text, market):
    if not OPENAI_API_KEY:
        return None
    try:
        if market == "us":
            prompt = f"""다음은 미국 뉴욕 증시 관련 뉴스들입니다.
투자자 관점에서 증시 흐름(상승/하락/보합), 주요 원인, 핵심 이슈를 100자 이내로 한국어로 요약해주세요.
요약문만 출력하세요.

뉴스:
{articles_text}"""
        else:
            prompt = f"""다음은 한국 증시 관련 뉴스들입니다.
투자자 관점에서 증시 흐름(상승/하락/보합), 주요 원인, 핵심 이슈를 100자 이내로 한국어로 요약해주세요.
요약문만 출력하세요.

뉴스:
{articles_text}"""

        res = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 200
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
        if market == "us":
            prompt = f"""다음은 미국 뉴욕 증시 관련 뉴스들입니다.
투자자 관점에서 증시 흐름(상승/하락/보합), 주요 원인, 핵심 이슈를 100자 이내로 한국어로 요약해주세요.
요약문만 출력하세요.

뉴스:
{articles_text}"""
        else:
            prompt = f"""다음은 한국 증시 관련 뉴스들입니다.
투자자 관점에서 증시 흐름(상승/하락/보합), 주요 원인, 핵심 이슈를 100자 이내로 한국어로 요약해주세요.
요약문만 출력하세요.

뉴스:
{articles_text}"""

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
        res = requests.post(url, json={
            "contents": [{"parts": [{"text": prompt}]}]
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
    print("GPT로 요약 시도...")
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
        "https://news.google.com/rss/search?q=NYSE+stock+market+today&hl=en-US&gl=US&ceid=US:en",
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
