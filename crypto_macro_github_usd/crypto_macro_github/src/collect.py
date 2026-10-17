from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
TIMEOUT = 25
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "daily-macro-btc-research/1.0"})

FRED_SERIES = {
    "DFF": "fed_funds_rate_pct",
    "DGS10": "us_10y_treasury_yield_pct",
    "DTWEXBGS": "trade_weighted_usd_index",
    "CPIAUCSL": "us_cpi_sa_index",
    "DCOILWTICO": "wti_crude_usd_per_barrel",
}


def get_json(url: str, params: dict[str, Any] | None = None) -> Any:
    response = SESSION.get(url, params=params, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


def write_csv(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False, encoding="utf-8-sig")


def collect_btc_usd() -> pd.DataFrame:
    """Download completed daily BTCUSDT candles. USDT is USD-like, not strictly USD."""
    raw = get_json(
        "https://api.binance.com/api/v3/klines",
        {"symbol": "BTCUSDT", "interval": "1d", "limit": 1000},
    )
    columns = [
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades", "taker_buy_base",
        "taker_buy_quote", "ignore",
    ]
    df = pd.DataFrame(raw, columns=columns)
    if df.empty:
        raise RuntimeError("Binance returned no BTCUSDT candles")

    df["date"] = pd.to_datetime(df["open_time"], unit="ms", utc=True).dt.strftime("%Y-%m-%d")
    numeric = ["open", "high", "low", "close", "volume", "quote_volume", "trades",
               "taker_buy_base", "taker_buy_quote"]
    for col in numeric:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # The last kline can still be forming; omit it unless its close time has passed.
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    df = df.loc[pd.to_numeric(df["close_time"], errors="coerce") < now_ms].copy()
    df = df.sort_values("date").drop_duplicates("date").reset_index(drop=True)

    df["return_1d_pct"] = df["close"].pct_change(1) * 100
    df["return_7d_pct"] = df["close"].pct_change(7) * 100
    df["return_30d_pct"] = df["close"].pct_change(30) * 100
    daily_returns = df["close"].pct_change()
    df["volatility_7d_annualized_pct"] = daily_returns.rolling(7).std() * (365 ** 0.5) * 100
    df["volatility_30d_annualized_pct"] = daily_returns.rolling(30).std() * (365 ** 0.5) * 100
    df["sma_20"] = df["close"].rolling(20).mean()
    df["sma_50"] = df["close"].rolling(50).mean()
    df["close_vs_sma20_pct"] = (df["close"] / df["sma_20"] - 1) * 100
    df["quote_volume_change_1d_pct"] = df["quote_volume"].pct_change() * 100
    df["taker_buy_quote_share_pct"] = (
        df["taker_buy_quote"] / df["quote_volume"].replace(0, pd.NA) * 100
    )
    df["quote_currency"] = "USDT (USD-like)"
    df = df.drop(columns=["open_time", "close_time", "ignore"], errors="ignore")
    return df


def collect_fred() -> tuple[pd.DataFrame, dict[str, Any]]:
    api_key = os.getenv("FRED_API_KEY", "").strip()
    if not api_key:
        return pd.DataFrame(columns=["date", "series_id", "series_name", "value"]), {
            "status": "skipped", "reason": "FRED_API_KEY secret not configured"
        }

    records: list[dict[str, Any]] = []
    statuses: dict[str, Any] = {}
    for series_id, series_name in FRED_SERIES.items():
        try:
            payload = get_json(
                "https://api.stlouisfed.org/fred/series/observations",
                {
                    "series_id": series_id,
                    "api_key": api_key,
                    "file_type": "json",
                    "sort_order": "asc",
                    "observation_start": "2015-01-01",
                },
            )
            obs = payload.get("observations", [])
            valid_count = 0
            for item in obs:
                value = item.get("value")
                if value in (None, ".", ""):
                    continue
                try:
                    numeric_value = float(value)
                except (TypeError, ValueError):
                    continue
                records.append({
                    "date": item.get("date"),
                    "series_id": series_id,
                    "series_name": series_name,
                    "value": numeric_value,
                })
                valid_count += 1
            statuses[series_id] = {"status": "ok", "observations": valid_count}
        except Exception as exc:
            statuses[series_id] = {"status": "error", "error": str(exc)[:300]}

    df = pd.DataFrame(records, columns=["date", "series_id", "series_name", "value"])
    return df, {"status": "ok" if not df.empty else "error", "series": statuses}


def build_summary(btc: pd.DataFrame, macro: pd.DataFrame) -> dict[str, Any]:
    if btc.empty:
        raise RuntimeError("BTC dataset is empty")
    last = btc.iloc[-1]
    summary: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "btc_pair": "BTCUSDT",
        "quote_currency_note": "USDT is USD-like but is not exactly USD",
        "latest_completed_daily_candle": str(last["date"]),
        "btc_close_usdt": float(last["close"]),
        "btc_return_1d_pct": safe_float(last.get("return_1d_pct")),
        "btc_return_7d_pct": safe_float(last.get("return_7d_pct")),
        "btc_return_30d_pct": safe_float(last.get("return_30d_pct")),
        "btc_volatility_7d_annualized_pct": safe_float(last.get("volatility_7d_annualized_pct")),
        "btc_volatility_30d_annualized_pct": safe_float(last.get("volatility_30d_annualized_pct")),
        "btc_sma20": safe_float(last.get("sma_20")),
        "btc_sma50": safe_float(last.get("sma_50")),
        "btc_close_vs_sma20_pct": safe_float(last.get("close_vs_sma20_pct")),
        "btc_quote_volume_usdt": safe_float(last.get("quote_volume")),
        "btc_taker_buy_quote_share_pct": safe_float(last.get("taker_buy_quote_share_pct")),
        "macro_latest": {},
        "rule_based_readout": [],
        "disclaimer": "Descriptive data summary only; not investment advice or a guaranteed forecast.",
    }

    if summary["btc_close_vs_sma20_pct"] is not None:
        if summary["btc_close_vs_sma20_pct"] > 0:
            summary["rule_based_readout"].append("BTC close is above its 20-day moving average.")
        else:
            summary["rule_based_readout"].append("BTC close is at or below its 20-day moving average.")
    r7 = summary["btc_return_7d_pct"]
    if r7 is not None:
        summary["rule_based_readout"].append(
            "BTC 7-day momentum is positive." if r7 > 0 else "BTC 7-day momentum is non-positive."
        )

    if not macro.empty:
        for series_id in FRED_SERIES:
            part = macro.loc[macro["series_id"] == series_id].sort_values("date")
            if not part.empty:
                latest = part.iloc[-1]
                summary["macro_latest"][series_id] = {
                    "name": str(latest["series_name"]),
                    "observation_date": str(latest["date"]),
                    "value": float(latest["value"]),
                }
    return summary


def safe_float(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def main() -> int:
    started = datetime.now(timezone.utc).isoformat()
    log: dict[str, Any] = {"started_at_utc": started, "steps": {}}

    try:
        btc = collect_btc_usd()
        write_csv(btc, DATA_DIR / "btc_usd_daily.csv")
        log["steps"]["btc_binance"] = {
            "status": "ok",
            "rows": int(len(btc)),
            "latest_date": str(btc.iloc[-1]["date"]) if not btc.empty else None,
        }
    except Exception as exc:
        log["steps"]["btc_binance"] = {"status": "error", "error": str(exc)[:500]}
        log["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        (DATA_DIR / "run_log.json").write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(log, ensure_ascii=False, indent=2))
        return 1

    try:
        macro, macro_status = collect_fred()
        write_csv(macro, DATA_DIR / "fred_macro.csv")
        log["steps"]["fred"] = macro_status
    except Exception as exc:
        macro = pd.DataFrame(columns=["date", "series_id", "series_name", "value"])
        log["steps"]["fred"] = {"status": "error", "error": str(exc)[:500]}

    try:
        summary = build_summary(btc, macro)
        (DATA_DIR / "latest_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        log["steps"]["summary"] = {"status": "ok"}
    except Exception as exc:
        log["steps"]["summary"] = {"status": "error", "error": str(exc)[:500]}

    log["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    (DATA_DIR / "run_log.json").write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(log, ensure_ascii=False, indent=2))
    return 0 if log["steps"].get("btc_binance", {}).get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
