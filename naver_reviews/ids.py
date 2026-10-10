"""업체 링크나 네이버지도 공유 문구에서 플레이스 ID와 업체명을 찾는다."""

import re
from urllib.parse import urlparse

from . import net

MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
)

SHORT_LINK_HOSTS = ("naver.me",)

_URL_RE = re.compile(r"https?://[^\s<>\"']+")
_ID_PATTERNS = (
    re.compile(r"/entry/place/(\d{5,})"),
    re.compile(
        r"/(?:place|restaurant|cafe|hairshop|nailshop|hospital|accommodation|"
        r"attraction|beauty|shopping)/(\d{5,})"
    ),
    re.compile(r"[?&](?:placeId|businessId|id)=(\d{5,})"),
)
_SHARE_HEADER_RE = re.compile(r"^\[\s*네이버\s*지도\s*\]\s*(.*)$")


def extract_place_id(text):
    """숫자 ID 또는 플레이스 주소에서 ID를 뽑는다. 못 찾으면 None."""
    if text is None:
        return None
    s = str(text).strip()
    if re.fullmatch(r"\d{5,}", s):
        return s
    for pattern in _ID_PATTERNS:
        m = pattern.search(s)
        if m:
            return m.group(1)
    return None


def find_urls(text):
    return _URL_RE.findall(str(text or ""))


def is_short_link(url):
    host = (urlparse(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in SHORT_LINK_HOSTS)


def name_from_share_text(text):
    """네이버지도 공유 문구에서 업체명을 꺼낸다. '[네이버지도]' 다음 줄(또는 같은 줄 뒤)이 업체명. 없으면 ''."""
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    for i, line in enumerate(lines):
        m = _SHARE_HEADER_RE.match(line)
        if not m:
            continue
        rest = m.group(1).strip()
        if rest and not find_urls(rest):
            return rest
        if i + 1 < len(lines) and not find_urls(lines[i + 1]):
            return lines[i + 1]
        return ""
    return ""


def follow_redirects(url, timeout):
    """브라우저 없이 단축 링크의 최종 주소를 찾는다. 연결에 실패하면 예외를 낸다."""
    _, final_url, _ = net.open_url(url, headers={"User-Agent": MOBILE_UA}, timeout=timeout)
    return final_url


def resolve_place_id(text, follow=follow_redirects, timeout=10):
    """숫자 ID, 플레이스 주소, 공유 문구(naver.me 단축 링크 포함)를 받아 플레이스 ID를 돌려준다."""
    pid = extract_place_id(text)
    if pid:
        return pid
    for url in find_urls(text):
        pid = extract_place_id(url)
        if pid:
            return pid
        if is_short_link(url):
            try:
                final_url = follow(url, timeout)
            except Exception:
                continue
            pid = extract_place_id(final_url)
            if pid:
                return pid
    return None
