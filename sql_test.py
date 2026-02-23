import asyncio
from src.collector.data_collector import UpbitCollector
from src.config import load_config
async def test():
    config = load_config()
    collector = UpbitCollector(config.upbit)
    print("Fetching top symbols with volatility...")
    res = collector.get_top_volume_symbols(3)
    print(res)

asyncio.run(test())
