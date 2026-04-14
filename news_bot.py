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

    def fmt_price(name, val, chg):
        if name in ["원달러"]:
            return f"{name}: {val:,.1f}원 {arrow(chg)}{abs(chg):.2f}%"
        elif name in ["WTI유가"]:
            return f"{name}: ${val:,.2f} {arrow(chg)}{abs(chg):.2f}%"
        elif name in ["금"]:
            return f"{name}: ${val:,.1f} {arrow(chg)}{abs(chg):.2f}%"
        elif name in ["비트코인"]:
            return f"{name}: ${val:,.0f} {arrow(chg)}{abs(chg):.2f}%"
        elif name in ["이더리움"]:
            return f"{name}: ${val:,.0f} {arrow(chg)}{abs(chg):.2f}%"
        else:
            return f"{name}: {val:,.2f} {arrow(chg)}{abs(chg):.2f}%"

    us_section = "*📊 미국 시장 지표*"
    kr_section = "\n*📊 한국 시장 지표*"
    macro_section = "\n*🌐 주요 매크로 지표*"
    crypto_section = "\n*🪙 가상자산*"

    us_lines = []
    kr_lines = []
    macro_lines = []
    crypto_lines = []

    us_names = ["S&P500", "나스닥", "다우"]
    kr_names = ["코스피", "코스닥"]
    macro_names = ["원달러", "WTI유가", "금"]
    crypto_names = ["비트코인", "이더리움"]

    for name in us_names:
        if name in data:
            val, chg = data[name]
            us_lines.append(fmt_price(name, val, chg))

    for name in kr_names:
        if name in data:
            val, chg = data[name]
            kr_lines.append(fmt_price(name, val, chg))

    for name in macro_names:
        if name in data:
            val, chg = data[name]
            macro_lines.append(fmt_price(name, val, chg))

    for name in crypto_names:
        if name in data:
            val, chg = data[name]
            crypto_lines.append(fmt_price(name, val, chg))

    result = us_section + "\n" + "\n".join(us_lines)
    result += kr_section + "\n" + "\n".join(kr_lines)
    result += macro_section + "\n" + "\n".join(macro_lines)
    result += crypto_section + "\n" + "\n".join(crypto_lines)

    return result

def build_prompt(articles_text, market):
    if market == "us":
        return f"""당신은 한국의 시니어 매크로 애널리스트입니다.

[예시 문체]
"미국 증시 상승 마감. 미-이란 협상 기대감 부상으로 투심 개선. 국제유가 장중 배럴당 100달러 돌파 후 협상 기대감에 상승폭 축소 마감. 나스닥 기술주 중심 매수세 유입, 연준 금리 동결 가능성 부각되며 위험자산 선호 심리 강화."

[작성 규칙]
- 반드시 한국어로만 작성
- 150~200자 내외
- 문장 끝은 반드시 명사형 또는 명사구로 종결 (~했다/~됩니다 절대 금지)
- 예시: "상승 마감.", "매수세 유입.", "투심 위축.", "하락 전환.", "관망세 지속."
- 개별 종목 언급 금지
- 아래 순서로 서술:
  1. 증시 방향 + 핵심 한 줄 원인
  2. 주요 매크로 변수 (금리/유가/환율/지정학 등) 및 수치 포함
  3. 투자자 심리 및 수급 흐름
- 요약문만 출력 (제목, 번호, 불릿 없이 하나의 단락으로)

뉴스:
{articles_text}"""
    else:
        return f"""당신은 한국의 시니어 매크로 애널리스트입니다.

[예시 문체]
"국내 증시 상승 마감. 30거래일 만에 장중 코스피 2,600선 돌파. 외국인 순매수 전환으로 수급 개선, 원달러 환율 하락세로 외국인 매수 유인 확대. 미국 증시 반등 훈풍 및 반도체 업황 회복 기대감이 투심 긍정 작용."

[작성 규칙]
- 반드시 한국어로만 작성
- 150~200자 내외
- 문장 끝은 반드시 명사형 또는 명사구로 종결 (~했다/~됩니다 절대 금지)
- 예시: "상승 마감.", "외국인 순매수 전환.", "투심 위축.", "하락 압력 지속.", "관망세 우세."
- 개별 종목 언급 금지
- 아래 순서로 서술:
  1. 증시 방향 + 핵심 한 줄 원인
  2. 주요 매크로 변수 (환율/외국인수급/유가/금리 등) 및 수치 포함
  3. 투자자 심리 및 수급 흐름
- 요약문만 출력 (제목, 번호, 불릿 없이 하나의 단락으로)

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
        if 'candidates' in data:
            return data['candidates'][0]['content']['parts'][0]['text'].strip()
        return None
    except Exception as e:
        print(f"Gemini 오류: {e}")
        return None

def summarize(articles_text, market):
    result = summarize_with_groq(articles_text, market)
    if result:
        return result
    result = summarize_with_gpt(articles_text, market)
    if result:
        return result
    result = summarize_with_gemini(articles_text, market)
    if result:
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
    summary = summarize(articles_text, "us")
    return summary

def get_kr_news():
    rss_urls = [
        "https://www.yna.co.kr/rss/economy.xml",
        "https://news.kbs.co.kr/rss/rss_economy.xml",
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
    summary = summarize(articles_text, "kr")
    return summary

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
