# 🗺️ Project Command Center

**AI-powered 6-project management dashboard with pixel art map — built at zero cost.**

> "コスト0で6つのプロジェクトを自動管理するダッシュボードを作った話"
> Read the full story on [note](https://note.com/note_rice/n/nd836f965d468)

---

## Overview

A freelance web director's personal command center for managing 6 simultaneous revenue projects using AI agents, Python scripts, and Google Sheets — with zero monthly infrastructure cost.

This system autonomously:
- Scrapes job listings from Lancers / Coconala / Crowdworks daily
- Generates X (Twitter) posts using Claude API
- Tracks GA4 analytics for multiple properties
- Syncs project state to Google Drive, Desktop, and Notion
- Sends Gmail notifications and creates Google Calendar reminders

---

## Architecture

```
ProjectCommandCenter/
├── AutoBotProject/          # Core automation scripts
│   ├── generate_posts.py    # Claude API → X post generation + Gmail + Calendar
│   ├── get_x_stats.py       # X (Twitter) follower/impression tracking
│   ├── bot_core.py          # X auto-follow bot (Playwright)
│   └── x_auto_post.py       # X scheduled posting
├── PROJECT03_WordPress/
│   └── check_jobs.py        # Job scraping (Lancers/Coconala/Crowdworks) → Sheets
└── _shared/
    ├── drive_sync.py         # PROJECT_STATE.md → Drive + Desktop + Notion
    └── credentials/          # OAuth tokens (not committed)
```

---

## Features

### Job Search Automation (PJ⑤)
- Scrapes 3 platforms (Lancers, Coconala, Crowdworks) daily
- Filters by skill keywords (AI/automation/web dev)
- Auto-rates jobs ◎/○/△/✕ by budget, deadline, and client score
- Writes results to Google Sheets with color coding
- Dropdown status: 新着 / 検討中 / 見送り / 応募済み
- Deduplication: skips already-seen or manually dismissed jobs

### X Post Generation (PJ②)
- Reads today's schedule from Google Sheets
- Generates themed posts via Claude API (claude-opus-4-6)
- Sends posts by email (Gmail API) + registers Google Calendar reminders
- Supports post types: 公開告知 / 有料note導線 / 誘導 / ノウハウ共有

### Morning Dashboard
- Weather (Tokyo), Google Calendar, GA4 analytics
- Job pickup, X stats, AI news (Google News RSS)
- Focus task suggestion with date-accurate filtering

### Project State Sync
- Single `PROJECT_STATE.md` shared between Claude Code and Cowork AI
- Auto-syncs to Google Drive, Desktop copy, and Notion on every task completion

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| AI | Claude API (claude-opus-4-6) |
| Automation | Python 3, Playwright, BeautifulSoup |
| Spreadsheet | Google Sheets API (gspread) |
| Notifications | Gmail API, Google Calendar API |
| Sync | Google Drive API, Notion API |
| AI Agents | Claude Code custom agents (~/.claude/agents/) |

---

## Cost

| Service | Cost |
|---------|------|
| Claude API | ~$0.01–0.05/day |
| Google APIs | Free tier |
| Vercel | Free |
| Everything else | $0 |

**Total: effectively $0/month** for the infrastructure.

---

## Projects Managed

| # | Project | Platform |
|---|---------|----------|
| ① | Japanese Fermentation Content | WordPress / Pinterest / Gumroad |
| ② | Web Director × AI Content | X(Twitter) / note.com |
| ③ | Affiliate Blog (JP) | WordPress / Pinterest |
| ④ | tomatick.app (Pomodoro SaaS) | Next.js / Vercel |
| ⑤ | Freelance Job Search | Lancers / Coconala / Crowdworks |
| ⑥ | Overseas Digital Products | Gumroad / Etsy / Pinterest |

---

## Author

Freelance web director with 15 years of experience, building AI-powered automation systems.
- X: [@hirowisdom98444](https://x.com/hirowisdom98444)
- note: [とあるWebディレクターの裏側](https://note.com/note_rice)
