import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import yfinance as yf

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '').strip()
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '').strip()
NEWS_API_KEY = os.environ.get('NEWS_API_KEY', '').strip()
GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '').strip()
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '').strip()
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '').strip()

# 현재 KST 시간 기준으로 발송 세션 판단
now_utc = datetime.utcnow()
now_kst = now_utc + timedelta(hours=9)
hour_kst = now_kst.hour
IS_MORNING = hour_kst < 12  # 08:30 발송
print(f"현재 KST: {now_kst.strftime('%Y-%m-%d %H:%M')} / {'오전 세션' if IS_MORNING else '오후 세션'}")

def get_market_data():
    tickers = {
        "S&P500": "^GSPC",
        "나스닥": "^IXIC",
        "다우": "^DJI",
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
            hist = ticker.history(period="2d")
            if len(hist) >= 2:
                prev = hist['Close'].iloc[-2]
                curr = hist['Close'].iloc[-1]
                change = ((curr - prev) / prev) * 100
                results[name] = (curr, change)
            elif len(hist) == 1:
                curr = hist['Close'].iloc[-1]
                results[name] = (curr, 0)
        except Exception as e:
            print(f"{name} 데이터 오류: {e}")
    return results

def format_market_data(data):
    def arrow(chg):
        return "▲" if chg >= 0 else "▼"

    def fmt(name, val, chg):
        if name == "원달러":
            return f"{name}: {val:,.1f}원 {arrow(chg)}{abs(chg):.2f}%"
        elif name in ["WTI유가", "금"]:
            return f"{name}: ${val:,.2f} {arrow(chg)}{abs(chg):.2f}%"
        elif name in ["비트코인", "이더리움"]:
            return f"{name}: ${val:,.0f} {arrow(chg)}{abs(chg):.2f}%"
        else:
            return f"{name}: {val:,.2f} {arrow(chg)}{abs(chg):.2f}%"

    sections = {
        "📊 *미국 지수*": ["S&P500", "나스닥", "다우"],
        "📊 *한국 지수*": ["코스피", "코스닥"],
        "🌐 *매크로 지표*": ["원달러", "WTI유가", "금"],
        "🪙 *가상자산*": ["비트코인", "이더리움"],
    }

    lines = []
    for section, names in sections.items():
        lines.append(section)
        for name in names:
            if name in data:
                val, chg = data[name]
                lines.append(fmt(name, val, chg))
    return "\n".join(lines)

def build_prompt(articles_text, market, session):
    if market == "us":
        return f"""당신은 한국의 시니어 매크로 애널리스트입니다.

[예시 문체]
"미국 증시 상승 마감. 미-이란 협상 기대감 부상으로 투심 개선. 국제유가 장중 배럴당 100달러 돌파 후 협상 기대감에 상승폭 축소 마감. 나스닥 기술주 중심 매수세 유입, 연준 금리 동결 가능성 부각되며 위험자산 선호 심리 강화."

[작성 규칙]
- 반드시 한국어로만 작성
- 150~200자 내외
- 문장 끝은 반드시 명사형 종결 (~했다/~됩니다 절대 금지)
- 개별 종목 언급 금지
- 아래 순서로 서술:
  1. 증시 방향 + 핵심 원인 한 줄
  2. 주요 매크로 변수 (금리/유가/환율/지정학) 및 수치 포함
  3. 투자자 심리 및 수급 흐름
- 요약문만 출력 (제목/번호/불릿 없이 단락으로)

뉴스:
{articles_text}"""
    else:
        if session == "morning":
            time_context = "전일 장 마감 이후 기사 기준"
        else:
            time_context = "당일 오후 12시 이후 기사 기준"

        return f"""당신은 한국의 시니어 매크로 애널리스트입니다. ({time_context})

[예시 문체]
"국내 증시 상승 마감. 30거래일 만에 장중 코스피 2,600선 돌파. 외국인 순매수 전환으로 수급 개선, 원달러 환율 하락세로 외국인 매수 유인 확대. 미국 증시 반등 훈풍 및 반도체 업황 회복 기대감이 투심 긍정 작용."

[작성 규칙]
- 반드시 한국어로만 작성
- 150~200자 내외
- 문장 끝은 반드시 명사형 종결 (~했다/~됩니다 절대 금지)
- 개별 종목 언급 금지
- 아래 순서로 서술:
  1. 증시 방향 + 핵심 원인 한 줄
  2. 주요 매크로 변수 (환율/외국인수급/유가/금리) 및 수치 포함
  3. 투자자 심리 및 수급 흐름
- 요약문만 출력 (제목/번호/불릿 없이 단락으로)

뉴스:
{articles_text}"""

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
                    {"role": "system", "content": "당신은 한국의 시니어 매크로 애널리스트입니다. 반드시 한국어로만 답변하세요."},
                    {"role": "user", "content": build_prompt(articles_text, market, session)}
                ],
                "max_tokens": 400,
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
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "당신은 한국의 시니어 매크로 애널리스트입니다. 반드시 한국어로만 답변하세요."},
                    {"role": "user", "content": build_prompt(articles_text, market, session)}
                ],
                "max_tokens": 400,
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

def summarize_with_gemini(articles_text, market, session):
    if not GEMINI_API_KEY:
        return None
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
        res = requests.post(url, json={
            "contents": [{"parts": [{"text": build_prompt(articles_text, market, session)}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 400}
        })
        data = res.json()
        if 'candidates' in data:
            return data['candidates'][0]['content']['parts'][0]['text'].strip()
        return None
    except Exception as e:
        print(f"Gemini 오류: {e}")
        return None

def summarize(articles_text, market, session):
    result = summarize_with_groq(articles_text, market, session)
    if result:
        return result
    result = summarize_with_gpt(articles_text, market, session)
    if result:
        return result
    result = summarize_with_gemini(articles_text, market, session)
    if result:
        return result
    return "요약 실패"

def get_us_news():
    # 구글 뉴스 RSS - 최신 미국 증시 기사
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
    # 오전: 전일 마감 이후 기사 / 오후: 당일 낮 12시 이후 기사
    if IS_MORNING:
        query = "코스피 코스닥 증시 마감"
    else:
        query = "코스피 코스닥 증시 오후"

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
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    res = requests.post(url, json=payload)
    print("텔레그램 응답:", res.json())

if __name__ == "__main__":
    session_label = "🌅 오전 브리프" if IS_MORNING else "🌆 오후 브리프"
    header = f"📰 *{session_label}* — {now_kst.strftime('%Y년 %m월 %d일 %H:%M')} KST\n"

    print("시장 데이터 수집 중...")
    market_data = get_market_data()
    market_block = format_market_data(market_data)

    print("미국 뉴스 수집 중...")
    us_summary = get_us_news()

    print("한국 뉴스 수집 중...")
    kr_summary = get_kr_news()

    us_block = f"*🇺🇸 미국 증시 시황*\n{us_summary}"
    kr_block = f"*🇰🇷 한국 증시 시황*\n{kr_summary}"

    full_message = (
        header + "\n"
        + market_block + "\n\n"
        + us_block + "\n\n"
        + kr_block
    )

    send_telegram(full_message)
    print("전송 완료!")
