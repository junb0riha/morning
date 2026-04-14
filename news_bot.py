import os
import requests
from datetime import datetime, timedelta

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '').strip()
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '').strip()
NEWS_API_KEY = os.environ.get('NEWS_API_KEY', '').strip()

print(f"토큰 길이: {len(TELEGRAM_TOKEN)}")
print(f"토큰 앞10자: {TELEGRAM_TOKEN[:10]}")
print(f"Chat ID: '{TELEGRAM_CHAT_ID}'")

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
    articles = res.get('articles', [])
    lines = ["🇺🇸 *전일 미국 시장 주요 뉴스*\n"]
    for i, a in enumerate(articles, 1):
        title = a.get('title', '').split(' - ')[0]
        url_link = a.get('url', '')
        lines.append(f"{i}. [{title}]({url_link})")
    return "\n".join(lines)

if __name__ == "__main__":
    now_kst = datetime.utcnow() + timedelta(hours=9)
    header = f"📰 *모닝 브리프* — {now_kst.strftime('%Y년 %m월 %d일 %H:%M')} KST\n"
    us_news = get_us_news()
    full_message = header + "\n" + us_news
    send_telegram(full_message)
    print("전송 완료!")
