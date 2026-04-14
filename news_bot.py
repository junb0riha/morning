import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import yfinance as yf
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '').strip()
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '').strip()
NEWS_API_KEY = os.environ.get('NEWS_API_KEY', '').strip()
GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '').strip()
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '').strip()
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '').strip()
EMAIL_SENDER = os.environ.get('EMAIL_SENDER', '').strip()
EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD', '').strip()
EMAIL_RECEIVER = 'junbo119.shim@samsung.com'

now_utc = datetime.utcnow()
now_kst = now_utc + timedelta(hours=9)
hour_kst = now_kst.hour
IS_MORNING = hour_kst < 12
MONTH_START = now_kst.date().replace(day=1)
DIVIDER = '━━━━━'

print(f"현재 KST: {now_kst.strftime('%Y-%m-%d %H:%M')} / {'오전 세션' if IS_MORNING else '오후 세션'}")

def get_market_data():
    tickers = {
        "S&P500": "^GSPC",
        "나스닥": "^IXIC",
        "다우": "^DJI",
        "필라델피아반도체": "^SOX",
        "코스피": "^KS11",
        "코스닥": "^KQ11",
        "원달러": "KRW=X",
        "WTI유가": "CL=F",
        "금": "GC=F",
        "비트코인": "BTC-USD",
        "이더리움": "ETH-USD",
    }
    results = {}
    for name, symbol in tickers.items():
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="40d")
            if len(hist) < 2:
                continue
            curr = hist['Close'].iloc[-1]
            curr_date = hist.index[-1].date()
            prev = hist['Close'].iloc[-2]
            day_change = ((curr - prev) / prev) * 100

            month_price = None
            for i in range(len(hist) - 1, -1, -1):
                d = hist.index[i].date()
                if d < MONTH_START:
                    month_price = hist['Close'].iloc[i]
                    break

            month_change = ((curr - month_price) / month_price) * 100 if month_price else None
            results[name] = {
                "price": curr,
                "date": curr_date,
                "day_change": day_change,
                "month_change": month_change,
            }
        except Exception as e:
            print(f"{name} 데이터 오류: {e}")
    return results

def format_market_data(data):
    def arrow(chg):
        return "▲" if chg >= 0 else "▼"

    def fmt(name, d):
        price = d["price"]
        day_chg = d["day_change"]
        month_chg = d["month_change"]

        if name == "원달러":
            price_str = f"{price:,.1f}원"
        elif name in ["WTI유가", "금"]:
            price_str = f"${price:,.2f}"
        elif name in ["비트코인", "이더리움"]:
            price_str = f"${price:,.0f}"
        else:
            price_str = f"{price:,.2f}"

        day_str = f"{arrow(day_chg)}{abs(day_chg):.2f}%"
        month_str = f"월간 {arrow(month_chg)}{abs(month_chg):.2f}%" if month_chg is not None else "월간 -"
        return f"{name}: {price_str}  {day_str}  ({month_str})"

    lines = []

    us_names = ["S&P500", "나스닥", "다우", "필라델피아반도체"]
    if us_names[0] in data:
        date_str = data[us_names[0]]["date"].strftime("%m/%d")
        lines.append(f"🇺🇸미국 ({date_str} 기준)")
    for name in us_names:
        if name in data:
            lines.append(fmt(name, data[name]))
    lines.append("")

    kr_names = ["코스피", "코스닥"]
    if kr_names[0] in data:
        date_str = data[kr_names[0]]["date"].strftime("%m/%d")
        lines.append(f"🇰🇷한국 ({date_str} 기준)")
    for name in kr_names:
        if name in data:
            lines.append(fmt(name, data[name]))
    lines.append("")

    macro_names = ["원달러", "WTI유가", "금"]
    if macro_names[0] in data:
        date_str = data[macro_names[0]]["date"].strftime("%m/%d")
        lines.append(f"✔️매크로 ({date_str} 기준)")
    for name in macro_names:
        if name in data:
            lines.append(fmt(name, data[name]))
    lines.append("")

    crypto_names = ["비트코인", "이더리움"]
    if crypto_names[0] in data:
        date_str = data[crypto_names[0]]["date"].strftime("%m/%d")
        lines.append(f"✔️코인 ({date_str} 기준)")
    for name in crypto_names:
        if name in data:
            lines.append(fmt(name, data[name]))

    return "\n".join(lines)

def build_prompt(articles_text, market, session):
    if market == "us":
        return f"""당신은 한국의 시니어 매크로 애널리스트입니다.

[예시 문체]
"미국 증시 상승 마감. 미-이란 핵협상 재개 기대감으로 투심 회복. WTI 유가 장중 배럴당 103달러 돌파 후 협상 기대감에 상승폭 축소. 연준 금리 동결 전망 유지 속 나스닥 기술주 중심 매수세 유입, 위험자산 선호 심리 강화."

[작성 규칙]
- 반드시 한국어로만 작성
- 150자 이상 200자 이하 (공백 포함, 반드시 준수)
- 문장 끝은 반드시 명사형 종결 (~했다/~됩니다 절대 금지)
- 개별 종목 언급 금지
- "가능성이 있다", "~할 수 있다", "~될 수 있다" 등 불확실 추측 표현 절대 금지
- "개미", "개미투자자" 등 속어/슬랭 표현 절대 금지. 대신 "개인투자자" 사용
- 아래 순서로 서술:
  1. 증시 방향 + 핵심 원인 한 줄
  2. 주요 매크로 변수 (금리/유가/환율/지정학) 및 수치 포함
  3. 투자자 심리 및 수급 흐름
- 요약문만 출력 (제목/번호/불릿 없이 단락으로)

뉴스:
{articles_text}"""
    else:
        time_context = "전일 장 마감 이후 기사 기준" if session == "morning" else "당일 오후 12시 이후 기사 기준"
        return f"""당신은 한국의 시니어 매크로 애널리스트입니다. ({time_context})

[예시 문체]
"국내 증시 상승 마감. 30거래일 만에 장중 코스피 2,600선 돌파. 외국인 순매수 전환으로 수급 개선, 원달러 환율 하락세로 외국인 매수 유인 확대. 미국 증시 반등 훈풍 및 반도체 업황 회복 기대감이 투심 긍정 작용."

[작성 규칙]
- 반드시 한국어로만 작성
- 150자 이상 200자 이하 (공백 포함, 반드시 준수)
- 문장 끝은 반드시 명사형 종결 (~했다/~됩니다 절대 금지)
- 개별 종목 언급 금지
- "가능성이 있다", "~할 수 있다", "~될 수 있다" 등 불확실 추측 표현 절대 금지
- "개미", "개미투자자" 등 속어/슬랭 표현 절대 금지. 대신 "개인투자자" 사용
- 아래 순서로 서술:
  1. 증시 방향 + 핵심 원인 한 줄
  2. 주요 매크로 변수 (환율/외국인수급/유가/금리) 및 수치 포함
  3. 투자자 심리 및 수급 흐름
- 요약문만 출력 (제목/번호/불릿 없이 단락으로)

뉴스:
{articles_text}"""

def summarize_with_gemini(articles_text, market, session):
    if not GEMINI_API_KEY:
        return None
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
        res = requests.post(url, json={
            "contents": [{"parts": [{"text": build_prompt(articles_text, market, session)}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 300}
        })
        data = res.json()
        if 'candidates' in data:
            return data['candidates'][0]['content']['parts'][0]['text'].strip()
        return None
    except Exception as e:
        print(f"Gemini 오류: {e}")
        return None

def summarize_with_groq(articles_text, market, session):
    if not GROQ_API_KEY:
        return None
    try:
        res = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": "당신은 한국의 시니어 매크로 애널리스트입니다. 반드시 한국어로만 답변하세요."},
                    {"role": "user", "content": build_prompt(articles_text, market, session)}
                ],
                "max_tokens": 300,
                "temperature": 0.3
            }
        )
        data = res.json()
        if 'choices' in data:
            return data['choices'][0]['message']['content'].strip()
        return None
    except Exception as e:
        print(f"Groq 오류: {e}")
        return None

def summarize_with_gpt(articles_text, market, session):
    if not OPENAI_API_KEY:
        return None
    try:
        res = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "당신은 한국의 시니어 매크로 애널리스트입니다. 반드시 한국어로만 답변하세요."},
                    {"role": "user", "content": build_prompt(articles_text, market, session)}
                ],
                "max_tokens": 300,
                "temperature": 0.3
            }
        )
        data = res.json()
        if 'choices' in data:
            return data['choices'][0]['message']['content'].strip()
        return None
    except Exception as e:
        print(f"GPT 오류: {e}")
        return None

def summarize(articles_text, market, session):
    result = summarize_with_gemini(articles_text, market, session)
    if result:
        print("Gemini 요약 성공!")
        return result
    result = summarize_with_groq(articles_text, market, session)
    if result:
        print("Groq 요약 성공!")
        return result
    result = summarize_with_gpt(articles_text, market, session)
    if result:
        print("GPT 요약 성공!")
        return result
    return "요약 실패"

def get_us_news():
    rss_urls = [
        "https://news.google.com/rss/search?q=US+stock+market+NYSE+Nasdaq+S%26P500&hl=en-US&gl=US&ceid=US:en",
        "https://feeds.finance.yahoo.com/rss/2.0/headline?s=%5EGSPC&region=US&lang=en-US",
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
    session = "morning" if IS_MORNING else "afternoon"
    return summarize(articles_text, "us", session)

def get_kr_news():
    query = "코스피 코스닥 증시 마감" if IS_MORNING else "코스피 코스닥 증시 오후"
    rss_urls = [
        f"https://news.google.com/rss/search?q={requests.utils.quote(query)}&hl=ko&gl=KR&ceid=KR:ko",
        "https://www.yna.co.kr/rss/economy.xml",
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

    if not articles:
        return "뉴스 수집 실패"

    articles_text = "\n".join(articles[:5])
    session = "morning" if IS_MORNING else "afternoon"
    return summarize(articles_text, "kr", session)

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "disable_web_page_preview": True
    }
    res = requests.post(url, json=payload)
    print("텔레그램 응답:", res.status_code)

def send_email(subject, body):
    if not EMAIL_SENDER or not EMAIL_PASSWORD:
        print("이메일 설정 없음, 스킵")
        return
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = EMAIL_SENDER
        msg['To'] = EMAIL_RECEIVER

        text_part = MIMEText(body, 'plain', 'utf-8')
        html = f"""
<html><body>
<div style="font-family: 'Malgun Gothic', Arial, sans-serif; font-size: 14px; line-height: 2.0; max-width: 620px; margin: 0 auto; padding: 24px; color: #1a1a1a;">
<pre style="font-family: 'Malgun Gothic', Arial, sans-serif; font-size: 14px; line-height: 2.0; white-space: pre-wrap; word-break: keep-all;">{body}</pre>
</div>
</body></html>
"""
        html_part = MIMEText(html, 'html', 'utf-8')
        msg.attach(text_part)
        msg.attach(html_part)

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(EMAIL_SENDER, EMAIL_PASSWORD)
            smtp.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
        print("이메일 전송 완료!")
    except Exception as e:
        print(f"이메일 오류: {e}")

if __name__ == "__main__":
    session_label = "오전 브리프" if IS_MORNING else "오후 브리프"
    date_str = now_kst.strftime('%Y년 %m월 %d일 %H:%M')

    print("시장 데이터 수집 중...")
    market_data = get_market_data()
    market_block = format_market_data(market_data)

    print("미국 뉴스 수집 중...")
    us_summary = get_us_news()

    print("한국 뉴스 수집 중...")
    kr_summary = get_kr_news()

    full_message = f"""{session_label} — {date_str} KST
{DIVIDER}

{market_block}

{DIVIDER}
🇺🇸 미국 증시 시황
{DIVIDER}
{us_summary}

{DIVIDER}
🇰🇷 한국 증시 시황
{DIVIDER}
{kr_summary}"""

    send_telegram(full_message)

    email_subject = f"[시황 브리프] {date_str} - {session_label}"
    send_email(email_subject, full_message)

    print("전송 완료!")
