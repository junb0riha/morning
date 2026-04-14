import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '').strip()
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '').strip()
NEWS_API_KEY = os.environ.get('NEWS_API_KEY', '').strip()
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '').strip()

def summarize_news(title, description):
    if not GEMINI_API_KEY:
        return title
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
        res = requests.post(url, json={
            "contents": [{
                "parts": [{
                    "text": f"다음 뉴스를 투자자 관점에서 핵심만 한 줄(30자 이내)로 요약해줘. 요약문만 출력해:\n제목: {title}\n내용: {description}"
                }]
            }]
        })
        return res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except Exception as e:
        print(f"요약 오류: {e}")
        return title

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    requests.post(url, json=payload)

def get_us_news():
    url = (
        f"https://newsapi.org/v2/top-headlines"
        f"?category=business&language=en&country=us"
        f"&apiKey={NEWS_API_KEY}&pageSize=5"
    )
    res = requests.get(url).json()
    articles = res.get('articles', [])
    lines = ["🇺🇸 *전일 미국 시장 주요 뉴스*\n"]
    for i, a in enumerate(articles, 1):
        title = a.get('title', '').split(' - ')[0]
        description = a.get('description', '')
        url_link = a.get('url', '')
        summary = summarize_news(title, description)
        lines.append(f"{i}. [{summary}]({url_link})")
    return "\n".join(lines)

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
            for item in root.findall('.//item')[:3]:
                title = item.findtext('title', '').strip()
                description = item.findtext('description', '').strip()
                link = item.findtext('link', '').strip()
                if title:
                    articles.append((title, description, link))
            if len(articles) >= 5:
                break
        except Exception as e:
            print(f"RSS 오류: {e}")
            continue

    lines = ["\n🇰🇷 *한국 시장 주요 뉴스*\n"]
    for i, (title, description, link) in enumerate(articles[:5], 1):
        summary = summarize_news(title, description)
        lines.append(f"{i}. [{summary}]({link})")
    return "\n".join(lines)

if __name__ == "__main__":
    now_kst = datetime.utcnow() + timedelta(hours=9)
    header = f"📰 *모닝 브리프* — {now_kst.strftime('%Y년 %m월 %d일 %H:%M')} KST\n"
    us_news = get_us_news()
    kr_news = get_kr_news()
    full_message = header + "\n" + us_news + "\n" + kr_news
    send_telegram(full_message)
    print("전송 완료!")
