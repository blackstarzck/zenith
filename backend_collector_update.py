import re

with open("src/collector/data_collector.py", "r", encoding="utf-8") as f:
    content = f.read()

# Update method signature
content = content.replace("def get_top_volume_symbols(self, top_n: int = 10) -> list[str]:", "def get_top_volume_symbols(self, top_n: int = 10) -> list[dict[str, Any]]:")
content = content.replace("def _get_top_volume_symbols_legacy(self, top_n: int = 10) -> list[str]:", "def _get_top_volume_symbols_legacy(self, top_n: int = 10) -> list[dict[str, Any]]:")

# Update get_top_volume_symbols body
old_body1 = """            top_symbols = [sym for sym, _ in volumes[:top_n]]
            logger.info("거래 대금 상위 %d: %s", top_n, top_symbols)
            return top_symbols"""

new_body1 = """            top_symbols = [sym for sym, _ in volumes[:top_n]]
            
            # 변동성 계산 추가
            from src.strategy.indicators import calc_volatility_ratio
            result = []
            for sym in top_symbols:
                df = self.get_ohlcv(sym, "minute15", 200)
                vol_ratio = 0.0
                if not df.empty:
                    vol_ratio = calc_volatility_ratio(df["close"])
                result.append({"symbol": sym, "volatility": vol_ratio})
                time.sleep(0.05) # Rate limit 방어
                
            logger.info("거래 대금 상위 %d: %s", top_n, top_symbols)
            return result"""

if old_body1 in content:
    content = content.replace(old_body1, new_body1)

# Update legacy body
old_body2 = """        top_symbols = [sym for sym, _ in volumes[:top_n]]
        logger.info("거래 대금 상위 %d (레거시): %s", top_n, top_symbols)
        return top_symbols"""

new_body2 = """        top_symbols = [sym for sym, _ in volumes[:top_n]]
        
        # 변동성 계산 추가
        from src.strategy.indicators import calc_volatility_ratio
        result = []
        for sym in top_symbols:
            df = self.get_ohlcv(sym, "minute15", 200)
            vol_ratio = 0.0
            if not df.empty:
                vol_ratio = calc_volatility_ratio(df["close"])
            result.append({"symbol": sym, "volatility": vol_ratio})
            time.sleep(0.05) # Rate limit 방어
            
        logger.info("거래 대금 상위 %d (레거시): %s", top_n, top_symbols)
        return result"""

if old_body2 in content:
    content = content.replace(old_body2, new_body2)

with open("src/collector/data_collector.py", "w", encoding="utf-8") as f:
    f.write(content)

