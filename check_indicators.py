import asyncio
import pyupbit
from src.collector.data_collector import UpbitCollector
from src.config import load_config
from src.strategy.indicators import compute_snapshot, calc_ma_trend, calc_rsi_slope

async def main():
    config = load_config()
    collector = UpbitCollector(config.upbit)
    
    symbols = ["KRW-BTC", "KRW-ETH", "KRW-XRP", "KRW-DOGE", "KRW-USDT"]
    for symbol in symbols:
        df = pyupbit.get_ohlcv(symbol, "minute15", 200)
        if df is None or df.empty:
            continue
        snapshot = compute_snapshot(df, 20, 2.0, 14, 14)
        
        is_uptrend = calc_ma_trend(df["close"], 20, 50)
        rsi_slope = calc_rsi_slope(df["close"], 14, 3)
        price = snapshot.current_price
        bb_lower = snapshot.bb.lower
        vol_ratio = snapshot.volatility_ratio
        
        print(f"--- {symbol} ---")
        print(f"Price: {price}, BB Lower: {bb_lower:.2f} (Below: {price < bb_lower})")
        print(f"RSI: {snapshot.rsi:.2f} (<=35: {snapshot.rsi <= 35})")
        print(f"RSI Slope: {rsi_slope:.4f} (>0: {rsi_slope > 0})")
        print(f"MA20 > MA50 (Uptrend): {is_uptrend}")
        print(f"Volatility Ratio: {vol_ratio:.2f} (<2.0: {vol_ratio < 2.0})")
        print()

asyncio.run(main())
