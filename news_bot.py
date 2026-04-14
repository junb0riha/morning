import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '').strip()
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '').strip()
NEWS_API_KEY = os.environ.get('NEWS_API_KEY', '').strip()
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '').strip()

print(f"GEMINI_API_KEY 길이: {len(GEMINI_API_KEY)}")

def summarize_with_gemini(articles_text, market):
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
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

        res = requests.post(url, json={
            "contents": [{"parts": [{"text": prompt}]}]
        })
        print(f"Gemini 응답: {res.json()}")
        return res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except Exception as e:
        print(f"Gemini 오류: {e}")
        return "요약 실패"

def get_us_news():
    # 한국시간 00시~09시 = UTC 전날 15시~00시
    now_utc = datetime.utcnow()
    time_from = (now_utc - timedelta(hours=18)).strftime('%Y-%m-%dT%H:%M:%SZ')

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
        # fallback: NewsAPI
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
    summary = summarize_with_gemini(articles_text, "us")
    return f"🇺🇸 *미국 증시 (전일)*\n{summary}"

def get_kr_news():
    rss_urls = [
        "https://finance.naver.com/news/news_list.naver?mode=RSS&section=market_now",
        "https://www.yonhapnewstv.co.kr/category/news/economy/feed/",
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
            print(f"한국 RSS 오류: {e}")

    articles_text = "\n".join(articles[:5])
    print(f"한국 뉴스 수집: {len(articles)}건")
    summary = summarize_with_gemini(articles_text, "kr")
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
