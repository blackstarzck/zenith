import re

# Update storage/client.py
with open("src/storage/client.py", "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace("top_symbols: list[str] | None = None,", "top_symbols: list[dict[str, Any]] | list[str] | None = None,")

with open("src/storage/client.py", "w", encoding="utf-8") as f:
    f.write(content)

# Update orchestrator.py
with open("src/orchestrator.py", "r", encoding="utf-8") as f:
    content = f.read()

# get_top_volume_symbols will return dicts instead of strings
old_call1 = """self._target_symbols = self._collector.get_top_volume_symbols(
                self._config.strategy.top_volume_count
            )
            # 상위 종목 변경 → bot_state 갱신
            self._storage.upsert_bot_state(top_symbols=self._target_symbols)"""

new_call1 = """top_symbols_data = self._collector.get_top_volume_symbols(
                self._config.strategy.top_volume_count
            )
            self._target_symbols = [item["symbol"] if isinstance(item, dict) else item for item in top_symbols_data]
            # 상위 종목 변경 → bot_state 갱신
            self._storage.upsert_bot_state(top_symbols=top_symbols_data)"""

if old_call1 in content:
    content = content.replace(old_call1, new_call1)

old_call2 = """self._target_symbols = self._collector.get_top_volume_symbols(
                self._config.strategy.top_volume_count
            )
            self._storage.upsert_bot_state(top_symbols=self._target_symbols)"""

new_call2 = """top_symbols_data = self._collector.get_top_volume_symbols(
                self._config.strategy.top_volume_count
            )
            self._target_symbols = [item["symbol"] if isinstance(item, dict) else item for item in top_symbols_data]
            self._storage.upsert_bot_state(top_symbols=top_symbols_data)"""

if old_call2 in content:
    content = content.replace(old_call2, new_call2)
    
old_call3 = """tickers = self._collector.get_top_volume_symbols(
            self._config.strategy.top_volume_count
        )"""

new_call3 = """top_symbols_data = self._collector.get_top_volume_symbols(
            self._config.strategy.top_volume_count
        )
        tickers = [item["symbol"] if isinstance(item, dict) else item for item in top_symbols_data]"""
        
if old_call3 in content:
    content = content.replace(old_call3, new_call3)

with open("src/orchestrator.py", "w", encoding="utf-8") as f:
    f.write(content)

