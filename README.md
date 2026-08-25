# 🤖 AI Daily News Digest Agent

> **Zero-cost, fully automated AI news curation for Senior AI Engineers & Researchers.**  
> Delivers a beautifully formatted email every morning at 6:00 AM EST with the most important AI developments worldwide — with technical analysis on why each matters and what action to take.

---

## ✨ What It Does

Every morning, this agent:

1. **Scans 50+ sources** across 8 AI domains:
   - 🧠 **LLMs** — architecture, training, inference optimization
   - 🎨 **GenAI** — diffusion, multimodal, creative AI
   - 🤖 **Robotics / Embodied AI**
   - ⚡ **AI Chips & Hardware** — GPUs, TPUs, training clusters
   - 🛡️ **AI Safety & Alignment**
   - 📊 **AI Evaluation & Benchmarks**
   - 👁️ **Computer Vision**
   - 🛠️ **Open-Source Tools** (GitHub trending)

2. **Deduplicates** articles by URL and near-duplicate titles

3. **Intelligently curates** using an LLM (Groq/Gemini free tier) with a prompt engineered for senior AI engineers — rejecting marketing fluff and prioritizing technical substance

4. **Explains why each story matters** with:
   - Technical summary
   - Impact analysis for practitioners
   - Concrete action item

5. **Emails you** a beautiful HTML digest

---

## 🚀 Setup (5 minutes)

### Step 1: Fork / Create Repo

Create a new **public** GitHub repository and upload these files, or fork this repo.

### Step 2: Get Free API Keys

#### Option A: Groq (Recommended — fastest, generous free tier)
1. Go to [console.groq.com](https://console.groq.com)
2. Sign up and create an API key
3. Free tier: 20 requests/minute, 1,440 requests/day, 6,000 tokens/minute

#### Option B: Gemini (Google AI Studio)
1. Go to [aistudio.google.com](https://aistudio.google.com)
2. Create API key
3. Free tier: 1,500 requests/day for Gemini 1.5 Flash

> **Tip:** You can set both and use `LLM_PROVIDER` to switch between them.

### Step 3: Configure Gmail for SMTP

You need an **App Password** (NOT your regular password):

1. Enable 2-Factor Authentication on your Google Account
2. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Generate an app password for "Mail"
4. Save this 16-character password

### Step 4: Add GitHub Secrets

In your repo, go to **Settings → Secrets and variables → Actions → New repository secret**.

Add these secrets:

| Secret Name | Value |
|-------------|-------|
| `GROQ_API_KEY` | Your Groq API key |
| `GEMINI_API_KEY` | Your Gemini API key (optional backup) |
| `SENDER_EMAIL` | Your Gmail address (e.g., `you@gmail.com`) |
| `SENDER_PASSWORD` | Your Gmail App Password |
| `RECIPIENT_EMAIL` | Where to send the digest (can be same as sender) |
| `LLM_PROVIDER` | `groq` or `gemini` |

### Step 5: Test It

Go to **Actions → AI Daily News Digest → Run workflow** (click "Run workflow").

Check your email in ~2 minutes!

---

## 📁 File Structure

```
.
├── ai_news_digest.py          # Main agent script
├── requirements.txt           # Python dependencies
├── .github/
│   └── workflows/
│       └── daily_digest.yml   # GitHub Actions schedule
└── README.md                  # This file
```

---

## 🔧 Customization

### Change the time
Edit `.github/workflows/daily_digest.yml`:
```yaml
# 6 AM EST = 11 AM UTC
cron: "0 11 * * *"
```

Use [crontab.guru](https://crontab.guru) to generate your own schedule.

### Add more sources
Edit the `SOURCES` dict in `ai_news_digest.py`. Any RSS feed works:

```python
"your_source": {
    "url": "https://example.com/feed.xml",
    "type": "rss"
}
```

### Change email provider
Replace the SMTP section in `send_email()` with your provider:
- **Outlook**: `smtp.office365.com:587` (use STARTTLS)
- **SendGrid**: Use their API instead of SMTP

### Adjust curation strictness
Edit the `system_prompt` in `curate_with_groq()`. Make it stricter or looser based on your taste.

---

## 💰 Cost Breakdown

| Component | Cost |
|-----------|------|
| GitHub Actions (public repo) | **$0** (2,000 min/month) |
| Groq API | **$0** (free tier) |
| Gemini API | **$0** (free tier) |
| Gmail SMTP | **$0** |
| **Total** | **$0** |

---

## 🛠️ Troubleshooting

**Email not arriving?**
- Check GitHub Actions logs: Actions → AI Daily News Digest → latest run
- Verify Gmail App Password (not regular password)
- Check spam folder
- Ensure `SENDER_EMAIL` matches the account that generated the App Password

**LLM curation failing?**
- Check that `GROQ_API_KEY` is set correctly in Secrets
- Groq free tier has rate limits; the script handles this gracefully
- Try switching to `GEMINI_API_KEY` with `LLM_PROVIDER=gemini`

**Too many / too few articles?**
- Adjust `MAX_ARTICLES_PER_SOURCE` (default: 15)
- Tweak the LLM prompt in `curate_with_groq()`

**Want to see the digest without email?**
- After each run, go to Actions → latest run → Artifacts → download `daily-digest-*`
- Contains `digest.html` and `digest.json`

---

## 📜 License

MIT — use it, fork it, improve it.

---

*Built for engineers who want to stay ahead without drowning in noise.*
