import re

with open("frontend/src/components/AppLayout.tsx", "r", encoding="utf-8") as f:
    content = f.read()

old_code = """function getBotStatusTooltip(
  botStatus: BotStatus,
  upbitStatus: UpbitStatus,
  kakaoStatus: KakaoStatus,
  isActive: boolean | undefined,
): string {"""

new_code = """function getBotStatusTooltip(
  botStatus: BotStatus,
  upbitStatus: UpbitStatus,
  _kakaoStatus: KakaoStatus,
  isActive: boolean | undefined,
): string {"""

if old_code in content:
    content = content.replace(old_code, new_code)

with open("frontend/src/components/AppLayout.tsx", "w", encoding="utf-8") as f:
    f.write(content)

