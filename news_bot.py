import os
import requests

TELEGRAM_TOKEN = os.environ['TELEGRAM_TOKEN']
TELEGRAM_CHAT_ID = os.environ['TELEGRAM_CHAT_ID']
NEWS_API_KEY = os.environ['NEWS_API_KEY']

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

def get_us_news():
    url = (
        f"https://newsapi.org/v2/top-headlines"
        f"?category=business&language=en&country=us"
        f"&apiKey={NEWS_API_KEY}&pageSize=5"
    )
    res = requests.get(url).json()
    print("미국 뉴스 API 응답:", res)
    articles = res.get('articles', [])
    lines = ["🇺🇸 *전일 미국 시장 주요 뉴스*\n"]
    for i, a in enumerate(articles, 1):
        title = a.get('title', '').split(' - ')[0]
        url_link = a.get('url', '')
        lines.append(f"{i}. [{title}]({url_link})")
    return "\n".join(lines)

def get_kr_news():
    url = (
        f"https://newsapi.org/v2/top-headlines"
        f"?category=business&language=ko&country=kr"
        f"&apiKey={NEWS_API_KEY}&pageSize=5"
    )
    res = requests.get(url).json()
    print("한국 뉴스 API 응답:", res)
    articles = res.get('articles', [])
    lines = ["\n🇰🇷 *한국 시장 주요 뉴스*\n"]
    for i, a in enumerate(articles, 1):
        title = a.get('title', '').split(' - ')[0]
        url_link = a.get('url', '')
        lines.append(f"{i}. [{title}]({url_link})")
    return "\n".join(lines)

if __name__ == "__main__":
    from datetime import datetime, timedelta
    now_kst = datetime.utcnow() + timedelta(hours=9)
    header = f"📰 *모닝 브리프* — {now_kst.strftime('%Y년 %m월 %d일 %H:%M')} KST\n"
    us_news = get_us_news()
    kr_news = get_kr_news()
    full_message = header + "\n" + us_news + "\n" + kr_news
    send_telegram(full_message)
    print("전송 완료!")
