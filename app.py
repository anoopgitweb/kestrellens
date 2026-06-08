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
from datetime import datetime, timedelta, timezone
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
        "all": None,
        "24h": 1,
        "3d": 3,
        "7d": 7,
        "30d": 30,
    }
    return ranges.get(value, 7)


def _preferred_interest_query(interest):
    normalized = _normalize_text(interest)
    preferred = {
        "claude": "Anthropic Claude AI",
        "chatgpt": "OpenAI ChatGPT",
        "gemini": "Google Gemini AI",
        "grok": "xAI Grok",
        "agenticai": "agentic AI",
        "genai": "generative AI",
    }
    return preferred.get(normalized, str(interest).strip())


def _rss_url(company, days, contextual=False, mode="companies"):
    company_query = _preferred_company_query(company) if mode != "interests" else _preferred_interest_query(company)
    date_clause = f" when:{days}d" if days else ""
    query = f'"{company_query}"{date_clause}'
    if contextual:
        if mode == "interests":
            business_context = (
                "news OR latest OR analysis OR research OR launch OR AI OR "
                "technology OR customer OR business OR regulation OR market OR trend"
            )
        else:
            business_context = (
                "company OR business OR CEO OR earnings OR revenue OR partnership OR "
                "acquisition OR AI OR customer OR launch OR investment OR lawsuit OR "
                "regulatory OR expansion OR layoffs OR stock OR shares OR outage"
            )
        query = f'"{company_query}" ({business_context}){date_clause}'
    params = urllib.parse.urlencode({
        "q": query,
        "hl": "en-IN",
        "gl": "IN",
        "ceid": "IN:en",
        "scoring": "n",
    })
    return f"https://news.google.com/rss/search?{params}"


def _rss_urls(company, days, mode="companies"):
    return [
        _rss_url(company, days, mode=mode),
        _rss_url(company, days, contextual=True, mode=mode),
    ]


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


def _vertical(company, title):
    normalized = _normalize_text(company)
    company_verticals = {
        "revolut": "BFSI",
        "scotiabank": "BFSI",
        "westpac": "BFSI",
        "dhanalaxmibank": "BFSI",
        "lloyds": "BFSI",
        "db": "Data & Risk",
        "dnb": "Data & Risk",
        "dunbradstreet": "Data & Risk",
        "cisco": "Technology",
        "netapp": "Technology",
        "openai": "AI & Technology",
        "anthropic": "AI & Technology",
        "oracle": "Technology",
        "adobe": "Technology",
        "accenture": "IT Services",
        "concentrix": "CX / BPO",
        "airbnb": "Travel & Hospitality",
        "airbnbinc": "Travel & Hospitality",
    }
    if normalized in company_verticals:
        return company_verticals[normalized]

    text = f"{company} {title}".lower()
    rules = [
        ("BFSI", ["bank", "banking", "fintech", "insurance", "payments", "lending", "credit", "wealth"]),
        ("Retail & Ecommerce", ["retail", "ecommerce", "commerce", "store", "shopping"]),
        ("Travel & Hospitality", ["travel", "hotel", "airline", "hospitality", "booking", "host"]),
        ("Healthcare", ["health", "hospital", "patient", "pharma", "medical"]),
        ("Technology", ["software", "cloud", "cyber", "security", "data", "network", "platform"]),
        ("AI & Technology", [" ai ", "agentic", "genai", "model", "automation", "chatbot"]),
        ("CX / BPO", ["customer experience", "contact center", "bpo", "outsourcing", "support"]),
    ]
    padded = f" {text} "
    for vertical, words in rules:
        if any(word in padded for word in words):
            return vertical
    return "Market"


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


def _interest_terms(interest):
    raw = (interest or "").strip().lower()
    terms = {raw, _normalize_text(raw)}
    aliases = {
        "chatgpt": ["chatgpt", "chat gpt", "openai chatgpt"],
        "claude": ["claude", "anthropic claude"],
        "gemini": ["gemini", "google gemini"],
        "agenticai": ["agentic ai", "ai agents", "agentic"],
        "genai": ["genai", "generative ai"],
    }
    for alias in aliases.get(_normalize_text(raw), []):
        terms.add(alias)
        terms.add(_normalize_text(alias))
    return {term for term in terms if len(term) > 2}


def _is_interest_relevant(interest, title, source):
    text = f"{title} {source}"
    lower = text.lower()
    normalized = _normalize_text(text)
    if not any(term in lower or term in normalized for term in _interest_terms(interest)):
        return False

    ai_topics = {"claude", "chatgpt", "gemini", "grok", "openai", "anthropic"}
    ai_context = (
        "ai", "anthropic", "openai", "google", "xai", "chatbot", "model",
        "llm", "opus", "sonnet", "haiku", "gpt", "coding", "code",
        "artificial intelligence", "machine learning", "agents", "agentic",
        "api", "developer", "cybersecurity",
    )
    if _normalize_text(interest) in ai_topics and not any(term in lower for term in ai_context):
        return False

    noise_patterns = (
        r"\bquiz\b",
        r"\bmovie\b",
        r"\bsong\b",
        r"\bcelebrity\b",
        r"\bhoroscope\b",
        r"\bobituary\b",
        r"\bfuneral\b",
        r"\bstanley cup\b",
        r"\bnhl\b",
        r"\bdeath certificate\b",
        r"\bfound dead\b",
    )
    return not any(re.search(pattern, lower) for pattern in noise_patterns)


def _article_id(company, title, link):
    base = f"{company}|{title}|{link}"
    return str(abs(hash(base)))


def _empty_scan_stats(companies, date_range, mode):
    return {
        "mode": mode,
        "dateRange": date_range,
        "trackedCount": len([c for c in companies if str(c).strip()]),
        "rssUrlsRequested": 0,
        "rawItemsScanned": 0,
        "relevantItemsKept": 0,
        "duplicateCount": 0,
        "uniqueSourcesCount": 0,
        "errorsCount": 0,
        "scanTimestamp": datetime.now(IST).strftime("%d %b %Y, %I:%M %p IST"),
        "perTarget": [],
        "rssUrls": [],
        "uniqueSources": [],
        "topSources": [],
    }


def _fetch_company_news(company, days, mode="companies", stats=None):
    cache_key = (mode, company.lower(), days)
    cached = NEWS_CACHE.get(cache_key)
    if cached and time.time() - cached["time"] < CACHE_SECONDS:
        if stats is not None:
            urls = _rss_urls(company, days, mode=mode)
            stats["rssUrlsRequested"] += len(urls)
            stats["rssUrls"].extend([
                {"target": company, "type": "Baseline" if i == 0 else "Contextual", "url": url, "cacheHit": True}
                for i, url in enumerate(urls)
            ])
            stats["relevantItemsKept"] += len(cached["items"])
            stats["perTarget"].append({
                "name": company,
                "rssUrls": len(_rss_urls(company, days, mode=mode)),
                "rawItems": 0,
                "keptItems": len(cached["items"]),
                "sources": sorted({item.get("source", "") for item in cached["items"] if item.get("source")}),
                "latestUpdate": cached["items"][0].get("publishedIST", "") if cached["items"] else "",
                "cacheHit": True,
            })
        return cached["items"]

    items = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days) if days else None
    seen = set()
    target_stats = {"name": company, "rssUrls": 0, "rawItems": 0, "keptItems": 0, "sources": set(), "latestUpdate": "", "cacheHit": False}
    for index, url in enumerate(_rss_urls(company, days, mode=mode)):
        if stats is not None:
            stats["rssUrlsRequested"] += 1
            stats["rssUrls"].append({
                "target": company,
                "type": "Baseline" if index == 0 else "Contextual",
                "url": url,
                "cacheHit": False,
            })
        target_stats["rssUrls"] += 1
        xml_bytes = _fetch_url(url)
        root = ET.fromstring(xml_bytes)
        for item in root.findall("./channel/item"):
            if stats is not None:
                stats["rawItemsScanned"] += 1
            target_stats["rawItems"] += 1
            title = _clean_title(item.findtext("title"))
            link = item.findtext("link") or ""
            source = _parse_google_source(item)
            published = _item_published_date(item)
            if cutoff and published and published < cutoff:
                continue
            if not title or not link:
                continue
            relevant = _is_interest_relevant(company, title, source) if mode == "interests" else _is_company_relevant(company, title, source)
            if not relevant:
                continue
            key = (title.lower(), source.lower())
            if key in seen:
                if stats is not None:
                    stats["duplicateCount"] += 1
                continue
            seen.add(key)
            target_stats["sources"].add(source)
            items.append({
                "id": _article_id(company, title, link),
                "company": company,
                "vertical": _vertical(company, title),
                "date": published.isoformat() if published else "",
                "displayDate": published.strftime("%d %b %Y") if published else "",
                "displayTimeIST": published.astimezone(IST).strftime("%I:%M %p IST") if published else "",
                "publishedIST": published.astimezone(IST).strftime("%d %b %Y, %I:%M %p IST") if published else "",
                "source": source,
                "headline": title,
                "url": link,
                "sentiment": _sentiment(title),
            })

    items.sort(key=lambda item: item.get("date") or "", reverse=True)
    target_stats["keptItems"] = len(items)
    target_stats["latestUpdate"] = items[0].get("publishedIST", "") if items else ""
    if stats is not None:
        stats["relevantItemsKept"] += len(items)
        target_stats["sources"] = sorted(target_stats["sources"])
        stats["perTarget"].append(target_stats)

    NEWS_CACHE[cache_key] = {"time": time.time(), "items": items}
    return items


def _fetch_news(companies, date_range, mode="companies"):
    days = _date_range_to_days(date_range)
    stats = _empty_scan_stats(companies, date_range, mode)
    articles = []
    errors = []
    for company in companies:
        name = str(company).strip()
        if not name:
            continue
        try:
            articles.extend(_fetch_company_news(name, days, mode=mode, stats=stats))
        except (urllib.error.URLError, TimeoutError, ET.ParseError, OSError) as exc:
            errors.append({"company": name, "error": str(exc)})
            stats["errorsCount"] += 1

    deduped = {}
    for article in articles:
        key = (article["headline"].lower(), article["source"].lower())
        if key in deduped:
            stats["duplicateCount"] += 1
        deduped.setdefault(key, article)

    sorted_articles = sorted(
        deduped.values(),
        key=lambda item: item.get("date") or "",
        reverse=True,
    )
    source_counts = {}
    for article in sorted_articles:
        source_counts[article.get("source") or "Unknown"] = source_counts.get(article.get("source") or "Unknown", 0) + 1
    stats["uniqueSourcesCount"] = len(source_counts)
    stats["uniqueSources"] = [{"source": source, "count": count} for source, count in sorted(source_counts.items(), key=lambda x: x[0].lower())]
    stats["topSources"] = [{"source": source, "count": count} for source, count in sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[:8]]
    stats["relevantItemsKept"] = len(sorted_articles)
    return sorted_articles, errors, stats


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
            mode = payload.get("mode") or "companies"
            articles, errors, scan = _fetch_news(companies, date_range, mode=mode)
            _json_response(self, 200, {
                "articles": articles,
                "briefing": _briefing(articles),
                "errors": errors,
                "scan": scan,
            })
            return
        if self.path == "/api/scan-test":
            payload = _read_json(self)
            keyword = str(payload.get("keyword") or "").strip()
            if not keyword:
                _json_response(self, 400, {"error": "Keyword is required."})
                return
            date_range = payload.get("dateRange") or "7d"
            mode = payload.get("mode") or "interests"
            articles, errors, scan = _fetch_news([keyword], date_range, mode=mode)
            _json_response(self, 200, {
                "keyword": keyword,
                "articles": articles[:20],
                "errors": errors,
                "scan": scan,
            })
            return
        _json_response(self, 404, {"error": "Not found"})


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"KestrelIQ running at http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
