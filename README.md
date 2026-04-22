# Github Review Bot (AI Senior Engineer)

An autonomous AI code review agent that installs as a GitHub App and automatically reviews pull requests using Claude. When a PR is opened or updated, it fetches the diff, runs a two-pass Claude pipeline, and posts inline comments on specific lines + a structured summary — like having a senior engineer review every commit.

**[Live Demo](#demo) · [GitHub App](#installation)**

---

## Demo

> Open a PR with bad code → bot reviews it in ~10 seconds

![Demo GIF](demo.gif)


---

## How It Works

```
PR opened / commit pushed
        ↓
GitHub fires webhook → FastAPI server
        ↓
Fetch raw unified diff via GitHub REST API
        ↓
Pass 1 → Claude analyzes diff line by line
         returns structured JSON: [{file, position, severity, category, comment}]
        ↓
Pass 2 → Claude generates markdown summary from analysis findings
        ↓
POST inline comments to GitHub Reviews API (Files changed tab)
POST summary comment to PR conversation
        ↓
Review appears on PR within ~10 seconds
```

**Two-pass pipeline design:** The first Claude call focuses purely on finding issues and returning structured JSON with exact diff positions. The second call takes those findings and writes a human-readable summary. While 2 passes doubles expense, separating these concerns produces better output than asking Claude to do both at once.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Server | Python, FastAPI |
| GitHub Integration | PyGithub, GitHub Apps API, RSA JWT auth |
| AI Pipeline | Anthropic Claude (claude-haiku-4-5) |
| Diff Parsing | Custom unified diff parser with position mapping |
| Deploy | Railway |

---

## Key Engineering Details

**Webhook security** — Every incoming webhook is verified using HMAC-SHA256 signature validation against a shared secret. Requests with invalid signatures are rejected with 401 before any processing occurs.

**GitHub App JWT auth** — The server authenticates as a GitHub App using RS256-signed JWTs generated from an RSA private key, then exchanges them for short-lived installation access tokens scoped to the specific repo.

**Diff position mapping** — GitHub's PR review API requires comments to reference a `position` — the line number within the unified diff counting from the `@@` hunk header. The diff parser maps each changed line to its correct diff position so inline comments land on the right lines.

**Background task architecture** — The webhook handler returns `200 OK` immediately (GitHub requires a response within 10 seconds) and runs the full review pipeline as a FastAPI background task, which can take 10–30 seconds depending on diff size.

**Structured AI output** — The review prompt instructs Claude to return only valid JSON matching a strict schema. If Claude wraps output in markdown fences, the parser strips them before JSON parsing. Invalid positions are filtered before posting to avoid 422 errors from GitHub.

---

## Installation

### Run locally

```bash
git clone https://github.com/pvparekh/github-review-bot
cd github-review-bot
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

Create `.env`:
```
GITHUB_APP_ID=your_app_id
GITHUB_PRIVATE_KEY_PATH=./your-private-key.pem
GITHUB_WEBHOOK_SECRET=your_webhook_secret
ANTHROPIC_API_KEY=your_anthropic_key
```

```bash
uvicorn app.main:app --port 8000
```

Use ngrok for local webhook testing:
```bash
ngrok http 8000
```

### GitHub App Setup

1. Go to GitHub → Settings → Developer Settings → GitHub Apps → New GitHub App
2. Set webhook URL to your server URL + `/webhook`
3. Set permissions: Contents (read), Pull requests (read & write)
4. Subscribe to: Pull request events
5. Generate a private key and add to your project root
6. Install the app on any repo you want reviewed

---

## Project Structure

```
app/
├── main.py          # FastAPI app, webhook endpoint, signature verification
├── github_client.py # GitHub API: auth, diff fetching, review posting
├── diff_parser.py   # Unified diff parser with position mapping
├── reviewer.py      # Claude integration, two-pass pipeline orchestration
└── models.py        # Pydantic models for review comments
```

---

---

## Built By

Parth Parekh — April 2026