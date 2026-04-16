def fetch_history_with_retry(symbol, retries=3, base_sleep=2):
    last_error = None
    for attempt in range(retries):
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="40d", auto_adjust=False)
            if hist is not None and len(hist) >= 2:
                return hist
            raise RuntimeError(f"{symbol} 히스토리 데이터 부족")
        except Exception as e:
            last_error = e
            print(f"{symbol} 재시도 {attempt + 1}/{retries} 실패: {e}")
            time.sleep(base_sleep * (attempt + 1))
    raise last_error
