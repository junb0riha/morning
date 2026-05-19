import os
import re
import html
import json
import time
import requests
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
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

CACHE_FILE = Path("market_cache.json")

now_utc = datetime.utcnow()
now_kst = now_utc + timedelta(hours=9)
MONTH_START = now_kst.date().replace(day=1)
YEAR_START = now_kst.date().replace(month=1, day=1)
DIVIDER = '━━━━━'

# 시간 기준
# 미국 뉴스: 당일 KST 06:00 이후 기사
# 한국 뉴스: 당일 KST 15:30 이후 기사
US_NEWS_CUTOFF_KST = now_kst.replace(hour=6, minute=0, second=0, microsecond=0)
KR_NEWS_CUTOFF_KST = now_kst.replace(hour=15, minute=30, second=0, microsecond=0)

print(f"현재 KST: {now_kst.strftime('%Y-%m-%d %H:%M')}")
print(f"미국 뉴스 기준: {US_NEWS_CUTOFF_KST.strftime('%H:%M')} KST 이후")
print(f"한국 뉴스 기준: {KR_NEWS_CUTOFF_KST.strftime('%H:%M')} KST 이후")


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def parse_pub_date(pub_date_str: str):
    """RSS pubDate 문자열을 KST datetime으로 변환"""
    try:
        dt = parsedate_to_datetime(pub_date_str)
        return dt.astimezone(tz=None).replace(tzinfo=None) + timedelta(hours=9) - timedelta(hours=dt.utcoffset().total_seconds() / 3600 if dt.utcoffset() else 0)
    except Exception:
        return None


def save_market_cache(data: dict):
    try:
        payload = {
            "saved_at_kst": now_kst.strftime("%Y-%m-%d %H:%M"),
            "data": data
        }
        CACHE_FILE.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        print("시장 데이터 캐시 저장 완료")
    except Exception as e:
        print(f"캐시 저장 오류: {e}")


def load_market_cache():
    try:
        if CACHE_FILE.exists():
            payload = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            print("시장 데이터 캐시 로드 완료")
            return payload
    except Exception as e:
        print(f"캐시 로드 오류: {e}")
    return None


def fetch_history_with_retry(symbol, retries=3, base_sleep=2):
    last_error = None
    for attempt in range(retries):
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="400d", auto_adjust=False)
            if hist is not None and len(hist) >= 2:
                return hist
            raise RuntimeError(f"{symbol} 히스토리 데이터 부족")
        except Exception as e:
            last_error = e
            print(f"{symbol} 재시도 {attempt + 1}/{retries} 실패: {e}")
            time.sleep(base_sleep * (attempt + 1))
    raise last_error


def get_market_data():
    tickers = {
        "S&P500": "^GSPC",
        "나스닥": "^IXIC",
        "다우": "^DJI",
        "필라델피아반도체": "^SOX",
        "코스피": "^KS11",
        "코스닥": "^KQ11",
        "원달러": "KRW=X",
        "달러인덱스": "DX-Y.NYB",
        "WTI유가": "CL=F",
        "금": "GC=F",
        "미10년금리": "^TNX",
        "미2년금리": "^IRX",
        "VIX": "^VIX",
        "비트코인": "BTC-USD",
        "이더리움": "ETH-USD",
    }

    results = {}
    failed = []

    for name, symbol in tickers.items():
        try:
            hist = fetch_history_with_retry(symbol)
            curr = float(hist['Close'].iloc[-1])
            prev = float(hist['Close'].iloc[-2])
            curr_date = hist.index[-1].date()
            day_change = ((curr - prev) / prev) * 100

            month_price = None
            for i in range(len(hist) - 1, -1, -1):
                if hist.index[i].date() < MONTH_START:
                    month_price = float(hist['Close'].iloc[i])
                    break

            year_price = None
            for i in range(len(hist) - 1, -1, -1):
                if hist.index[i].date() < YEAR_START:
                    year_price = float(hist['Close'].iloc[i])
                    break

            month_change = ((curr - month_price) / month_price) * 100 if month_price else None
            year_change = ((curr - year_price) / year_price) * 100 if year_price else None

            results[name] = {
                "price": curr,
                "date": curr_date.isoformat(),
                "day_change": day_change,
                "month_change": month_change,
                "year_change": year_change,
                "source_status": "live"
            }

        except Exception as e:
            failed.append(name)
            print(f"{name} 데이터 오류: {e}")

    return results, failed


def format_market_data(data):
    def arrow(chg):
        return "▲" if chg >= 0 else "▼"

    def fmt(name, d):
        price = d["price"]
        day_chg = d["day_change"]
        month_chg = d["month_change"]
        year_chg = d["year_change"]
        status = d.get("source_status", "live")

        if name == "원달러":
            price_str = f"{price:,.1f}원"
        elif name in ["WTI유가", "금"]:
            price_str = f"${price:,.2f}"
        elif name in ["비트코인", "이더리움"]:
            price_str = f"${price:,.0f}"
        elif name in ["미10년금리", "미2년금리", "VIX", "달러인덱스"]:
            price_str = f"{price:.2f}"
        else:
            price_str = f"{price:,.2f}"

        day_str = f"{arrow(day_chg)}{abs(day_chg):.2f}%"
        mtd_str = f"MTD {arrow(month_chg)}{abs(month_chg):.2f}%" if month_chg is not None else "MTD -"
        ytd_str = f"YTD {arrow(year_chg)}{abs(year_chg):.2f}%" if year_chg is not None else "YTD -"

        if name in ["미10년금리", "미2년금리", "VIX"]:
            prev_price = price / (1 + day_chg / 100) if day_chg != -100 else price
            day_pt = price - prev_price
            day_str = f"{'+' if day_pt >= 0 else ''}{day_pt:.2f}pt"
            if month_chg is not None:
                prev_m = price / (1 + month_chg / 100)
                mtd_pt = price - prev_m
                mtd_str = f"MTD {'+' if mtd_pt >= 0 else ''}{mtd_pt:.2f}pt"
            if year_chg is not None:
                prev_y = price / (1 + year_chg / 100)
                ytd_pt = price - prev_y
                ytd_str = f"YTD {'+' if ytd_pt >= 0 else ''}{ytd_pt:.2f}pt"

        stale = " [cached]" if status == "cached" else ""
        return f"{name}: {price_str}  {day_str}  ({mtd_str} / {ytd_str}){stale}"

    lines = []

    us_names = ["S&P500", "나스닥", "다우", "필라델피아반도체"]
    us_available = [n for n in us_names if n in data]
    if us_available:
        date_str = data[us_available[0]]["date"][5:].replace("-", "/")
        lines.append(f"🇺🇸미국 ({date_str} 기준)")
        for name in us_names:
            if name in data:
                lines.append(fmt(name, data[name]))
        lines.append("")

    kr_names = ["코스피", "코스닥"]
    kr_available = [n for n in kr_names if n in data]
    if kr_available:
        date_str = data[kr_available[0]]["date"][5:].replace("-", "/")
        lines.append(f"🇰🇷한국 ({date_str} 기준)")
        for name in kr_names:
            if name in data:
                lines.append(fmt(name, data[name]))
        lines.append("")

    macro_names = ["원달러", "달러인덱스", "WTI유가", "금"]
    macro_available = [n for n in macro_names if n in data]
    if macro_available:
        date_str = data[macro_available[0]]["date"][5:].replace("-", "/")
        lines.append(f"▪ 매크로 ({date_str} 기준)")
        for name in macro_names:
            if name in data:
                lines.append(fmt(name, data[name]))
        lines.append("")

    rate_names = ["미10년금리", "미2년금리", "VIX"]
    rate_available = [n for n in rate_names if n in data]
    if rate_available:
        date_str = data[rate_available[0]]["date"][5:].replace("-", "/")
        lines.append(f"▪ 금리/변동성 ({date_str} 기준)")
        for name in rate_names:
            if name in data:
                lines.append(fmt(name, data[name]))
        lines.append("")

    crypto_names = ["비트코인", "이더리움"]
    crypto_available = [n for n in crypto_names if n in data]
    if crypto_available:
        date_str = data[crypto_available[0]]["date"][5:].replace("-", "/")
        lines.append(f"▪ 코인 ({date_str} 기준)")
        for name in crypto_names:
            if name in data:
                lines.append(fmt(name, data[name]))

    return "\n".join(lines).strip()


def build_prompt(articles_text, market):
    if market == "us":
        return f"""당신은 한국 증권사 데일리 시황을 작성하는 시니어 애널리스트입니다. (전영업일 미국 증시 마감 기사 기준)

[문체 기준]
- 반드시 한국어로만 작성
- 한국 증권사 데일리 시황 문체 사용
- 짧고 단정한 기사체
- 첫 문장은 반드시 아래 둘 중 하나로 시작
  1) 미국 증시 상승 마감.
  2) 미국 증시 하락 마감.
- 모든 문장은 명사형으로 종결
  (예: "~마감.", "~확대.", "~유입.", "~부각.", "~우위.", "~반영.", "~강화.", "~전환.")
- "~했다", "~됩니다", "~이다", "~다" 등 서술형 종결 절대 금지
- "가능성이 있다", "~할 수 있다" 등 추측 표현 절대 금지
- 금리 관련 코멘트 금지
- 개별 종목 언급 금지
- 뉴스에 없는 내용 추가 금지
- 3문장 이상 5문장 이하
- 270자 이상 300자 이하

[서술 순서]
1. 증시 방향
2. 핵심 재료 1~2개
3. 유가/환율/지정학 변수 중 1개
4. 투자심리 또는 수급 흐름

[출력 규칙]
- 한 단락으로만 출력
- 제목, 번호, 불릿 금지
- 중복 표현 금지

뉴스:
{articles_text}"""
    else:
        return f"""당신은 한국 증권사 데일리 시황을 작성하는 시니어 애널리스트입니다. (당일 오후 3시 30분 이후 국내 증시 마감 기사 기준)

[문체 기준]
- 반드시 한국어로만 작성
- 한국 증권사 데일리 시황 문체 사용
- 짧고 단정한 기사체
- 첫 문장은 반드시 아래 둘 중 하나로 시작
  1) 국내 증시 상승 마감.
  2) 국내 증시 하락 마감.
- 모든 문장은 명사형으로 종결
  (예: "~마감.", "~확대.", "~유입.", "~부각.", "~우위.", "~반영.", "~전환.")
- "~했다", "~됩니다", "~이다", "~다" 등 서술형 종결 절대 금지
- "가능성이 있다", "~할 수 있다" 등 추측 표현 절대 금지
- 금리 관련 코멘트 금지
- 개별 종목 언급 금지
- 뉴스에 없는 내용 추가 금지
- 외국인/기관/개인 수급 중 최소 1개 반드시 반영
- 환율 수치가 기사별로 엇갈리면 숫자 직접 언급 금지
- 3문장 이상 5문장 이하
- 270자 이상 300자 이하

[서술 순서]
1. 증시 방향
2. 핵심 재료 1~2개
3. 환율/외국인수급 중 1개
4. 투자심리 또는 수급 흐름

[출력 규칙]
- 한 단락으로만 출력
- 제목, 번호, 불릿 금지
- 중복 표현 금지

뉴스:
{articles_text}"""


def post_process_summary(text, market):
    if not text:
        return "요약 실패"
    text = clean_text(text)
    text = text.replace('"', '').replace("'", "")
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'^(미국 증시 시황|국내 증시 시황|한국 증시 시황|시황)\s*[:：-]?\s*', '', text)

    if market == "us":
        if not (text.startswith("미국 증시 상승 마감.") or text.startswith("미국 증시 하락 마감.")):
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

    sentences = [s.strip() for s in re.split(r'(?<=\.)\s+', text) if s.strip()]
    deduped = []
    seen = set()
    for s in sentences:
        if s not in seen:
            seen.add(s)
            deduped.append(s)
    text = " ".join(deduped)

    if len(text) > 350:
        cut = text[:350]
        last_period = cut.rfind('.')
        if last_period > 200:
            text = cut[:last_period + 1]

    return text.strip()


def summarize_with_gemini(prompt_text):
    if not GEMINI_API_KEY:
        return None
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
        res = requests.post(url, json={
            "contents": [{"parts": [{"text": prompt_text}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 400}
        }, timeout=20)
        data = res.json()
        if 'candidates' in data:
            return data['candidates'][0]['content']['parts'][0]['text'].strip()
        return None
    except Exception as e:
        print(f"Gemini 오류: {e}")
        return None


def summarize_with_groq(prompt_text):
    if not GROQ_API_KEY:
        return None
    try:
        res = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": "당신은 한국 증권사 데일리 시황을 작성하는 시니어 애널리스트입니다. 반드시 한국어로만 답변하세요."},
                    {"role": "user", "content": prompt_text}
                ],
                "max_tokens": 400,
                "temperature": 0.2
            }, timeout=20)
        data = res.json()
        if 'choices' in data:
            return data['choices'][0]['message']['content'].strip()
        return None
    except Exception as e:
        print(f"Groq 오류: {e}")
        return None


def summarize_with_gpt(prompt_text):
    if not OPENAI_API_KEY:
        return None
    try:
        res = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "당신은 한국 증권사 데일리 시황을 작성하는 시니어 애널리스트입니다. 반드시 한국어로만 답변하세요."},
                    {"role": "user", "content": prompt_text}
                ],
                "max_tokens": 400,
                "temperature": 0.2
            }, timeout=20)
        data = res.json()
        if 'choices' in data:
            return data['choices'][0]['message']['content'].strip()
        return None
    except Exception as e:
        print(f"GPT 오류: {e}")
        return None


def summarize(articles_text, market):
    base_prompt = build_prompt(articles_text, market)
    engines = [
        ("Gemini", summarize_with_gemini),
        ("Groq", summarize_with_groq),
        ("GPT", summarize_with_gpt),
    ]
    best_result = None
    for engine_name, engine_func in engines:
        result = engine_func(base_prompt)
        if result:
            result = post_process_summary(result, market)
            if len(result) < 260:
                retry_prompt = base_prompt + """

[재작성 지시]
- 반드시 270자 이상 300자 이하
- 반드시 3문장 이상 5문장 이하
- 모든 문장 명사형 종결 필수
- 같은 의미 반복 금지
- 수급 문장 1개 반드시 포함
"""
                retry_result = engine_func(retry_prompt)
                if retry_result:
                    retry_result = post_process_summary(retry_result, market)
                    if len(retry_result) >= len(result):
                        result = retry_result

            print(f"{engine_name} 요약 성공 / 길이: {len(result)}")
            if len(result) >= 260:
                return result
            if not best_result or len(result) > len(best_result):
                best_result = result

    return best_result if best_result else "요약 실패"


def parse_rss_items(rss_url, cutoff_kst=None, limit=10):
    """RSS 파싱 + cutoff_kst 이후 기사만 필터링"""
    articles = []
    try:
        res = requests.get(rss_url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        if res.status_code != 200:
            raise RuntimeError(f"HTTP {res.status_code}")
        content_type = res.headers.get("Content-Type", "")
        if "xml" not in content_type and "rss" not in content_type and not res.text.lstrip().startswith("<"):
            raise RuntimeError(f"비정상 응답: {content_type}")

        root = ET.fromstring(res.content)
        count = 0
        for item in root.findall('.//item'):
            if count >= limit:
                break
            title = clean_text(item.findtext('title', ''))
            description = clean_text(item.findtext('description', ''))
            pub_date_str = clean_text(item.findtext('pubDate', ''))
            if not title:
                continue

            # 시간 필터링
            if cutoff_kst and pub_date_str:
                pub_kst = parse_pub_date(pub_date_str)
                if pub_kst and pub_kst < cutoff_kst:
                    continue

            articles.append(f"- [{pub_date_str}] {title}: {description}")
            count += 1

    except Exception as e:
        print(f"RSS 오류: {rss_url} / {e}")
    return articles


def dedupe_articles_by_title(articles):
    deduped = []
    seen_titles = set()
    for item in articles:
        try:
            title_part = item.split("] ", 1)[-1].split(":", 1)[0].strip()
        except Exception:
            title_part = item
        normalized = re.sub(r'\s+', ' ', title_part).strip().lower()
        if normalized and normalized not in seen_titles:
            seen_titles.add(normalized)
            deduped.append(item)
    return deduped


def get_us_news():
    """전영업일 미국 마감 기사 - 당일 KST 06:00 이후 수집"""
    queries = [
        "US stocks close market wrap S&P 500 Nasdaq Dow",
        "Wall Street stocks close market recap",
        "S&P 500 Nasdaq Dow close recap overnight",
        "US market close oil risk sentiment",
    ]
    rss_urls = [
        f"https://news.google.com/rss/search?q={requests.utils.quote(q)}&hl=en-US&gl=US&ceid=US:en"
        for q in queries
    ]
    rss_urls.extend([
        "https://feeds.marketwatch.com/marketwatch/topstories/",
        "https://feeds.finance.yahoo.com/rss/2.0/headline?s=%5EGSPC&region=US&lang=en-US",
    ])

    articles = []
    for rss_url in rss_urls:
        items = parse_rss_items(rss_url, cutoff_kst=US_NEWS_CUTOFF_KST, limit=7)
        articles.extend(items)

    articles = dedupe_articles_by_title(articles)
    print(f"미국 뉴스 수집 (필터 후): {len(articles)}건")

    # 필터 후 기사가 없으면 시간 필터 없이 재시도
    if not articles:
        print("미국 뉴스 시간 필터 결과 없음 → 필터 없이 재시도")
        for rss_url in rss_urls[:4]:
            items = parse_rss_items(rss_url, cutoff_kst=None, limit=5)
            articles.extend(items)
        articles = dedupe_articles_by_title(articles)
        print(f"미국 뉴스 재수집: {len(articles)}건")

    if not articles:
        return "미국 증시 시황 뉴스 수집 실패."

    articles_text = "\n".join(articles[:10])
    return summarize(articles_text, "us")


def get_kr_news():
    """당일 KST 15:30 이후 국내 마감 기사 수집"""
    queries = [
        "코스피 장 마감 외국인 기관 개인 환율",
        "코스닥 장 마감 외국인 기관 환율",
        "국내 증시 마감 시황 외국인 수급 환율",
        "코스피 코스닥 마감 시황 외국인 환율",
    ]
    rss_urls = [
        f"https://news.google.com/rss/search?q={requests.utils.quote(q)}&hl=ko&gl=KR&ceid=KR:ko"
        for q in queries
    ]
    rss_urls.append("https://www.yna.co.kr/rss/economy.xml")

    articles = []
    for rss_url in rss_urls:
        items = parse_rss_items(rss_url, cutoff_kst=KR_NEWS_CUTOFF_KST, limit=7)
        articles.extend(items)

    articles = dedupe_articles_by_title(articles)
    print(f"한국 뉴스 수집 (필터 후): {len(articles)}건")

    # 필터 후 기사가 없으면 시간 필터 없이 재시도
    if not articles:
        print("한국 뉴스 시간 필터 결과 없음 → 필터 없이 재시도")
        for rss_url in rss_urls[:4]:
            items = parse_rss_items(rss_url, cutoff_kst=None, limit=5)
            articles.extend(items)
        articles = dedupe_articles_by_title(articles)
        print(f"한국 뉴스 재수집: {len(articles)}건")

    if not articles:
        return "국내 증시 시황 뉴스 수집 실패."

    articles_text = "\n".join(articles[:10])
    return summarize(articles_text, "kr")


def build_telegram_message(date_str, header_block, us_summary, kr_summary):
    """텔레그램용 메시지 - 마크다운 볼드 적용"""
    return f"""*데일리 브리프 — {date_str} KST*
{DIVIDER}

{header_block}

{DIVIDER}
*🇺🇸 미국 증시 시황*
{DIVIDER}
{us_summary}

{DIVIDER}
*🇰🇷 한국 증시 시황*
{DIVIDER}
{kr_summary}"""


def build_email_body(date_str, header_block, us_summary, kr_summary):
    """이메일용 메시지 - plain text (별표 제거)"""
    return f"""데일리 브리프 — {date_str} KST
{DIVIDER}

{header_block}

{DIVIDER}
🇺🇸 미국 증시 시황
{DIVIDER}
{us_summary}

{DIVIDER}
🇰🇷 한국 증시 시황
{DIVIDER}
{kr_summary}"""


def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
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
    date_str = now_kst.strftime('%Y년 %m월 %d일 %H:%M')

    print("시장 데이터 수집 중...")
    market_data, failed_items = get_market_data()

    market_note = ""
    market_block = ""

    if market_data:
        save_market_cache(market_data)
        fail_count = len(failed_items)
        if fail_count > 0:
            market_note = f"※ 시장 데이터 일부 수집 실패 ({fail_count}/15)"
        market_block = format_market_data(market_data)
    else:
        cache_payload = load_market_cache()
        if cache_payload and cache_payload.get("data"):
            market_data = cache_payload["data"]
            for key in market_data:
                market_data[key]["source_status"] = "cached"
            market_note = f"※ 실시간 수집 실패 — 마지막 정상 수집값 사용 ({cache_payload['saved_at_kst']} KST)"
            market_block = format_market_data(market_data)
        else:
            market_note = "※ 시장 데이터 수집 실패"
            market_block = ""

    print("미국 뉴스 수집 중...")
    us_summary = get_us_news()

    print("한국 뉴스 수집 중...")
    kr_summary = get_kr_news()

    header_block = f"{market_note}\n{market_block}" if market_note else market_block

    tg_message = build_telegram_message(date_str, header_block, us_summary, kr_summary)
    email_body = build_email_body(date_str, header_block, us_summary, kr_summary)

    send_telegram(tg_message)

    email_subject = f"[데일리 브리프] {date_str}"
    send_email(email_subject, email_body)

    print("전송 완료")
