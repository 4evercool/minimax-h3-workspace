"""Free web search without a key (the public Bing results page; DuckDuckGo shows a robot check to programs). The Agent chat uses it only when the user ticks «Искать в интернете»."""
import asyncio
import html
import re
import urllib.parse

import aiohttp

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def _clean(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def _real_url(href):
    href = html.unescape(href)
    if href.startswith("//"):
        href = "https:" + href
    q = urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get("uddg")
    return urllib.parse.unquote(q[0]) if q else href


def _bing_url(href):
    """Bing links may be redirects: «bing.com/ck/a?...&u=a1<base64 of the real address>»."""
    href = html.unescape(href)
    if "bing.com/ck/a" in href:
        u = (urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get("u") or [""])[0]
        if u.startswith("a1"):
            try:
                import base64
                return base64.urlsafe_b64decode(u[2:] + "=" * (-len(u[2:]) % 4)).decode("utf-8", "replace")
            except Exception:
                pass
    return href


def parse(page, limit=5):
    """Results of a Bing page: [{title, url, text}]."""
    out = []
    for blk in re.split(r'<li class="b_algo"', page)[1:]:
        h = re.search(r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', blk, re.S)
        if not h:
            continue
        sn = re.search(r'<p[^>]*>(.*?)</p>', blk, re.S) or re.search(r'class="b_caption"[^>]*>(.*?)</div>', blk, re.S)
        url = _bing_url(h.group(1))
        if not url.startswith("http"):
            continue
        out.append({"title": _clean(h.group(2)), "url": url, "text": re.sub(r"\s*Подробнее\s*$", "", _clean(sn.group(1))) if sn else ""})
        if len(out) >= limit:
            break
    return out


async def search(session, query, limit=5):
    query = " ".join((query or "").split())[:200]
    if not query:
        return []
    for attempt in range(3):   # Bing sometimes answers with an empty page; a short pause and one more try usually helps
        async with session.get("https://www.bing.com/search", params={"q": query, "setlang": "ru", "cc": "ru"},
                               headers={"User-Agent": UA, "Accept-Language": "ru-RU,ru;q=0.9"},
                               timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status != 200:
                raise RuntimeError(f"поиск ответил кодом {r.status}")
            found = parse(await r.text(), limit)
        if found:
            return found
        await asyncio.sleep(1.5)
    return []


def as_text(results):
    return "\n".join(f"{i}. {r['title']} ({urllib.parse.urlparse(r['url']).hostname}): {r['text']}" for i, r in enumerate(results, 1))
