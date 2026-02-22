"""
카카오톡 OAuth 초기 인증 헬퍼.

사용법:
    1. https://developers.kakao.com 에서 애플리케이션 생성
    2. 카카오 로그인 활성화 + 동의 항목에서 "카카오톡 메시지 전송" 동의
    3. Redirect URI에 http://localhost:5000/callback 등록
    4. 이 스크립트 실행: python scripts/kakao_auth.py
    5. 브라우저에서 카카오 로그인 → 동의 → .env에 토큰 자동 저장
"""

import http.server
import os
import sys
import threading
import urllib.parse
import webbrowser

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from dotenv import load_dotenv, set_key

load_dotenv()

KAKAO_AUTH_URL = "https://kauth.kakao.com/oauth/authorize"
KAKAO_TOKEN_URL = "https://kauth.kakao.com/oauth/token"
REDIRECT_URI = "http://localhost:5000/callback"
ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")

# 토큰 저장용 전역 변수
_token_result: dict | None = None
_server_should_stop = threading.Event()


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    """카카오 OAuth 콜백 수신 핸들러."""

    def do_GET(self) -> None:
        global _token_result

        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return

        params = urllib.parse.parse_qs(parsed.query)

        if "error" in params:
            error = params["error"][0]
            desc = params.get("error_description", [""])[0]
            self._respond_html(f"<h2>인증 실패</h2><p>{error}: {desc}</p>")
            _server_should_stop.set()
            return

        if "code" not in params:
            self._respond_html("<h2>인증 코드 없음</h2><p>다시 시도하세요.</p>")
            _server_should_stop.set()
            return

        auth_code = params["code"][0]
        rest_api_key = os.getenv("KAKAO_REST_API_KEY", "")

        # 인증 코드 → Access Token + Refresh Token 교환
        try:
            resp = httpx.post(
                KAKAO_TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "client_id": rest_api_key,
                    "redirect_uri": REDIRECT_URI,
                    "code": auth_code,
                },
                timeout=10,
            )
            resp.raise_for_status()
            _token_result = resp.json()
        except Exception as e:
            self._respond_html(f"<h2>토큰 교환 실패</h2><pre>{e}</pre>")
            _server_should_stop.set()
            return

        access_token = _token_result.get("access_token", "")
        refresh_token = _token_result.get("refresh_token", "")

        # .env에 저장
        set_key(ENV_PATH, "KAKAO_ACCESS_TOKEN", access_token)
        set_key(ENV_PATH, "KAKAO_REFRESH_TOKEN", refresh_token)

        self._respond_html(
            "<h2>인증 완료!</h2>"
            "<p>Access Token과 Refresh Token이 <code>.env</code>에 저장되었습니다.</p>"
            "<p>이 창을 닫아도 됩니다.</p>"
        )
        _server_should_stop.set()

    def _respond_html(self, body: str) -> None:
        html = (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<title>Zenith - Kakao Auth</title>"
            "<style>body{font-family:sans-serif;max-width:600px;margin:60px auto;text-align:center;}"
            "code{background:#f0f0f0;padding:2px 6px;border-radius:3px;}</style>"
            f"</head><body>{body}</body></html>"
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format: str, *args: object) -> None:
        # 콘솔 로그 억제
        pass


def main() -> None:
    rest_api_key = os.getenv("KAKAO_REST_API_KEY", "")
    if not rest_api_key:
        print("[ERROR] KAKAO_REST_API_KEY가 .env에 설정되지 않았습니다.")
        print("  1. https://developers.kakao.com 에서 앱 생성")
        print("  2. REST API 키를 .env의 KAKAO_REST_API_KEY에 입력")
        sys.exit(1)

    # 1. 로컬 서버 시작 (콜백 수신용)
    server = http.server.HTTPServer(("localhost", 5000), CallbackHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    # 2. 카카오 인증 페이지 열기
    scope = "talk_message"
    auth_url = (
        f"{KAKAO_AUTH_URL}"
        f"?client_id={rest_api_key}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
        f"&response_type=code"
        f"&scope={scope}"
    )

    print("=" * 60)
    print("Zenith - KakaoTalk OAuth 인증")
    print("=" * 60)
    print()
    print("브라우저에서 카카오 로그인 페이지가 열립니다.")
    print("로그인 후 '동의하고 계속하기'를 클릭하세요.")
    print()
    print(f"브라우저가 열리지 않으면 아래 URL을 수동으로 열어주세요:")
    print(f"  {auth_url}")
    print()

    webbrowser.open(auth_url)

    # 3. 콜백 대기
    _server_should_stop.wait(timeout=120)
    server.shutdown()

    if _token_result:
        print("[SUCCESS] 카카오 인증 완료!")
        print(f"  Access Token:  {_token_result.get('access_token', '')[:20]}...")
        print(f"  Refresh Token: {_token_result.get('refresh_token', '')[:20]}...")
        expires_in = _token_result.get("expires_in", 0)
        refresh_expires = _token_result.get("refresh_token_expires_in", 0)
        print(f"  Access Token 만료: {expires_in // 3600}시간")
        print(f"  Refresh Token 만료: {refresh_expires // 86400}일")
        print()
        print("  토큰이 .env에 저장되었습니다.")
        print("  봇이 Access Token 만료 시 Refresh Token으로 자동 갱신합니다.")
    else:
        print("[ERROR] 인증이 완료되지 않았습니다. 다시 시도해주세요.")
        sys.exit(1)


if __name__ == "__main__":
    main()
