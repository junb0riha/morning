import os
import re
import html
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


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


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
            hist = ticker.history(period="40d", auto_adjust=False)

            if hist is None or len(hist) < 2:
                continue

            curr = float(hist['Close'].iloc[-1])
            prev = float(hist['Close'].iloc[-2])
            curr_date = hist.index[-1].date()
            day_change = ((curr - prev) / prev) * 100

            month_price = None
            for i in range(len(hist) - 1, -1, -1):
                d = hist.index[i].date()
                if d < MONTH_START:
                    month_price = float(hist['Close'].iloc[i])
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
    us_available = [name for name in us_names if name in data]
    if us_available:
        date_str = data[us_available[0]]["date"].strftime("%m/%d")
        lines.append(f"🇺🇸미국 ({date_str} 기준)")
        for name in us_names:
            if name in data:
                lines.append(fmt(name, data[name]))
        lines.append("")

    kr_names = ["코스피", "코스닥"]
    kr_available = [name for name in kr_names if name in data]
    if kr_available:
        date_str = data[kr_available[0]]["date"].strftime("%m/%d")
        lines.append(f"🇰🇷한국 ({date_str} 기준)")
        for name in kr_names:
            if name in data:
                lines.append(fmt(name, data[name]))
        lines.append("")

    macro_names = ["원달러", "WTI유가", "금"]
    macro_available = [name for name in macro_names if name in data]
    if macro_available:
        date_str = data[macro_available[0]]["date"].strftime("%m/%d")
        lines.append(f"▪ 매크로 ({date_str} 기준)")
        for name in macro_names:
            if name in data:
                lines.append(fmt(name, data[name]))
        lines.append("")

    crypto_names = ["비트코인", "이더리움"]
    crypto_available = [name for name in crypto_names if name in data]
    if crypto_available:
        date_str = data[crypto_available[0]]["date"].strftime("%m/%d")
        lines.append(f"▪ 코인 ({date_str} 기준)")
        for name in crypto_names:
            if name in data:
                lines.append(fmt(name, data[name]))

    return "\n".join(lines).strip()


def build_prompt(articles_text, market, session):
    if market == "us":
        session_note = "전일 미국 증시 마감 기사 기준" if session == "morning" else "가장 최근 미국 증시 마감 기사 기준"
        return f"""당신은 한국 증권사 데일리 시황을 작성하는 시니어 애널리스트입니다. ({session_note})

[문체 기준]
- 반드시 한국어로만 작성
- 한국 증권사 데일리 시황 문체 사용
- 짧고 단정한 기사체 사용
- 첫 문장은 반드시 아래 둘 중 하나로 시작
  1) 미국 증시 상승 마감.
  2) 미국 증시 하락 마감.
- 문장 종결은 "~마감.", "~확대.", "~완화.", "~유입.", "~부각.", "~우위.", "~반영." 같은 짧은 기사체 허용
- 억지 명사형 종결 금지
- "~했다", "~됩니다", "~이다", "~다" 위주의 장문 설명체 금지
- "가능성이 있다", "~할 수 있다", "~될 수 있다" 등 추측 표현 금지
- 개별 종목 언급 금지
- 뉴스에 없는 내용 추가 금지
- 기사 간 내용이 상충할 경우, 종가 방향과 가장 직접 연결되는 재료만 채택
- 장중 기사보다 마감 기사 우선
- 220자 이상 250자 이하

[서술 순서]
1. 증시 방향
2. 핵심 재료 1~2개
3. 금리/유가/환율/정책 변수 중 중요한 것 1개만 반영
4. 투자심리 또는 수급 흐름 1문장

[출력 규칙]
- 결과는 한 단락만 출력
- 제목, 번호, 불릿 금지
- 과장 표현 금지
- 중복 표현 금지

뉴스:
{articles_text}"""
    else:
        session_note = "전일 국내 증시 마감 기사 기준" if session == "morning" else "당일 국내 증시 마감 기사 기준"
        return f"""당신은 한국 증권사 데일리 시황을 작성하는 시니어 애널리스트입니다. ({session_note})

[문체 기준]
- 반드시 한국어로만 작성
- 한국 증권사 데일리 시황 문체 사용
- 짧고 단정한 기사체 사용
- 첫 문장은 반드시 아래 둘 중 하나로 시작
  1) 국내 증시 상승 마감.
  2) 국내 증시 하락 마감.
- 문장 종결은 "~마감.", "~확대.", "~완화.", "~유입.", "~부각.", "~우위.", "~반영." 같은 짧은 기사체 허용
- 억지 명사형 종결 금지
- "~했다", "~됩니다", "~이다", "~다" 위주의 장문 설명체 금지
- "가능성이 있다", "~할 수 있다", "~될 수 있다" 등 추측 표현 금지
- 개별 종목 언급 금지
- 뉴스에 없는 내용 추가 금지
- 기사 간 내용이 상충할 경우, 장 마감 방향과 수급에 직접 연결되는 재료만 채택
- 장중 기사보다 마감 기사 우선
- 220자 이상 250자 이하

[서술 순서]
1. 증시 방향
2. 핵심 재료 1~2개
3. 환율/외국인수급/금리 중 중요한 것 1개만 반영
4. 투자심리 또는 수급 흐름 1문장

[출력 규칙]
- 결과는 한 단락만 출력
- 제목, 번호, 불릿 금지
- 과장 표현 금지
- 중복 표현 금지

뉴스:
{articles_text}"""


def post_process_summary(text, market):
    if not text:
        return "요약 실패"

    text = clean_text(text)
    text = text.replace('"', '').replace("'", "")
    text = re.sub(r'\s+', ' ', text).strip()

    # LLM이 제목처럼 뱉는 경우 제거
    text = re.sub(r'^(미국 증시 시황|국내 증시 시황|한국 증시 시황|시황)\s*[:：-]?\s*', '', text)

    # 첫 문장 보정
    if market == "us":
        if not (text.startswith("미국 증시 상승 마감.") or text.startswith("미국 증시 하락 마감.")):
            # 방향성 키워드 기반 단순 보정
            if any(x in text for x in ["상승", "반등", "강세", "오름세"]):
                text = "미국 증시 상승 마감. " + text
            elif any(x in text for x in ["하락", "약세", "내림세"]):
                text = "미국 증시 하락 마감. " + text
    else:
        if not (text.startswith("국내 증시 상승 마감.") or text.startswith("국내 증시 하락 마감.")):
            if any(x in text for x in ["상승", "반등", "강세", "오름세"]):
                text = "국내 증시 상승 마감. " + text
            elif any(x in text for x in ["하락", "약세", "내림세"]):
                text = "국내 증시 하락 마감. " + text

    # 중복 문장 제거
    sentences = [s.strip() for s in re.split(r'(?<=\.)\s+', text) if s.strip()]
    deduped = []
    seen = set()
    for s in sentences:
        if s not in seen:
            seen.add(s)
            deduped.append(s)
    text = " ".join(deduped)

    # 너무 길면 잘라내기
    if len(text) > 300:
        cut = text[:300]
        last_period = cut.rfind('.')
        if last_period > 150:
            text = cut[:last_period + 1]

    return text.strip()


def summarize_with_gemini(articles_text, market, session):
    if not GEMINI_API_KEY:
        return None
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
        res = requests.post(
            url,
            json={
                "contents": [{"parts": [{"text": build_prompt(articles_text, market, session)}]}],
                "generationConfig": {
                    "temperature": 0.2,
                    "maxOutputTokens": 300
                }
            },
            timeout=20
        )
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
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": "당신은 한국 증권사 데일리 시황을 작성하는 시니어 애널리스트입니다. 반드시 한국어로만 답변하세요."},
                    {"role": "user", "content": build_prompt(articles_text, market, session)}
                ],
                "max_tokens": 300,
                "temperature": 0.2
            },
            timeout=20
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
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "당신은 한국 증권사 데일리 시황을 작성하는 시니어 애널리스트입니다. 반드시 한국어로만 답변하세요."},
                    {"role": "user", "content": build_prompt(articles_text, market, session)}
                ],
                "max_tokens": 300,
                "temperature": 0.2
            },
            timeout=20
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
        print("Gemini 요약 성공")
        return post_process_summary(result, market)

    result = summarize_with_groq(articles_text, market, session)
    if result:
        print("Groq 요약 성공")
        return post_process_summary(result, market)

    result = summarize_with_gpt(articles_text, market, session)
    if result:
        print("GPT 요약 성공")
        return post_process_summary(result, market)

    return "요약 실패"


def parse_rss_items(rss_url, limit=5):
    articles = []
    try:
        res = requests.get(rss_url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        root = ET.fromstring(res.content)
        for item in root.findall('.//item')[:limit]:
            title = clean_text(item.findtext('title', ''))
            description = clean_text(item.findtext('description', ''))
            pub_date = clean_text(item.findtext('pubDate', ''))
            if title:
                articles.append(f"- [{pub_date}] {title}: {description}")
    except Exception as e:
        print(f"RSS 오류: {rss_url} / {e}")
    return articles


def get_us_news():
    # 오전/오후 모두 "마감 시황" 위주로 고정
    queries = [
        "US stocks close market wrap S&P 500 Nasdaq Dow",
        "Wall Street stocks close market recap",
        "Nasdaq Dow S&P 500 close recap"
    ]

    rss_urls = []
    for q in queries:
        rss_urls.append(
            f"https://news.google.com/rss/search?q={requests.utils.quote(q)}&hl=en-US&gl=US&ceid=US:en"
        )

    rss_urls.extend([
        "https://feeds.marketwatch.com/marketwatch/topstories/",
        "https://feeds.finance.yahoo.com/rss/2.0/headline?s=%5EGSPC&region=US&lang=en-US",
    ])

    articles = []
    for rss_url in rss_urls:
        items = parse_rss_items(rss_url, limit=5)
        for item in items:
            if item not in articles:
                articles.append(item)
        if len(articles) >= 7:
            break

    if not articles and NEWS_API_KEY:
        try:
            url = (
                f"https://newsapi.org/v2/everything"
                f"?q={requests.utils.quote('US stocks close Wall Street market wrap')}"
                f"&language=en&sortBy=publishedAt&pageSize=7&apiKey={NEWS_API_KEY}"
            )
            res = requests.get(url, timeout=10).json()
            for a in res.get('articles', []):
                title = clean_text(a.get('title', ''))
                desc = clean_text(a.get('description', ''))
                pub = clean_text(a.get('publishedAt', ''))
                if title:
                    articles.append(f"- [{pub}] {title}: {desc}")
        except Exception as e:
            print(f"미국 NewsAPI 오류: {e}")

    articles_text = "\n".join(articles[:7])
    print(f"미국 뉴스 수집: {len(articles[:7])}건")
    session = "morning" if IS_MORNING else "afternoon"
    return summarize(articles_text, "us", session)


def get_kr_news():
    # 오전: 전일 마감 시황 / 오후: 당일 마감 시황
    if IS_MORNING:
        queries = [
            "코스피 코스닥 전일 마감 시황 외국인 환율",
            "국내 증시 마감 시황 코스피 코스닥",
        ]
    else:
        queries = [
            "코스피 코스닥 장 마감 시황 외국인 환율",
            "국내 증시 장 마감 시황 코스피 코스닥",
        ]

    rss_urls = []
    for q in queries:
        rss_urls.append(
            f"https://news.google.com/rss/search?q={requests.utils.quote(q)}&hl=ko&gl=KR&ceid=KR:ko"
        )

    rss_urls.extend([
        "https://www.yna.co.kr/rss/marketplus.xml",
        "https://www.yna.co.kr/rss/economy.xml",
    ])

    articles = []
    for rss_url in rss_urls:
        items = parse_rss_items(rss_url, limit=5)
        for item in items:
            if item not in articles:
                articles.append(item)
        if len(articles) >= 7:
            break

    if not articles and NEWS_API_KEY:
        try:
            query = "코스피 코스닥 장 마감 시황 외국인 환율" if not IS_MORNING else "코스피 코스닥 전일 마감 시황 외국인 환율"
            url = (
                f"https://newsapi.org/v2/everything"
                f"?q={requests.utils.quote(query)}"
                f"&language=ko&sortBy=publishedAt&pageSize=7&apiKey={NEWS_API_KEY}"
            )
            res = requests.get(url, timeout=10).json()
            for a in res.get('articles', []):
                title = clean_text(a.get('title', ''))
                desc = clean_text(a.get('description', ''))
                pub = clean_text(a.get('publishedAt', ''))
                if title:
                    articles.append(f"- [{pub}] {title}: {desc}")
        except Exception as e:
            print(f"한국 NewsAPI 오류: {e}")

    if not articles:
        return "뉴스 수집 실패"

    articles_text = "\n".join(articles[:7])
    print(f"한국 뉴스 수집: {len(articles[:7])}건")
    session = "morning" if IS_MORNING else "afternoon"
    return summarize(articles_text, "kr", session)


def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "disable_web_page_preview": True
    }
    res = requests.post(url, json=payload, timeout=15)
    print("텔레그램 응답:", res.status_code, res.text[:200])


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

        html_body = f"""
<html>
  <body>
    <div style="font-family:'Malgun Gothic',Arial,sans-serif;font-size:14px;line-height:2.0;max-width:620px;margin:0 auto;padding:24px;color:#1a1a1a;">
      <pre style="font-family:'Malgun Gothic',Arial,sans-serif;font-size:14px;line-height:2.0;white-space:pre-wrap;word-break:keep-all;">{body}</pre>
    </div>
  </body>
</html>
"""
        html_part = MIMEText(html_body, 'html', 'utf-8')

        msg.attach(text_part)
        msg.attach(html_part)

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(EMAIL_SENDER, EMAIL_PASSWORD)
            smtp.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())

        print("이메일 전송 완료")
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

    print("전송 완료")
