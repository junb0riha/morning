import os
import re
import html
import json
import time
import calendar
import requests
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
import yfinance as yf
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

TELEGRAM_TOKEN   = os.environ.get('TELEGRAM_TOKEN', '').strip()
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '').strip()
NEWS_API_KEY     = os.environ.get('NEWS_API_KEY', '').strip()
GROQ_API_KEY     = os.environ.get('GROQ_API_KEY', '').strip()
OPENAI_API_KEY   = os.environ.get('OPENAI_API_KEY', '').strip()
GEMINI_API_KEY   = os.environ.get('GEMINI_API_KEY', '').strip()
EMAIL_SENDER     = os.environ.get('EMAIL_SENDER', '').strip()
EMAIL_PASSWORD   = os.environ.get('EMAIL_PASSWORD', '').strip()
EMAIL_RECEIVER   = 'junbo119.shim@samsung.com'

CACHE_FILE = Path("market_cache.json")
DIVIDER    = '━━━━━'

now_utc     = datetime.utcnow()
now_kst     = now_utc + timedelta(hours=9)
IS_MORNING  = now_kst.hour < 12
YEAR_START  = now_kst.date().replace(month=1, day=1)

print(f"현재 KST: {now_kst.strftime('%Y-%m-%d %H:%M')} / {'오전' if IS_MORNING else '오후'} 세션")


def clean_text(text):
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r'<[^>]+>', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


TICKERS = {
    "S&P500": "^GSPC", "나스닥": "^IXIC", "다우": "^DJI", "필라델피아반도체": "^SOX",
    "코스피": "^KS11", "코스닥": "^KQ11",
    "원달러": "KRW=X", "달러인덱스": "DX-Y.NYB",
    "WTI유가": "CL=F", "금": "GC=F",
    "비트코인": "BTC-USD", "이더리움": "ETH-USD",
    "미10년금리": "^TNX", "미2년금리": "^IRX", "VIX": "^VIX",
}

def fetch_history(symbol, retries=3):
    for attempt in range(retries):
        try:
            hist = yf.Ticker(symbol).history(period="400d", auto_adjust=False)
            if hist is not None and len(hist) >= 2:
                return hist
        except Exception as e:
            print(f"{symbol} 재시도 {attempt+1}/{retries}: {e}")
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"{symbol} 데이터 수집 실패")


def get_market_data():
    results, failed = {}, []
    for name, symbol in TICKERS.items():
        try:
            hist = fetch_history(symbol)
            curr = float(hist['Close'].iloc[-1])
            prev = float(hist['Close'].iloc[-2])
            cdate = hist.index[-1].date()
            day_chg = (curr - prev) / prev * 100

            yp = None
            for i in range(len(hist)-1, -1, -1):
                if hist.index[i].date() < YEAR_START:
                    yp = float(hist['Close'].iloc[i])
                    break

            results[name] = {
                "price":         curr,
                "date":          cdate.isoformat(),
                "day_change":    day_chg,
                "year_change":   (curr - yp) / yp * 100 if yp else None,
                "source_status": "live",
            }
        except Exception as e:
            failed.append(name)
            print(f"{name} 오류: {e}")
    return results, failed


def save_cache(data):
    try:
        CACHE_FILE.write_text(
            json.dumps({"saved_at_kst": now_kst.strftime("%Y-%m-%d %H:%M"), "data": data},
                       ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"캐시 저장 오류: {e}")


def load_cache():
    try:
        if CACHE_FILE.exists():
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"캐시 로드 오류: {e}")
    return None


def format_market_data(data):
    def arrow(v): return "▲" if v >= 0 else "▼"

    def fmt_price(name, p):
        if name == "원달러":                    return f"{p:,.1f}원"
        if name in ("WTI유가", "금"):            return f"${p:,.2f}"
        if name in ("비트코인", "이더리움"):     return f"${p:,.0f}"
        if name in ("미10년금리","미2년금리","VIX","달러인덱스"): return f"{p:.2f}"
        return f"{p:,.2f}"

    def fmt_row(name, d):
        p, dc, yc = d["price"], d["day_change"], d["year_change"]
        stale = " [cached]" if d.get("source_status") == "cached" else ""

        if name in ("미10년금리","미2년금리","VIX"):
            d_pt = p - p / (1 + dc/100)
            y_pt = p - p / (1 + yc/100) if yc is not None else None
            d_str = f"{'+' if dc>=0 else ''}{d_pt:.2f}pt"
            y_str = f"YTD {'+' if y_pt>=0 else ''}{y_pt:.2f}pt" if y_pt is not None else "YTD -"
        else:
            d_str = f"{arrow(dc)}{abs(dc):.2f}%"
            y_str = f"YTD {arrow(yc)}{abs(yc):.2f}%" if yc is not None else "YTD -"

        return f"{name} {fmt_price(name,p)}  {d_str}  {y_str}{stale}"

    def section(emoji, title, names):
        avail = [n for n in names if n in data]
        if not avail: return ""
        date_str = data[avail[0]]["date"][5:].replace("-","/")
        rows = "\n".join(fmt_row(n, data[n]) for n in names if n in data)
        return f"{emoji} {title}  ({date_str})\n{rows}\n"

    parts = [
        section("🇺🇸", "미국",     ["S&P500","나스닥","다우","필라델피아반도체"]),
        section("🇰🇷", "한국",     ["코스피","코스닥"]),
        section("💱", "매크로",    ["원달러","달러인덱스","WTI유가","금"]),
        section("📊", "금리/변동성", ["미10년금리","미2년금리","VIX"]),
        section("₿", "코인",      ["비트코인","이더리움"]),
    ]
    return "\n".join(p for p in parts if p).strip()


if IS_MORNING:
    NEWS_CUTOFF_KST = (now_kst - timedelta(days=1)).replace(hour=6, minute=0, second=0, microsecond=0)
else:
    NEWS_CUTOFF_KST = now_kst.replace(hour=15, minute=20, second=0, microsecond=0)
NEWS_CUTOFF_UTC = NEWS_CUTOFF_KST - timedelta(hours=9)
print(f"뉴스 cutoff: {NEWS_CUTOFF_KST.strftime('%Y-%m-%d %H:%M')} KST 이후")


def parse_rss(url, limit=15, cutoff_utc=None):
    try:
        res = requests.get(url, timeout=8, headers={"User-Agent":"Mozilla/5.0"})
        if res.status_code != 200:
            raise RuntimeError(f"HTTP {res.status_code}")
        root = ET.fromstring(res.content)
        items = root.findall('.//item')

        filtered, all_items = [], []
        for item in items[:limit]:
            title = clean_text(item.findtext('title',''))
            desc  = clean_text(item.findtext('description',''))
            pub   = clean_text(item.findtext('pubDate',''))
            if not title:
                continue
            entry = f"- [{pub}] {title}: {desc}"
            all_items.append(entry)

            if cutoff_utc:
                try:
                    dt = parsedate_to_datetime(pub)
                    if calendar.timegm(dt.utctimetuple()) >= calendar.timegm(cutoff_utc.utctimetuple()):
                        filtered.append(entry)
                except Exception:
                    filtered.append(entry)
            else:
                filtered.append(entry)

        if cutoff_utc and not filtered and all_items:
            print(f"  cutoff 이후 기사 없음, 최신 5개 폴백: {url[:50]}")
            return all_items[:5]
        return filtered
    except Exception as e:
        print(f"RSS 오류: {url[:60]} / {e}")
    return []


def dedupe(articles):
    seen, out = set(), []
    for item in articles:
        key = re.sub(r'\s+','', item.split("] ",1)[-1].split(":",1)[0]).lower()
        if key and key not in seen:
            seen.add(key)
            out.append(item)
    return out


def gnews_rss(query, lang="ko", country="KR"):
    q = requests.utils.quote(query)
    return f"https://news.google.com/rss/search?q={q}&hl={lang}-{country}&gl={country}&ceid={country}:{lang}"


def get_us_news():
    us_cutoff_utc = (now_kst - timedelta(days=1)).replace(hour=21, minute=0, second=0, microsecond=0) - timedelta(hours=9)
    queries = [
        "US stocks close market wrap S&P 500 Nasdaq Dow",
        "Wall Street stocks close market recap",
        "US market close treasury yields oil risk sentiment",
    ]
    urls = [gnews_rss(q,"en","US") for q in queries] + [
        "https://feeds.marketwatch.com/marketwatch/topstories/",
        "https://feeds.finance.yahoo.com/rss/2.0/headline?s=%5EGSPC&region=US&lang=en-US",
    ]
    articles = dedupe([a for url in urls for a in parse_rss(url, cutoff_utc=us_cutoff_utc)])
    print(f"미국 뉴스 수집: {len(articles)}건")
    return articles


def get_kr_news():
    suffix = "전일 마감" if IS_MORNING else "장 마감"
    queries = [
        f"코스피 {suffix} 외국인 기관 환율",
        f"코스닥 {suffix} 외국인 기관 환율",
        f"국내 증시 {suffix} 시황 외국인 수급",
        f"코스피 {suffix} 시황",
    ]
    urls = [gnews_rss(q) for q in queries] + [
        "https://www.yna.co.kr/rss/economy.xml",
        "https://finance.naver.com/news/news_list.naver?mode=LSS2D&section0=101&section1=258&rss=true",
        "https://ssl.pstatic.net/static/nf/rss/stock_market_rss.xml",
    ]
    articles = dedupe([a for url in urls for a in parse_rss(url, cutoff_utc=NEWS_CUTOFF_UTC)])
    print(f"한국 뉴스 수집: {len(articles)}건")

    if len(articles) < 3 and NEWS_API_KEY:
        try:
            from_dt = NEWS_CUTOFF_UTC.strftime("%Y-%m-%dT%H:%M:%SZ")
            q = requests.utils.quote(f"코스피 {suffix} 외국인 기관 환율 시황")
            res = requests.get(
                f"https://newsapi.org/v2/everything?q={q}&language=ko&sortBy=publishedAt"
                f"&from={from_dt}&pageSize=10&apiKey={NEWS_API_KEY}",
                timeout=10).json()
            extra = dedupe([
                f"- [{a.get('publishedAt','')}] {clean_text(a.get('title',''))}: {clean_text(a.get('description',''))}"
                for a in res.get('articles',[]) if a.get('title')
            ])
            articles = dedupe(articles + extra)
            print(f"NewsAPI 보완: 총 {len(articles)}건")
        except Exception as e:
            print(f"NewsAPI 오류: {e}")
    return articles


SYSTEM_PROMPT = "당신은 한국 증권사 데일리 시황을 작성하는 시니어 애널리스트입니다. 반드시 한국어로만 답변하세요."

def call_gemini(prompt, temp=0.2, max_tok=400):
    if not GEMINI_API_KEY: return None
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
        r = requests.post(url, json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temp, "maxOutputTokens": max_tok}
        }, timeout=20).json()
        return r['candidates'][0]['content']['parts'][0]['text'].strip()
    except Exception as e:
        print(f"Gemini 오류: {e}"); return None


def call_groq(prompt, temp=0.2, max_tok=400):
    if not GROQ_API_KEY: return None
    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type":"application/json"},
            json={"model":"llama-3.3-70b-versatile",
                  "messages":[{"role":"system","content":SYSTEM_PROMPT},{"role":"user","content":prompt}],
                  "max_tokens":max_tok,"temperature":temp}, timeout=20).json()
        return r['choices'][0]['message']['content'].strip()
    except Exception as e:
        print(f"Groq 오류: {e}"); return None


def call_gpt(prompt, temp=0.2, max_tok=400):
    if not OPENAI_API_KEY: return None
    try:
        r = requests.post("https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type":"application/json"},
            json={"model":"gpt-4o-mini",
                  "messages":[{"role":"system","content":SYSTEM_PROMPT},{"role":"user","content":prompt}],
                  "max_tokens":max_tok,"temperature":temp}, timeout=20).json()
        return r['choices'][0]['message']['content'].strip()
    except Exception as e:
        print(f"GPT 오류: {e}"); return None


def get_daily_fortune():
    date_label = now_kst.strftime("%Y년 %m월 %d일")
    weekday = ["월","화","수","목","금","토","일"][now_kst.weekday()]

    prompt = f"""당신은 사주명리학 전문가입니다.

[사주 정보]
- 생년월일: 1992년 1월 19일
- 태어난 시간: 오후 4시 30분
- 성별: 남성

위 사주를 바탕으로 오늘({date_label}, {weekday}요일)의 일진과 운세 흐름을 분석하여 아래 형식으로 출력하세요.

[출력 형식 - 반드시 4줄만]
☀️ 종합운: (50자 이상 100자 이하)
💰 금전운: (50자 이상 100자 이하)
💼 직장운: (50자 이상 100자 이하)
🌹 애정운: (50자 이상 100자 이하)

[규칙]
- 사주 일간과 오늘 일진의 관계를 반영한 현실적인 운세
- 한자 사용 절대 금지 (甲乙丙丁, 申時, 壬水 등 모든 한자 금지)
- 한글로만 서술 (기운, 흐름, 길일, 조화 등 한글 표현 사용)
- 긍정적이되 과장 없이
- 각 줄 반드시 50자 이상 100자 이하
- 4줄 외 어떤 설명도 출력 금지"""

    for fn in [call_gemini, call_groq, call_gpt]:
        try:
            result = fn(prompt, temp=0.7, max_tok=800)
            if result:
                print("운세 생성 완료")
                return result.strip()
        except Exception:
            pass
    return "오늘의 운세를 불러오지 못했습니다."


RULES_COMMON = """
[문체 기준]
- 짧고 단정한 기사체 (증권사 데일리 시황)
- 문장 종결: "~마감.", "~확대.", "~완화.", "~유입.", "~부각." 등 허용
- 장문 설명체("~했다","~됩니다","~이다") 금지
- 추측 표현("~할 수 있다","~가능성이 있다") 금지
- 개별 종목 언급 금지 / 뉴스에 없는 내용 추가 금지
- 기사 상충 시 종가 방향과 직결된 재료만 채택
- 장중 기사보다 마감 기사 우선
- 반드시 3~5문장 / 반드시 270자 이상 300자 이하

[서술 순서]
1. 증시 방향
2. 핵심 재료 1~2개
3. 금리/유가/환율/정책 중 중요한 것 1개
4. 투자심리 또는 수급 흐름 1문장

[출력 규칙]
- 한 단락만 출력 / 제목·번호·불릿 금지 / 과장·중복 표현 금지
"""

RETRY_SUFFIX = """

[재작성 지시 - 글자 수 부족]
- 반드시 270자 이상 300자 이하
- 반드시 3~5문장
- 같은 의미 반복 금지
- 수급 문장 1개 반드시 포함
- 환율 숫자 불명확 시 직접 언급 금지
"""

def build_prompt(articles_text, market, session):
    if market == "us":
        first_sent = '첫 문장은 반드시 "미국 증시 상승 마감." 또는 "미국 증시 하락 마감." 으로 시작'
        session_note = "전일 미국 증시 마감" if session == "morning" else "최근 미국 증시 마감"
        extra = ""
    else:
        first_sent = '첫 문장은 반드시 "국내 증시 상승 마감." 또는 "국내 증시 하락 마감." 으로 시작'
        session_note = "전일 국내 증시 마감" if session == "morning" else "당일 국내 증시 마감"
        extra = "- 외국인/기관/개인 수급 중 최소 1개 반드시 반영\n- 환율 수치가 기사별로 엇갈리면 숫자 직접 언급 금지\n"

    return f"""당신은 한국 증권사 데일리 시황 작성 시니어 애널리스트입니다. ({session_note} 기준)

{first_sent}
{extra}{RULES_COMMON}
뉴스:
{articles_text}"""


def post_process(text, market):
    if not text: return "요약 실패"
    text = clean_text(text).replace('"','').replace("'",'')
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'^(미국|국내|한국) 증시 시황\s*[::-]?\s*', '', text)

    prefix_map = {
        "us": ("미국 증시 상승 마감.", "미국 증시 하락 마감."),
        "kr": ("국내 증시 상승 마감.", "국내 증시 하락 마감."),
    }
    up_prefix, dn_prefix = prefix_map[market]
    if not (text.startswith(up_prefix) or text.startswith(dn_prefix)):
        if any(x in text for x in ["상승","반등","강세","오름세"]):
            text = up_prefix + " " + text
        elif any(x in text for x in ["하락","약세","내림세"]):
            text = dn_prefix + " " + text

    sentences = [s.strip() for s in re.split(r'(?<=\.)\s+', text) if s.strip()]
    seen, deduped = set(), []
    for s in sentences:
        if s not in seen:
            seen.add(s); deduped.append(s)
    text = " ".join(deduped)

    if len(text) > 350:
        cut = text[:350]
        lp = cut.rfind('.')
        if lp > 200:
            text = cut[:lp+1]
    return text.strip()


def summarize(articles_text, market, session):
    if not articles_text:
        return "뉴스 수집 실패"
    prompt = build_prompt(articles_text, market, session)
    engines = [("Gemini", call_gemini), ("Groq", call_groq), ("GPT", call_gpt)]
    best = None

    for name, fn in engines:
        result = fn(prompt)
        if not result:
            continue
        result = post_process(result, market)

        if len(result) < 270:
            retry = fn(prompt + RETRY_SUFFIX)
            if retry:
                retry = post_process(retry, market)
                if len(retry) > len(result):
                    result = retry

        print(f"{name} 요약 완료 / {len(result)}자")
        if len(result) >= 270:
            return result
        if not best or len(result) > len(best):
            best = result
    return best or "요약 실패"


def get_watchlist(us_text, kr_text):
    if not us_text and not kr_text:
        return "뉴스 수집 실패로 관심 종목 추출 불가"

    prompt = f"""당신은 한국 증권사 애널리스트입니다. 아래 뉴스에서 오늘(또는 가장 최근 거래일) 주목할 만한 종목을 추출하세요.

[추출 기준]
- 뉴스에 직접 언급된 종목 중, 시황에 영향이 크거나 투자자 관심이 높은 종목
- 미국 2~3개, 한국 2~3개 선정
- 각 종목별로 "왜 주목해야 하는지" 핵심 이유 1줄 (40자 이내)

[출력 형식 - 아래 형식을 정확히 지킬 것]
🇺🇸 미국
- [종목명(한글)]: [주목 사유]
- [종목명(한글)]: [주목 사유]

🇰🇷 한국
- [종목명(한글)]: [주목 사유]
- [종목명(한글)]: [주목 사유]

[규칙]
- 뉴스에 명확히 언급된 종목만 선택, 추측 금지
- 반드시 한글 종목명 사용 (예: 엔비디아, 테슬라, 삼성전자, SK하이닉스)
- 미국 종목 괄호에 영문 티커 병기 (예: 엔비디아(NVDA))
- 40자 이내 짧고 명료하게
- 다른 설명, 제목, 번호 금지

[미국 뉴스]
{us_text[:2000]}

[한국 뉴스]
{kr_text[:2000]}"""

    for fn in [call_gemini, call_groq, call_gpt]:
        try:
            result = fn(prompt, temp=0.3, max_tok=600)
            if result:
                print("관심 종목 추출 완료")
                return result.strip()
        except Exception:
            pass
    return "관심 종목 추출 실패"


def send_telegram(message):
    res = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "disable_web_page_preview": True},
        timeout=15)
    print("텔레그램:", res.status_code)


def send_email(subject, body):
    if not EMAIL_SENDER or not EMAIL_PASSWORD:
        print("이메일 설정 없음, 스킵"); return
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From']    = EMAIL_SENDER
        msg['To']      = EMAIL_RECEIVER
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        msg.attach(MIMEText(
            f'<html><body><pre style="font-family:Malgun Gothic,Arial,sans-serif;'
            f'font-size:14px;line-height:2.0;white-space:pre-wrap">{body}</pre></body></html>',
            'html', 'utf-8'))
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(EMAIL_SENDER, EMAIL_PASSWORD)
            smtp.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
        print("이메일 전송 완료")
    except Exception as e:
        print(f"이메일 오류: {e}")


if __name__ == "__main__":
    date_str = now_kst.strftime("'%y.%m.%d %H:%M")
    session  = "morning" if IS_MORNING else "afternoon"

    print("시장 데이터 수집 중...")
    market_data, failed = get_market_data()
    market_note = ""

    if market_data:
        save_cache(market_data)
        if failed:
            market_note = f"※ 시장 데이터 일부 수집 실패 ({len(failed)}/15)"
        market_block = format_market_data(market_data)
    else:
        cached = load_cache()
        if cached and cached.get("data"):
            market_data = cached["data"]
            for k in market_data:
                market_data[k]["source_status"] = "cached"
            market_note  = f"※ 실시간 수집 실패 - 마지막 정상값 사용 ({cached['saved_at_kst']} KST)"
            market_block = format_market_data(market_data)
        else:
            market_note  = "※ 시장 데이터 수집 실패"
            market_block = ""

    print("미국 뉴스 수집 중...")
    us_articles = get_us_news()
    us_text     = "\n".join(us_articles[:10]) if us_articles else ""
    us_summary  = summarize(us_text, "us", session) if us_text else "미국 증시 시황 뉴스 수집 실패."

    print("한국 뉴스 수집 중...")
    kr_articles = get_kr_news()
    kr_text     = "\n".join(kr_articles[:10]) if kr_articles else ""
    kr_summary  = summarize(kr_text, "kr", session) if kr_text else "국내 증시 시황 뉴스 수집 실패."

    print("운세 생성 중...")
    fortune = get_daily_fortune()

    print("관심 종목 추출 중...")
    watchlist = get_watchlist(us_text, kr_text)

    header = f"{market_note}\n{market_block}" if market_note else market_block
    full_message = f"""brief - {date_str}
{DIVIDER}
🔮 오늘의 운세
{fortune}

{DIVIDER}
📈 마켓 데이터
{DIVIDER}
{header}

{DIVIDER}
🇺🇸 미국 증시
{DIVIDER}
{us_summary}

{DIVIDER}
🇰🇷 한국 증시
{DIVIDER}
{kr_summary}

{DIVIDER}
🎯 오늘의 관심 종목
{DIVIDER}
{watchlist}"""

    send_telegram(full_message)
    send_email(f"brief - {date_str}", full_message)
    print("전송 완료")
