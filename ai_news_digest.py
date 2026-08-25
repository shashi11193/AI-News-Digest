#!/usr/bin/env python3
"""
AI News Digest Agent v4 — Per-Article Curation
One LLM call per article. Small, reliable, specific.
"""

import os
import re
import json
import feedparser
import requests
import smtplib
import time
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from urllib.parse import quote

# ─── CONFIG ───
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq")
MAX_ARTICLES_PER_SOURCE = 12
DAYS_BACK = 1
MAX_ARTICLES_TO_CURATE = 18
HEALTH_LOG_PATH = "output/health_log.json"

# ─── SOURCES ───
SOURCES = {
    "google_news_llm": {
        "url": "https://news.google.com/rss/search?q=large+language+model+OR+LLM+OR+transformer+architecture+OR+mixture+of+experts&hl=en-US&gl=US&ceid=US:en",
        "type": "rss", "category": "LLMs"
    },
    "google_news_genai": {
        "url": "https://news.google.com/rss/search?q=generative+AI+OR+diffusion+model+OR+multimodal+AI+OR+Sora+OR+image+generation&hl=en-US&gl=US&ceid=US:en",
        "type": "rss", "category": "GenAI"
    },
    "google_news_agents": {
        "url": "https://news.google.com/rss/search?q=AI+agent+OR+autonomous+agent+OR+agentic+AI+OR+AI+workflow&hl=en-US&gl=US&ceid=US:en",
        "type": "rss", "category": "Agents"
    },
    "google_news_robotics": {
        "url": "https://news.google.com/rss/search?q=AI+robotics+OR+embodied+AI+OR+humanoid+robot+OR+Figure+AI&hl=en-US&gl=US&ceid=US:en",
        "type": "rss", "category": "Robotics"
    },
    "google_news_chips": {
        "url": "https://news.google.com/rss/search?q=AI+chip+OR+GPU+OR+TPU+OR+AI+hardware+OR+NVIDIA+OR+training+cluster&hl=en-US&gl=US&ceid=US:en",
        "type": "rss", "category": "Hardware"
    },
    "google_news_safety": {
        "url": "https://news.google.com/rss/search?q=AI+safety+OR+AI+alignment+OR+AI+regulation+OR+EU+AI+Act&hl=en-US&gl=US&ceid=US:en",
        "type": "rss", "category": "Safety"
    },
    "google_news_evaluation": {
        "url": "https://news.google.com/rss/search?q=AI+evaluation+OR+LLM+benchmark+OR+model+evaluation+OR+MMLU+OR+SWE-bench&hl=en-US&gl=US&ceid=US:en",
        "type": "rss", "category": "Evaluation"
    },
    "google_news_vision": {
        "url": "https://news.google.com/rss/search?q=computer+vision+OR+image+generation+OR+video+generation+AI&hl=en-US&gl=US&ceid=US:en",
        "type": "rss", "category": "Vision"
    },
    "google_news_releases": {
        "url": "https://news.google.com/rss/search?q=new+AI+model+release+OR+new+LLM+announced+OR+AI+product+launch+2026&hl=en-US&gl=US&ceid=US:en",
        "type": "rss", "category": "Releases"
    },
    "hackernews": {
        "url": "https://hnrss.org/newest?q=artificial+intelligence+OR+machine+learning+OR+LLM+OR+neural+network",
        "type": "rss", "category": "Community"
    },
    "arxiv_ai": {
        "url": "http://export.arxiv.org/rss/cs.AI",
        "type": "rss", "category": "Research"
    },
    "arxiv_lg": {
        "url": "http://export.arxiv.org/rss/cs.LG",
        "type": "rss", "category": "Research"
    },
    "arxiv_cl": {
        "url": "http://export.arxiv.org/rss/cs.CL",
        "type": "rss", "category": "Research"
    },
    "reddit_ml": {
        "url": "https://www.reddit.com/r/MachineLearning/.rss",
        "type": "rss", "category": "Community"
    },
    "reddit_local_llama": {
        "url": "https://www.reddit.com/r/LocalLLaMA/.rss",
        "type": "rss", "category": "Community"
    },
    "openai_blog": {
        "url": "https://openai.com/blog/rss.xml",
        "type": "rss", "category": "LLMs"
    },
    "anthropic_blog": {
        "url": "https://www.anthropic.com/rss.xml",
        "type": "rss", "category": "LLMs"
    },
    "deepmind_blog": {
        "url": "https://deepmind.google/blog/rss.xml",
        "type": "rss", "category": "Research"
    },
    "techcrunch_ai": {
        "url": "https://techcrunch.com/category/artificial-intelligence/feed/",
        "type": "rss", "category": "Releases"
    },
    "venturebeat_ai": {
        "url": "https://venturebeat.com/category/ai/feed/",
        "type": "rss", "category": "Releases"
    },
    "mit_tech_review": {
        "url": "https://www.technologyreview.com/topic/artificial-intelligence/feed/",
        "type": "rss", "category": "Research"
    },
}

# ─── HEALTH TRACKING ───

def load_health_log():
    if os.path.exists(HEALTH_LOG_PATH):
        try:
            with open(HEALTH_LOG_PATH, "r") as f:
                return json.load(f)
        except:
            pass
    return {}


def save_health_log(log):
    os.makedirs("output", exist_ok=True)
    with open(HEALTH_LOG_PATH, "w") as f:
        json.dump(log, f, indent=2)


def update_source_health(health_log, source_name, success, error_msg=""):
    today = datetime.now().strftime("%Y-%m-%d")
    if source_name not in health_log:
        health_log[source_name] = {
            "consecutive_failures": 0, "total_failures": 0, "total_successes": 0,
            "last_success": "", "last_failure": "", "disabled": False,
            "error_history": []
        }
    entry = health_log[source_name]
    if success:
        entry["consecutive_failures"] = 0
        entry["total_successes"] += 1
        entry["last_success"] = today
        entry["disabled"] = False
    else:
        entry["consecutive_failures"] += 1
        entry["total_failures"] += 1
        entry["last_failure"] = today
        entry["error_history"].append(f"{today}: {error_msg}")
        entry["error_history"] = entry["error_history"][-5:]
        if entry["consecutive_failures"] >= 3:
            entry["disabled"] = True
            print(f"[HEALTH] ⚠️ {source_name} auto-disabled")
    return health_log


def get_source_status(health_log, source_name):
    if source_name not in health_log:
        return True
    return not health_log[source_name].get("disabled", False)


# ─── FETCH RSS ───

def fetch_rss(name, config, health_log):
    articles = []
    if not get_source_status(health_log, name):
        print(f"[SKIP] {name} is auto-disabled")
        return articles, health_log

    try:
        print(f"[FETCH] {name} ...")
        feed = feedparser.parse(config["url"])
        if feed.get("bozo") and feed.get("bozo_exception"):
            raise Exception(str(feed["bozo_exception"]))

        cutoff = datetime.now() - timedelta(days=DAYS_BACK)
        for entry in feed.entries[:MAX_ARTICLES_PER_SOURCE]:
            pub_date = None
            for field in ["published_parsed", "updated_parsed", "created_parsed"]:
                if hasattr(entry, field) and getattr(entry, field):
                    pub_date = datetime(*getattr(entry, field)[:6])
                    break

            if pub_date and pub_date < cutoff:
                continue

            title = entry.get("title", "").strip()
            if not title:
                continue

            # Skip old market research / forecast reports
            title_lower = title.lower()
            if any(x in title_lower for x in ["market size, share", "trends report", "forecast to 20", "market research", "industry report"]):
                continue

            summary = ""
            for field in ["summary", "description", "content"]:
                if hasattr(entry, field):
                    val = getattr(entry, field)
                    if isinstance(val, list) and val:
                        val = val[0].get("value", "")
                    summary = val[:1200] if val else ""
                    break
            summary = re.sub(r"<[^>]+>", " ", summary).strip()

            articles.append({
                "title": title,
                "url": entry.get("link", ""),
                "source": name,
                "published": pub_date.isoformat() if pub_date else "",
                "summary": summary,
                "category": config.get("category", "Research")
            })
        print(f"[FETCH] {name} -> {len(articles)} articles")
        health_log = update_source_health(health_log, name, True)
    except Exception as e:
        error_msg = str(e)[:100]
        print(f"[ERROR] {name}: {error_msg}")
        health_log = update_source_health(health_log, name, False, error_msg)
    return articles, health_log


# ─── DEDUPLICATE ───

def deduplicate(articles):
    seen_urls = set()
    seen_titles = set()
    unique = []
    for art in articles:
        url = art["url"].split("?")[0].rstrip("/")
        if url in seen_urls:
            continue
        norm_title = re.sub(r"[^\w\s]", "", art["title"].lower()).strip()
        if norm_title in seen_titles:
            continue
        seen_urls.add(url)
        seen_titles.add(norm_title)
        unique.append(art)
    print(f"[DEDUP] {len(articles)} -> {len(unique)} unique")
    return unique


# ─── PER-ARTICLE LLM CURATION ───

def analyze_article_with_llm(article, provider):
    """Analyze a single article with a small, focused LLM call."""

    title = article["title"]
    source = article["source"]
    summary = article["summary"][:800] if article["summary"] else ""
    category = article["category"]

    prompt = f"""You are a senior AI staff engineer reading tech news. A colleague shared this article with you.

TITLE: {title}
SOURCE: {source}
CATEGORY: {category}
SUMMARY: {summary}

Your job:
1. Decide if this is a genuinely significant AI/ML story with technical substance. Skip marketing fluff, vague partnerships, old news, or thin PR.
2. If it IS significant, write an original summary and analysis.
3. If it is NOT significant, reply with exactly: SKIP

Reply in this exact format:
HEADLINE: [A clean, informative title. Rewrite if the original is clickbait.]
SUMMARY: [2-3 sentences explaining what happened. Be specific. Include names, numbers, or technical details if present.]
WHY: [2-3 sentences on the technical or strategic implication. Reference concrete details. Be specific about what changed, who is affected, or what to watch.]

Rules:
- Do NOT start SUMMARY or WHY with phrases like "This article discusses" or "This is important because"
- Do NOT copy the title into the summary
- Write original analysis, not a rephrasing of the summary
- Be specific. Generic = useless."""

    if provider == "groq" and GROQ_API_KEY:
        return call_groq_single(prompt)
    elif provider == "gemini" and GEMINI_API_KEY:
        return call_gemini_single(prompt)
    return None


def call_groq_single(prompt, retries=2):
    for attempt in range(retries):
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                    "max_tokens": 800
                },
                timeout=45
            )
            if resp.status_code != 200:
                print(f"[GROQ] HTTP {resp.status_code}: {resp.text[:300]}")
                if attempt < retries - 1:
                    time.sleep(2)
                continue
            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()
            return parse_llm_response(content)
        except Exception as e:
            print(f"[GROQ] Error: {e}")
            if attempt < retries - 1:
                time.sleep(2)
    return None


def call_gemini_single(prompt, retries=2):
    for attempt in range(retries):
        try:
            resp = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}",
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.2, "maxOutputTokens": 800}
                },
                timeout=45
            )
            if resp.status_code != 200:
                print(f"[GEMINI] HTTP {resp.status_code}: {resp.text[:300]}")
                if attempt < retries - 1:
                    time.sleep(2)
                continue
            data = resp.json()
            content = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            return parse_llm_response(content)
        except Exception as e:
            print(f"[GEMINI] Error: {e}")
            if attempt < retries - 1:
                time.sleep(2)
    return None


def parse_llm_response(text):
    """Parse the LLM's plain-text response."""
    if not text or text.strip().upper() == "SKIP":
        return None

    if "SKIP" in text[:20].upper():
        return None

    result = {}
    lines = text.split("\n")
    current_key = None
    current_val = []

    for line in lines:
        line = line.strip()
        if line.startswith("HEADLINE:"):
            if current_key:
                result[current_key] = " ".join(current_val).strip()
            current_key = "headline"
            current_val = [line.replace("HEADLINE:", "").strip()]
        elif line.startswith("SUMMARY:"):
            if current_key:
                result[current_key] = " ".join(current_val).strip()
            current_key = "summary"
            current_val = [line.replace("SUMMARY:", "").strip()]
        elif line.startswith("WHY:"):
            if current_key:
                result[current_key] = " ".join(current_val).strip()
            current_key = "why_it_matters"
            current_val = [line.replace("WHY:", "").strip()]
        elif current_key and line:
            current_val.append(line)

    if current_key:
        result[current_key] = " ".join(current_val).strip()

    if "summary" in result and "why_it_matters" in result:
        return result
    return None


def curate_articles(articles):
    """Curate articles one by one."""
    selected = []
    provider = LLM_PROVIDER if LLM_PROVIDER in ["groq", "gemini"] else "groq"

    print(f"\n[CURATE] Processing up to {MAX_ARTICLES_TO_CURATE} articles one-by-one via {provider}...")

    for i, art in enumerate(articles[:MAX_ARTICLES_TO_CURATE]):
        print(f"[CURATE] {i+1}/{min(len(articles), MAX_ARTICLES_TO_CURATE)}: {art['title'][:60]}...")

        result = analyze_article_with_llm(art, provider)

        if not result:
            print(f"[CURATE]   -> Skipped (insignificant or LLM error)")
            continue

        # Validate: reject if summary is too similar to title
        if result["summary"].lower() in art["title"].lower() or art["title"].lower() in result["summary"].lower():
            print(f"[CURATE]   -> Skipped (summary echoes title)")
            continue

        # Validate: reject generic why_it_matters
        why_lower = result["why_it_matters"].lower()
        generic_phrases = ["this is important", "this matters because", "ai engineers should care", "significant development", "important for the field"]
        if any(p in why_lower for p in generic_phrases):
            print(f"[CURATE]   -> Skipped (generic analysis)")
            continue

        selected.append({
            "headline": result.get("headline", art["title"]),
            "url": art["url"],
            "source": art["source"],
            "category": art["category"],
            "summary": result["summary"],
            "why_it_matters": result["why_it_matters"]
        })
        print(f"[CURATE]   -> KEPT ({art['category']})")

        # Small delay to respect rate limits
        time.sleep(0.5)

    print(f"[CURATE] Final: {len(selected)} articles kept")
    return selected, provider


# ─── EMAIL FORMATTING ───

def generate_email_html(articles, date_str):
    cat_colors = {
        "LLMs": "#e74c3c", "GenAI": "#9b59b6", "Agents": "#8e44ad",
        "Robotics": "#3498db", "Hardware": "#f39c12", "Safety": "#e67e22",
        "Evaluation": "#1abc9c", "Vision": "#2ecc71", "Tools": "#34495e",
        "Research": "#16a085", "Releases": "#d35400", "Community": "#7f8c8d"
    }

    articles_html = ""
    for i, art in enumerate(articles, 1):
        cat = art.get("category", "Research")
        color = cat_colors.get(cat, "#34495e")

        articles_html += f"""
        <div style="margin-bottom:28px;padding-bottom:22px;border-bottom:1px solid #e9ecef;">
            <div style="margin-bottom:8px;">
                <span style="background:{color};color:white;padding:3px 10px;border-radius:10px;font-size:11px;font-weight:600;text-transform:uppercase;">{cat}</span>
                <span style="color:#95a5a6;font-size:11px;margin-left:8px;">{art.get('source','')}</span>
            </div>
            <h3 style="margin:0 0 10px 0;font-size:17px;line-height:1.4;">
                <a href="{art.get('url','#')}" style="color:#2c3e50;text-decoration:none;">{i}. {art.get('headline', art.get('title',''))}</a>
            </h3>
            <p style="margin:0 0 10px 0;color:#555;line-height:1.6;font-size:14px;">{art.get('summary','')}</p>
            <p style="margin:0;color:#2c3e50;line-height:1.6;font-size:14px;background:#f8f9fa;padding:10px 14px;border-left:3px solid {color};border-radius:0 4px 4px 0;">
                <strong style="color:{color};">Why it matters:</strong> {art.get('why_it_matters','')}
            </p>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;background:#f5f6fa;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f5f6fa;">
<tr><td align="center" style="padding:24px 16px;">
<table width="680" cellpadding="0" cellspacing="0" border="0" style="background:white;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,0.06);max-width:100%;">
<tr>
<td style="padding:28px 28px 18px 28px;background:#1a1a2e;border-radius:12px 12px 0 0;">
<h1 style="margin:0;color:white;font-size:22px;font-weight:700;">🧠 AI Daily Brief</h1>
<p style="margin:4px 0 0 0;color:#8892b0;font-size:13px;">{date_str}</p>
</td>
</tr>
<tr>
<td style="padding:12px 28px;background:#f8f9fa;border-bottom:1px solid #e9ecef;">
<p style="margin:0;color:#6c757d;font-size:12px;">{len(articles)} stories from the last 24 hours</p>
</td>
</tr>
<tr><td style="padding:20px 28px;">{articles_html}</td></tr>
<tr>
<td style="padding:16px 28px;background:#f8f9fa;border-radius:0 0 12px 12px;text-align:center;">
<p style="margin:0;color:#adb5bd;font-size:11px;">AI News Digest Agent</p>
</td>
</tr>
</table>
</td></tr>
</table>
</body>
</html>"""
    return html


def send_email(html_content, date_str):
    if not all([SENDER_EMAIL, SENDER_PASSWORD, RECIPIENT_EMAIL]):
        print("[WARN] Email credentials missing")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"🧠 AI Daily Brief — {date_str}"
        msg["From"] = SENDER_EMAIL
        msg["To"] = RECIPIENT_EMAIL
        msg.attach(MIMEText(html_content, "html"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, msg.as_string())
        print(f"[EMAIL] Sent to {RECIPIENT_EMAIL}")
        return True
    except Exception as e:
        print(f"[ERROR] Email failed: {e}")
        return False


# ─── MAIN ───

def main():
    print("="*60)
    print("🧠 AI NEWS DIGEST AGENT v4")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)

    health_log = load_health_log()
    all_articles = []

    for name, config in SOURCES.items():
        if config["type"] == "rss":
            arts, health_log = fetch_rss(name, config, health_log)
            all_articles.extend(arts)

    print(f"\n[TOTAL] Fetched {len(all_articles)} raw articles")

    if not all_articles:
        print("[WARN] No articles fetched.")
        save_health_log(health_log)
        return

    unique_articles = deduplicate(all_articles)
    selected, provider_used = curate_articles(unique_articles)

    if not selected:
        print("[WARN] No articles selected after curation.")
        save_health_log(health_log)
        return

    date_str = datetime.now().strftime("%A, %B %d, %Y")
    html = generate_email_html(selected, date_str)
    email_sent = send_email(html, date_str)

    os.makedirs("output", exist_ok=True)
    with open("output/digest.html", "w", encoding="utf-8") as f:
        f.write(html)
    with open("output/digest.json", "w", encoding="utf-8") as f:
        json.dump({"articles": selected}, f, indent=2)

    save_health_log(health_log)

    print("\n✅ Done!")
    print(f"   📧 Email: {email_sent}")
    print(f"   📰 Articles: {len(selected)}")


if __name__ == "__main__":
    main()
