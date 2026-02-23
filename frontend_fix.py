import re

with open("frontend/src/components/AppLayout.tsx", "r", encoding="utf-8") as f:
    content = f.read()

# Fix the lint error in AppLayout.tsx
old_code = "  const { upbitStatus, kakaoStatus, botActive } = (() => {"
new_code = "  const { upbitStatus, botActive } = (() => {"

if old_code in content:
    content = content.replace(old_code, new_code)

with open("frontend/src/components/AppLayout.tsx", "w", encoding="utf-8") as f:
    f.write(content)

