#!/usr/bin/env python3
"""
AI News Digest Agent for Senior AI Engineers & Researchers
Self-healing, resilient, health-monitoring edition.
Fetches, curates, and emails the most important AI news daily.
Free tier compatible: GitHub Actions + Groq/Gemini API + Gmail SMTP
"""

import os
import re
import json
import feedparser
import requests
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from collections import defaultdict
from urllib.parse import quote

# ─── CONFIG ───
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq")
MAX_ARTICLES_PER_SOURCE = 15
DAYS_BACK = 1
MAX_LLM_RETRIES = 2

# Track source health across runs
HEALTH_LOG_PATH = "output/health_log.json"

# ─── SOURCE CONFIGURATION ───
SOURCES = {
    "google_news_llm": {
        "url": "https://news.google.com/rss/search?q=large+language+model+OR+LLM+OR+transformer+architecture&hl=en-US&gl=US&ceid=US:en",
        "type": "rss"
    },
    "google_news_genai": {
        "url": "https://news.google.com/rss/search?q=generative+AI+OR+diffusion+model+OR+multimodal+AI&hl=en-US&gl=US&ceid=US:en",
        "type": "rss"
    },
    "google_news_robotics": {
        "url": "https://news.google.com/rss/search?q=AI+robotics+OR+embodied+AI+OR+humanoid+robot&hl=en-US&gl=US&ceid=US:en",
        "type": "rss"
    },
    "google_news_chips": {
        "url": "https://news.google.com/rss/search?q=AI+chip+OR+GPU+OR+TPU+OR+AI+hardware+OR+NVIDIA+OR+training+cluster&hl=en-US&gl=US&ceid=US:en",
        "type": "rss"
    },
    "google_news_safety": {
        "url": "https://news.google.com/rss/search?q=AI+safety+OR+AI+alignment+OR+AI+regulation+OR+EU+AI+Act&hl=en-US&gl=US&ceid=US:en",
        "type": "rss"
    },
    "google_news_evaluation": {
        "url": "https://news.google.com/rss/search?q=AI+evaluation+OR+LLM+benchmark+OR+model+evaluation+OR+AI+metrics&hl=en-US&gl=US&ceid=US:en",
        "type": "rss"
    },
    "google_news_vision": {
        "url": "https://news.google.com/rss/search?q=computer+vision+OR+image+generation+OR+video+generation+AI&hl=en-US&gl=US&ceid=US:en",
        "type": "rss"
    },
    "hackernews": {
        "url": "https://hnrss.org/newest?q=artificial+intelligence+OR+machine+learning+OR+LLM+OR+neural+network",
        "type": "rss"
    },
    "arxiv_ai": {
        "url": "http://export.arxiv.org/rss/cs.AI",
        "type": "rss"
    },
    "arxiv_lg": {
        "url": "http://export.arxiv.org/rss/cs.LG",
        "type": "rss"
    },
    "arxiv_cl": {
        "url": "http://export.arxiv.org/rss/cs.CL",
        "type": "rss"
    },
    "reddit_ml": {
        "url": "https://www.reddit.com/r/MachineLearning/.rss",
        "type": "rss"
    },
    "reddit_local_llama": {
        "url": "https://www.reddit.com/r/LocalLLaMA/.rss",
        "type": "rss"
    },
    "openai_blog": {
        "url": "https://openai.com/blog/rss.xml",
        "type": "rss"
    },
    "anthropic_blog": {
        "url": "https://www.anthropic.com/rss.xml",
        "type": "rss"
    },
    "deepmind_blog": {
        "url": "https://deepmind.google/blog/rss.xml",
        "type": "rss"
    },
}

# ─── HEALTH TRACKING ───

def load_health_log():
    """Load persistent health log from previous runs."""
    if os.path.exists(HEALTH_LOG_PATH):
        try:
            with open(HEALTH_LOG_PATH, "r") as f:
                return json.load(f)
        except:
            pass
    return {}


def save_health_log(log):
    """Save health log for next run."""
    os.makedirs("output", exist_ok=True)
    with open(HEALTH_LOG_PATH, "w") as f:
        json.dump(log, f, indent=2)


def update_source_health(health_log, source_name, success, article_count=0, error_msg=""):
    """Track source reliability. Auto-disable after 3 consecutive failures."""
    today = datetime.now().strftime("%Y-%m-%d")

    if source_name not in health_log:
        health_log[source_name] = {
            "consecutive_failures": 0,
            "total_failures": 0,
            "total_successes": 0,
            "last_success": "",
            "last_failure": "",
            "disabled": False,
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
        entry["error_history"] = entry["error_history"][-5:]  # Keep last 5

        # Auto-disable after 3 consecutive failures
        if entry["consecutive_failures"] >= 3:
            entry["disabled"] = True
            print(f"[HEALTH] ⚠️ {source_name} auto-disabled after 3 consecutive failures")

    return health_log


def get_source_status(health_log, source_name):
    """Check if source is healthy enough to fetch."""
    if source_name not in health_log:
        return True
    return not health_log[source_name].get("disabled", False)


# ─── FETCH FUNCTIONS ───

def fetch_rss(name, config, health_log):
    """Fetch and parse RSS feed with health tracking."""
    articles = []

    # Skip if auto-disabled
    if not get_source_status(health_log, name):
        print(f"[SKIP] {name} is auto-disabled due to repeated failures")
        return articles, health_log

    try:
        print(f"[FETCH] {name} ...")
        feed = feedparser.parse(config["url"])

        # Check for parse errors
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

            summary = ""
            for field in ["summary", "description", "content"]:
                if hasattr(entry, field):
                    val = getattr(entry, field)
                    if isinstance(val, list) and val:
                        val = val[0].get("value", "")
                    summary = val[:500] if val else ""
                    break

            summary = re.sub(r"<[^>]+>", " ", summary).strip()

            articles.append({
                "title": title,
                "url": entry.get("link", ""),
                "source": name,
                "published": pub_date.isoformat() if pub_date else "",
                "summary": summary,
                "category": name.split("_")[0] if "_" in name else name
            })

        print(f"[FETCH] {name} -> {len(articles)} articles")
        health_log = update_source_health(health_log, name, True, len(articles))
        return articles, health_log

    except Exception as e:
        error_msg = str(e)[:100]
        print(f"[ERROR] {name}: {error_msg}")
        health_log = update_source_health(health_log, name, False, error_msg=error_msg)
        return articles, health_log


def fetch_github_trending():
    """Fetch trending AI/ML repos from GitHub."""
    articles = []
    try:
        print("[FETCH] github_trending ...")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        query = quote("machine learning OR deep learning OR LLM OR neural network OR AI framework")
        url = f"https://api.github.com/search/repositories?q={query}+created:>{yesterday}&sort=stars&order=desc"

        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            for repo in data.get("items", [])[:10]:
                articles.append({
                    "title": f"[GitHub] {repo['full_name']}: {repo['description'] or 'No description'}",
                    "url": repo["html_url"],
                    "source": "github_trending",
                    "published": datetime.now().isoformat(),
                    "summary": f"⭐ {repo['stargazers_count']} stars | {repo['language'] or 'Unknown'} | {repo.get('topics', [])}",
                    "category": "tools"
                })
        print(f"[FETCH] github_trending -> {len(articles)} repos")
    except Exception as e:
        print(f"[ERROR] github_trending: {e}")
    return articles


def deduplicate(articles):
    """Remove duplicates by URL and near-duplicate titles."""
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

    print(f"[DEDUP] {len(articles)} -> {len(unique)} unique articles")
    return unique


# ─── LLM CURATION WITH FALLBACKS ───

def call_groq(prompt, system_prompt, retries=MAX_LLM_RETRIES):
    """Call Groq API with retry logic."""
    if not GROQ_API_KEY:
        return None

    for attempt in range(retries):
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.2,
                    "max_tokens": 4000,
                    "response_format": {"type": "json_object"}
                },
                timeout=60
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return json.loads(content)
        except Exception as e:
            print(f"[GROQ] Attempt {attempt + 1}/{retries} failed: {e}")
            if attempt < retries - 1:
                import time
                time.sleep(2 ** attempt)  # Exponential backoff
    return None


def call_gemini(prompt, retries=MAX_LLM_RETRIES):
    """Call Gemini API with retry logic."""
    if not GEMINI_API_KEY:
        return None

    for attempt in range(retries):
        try:
            resp = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}",
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2}
                },
                timeout=60
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(content)
        except Exception as e:
            print(f"[GEMINI] Attempt {attempt + 1}/{retries} failed: {e}")
            if attempt < retries - 1:
                import time
                time.sleep(2 ** attempt)
    return None


def curate_articles(articles):
    """Smart curation with multi-provider fallback and raw fallback."""

    system_prompt = """You are a senior AI research analyst and staff engineer. Review these AI news articles and select the 6-8 MOST significant ones for a Senior AI Software Engineer who also does research in their leisure time.

The reader cares about: LLMs, generative AI, multimodal models, AI evaluation & benchmarks, AI safety & alignment, robotics/embodied AI, AI chips/hardware, computer vision, and open-source AI tools.

For EACH selected article, provide:
1. headline — exact or slightly cleaned title
2. url — the link
3. source — where it came from  
4. category — one of: [LLMs | GenAI | Robotics | Hardware | Safety | Evaluation | Vision | Tools | Research]
5. summary — 2-3 sentences explaining what happened
6. why_it_matters — 2-3 sentences on why a senior AI engineer should care. Be specific: mention technical implications, competitive landscape shifts, or research directions worth following.
7. action_item — 1 sentence on what to do (read paper, test tool, watch company, etc.)

SELECTION CRITERIA (be strict):
- Select ONLY genuinely significant news: major model releases, breakthrough research, important benchmarks, policy changes, major open-source releases, surprising evaluation results
- REJECT: pure marketing fluff, minor hires, vague partnership announcements, incremental updates without technical substance, duplicate coverage
- PRIORITIZE: Open-source releases with code, new SOTA benchmarks, safety research with concrete findings, hardware efficiency breakthroughs, novel architectures

Output ONLY valid JSON in this exact format:
{
  "selected": [
    {
      "headline": "...",
      "url": "...",
      "source": "...",
      "category": "...",
      "summary": "...",
      "why_it_matters": "...",
      "action_item": "..."
    }
  ]
}"""

    article_text = "\n\n".join([
        f"[{i+1}] {a['title']}\nSource: {a['source']} | {a['url']}\nSummary: {a['summary'][:300]}"
        for i, a in enumerate(articles[:50])
    ])

    user_prompt = f"Here are {len(articles[:50])} articles from the last 24 hours. Select and analyze the most important ones:\n\n{article_text}"

    # Try primary provider
    result = None
    used_provider = None

    if LLM_PROVIDER == "gemini" and GEMINI_API_KEY:
        result = call_gemini(user_prompt)
        used_provider = "gemini"

    if not result and GROQ_API_KEY:
        result = call_groq(user_prompt, system_prompt)
        used_provider = "groq"

    if not result and GEMINI_API_KEY and LLM_PROVIDER != "gemini":
        result = call_gemini(user_prompt)
        used_provider = "gemini (fallback)"

    if result and "selected" in result:
        selected = result["selected"]
        print(f"[CURATE] {used_provider} selected {len(selected)} articles")
        return selected, used_provider

    # RAW FALLBACK: If all LLMs fail, still send top articles with basic formatting
    print("[FALLBACK] All LLM providers failed. Sending raw top articles with basic analysis.")
    fallback = []
    for a in articles[:8]:
        cat_map = {
            "google": "Research", "hackernews": "Tools", "arxiv": "Research",
            "reddit": "Tools", "openai": "LLMs", "anthropic": "LLMs",
            "deepmind": "Research", "github": "Tools"
        }
        category = "Research"
        for k, v in cat_map.items():
            if k in a["source"]:
                category = v
                break

        fallback.append({
            "headline": a["title"],
            "url": a["url"],
            "source": a["source"],
            "category": category,
            "summary": a["summary"] or "See article for details.",
            "why_it_matters": "This article was surfaced from a trusted AI source. Review to determine relevance to your work.",
            "action_item": "Read the full article to assess technical significance.",
            "fallback": True
        })

    return fallback, "raw_fallback"


# ─── EMAIL FORMATTING ───

def generate_email_html(articles, date_str, meta_info):
    """Generate beautiful HTML email digest with health status."""

    cat_colors = {
        "LLMs": "#e74c3c",
        "GenAI": "#9b59b6", 
        "Robotics": "#3498db",
        "Hardware": "#f39c12",
        "Safety": "#e67e22",
        "Evaluation": "#1abc9c",
        "Vision": "#2ecc71",
        "Tools": "#34495e",
        "Research": "#16a085"
    }

    # Health status banner
    health_banner = ""
    disabled_sources = meta_info.get("disabled_sources", [])
    if disabled_sources:
        health_banner = f"""
        <div style="background: #fff3cd; border: 1px solid #ffc107; border-radius: 6px; padding: 10px 14px; margin-bottom: 20px; font-size: 12px; color: #856404;">
            ⚠️ <strong>Source Health:</strong> {len(disabled_sources)} source(s) temporarily disabled due to repeated failures: {', '.join(disabled_sources)}. 
            They will auto-retry tomorrow. All other sources are working normally.
        </div>
        """

    # Fallback warning
    fallback_banner = ""
    if meta_info.get("used_fallback"):
        fallback_banner = """
        <div style="background: #d1ecf1; border: 1px solid #bee5eb; border-radius: 6px; padding: 10px 14px; margin-bottom: 20px; font-size: 12px; color: #0c5460;">
            ℹ️ <strong>Note:</strong> LLM curation services were temporarily unavailable today. Articles are shown raw from trusted sources — please review for relevance.
        </div>
        """

    articles_html = ""
    for i, art in enumerate(articles, 1):
        cat = art.get("category", "Research")
        color = cat_colors.get(cat, "#34495e")
        fallback_tag = "<span style=\'background: #95a5a6; color: white; padding: 2px 8px; border-radius: 10px; font-size: 10px; margin-left: 6px;\'>RAW</span>" if art.get("fallback") else ""

        articles_html += f"""
        <div style="margin-bottom: 32px; padding-bottom: 24px; border-bottom: 1px solid #ecf0f1;">
            <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">
                <span style="background: {color}; color: white; padding: 3px 10px; border-radius: 12px; font-size: 11px; font-weight: 600; text-transform: uppercase;">{cat}</span>
                <span style="color: #7f8c8d; font-size: 12px;">{art.get('source', 'Unknown')}</span>
                {fallback_tag}
            </div>
            <h3 style="margin: 0 0 10px 0; font-size: 18px; line-height: 1.4;">
                <a href="{art.get('url', '#')}" style="color: #2c3e50; text-decoration: none;">{i}. {art.get('headline', art.get('title', 'Untitled'))}</a>
            </h3>
            <p style="margin: 0 0 10px 0; color: #555; line-height: 1.6; font-size: 14px;">
                <strong>Summary:</strong> {art.get('summary', 'No summary available.')}
            </p>
            <p style="margin: 0 0 10px 0; color: #2c3e50; line-height: 1.6; font-size: 14px; background: #f8f9fa; padding: 10px 14px; border-left: 3px solid {color}; border-radius: 0 4px 4px 0;">
                <strong>💡 Why it matters:</strong> {art.get('why_it_matters', 'See article for details.')}
            </p>
            <p style="margin: 0; color: {color}; font-size: 13px; font-weight: 500;">
                ⚡ <strong>Action:</strong> {art.get('action_item', 'Read the full article.')}
            </p>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background: #f5f6fa;">
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background: #f5f6fa;">
        <tr>
            <td align="center" style="padding: 30px 20px;">
                <table width="680" cellpadding="0" cellspacing="0" border="0" style="background: white; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); max-width: 100%;">
                    <!-- Header -->
                    <tr>
                        <td style="padding: 30px 30px 20px 30px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 12px 12px 0 0;">
                            <h1 style="margin: 0; color: white; font-size: 24px; font-weight: 700;">🧠 AI Daily Brief</h1>
                            <p style="margin: 6px 0 0 0; color: rgba(255,255,255,0.85); font-size: 14px;">{date_str} | Curated for Senior AI Engineers & Researchers</p>
                        </td>
                    </tr>

                    <!-- Stats -->
                    <tr>
                        <td style="padding: 16px 30px; background: #f8f9fa; border-bottom: 1px solid #e9ecef;">
                            <p style="margin: 0; color: #6c757d; font-size: 13px;">
                                📊 <strong>{len(articles)} stories</strong> selected from 50+ sources | Provider: {meta_info.get('provider', 'Unknown')} | Sources active: {meta_info.get('active_sources', '?')}/{meta_info.get('total_sources', '?')}
                            </p>
                        </td>
                    </tr>

                    <!-- Health Banners -->
                    <tr>
                        <td style="padding: 0 30px;">
                            {health_banner}
                            {fallback_banner}
                        </td>
                    </tr>

                    <!-- Articles -->
                    <tr>
                        <td style="padding: 24px 30px;">
                            {articles_html}
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="padding: 20px 30px; background: #f8f9fa; border-radius: 0 0 12px 12px; text-align: center;">
                            <p style="margin: 0; color: #adb5bd; font-size: 12px;">
                                Generated by AI News Digest Agent | 
                                <a href="https://github.com/YOUR_USERNAME/ai-news-digest" style="color: #667eea; text-decoration: none;">View Source</a>
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""
    return html


def send_email(html_content, date_str):
    """Send email via Gmail SMTP."""
    if not all([SENDER_EMAIL, SENDER_PASSWORD, RECIPIENT_EMAIL]):
        print("[WARN] Email credentials missing, saving to file only")
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

        print(f"[EMAIL] Sent successfully to {RECIPIENT_EMAIL}")
        return True
    except Exception as e:
        print(f"[ERROR] Email failed: {e}")
        return False


# ─── MAIN ───

def main():
    print("="*60)
    print("🧠 AI NEWS DIGEST AGENT — Self-Healing Edition")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)

    # Load health log
    health_log = load_health_log()

    # 1. Fetch all sources
    all_articles = []
    for name, config in SOURCES.items():
        if config["type"] == "rss":
            arts, health_log = fetch_rss(name, config, health_log)
            all_articles.extend(arts)

    # GitHub trending
    all_articles.extend(fetch_github_trending())

    print(f"\n[TOTAL] Fetched {len(all_articles)} raw articles")

    if not all_articles:
        print("[WARN] No articles fetched. Sending health alert email.")
        # Could send an alert email here
        save_health_log(health_log)
        return

    # 2. Deduplicate
    unique_articles = deduplicate(all_articles)

    # 3. Curation with multi-provider fallback
    selected, provider_used = curate_articles(unique_articles)

    if not selected:
        print("[WARN] No articles selected. Exiting.")
        save_health_log(health_log)
        return

    # 4. Prepare meta info
    disabled_sources = [k for k, v in health_log.items() if v.get("disabled", False)]
    active_sources = len(SOURCES) - len(disabled_sources)

    meta_info = {
        "provider": provider_used,
        "used_fallback": provider_used == "raw_fallback",
        "disabled_sources": disabled_sources,
        "active_sources": active_sources,
        "total_sources": len(SOURCES)
    }

    # 5. Generate & send email
    date_str = datetime.now().strftime("%A, %B %d, %Y")
    html = generate_email_html(selected, date_str, meta_info)
    email_sent = send_email(html, date_str)

    # 6. Save outputs
    os.makedirs("output", exist_ok=True)
    with open("output/digest.html", "w", encoding="utf-8") as f:
        f.write(html)
    with open("output/digest.json", "w", encoding="utf-8") as f:
        json.dump({"articles": selected, "meta": meta_info}, f, indent=2)

    # 7. Save health log
    save_health_log(health_log)

    print("\n✅ Done!")
    print(f"   📧 Email sent: {email_sent}")
    print(f"   🤖 Provider: {provider_used}")
    print(f"   📰 Articles: {len(selected)}")
    print(f"   🏥 Healthy sources: {active_sources}/{len(SOURCES)}")
    if disabled_sources:
        print(f"   ⚠️  Disabled sources: {', '.join(disabled_sources)}")


if __name__ == "__main__":
    main()
