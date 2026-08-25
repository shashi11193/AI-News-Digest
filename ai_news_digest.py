#!/usr/bin/env python3
"""
AI News Digest Agent v3 — Reliable Deep Curation
Smaller LLM batches, robust fallback, clean formatting.
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
        "url": "https://news.google.com/rss/search?q=AI+agent+OR+autonomous+agent+OR+agentic+AI+OR+AI+workflow+OR+computer+use+agent&hl=en-US&gl=US&ceid=US:en",
        "type": "rss", "category": "Agents"
    },
    "google_news_robotics": {
        "url": "https://news.google.com/rss/search?q=AI+robotics+OR+embodied+AI+OR+humanoid+robot+OR+Figure+AI+OR+Boston+Dynamics+AI&hl=en-US&gl=US&ceid=US:en",
        "type": "rss", "category": "Robotics"
    },
    "google_news_chips": {
        "url": "https://news.google.com/rss/search?q=AI+chip+OR+GPU+OR+TPU+OR+AI+hardware+OR+NVIDIA+OR+training+cluster+OR+inference+optimization&hl=en-US&gl=US&ceid=US:en",
        "type": "rss", "category": "Hardware"
    },
    "google_news_safety": {
        "url": "https://news.google.com/rss/search?q=AI+safety+OR+AI+alignment+OR+AI+regulation+OR+EU+AI+Act+OR+AI+governance&hl=en-US&gl=US&ceid=US:en",
        "type": "rss", "category": "Safety"
    },
    "google_news_evaluation": {
        "url": "https://news.google.com/rss/search?q=AI+evaluation+OR+LLM+benchmark+OR+model+evaluation+OR+MMLU+OR+HumanEval+OR+SWE-bench&hl=en-US&gl=US&ceid=US:en",
        "type": "rss", "category": "Evaluation"
    },
    "google_news_vision": {
        "url": "https://news.google.com/rss/search?q=computer+vision+OR+image+generation+OR+video+generation+AI+OR+segment+anything+OR+YOLO&hl=en-US&gl=US&ceid=US:en",
        "type": "rss", "category": "Vision"
    },
    "google_news_releases": {
        "url": "https://news.google.com/rss/search?q=new+AI+model+release+OR+new+LLM+announced+OR+AI+product+launch+2026+OR+AI+startup+funding&hl=en-US&gl=US&ceid=US:en",
        "type": "rss", "category": "Releases"
    },
    "hackernews": {
        "url": "https://hnrss.org/newest?q=artificial+intelligence+OR+machine+learning+OR+LLM+OR+neural+network+OR+AI+model",
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
    "arxiv_robotics": {
        "url": "http://export.arxiv.org/rss/cs.RO",
        "type": "rss", "category": "Robotics"
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
    "wired_ai": {
        "url": "https://www.wired.com/tag/artificial-intelligence/feed/",
        "type": "rss", "category": "Safety"
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

            # Strict date filtering — reject if older than cutoff
            if pub_date and pub_date < cutoff:
                continue

            title = entry.get("title", "").strip()
            if not title:
                continue

            # Skip obvious old content / reports with years far in the past
            title_lower = title.lower()
            if any(x in title_lower for x in ["market size, share", "trends report", "forecast to 20", "market research"]):
                continue

            summary = ""
            for field in ["summary", "description", "content"]:
                if hasattr(entry, field):
                    val = getattr(entry, field)
                    if isinstance(val, list) and val:
                        val = val[0].get("value", "")
                    summary = val[:1000] if val else ""
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


def fetch_github_trending():
    articles = []
    try:
        print("[FETCH] github_trending ...")
        yesterday = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
        queries = [
            "machine learning OR deep learning OR LLM",
            "AI agent OR autonomous agent OR computer use",
            "diffusion model OR image generation OR video generation"
        ]
        for q in queries:
            query = quote(q)
            url = f"https://api.github.com/search/repositories?q={query}+created:>{yesterday}&sort=stars&order=desc"
            resp = requests.get(url, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                for repo in data.get("items", [])[:5]:
                    articles.append({
                        "title": f"[GitHub] {repo['full_name']}: {repo['description'] or 'No description'}",
                        "url": repo["html_url"],
                        "source": "github_trending",
                        "published": datetime.now().isoformat(),
                        "summary": f"⭐ {repo['stargazers_count']} stars | {repo['language'] or 'N/A'} | Topics: {', '.join(repo.get('topics', [])[:5])}",
                        "category": "Tools"
                    })
        print(f"[FETCH] github_trending -> {len(articles)} repos")
    except Exception as e:
        print(f"[ERROR] github_trending: {e}")
    return articles


# ─── SCRAPE ARTICLE CONTENT ───

def fetch_article_content(url):
    """Extract full article text via jina.ai reader."""
    if not url or not url.startswith("http"):
        return ""
    try:
        clean_url = url.replace("https://", "").replace("http://", "")
        jina_url = f"https://r.jina.ai/http://{clean_url}"
        resp = requests.get(jina_url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200:
            text = resp.text.strip()
            if len(text) > 4000:
                text = text[:4000] + "... [truncated]"
            return text
    except Exception as e:
        print(f"[SCRAPE FAIL] {url[:60]}...: {e}")
    return ""


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


# ─── LLM CURATION ───

def call_llm(prompt, system_prompt, provider):
    """Call LLM with detailed error logging."""
    if provider == "groq" and GROQ_API_KEY:
        return call_groq(prompt, system_prompt)
    elif provider == "gemini" and GEMINI_API_KEY:
        return call_gemini(prompt)
    return None, "no_key"


def call_groq(prompt, system_prompt, retries=MAX_LLM_RETRIES):
    if not GROQ_API_KEY:
        return None, "no_groq_key"
    for attempt in range(retries):
        try:
            print(f"[GROQ] Attempt {attempt+1}...")
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.2,
                    "max_tokens": 5000
                },
                timeout=120
            )
            print(f"[GROQ] Status: {resp.status_code}")
            if resp.status_code != 200:
                print(f"[GROQ] Error body: {resp.text[:500]}")
                if attempt < retries - 1:
                    import time
                    time.sleep(3)
                continue
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            # Extract JSON from response
            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group()), "groq"
            return json.loads(content), "groq"
        except Exception as e:
            print(f"[GROQ] Attempt {attempt+1} failed: {e}")
            if attempt < retries - 1:
                import time
                time.sleep(3)
    return None, "groq_failed"


def call_gemini(prompt, retries=MAX_LLM_RETRIES):
    if not GEMINI_API_KEY:
        return None, "no_gemini_key"
    for attempt in range(retries):
        try:
            print(f"[GEMINI] Attempt {attempt+1}...")
            resp = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}",
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.2}
                },
                timeout=120
            )
            print(f"[GEMINI] Status: {resp.status_code}")
            if resp.status_code != 200:
                print(f"[GEMINI] Error body: {resp.text[:500]}")
                if attempt < retries - 1:
                    import time
                    time.sleep(3)
                continue
            data = resp.json()
            content = data["candidates"][0]["content"]["parts"][0]["text"]
            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group()), "gemini"
            return json.loads(content), "gemini"
        except Exception as e:
            print(f"[GEMINI] Attempt {attempt+1} failed: {e}")
            if attempt < retries - 1:
                import time
                time.sleep(3)
    return None, "gemini_failed"


def curate_articles(articles):
    """Curate with smaller batches and robust fallback."""

    # Scrape content for top candidates
    print("\n[SCRAPE] Fetching article text...")
    enriched = []
    for art in articles[:25]:
        content = fetch_article_content(art["url"])
        art["full_text"] = content if content else (art["summary"] or "[No content available]")
        enriched.append(art)
    print(f"[SCRAPE] Enriched {len(enriched)} articles")

    # Build prompt — smaller batches to avoid token/time limits
    article_blocks = []
    for i, a in enumerate(enriched[:20]):
        text = a["full_text"][:1500]  # Cap at 1500 chars per article
        block = f"""ARTICLE [{i+1}]
TITLE: {a['title']}
SOURCE: {a['source']} | URL: {a['url']}
CATEGORY: {a['category']}
CONTENT:
{text}
---"""
        article_blocks.append(block)

    article_text = "\n\n".join(article_blocks)

    system_prompt = """You are a senior AI staff engineer who writes internal research briefs. You read AI news deeply and produce sharp, specific analysis.

TASK: Review the articles below (with their actual content) and select ALL genuinely significant stories. Include as many as deserve inclusion, up to a maximum of 15. If only 4 matter, include 4. If 12 matter, include 12.

For EACH selected article, output:
- headline: Clean, informative title. Rewrite if the original is clickbait or vague.
- url: The link
- source: Where it came from
- category: One of [LLMs | GenAI | Agents | Robotics | Hardware | Safety | Evaluation | Vision | Tools | Research | Releases]
- summary: 3-4 sentences summarizing the actual content. Explain what was built, released, discovered, or changed. Include specific names, numbers, or technical details when present.
- why_it_matters: 3-4 sentences of specific technical or strategic analysis. Reference concrete details from the article. Explain the implication for practitioners, researchers, or the competitive landscape. NEVER write generic statements.

STRICT RULES:
1. You have the FULL ARTICLE TEXT. Read it. Summarize FROM it.
2. If the article lacks technical substance (pure PR, no specs, no numbers), skip it.
3. Each summary and why_it_matters must be completely unique. Never reuse phrasing.
4. Prioritize: new model releases with specs, benchmark results with numbers, novel architectures, open-source code, safety research with findings, hardware gains with metrics.
5. Skip: vague partnerships, executive hires, marketing fluff, incremental UI updates, old market research reports.
6. Output ONLY a JSON object with a "selected" array."""

    user_prompt = f"Review these {len(enriched[:20])} articles from the last 24 hours.\n\n{article_text}\n\nOutput ONLY JSON: {{\"selected\": [...]}}"

    # Try primary provider
    result = None
    used_provider = None
    error_reason = ""

    if LLM_PROVIDER == "groq" and GROQ_API_KEY:
        result, status = call_llm(user_prompt, system_prompt, "groq")
        used_provider = "groq"
        error_reason = status
        print(f"[CURATE] Groq result: {status}")

    if not result and GEMINI_API_KEY:
        result, status = call_llm(user_prompt, system_prompt, "gemini")
        used_provider = "gemini"
        error_reason = status
        print(f"[CURATE] Gemini result: {status}")

    if not result and GROQ_API_KEY and LLM_PROVIDER != "groq":
        result, status = call_llm(user_prompt, system_prompt, "groq")
        used_provider = "groq (fallback)"
        error_reason = status
        print(f"[CURATE] Groq fallback result: {status}")

    if result and "selected" in result:
        selected = result["selected"]
        # Validate: reject if summaries are all identical (generic failure mode)
        summaries = [s.get("summary", "") for s in selected[:3]]
        if len(set(summaries)) == 1 and len(summaries) > 1:
            print("[CURATE] WARNING: LLM returned identical summaries. Using fallback.")
        else:
            print(f"[CURATE] {used_provider} selected {len(selected)} articles")
            return selected, used_provider

    # ─── INTELLIGENT FALLBACK ───
    print(f"[FALLBACK] LLM failed ({error_reason}). Building digest from scraped content.")
    fallback = []
    for a in enriched[:12]:
        content = a.get("full_text", "") or a["summary"]
        # Extract first few sentences as summary
        sentences = re.split(r"(?<=[.!?])\s+", content)
        summary = " ".join(sentences[:3])[:400] if sentences else content[:400]
        if not summary or len(summary) < 50:
            summary = a["summary"][:400] if a["summary"] else "See article for details."

        # Generate a basic why_it_matters from category
        cat = a["category"]
        why = f"Article from {a['source']} in the {cat} category. Review for technical details and implications."

        fallback.append({
            "headline": a["title"],
            "url": a["url"],
            "source": a["source"],
            "category": cat,
            "summary": summary,
            "why_it_matters": why,
            "fallback": True
        })

    return fallback, f"fallback ({error_reason})"


# ─── EMAIL FORMATTING ───

def generate_email_html(articles, date_str, meta_info):
    cat_colors = {
        "LLMs": "#e74c3c", "GenAI": "#9b59b6", "Agents": "#8e44ad",
        "Robotics": "#3498db", "Hardware": "#f39c12", "Safety": "#e67e22",
        "Evaluation": "#1abc9c", "Vision": "#2ecc71", "Tools": "#34495e",
        "Research": "#16a085", "Releases": "#d35400", "Community": "#7f8c8d"
    }

    health_banner = ""
    disabled_sources = meta_info.get("disabled_sources", [])
    if disabled_sources:
        health_banner = f"""<div style="background:#fff3cd;border:1px solid #ffc107;border-radius:6px;padding:10px 14px;margin-bottom:20px;font-size:12px;color:#856404;">⚠️ <strong>Source Health:</strong> {len(disabled_sources)} source(s) temporarily disabled: {', '.join(disabled_sources)}.</div>"""

    fallback_banner = ""
    if meta_info.get("used_fallback"):
        fallback_banner = """<div style="background:#d1ecf1;border:1px solid #bee5eb;border-radius:6px;padding:10px 14px;margin-bottom:20px;font-size:12px;color:#0c5460;">ℹ️ <strong>Note:</strong> Deep curation temporarily unavailable today. Articles summarized from original content.</div>"""

    articles_html = ""
    for i, art in enumerate(articles, 1):
        cat = art.get("category", "Research")
        color = cat_colors.get(cat, "#34495e")
        fallback_tag = "<span style='background:#95a5a6;color:white;padding:2px 8px;border-radius:10px;font-size:10px;margin-left:6px;'>RAW</span>" if art.get("fallback") else ""

        articles_html += f"""
        <div style="margin-bottom:32px;padding-bottom:24px;border-bottom:1px solid #e9ecef;">
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;flex-wrap:wrap;">
                <span style="background:{color};color:white;padding:4px 12px;border-radius:12px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">{cat}</span>
                <span style="color:#6c757d;font-size:12px;">{art.get('source','Unknown')}</span>
                {fallback_tag}
            </div>
            <h3 style="margin:0 0 12px 0;font-size:18px;line-height:1.4;color:#212529;">
                <a href="{art.get('url','#')}" style="color:#212529;text-decoration:none;">{i}. {art.get('headline', art.get('title','Untitled'))}</a>
            </h3>
            <div style="background:#f8f9fa;border-radius:8px;padding:14px 16px;margin-bottom:10px;">
                <p style="margin:0;color:#495057;line-height:1.6;font-size:14px;">{art.get('summary','No summary available.')}</p>
            </div>
            <div style="background:#fff;border-left:4px solid {color};padding:12px 16px;border-radius:0 6px 6px 0;">
                <p style="margin:0;color:#343a40;line-height:1.6;font-size:14px;"><strong style="color:{color};">Why it matters:</strong> {art.get('why_it_matters','')}</p>
            </div>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;background:#f8f9fa;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f8f9fa;">
<tr><td align="center" style="padding:28px 16px;">
<table width="700" cellpadding="0" cellspacing="0" border="0" style="background:white;border-radius:14px;box-shadow:0 2px 12px rgba(0,0,0,0.06);max-width:100%;">
<tr>
<td style="padding:30px 32px 20px 32px;background:linear-gradient(135deg,#1a1a2e 0%,#16213e 100%);border-radius:14px 14px 0 0;">
<h1 style="margin:0;color:white;font-size:24px;font-weight:700;letter-spacing:-0.3px;">🧠 AI Daily Brief</h1>
<p style="margin:6px 0 0 0;color:rgba(255,255,255,0.7);font-size:13px;">{date_str}</p>
</td>
</tr>
<tr>
<td style="padding:14px 32px;background:#f8f9fa;border-bottom:1px solid #e9ecef;">
<p style="margin:0;color:#6c757d;font-size:12px;">
📊 {len(articles)} stories | {meta_info.get('provider','Unknown')} | {meta_info.get('active_sources','?')}/{meta_info.get('total_sources','?')} sources active
</p>
</td>
</tr>
<tr><td style="padding:0 32px;">{health_banner}{fallback_banner}</td></tr>
<tr><td style="padding:24px 32px;">{articles_html}</td></tr>
<tr>
<td style="padding:18px 32px;background:#f8f9fa;border-radius:0 0 14px 14px;text-align:center;">
<p style="margin:0;color:#adb5bd;font-size:11px;">AI News Digest Agent | <a href="https://github.com/shashi11193/AI-News-Digest" style="color:#667eea;text-decoration:none;">Source</a></p>
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
    print("="*65)
    print("🧠 AI NEWS DIGEST AGENT v3")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*65)

    health_log = load_health_log()
    all_articles = []

    for name, config in SOURCES.items():
        if config["type"] == "rss":
            arts, health_log = fetch_rss(name, config, health_log)
            all_articles.extend(arts)

    all_articles.extend(fetch_github_trending())
    print(f"\n[TOTAL] Fetched {len(all_articles)} raw articles")

    if not all_articles:
        print("[WARN] No articles fetched.")
        save_health_log(health_log)
        return

    unique_articles = deduplicate(all_articles)
    selected, provider_used = curate_articles(unique_articles)

    if not selected:
        print("[WARN] No articles selected.")
        save_health_log(health_log)
        return

    disabled_sources = [k for k, v in health_log.items() if v.get("disabled", False)]
    meta_info = {
        "provider": provider_used,
        "used_fallback": "fallback" in provider_used.lower(),
        "disabled_sources": disabled_sources,
        "active_sources": len(SOURCES) - len(disabled_sources),
        "total_sources": len(SOURCES)
    }

    date_str = datetime.now().strftime("%A, %B %d, %Y")
    html = generate_email_html(selected, date_str, meta_info)
    email_sent = send_email(html, date_str)

    os.makedirs("output", exist_ok=True)
    with open("output/digest.html", "w", encoding="utf-8") as f:
        f.write(html)
    with open("output/digest.json", "w", encoding="utf-8") as f:
        json.dump({"articles": selected, "meta": meta_info}, f, indent=2)

    save_health_log(health_log)

    print("\n✅ Done!")
    print(f"   📧 Email: {email_sent}")
    print(f"   🤖 Provider: {provider_used}")
    print(f"   📰 Articles: {len(selected)}")
    print(f"   🏥 Sources: {meta_info['active_sources']}/{meta_info['total_sources']}")


if __name__ == "__main__":
    main()
