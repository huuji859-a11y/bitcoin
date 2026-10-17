# Daily Macro + Bitcoin Data Pipeline (USD)

GitHub Actions로 매일 미국 거시경제 데이터와 **달러 기준 비트코인(BTCUSDT)** 데이터를 수집하고 기초 지표를 계산합니다.

## 수집 데이터
- **Bitcoin (Binance BTCUSDT, USD/USDT 기준)**: 일봉 OHLCV, 거래대금, 수익률, 변동성, 이동평균
- **FRED**: 연방기금금리(DFF), 미국 10년물 국채금리(DGS10), 무역가중 달러지수(DTWEXBGS), CPI(CPIAUCSL), WTI 원유가격(DCOILWTICO)

> Binance BTCUSDT는 USDT 표시 페어입니다. 시장 데이터에서 달러와 거의 비슷하게 사용되지만, 엄밀히 USD 현물 가격과 완전히 동일하지는 않습니다. FRED 자료는 발표 주기와 시차가 달라 최신 관측일이 오늘과 다를 수 있습니다.

## GitHub 설정
1. 새 GitHub 저장소를 만들고 이 프로젝트 파일을 업로드합니다.
2. `Settings → Secrets and variables → Actions → New repository secret`에서 `FRED_API_KEY`를 추가합니다. 키가 없으면 BTC 데이터는 수집되고 FRED 데이터는 건너뜁니다.
   - FRED API 키: https://fred.stlouisfed.org/docs/api/api_key.html
3. `Settings → Actions → General → Workflow permissions`에서 `Read and write permissions`를 허용합니다.
4. `Actions` 탭에서 `Daily Macro and Bitcoin Data` → `Run workflow`로 테스트합니다.

## 자동 실행
매일 UTC 00:20 (한국시간 오전 9:20)에 실행됩니다. GitHub 예약 실행은 지연될 수 있습니다.

## 생성되는 파일
- `data/btc_usd_daily.csv`: BTCUSDT 일봉 및 기술 지표
- `data/fred_macro.csv`: FRED 거시경제 시계열
- `data/latest_summary.json`: 최신 데이터와 간단한 규칙 기반 상태 요약
- `data/run_log.json`: 수집 성공/실패 로그

## 로컬 실행
Python 3.11 이상:
```bash
pip install -r requirements.txt
export FRED_API_KEY="YOUR_KEY"  # Windows PowerShell: $env:FRED_API_KEY="YOUR_KEY"
python src/collect.py
```

## 출처 및 제한
- Binance 공개 시장 데이터 API: https://api.binance.com
- FRED API: https://fred.stlouisfed.org/docs/api/fred/
- API 제한, 서비스 장애, 데이터 지연이 있을 수 있습니다. `run_log.json`에서 상태를 확인하세요.
- 이 코드는 데이터 수집과 참고용 분석만 수행하며 자동 매매 주문을 내지 않습니다.
