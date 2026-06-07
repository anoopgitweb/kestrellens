import email.utils
import html
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo


HOST = os.environ.get("KESTRELIQ_HOST") or ("0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")
PORT = int(os.environ.get("PORT") or os.environ.get("KESTRELIQ_PORT", "8787"))
ROOT = Path(__file__).resolve().parent
INDEX_FILE = ROOT / "templates" / "index.html"
CACHE_SECONDS = 15 * 60
IST = ZoneInfo("Asia/Kolkata")

NEWS_CACHE = {}

POSITIVE_WORDS = {
    "acquires", "acquisition", "award", "beats", "breakthrough", "expands",
    "growth", "launches", "partnership", "profit", "raises", "record",
    "secures", "wins",
}
NEGATIVE_WORDS = {
    "breach", "cuts", "decline", "delay", "fined", "fraud", "investigation",
    "lawsuit", "loss", "recall", "risk", "sues", "warning", "withdraws",
}


def _json_response(handler, status, payload):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.end_headers()
    handler.wfile.write(body)


def _html_response(handler, status, text):
    body = text.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_json(handler):
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length <= 0:
        return {}
    raw = handler.rfile.read(length).decode("utf-8", errors="replace")
    return json.loads(raw)


def _date_range_to_days(value):
    ranges = {
        "24h": 1,
        "3d": 3,
        "7d": 7,
        "30d": 30,
    }
    return ranges.get(value, 7)


def _rss_url(company, days):
    company_query = _preferred_company_query(company)
    business_context = (
        "company OR business OR CEO OR earnings OR revenue OR partnership OR "
        "acquisition OR AI OR customer OR launch OR investment OR lawsuit OR "
        "regulatory OR expansion OR layoffs OR stock OR shares OR outage"
    )
    query = f'"{company_query}" ({business_context}) when:{days}d'
    params = urllib.parse.urlencode({
        "q": query,
        "hl": "en-IN",
        "gl": "IN",
        "ceid": "IN:en",
        "scoring": "n",
    })
    return f"https://news.google.com/rss/search?{params}"


def _fetch_url(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "KestrelIQ/1.0 (+local executive intelligence app)",
            "Accept": "application/rss+xml, application/xml, text/xml",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read()


def _parse_google_source(item):
    source = item.find("source")
    if source is not None and source.text:
        return source.text.strip()
    return "Google News"


def _parse_date(value):
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _item_published_date(item):
    candidates = [
        item.findtext("pubDate"),
        item.findtext("published"),
        item.findtext("updated"),
        item.findtext("{http://purl.org/dc/elements/1.1/}date"),
        item.findtext("{http://www.w3.org/2005/Atom}published"),
        item.findtext("{http://www.w3.org/2005/Atom}updated"),
    ]
    for value in candidates:
        parsed = _parse_date(value)
        if parsed:
            return parsed
    return datetime.now(timezone.utc)


def _sentiment(title):
    words = set(re.findall(r"[a-z][a-z0-9]+", title.lower()))
    positive = len(words & POSITIVE_WORDS)
    negative = len(words & NEGATIVE_WORDS)
    if positive > negative:
        return "positive"
    if negative > positive:
        return "negative"
    return "neutral"


def _clean_title(value):
    value = html.unescape(value or "").strip()
    value = re.sub(r"\s+-\s+[^-]{2,80}$", "", value)
    return value


def _normalize_text(value):
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def _company_terms(company):
    raw = (company or "").strip()
    lower = raw.lower()
    terms = {lower}
    normalized = _normalize_text(raw)
    if normalized:
        terms.add(normalized)

    aliases = {
        "airbnb": ["airbnb", "air bnb", "airbnb inc"],
        "airbnbinc": ["airbnb", "air bnb", "airbnb inc"],
        "openai": ["openai", "open ai"],
        "scotiabank": ["scotiabank", "scotia bank", "bank of nova scotia"],
        "db": ["d&b", "dnb", "dun & bradstreet", "dun and bradstreet", "dun bradstreet"],
        "dnb": ["d&b", "dnb", "dun & bradstreet", "dun and bradstreet", "dun bradstreet"],
        "lloyds": ["lloyds", "lloyds banking group", "lloyds bank"],
        "netapp": ["netapp", "net app"],
    }
    for alias in aliases.get(normalized, []):
        terms.add(alias)
        terms.add(_normalize_text(alias))
    return {term for term in terms if term}


def _preferred_company_query(company):
    normalized = _normalize_text(company)
    preferred = {
        "airbnb": "Airbnb",
        "airbnbinc": "Airbnb",
        "db": "Dun & Bradstreet",
        "dnb": "Dun & Bradstreet",
        "openai": "OpenAI",
        "scotiabank": "Scotiabank",
    }
    return preferred.get(normalized, company)


def _has_company_term(company, text):
    lower = (text or "").lower()
    normalized = _normalize_text(text)
    for term in _company_terms(company):
        if len(term) <= 2:
            continue
        if term in lower or term in normalized:
            return True
    return False


def _is_company_relevant(company, title, source):
    text = f"{title} {source}"
    if not _has_company_term(company, text):
        return False

    lower = text.lower()
    business_words = {
        "acquires", "acquisition", "ai", "agentic", "analyst", "appoints",
        "banking", "business", "ceo", "cloud", "company", "contract",
        "customer", "earnings", "executive", "expands", "funding", "growth",
        "investment", "launches", "lawsuit", "market", "merger", "outage",
        "partner", "partnership", "platform", "profit", "regulator",
        "revenue", "shares", "stock", "strategy", "valuation",
    }
    if any(re.search(rf"\b{re.escape(word)}\b", lower) for word in business_words):
        return True

    consumer_patterns = (
        r"\bshould i\b",
        r"\bhow to\b",
        r"\bbest\b",
        r"\bguide\b",
        r"\bclass\b",
        r"\bbecome a host\b",
        r"\blisting\b",
        r"\bhomeowner\b",
    )
    return not any(re.search(pattern, lower) for pattern in consumer_patterns)


def _article_id(company, title, link):
    base = f"{company}|{title}|{link}"
    return str(abs(hash(base)))


def _fetch_company_news(company, days):
    cache_key = (company.lower(), days)
    cached = NEWS_CACHE.get(cache_key)
    if cached and time.time() - cached["time"] < CACHE_SECONDS:
        return cached["items"]

    xml_bytes = _fetch_url(_rss_url(company, days))
    root = ET.fromstring(xml_bytes)
    items = []
    for item in root.findall("./channel/item"):
        title = _clean_title(item.findtext("title"))
        link = item.findtext("link") or ""
        source = _parse_google_source(item)
        published = _item_published_date(item)
        if not title or not link:
            continue
        if not _is_company_relevant(company, title, source):
            continue
        items.append({
            "id": _article_id(company, title, link),
            "company": company,
            "date": published.isoformat() if published else "",
            "displayDate": published.strftime("%d %b %Y") if published else "",
            "displayTimeIST": published.astimezone(IST).strftime("%I:%M %p IST") if published else "",
            "publishedIST": published.astimezone(IST).strftime("%d %b %Y, %I:%M %p IST") if published else "",
            "source": source,
            "headline": title,
            "url": link,
            "sentiment": _sentiment(title),
        })

    NEWS_CACHE[cache_key] = {"time": time.time(), "items": items}
    return items


def _fetch_news(companies, date_range):
    days = _date_range_to_days(date_range)
    articles = []
    errors = []
    for company in companies:
        name = str(company).strip()
        if not name:
            continue
        try:
            articles.extend(_fetch_company_news(name, days))
        except (urllib.error.URLError, TimeoutError, ET.ParseError, OSError) as exc:
            errors.append({"company": name, "error": str(exc)})

    deduped = {}
    for article in articles:
        key = (article["headline"].lower(), article["source"].lower())
        deduped.setdefault(key, article)

    sorted_articles = sorted(
        deduped.values(),
        key=lambda item: item.get("date") or "",
        reverse=True,
    )
    return sorted_articles, errors


def _briefing(articles):
    by_company = {}
    for article in articles:
        by_company.setdefault(article["company"], []).append(article)

    highlights = []
    risks = []
    for company, items in by_company.items():
        positives = [x for x in items if x["sentiment"] == "positive"]
        negatives = [x for x in items if x["sentiment"] == "negative"]
        lead = items[0] if items else None
        highlights.append({
            "company": company,
            "count": len(items),
            "positive": len(positives),
            "negative": len(negatives),
            "lead": lead,
        })
        risks.extend(negatives[:2])

    return {
        "generatedAt": datetime.now().strftime("%d %b %Y, %H:%M"),
        "companies": sorted(highlights, key=lambda item: item["count"], reverse=True),
        "risks": risks[:8],
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[KestrelIQ] {self.address_string()} - {fmt % args}")

    def do_OPTIONS(self):
        _json_response(self, 200, {"ok": True})

    def do_GET(self):
        if self.path in {"/", "/index.html"}:
            if not INDEX_FILE.exists():
                _html_response(self, 500, "templates/index.html is missing.")
                return
            _html_response(self, 200, INDEX_FILE.read_text(encoding="utf-8"))
            return
        if self.path == "/api/health":
            _json_response(self, 200, {"ok": True, "service": "KestrelIQ"})
            return
        _json_response(self, 404, {"error": "Not found"})

    def do_POST(self):
        if self.path == "/api/news":
            payload = _read_json(self)
            companies = payload.get("companies") or []
            date_range = payload.get("dateRange") or "7d"
            articles, errors = _fetch_news(companies, date_range)
            _json_response(self, 200, {
                "articles": articles,
                "briefing": _briefing(articles),
                "errors": errors,
            })
            return
        _json_response(self, 404, {"error": "Not found"})


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"KestrelIQ running at http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
