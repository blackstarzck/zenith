import re

with open("frontend/src/pages/DashboardPage.tsx", "r", encoding="utf-8") as f:
    content = f.read()

# Replace the complicated IIFE for topSymbols parsing
old_code = """  const topSymbols: string[] = (() => {
    const raw = botState?.top_symbols;
    if (!raw) return [];
    if (Array.isArray(raw)) return raw;
    if (typeof raw === 'string') {
      try { return JSON.parse(raw); } catch { return []; }
    }
    return [];
  })();"""

new_code = """  const topSymbolObjects = (() => {
    const raw = botState?.top_symbols;
    if (!raw) return [];
    
    let arr: any[] = [];
    if (Array.isArray(raw)) arr = raw;
    else if (typeof raw === 'string') {
      try { arr = JSON.parse(raw); } catch { return []; }
    }
    
    return arr.map(item => 
      typeof item === 'string' ? { symbol: item, volatility: undefined } : item
    );
  })();
  
  const topSymbols: string[] = topSymbolObjects.map(item => item.symbol);"""

if old_code in content:
    content = content.replace(old_code, new_code)

old_all_rows = """          const allRows = [
            ...topSymbols.map((symbol, idx) => ({
              key: symbol,
              rank: idx + 1,
              symbol,
              pos: heldPositions.get(symbol) ?? null,
              snap: latestSnapshots.get(symbol) ?? null,
              ticker: tickers.get(symbol) ?? null,
            })),
            ...extraHeld.map((symbol) => ({
              key: symbol,
              rank: null as number | null,
              symbol,
              pos: heldPositions.get(symbol) ?? null,
              snap: latestSnapshots.get(symbol) ?? null,
              ticker: tickers.get(symbol) ?? null,
            })),
          ];"""

new_all_rows = """          const allRows = [
            ...topSymbolObjects.map((item, idx) => ({
              key: item.symbol,
              rank: idx + 1,
              symbol: item.symbol,
              volatility: item.volatility,
              pos: heldPositions.get(item.symbol) ?? null,
              snap: latestSnapshots.get(item.symbol) ?? null,
              ticker: tickers.get(item.symbol) ?? null,
            })),
            ...extraHeld.map((symbol) => ({
              key: symbol,
              rank: null as number | null,
              symbol,
              volatility: undefined as number | undefined,
              pos: heldPositions.get(symbol) ?? null,
              snap: latestSnapshots.get(symbol) ?? null,
              ticker: tickers.get(symbol) ?? null,
            })),
          ];"""

if old_all_rows in content:
    content = content.replace(old_all_rows, new_all_rows)

old_col = """                {
                  title: '종목',
                  dataIndex: 'symbol',
                  width: 110,
                  render: (v: string, record: RowType) => {
                    const krw = v.replace('KRW-', '');
                    return (
                      <Space direction="vertical" size={0}>
                        <Text strong style={{ fontSize: 14 }}>{krw}</Text>
                        <Text type="secondary" style={{ fontSize: 11 }}>{v}</Text>
                      </Space>
                    );
                  }
                },"""

new_col = """                {
                  title: '종목',
                  dataIndex: 'symbol',
                  width: 110,
                  render: (v: string, record: RowType) => {
                    const krw = v.replace('KRW-', '');
                    return (
                      <Space direction="vertical" size={0}>
                        <Text strong style={{ fontSize: 14 }}>{krw}</Text>
                        <Text type="secondary" style={{ fontSize: 11 }}>{v}</Text>
                      </Space>
                    );
                  }
                },
                {
                  title: '변동성',
                  dataIndex: 'volatility',
                  width: 80,
                  align: 'right',
                  render: (vol: number | undefined) => {
                    if (vol === undefined || vol === null) return <Text type="secondary">-</Text>;
                    const color = vol >= 2.0 ? '#cf1322' : (vol >= 1.5 ? '#fa8c16' : '#389e0d');
                    return <Text style={{ color, fontSize: 13, fontWeight: '500' }}>{vol.toFixed(2)}x</Text>;
                  }
                },"""

if old_col in content:
    content = content.replace(old_col, new_col)


with open("frontend/src/pages/DashboardPage.tsx", "w", encoding="utf-8") as f:
    f.write(content)

