"""브라우저 없이 웹 주소를 여는 최소한의 HTTP 도구."""

import ssl
import urllib.error
import urllib.request

DESKTOP_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
)


def _certifi_context():
    try:
        import certifi
    except ImportError:
        return None
    return ssl.create_default_context(cafile=certifi.where())


def _is_cert_error(error):
    reason = getattr(error, "reason", error)
    return isinstance(reason, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in str(reason)


def _read(request, timeout, context):
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=context) as resp:
            return resp.status, resp.geturl(), resp.read()
    except urllib.error.HTTPError as e:  # 4xx·5xx도 상태 코드와 본문을 돌려준다
        try:
            body = e.read()
        except Exception:
            body = b""
        return e.code, e.geturl() or request.full_url, body


def open_url(url, headers=None, timeout=20):
    """(상태 코드, 최종 주소, 본문 bytes)를 돌려준다.

    맥의 일부 파이썬처럼 인증서 설정이 없어 실패하면 certifi 인증서로 한 번 더 시도한다.
    """
    request = urllib.request.Request(url, headers=headers or {})
    try:
        return _read(request, timeout, None)
    except urllib.error.URLError as e:
        context = _certifi_context() if _is_cert_error(e) else None
        if context is None:
            raise
        return _read(request, timeout, context)
