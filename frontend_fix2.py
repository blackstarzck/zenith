import re

with open("frontend/src/components/AppLayout.tsx", "r", encoding="utf-8") as f:
    content = f.read()

# Fix the lint error in AppLayout.tsx
old_code = "function getBotStatusTooltip(\n  status: 'online' | 'error' | 'offline',\n  upbitStatus: UpbitStatus,\n  kakaoStatus: KakaoStatus,\n  isActive: boolean | undefined,\n): string {"
new_code = "function getBotStatusTooltip(\n  status: 'online' | 'error' | 'offline',\n  upbitStatus: UpbitStatus,\n  _kakaoStatus: KakaoStatus,\n  isActive: boolean | undefined,\n): string {"

if old_code in content:
    content = content.replace(old_code, new_code)
    
old_code2 = "function getBotStatusTooltip("
new_code2 = "function getBotStatusTooltip("

with open("frontend/src/components/AppLayout.tsx", "w", encoding="utf-8") as f:
    f.write(content)

