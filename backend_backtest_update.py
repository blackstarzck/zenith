import re

with open("src/backtest/paper_trading.py", "r", encoding="utf-8") as f:
    content = f.read()

old_call = """self._target_symbols = self._collector.get_top_volume_symbols(
                self._config.strategy.top_volume_count
            )"""

new_call = """top_symbols_data = self._collector.get_top_volume_symbols(
                self._config.strategy.top_volume_count
            )
            self._target_symbols = [item["symbol"] if isinstance(item, dict) else item for item in top_symbols_data]"""

if old_call in content:
    content = content.replace(old_call, new_call)

with open("src/backtest/paper_trading.py", "w", encoding="utf-8") as f:
    f.write(content)

