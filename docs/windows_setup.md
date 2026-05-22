# Windows Setup Guide — Johnny AI System

*For running the full Johnny stack (MCP server, Telegram bot, Ollama local LLM)
on a Windows desktop. Written for an NVIDIA RTX GPU.*

---

## What you get

| Component | What it does |
|---|---|
| **MCP server** (`mcp_server.py`) | Claude Desktop plugs into this. Gives Claude access to your 16 MCP tools — search your brain, capture thoughts, pull forex notes, etc. |
| **Ollama + local LLM** | Free AI that runs entirely on your GPU. Used for quick tasks, Kanaan proposals, Smarty research. |
| **Telegram bot** (`telegram_bot.py`) | Capture thoughts from your phone. Replies from the AI arrive back. |
| **Scheduler** (`scheduler.py`) | Morning briefing at 7am, NY session nudge at 7:45pm, trade journal at 10:30pm. |

---

## Step 1 — Install prerequisites

### Git
Download from https://git-scm.com/download/win  
Install with defaults. Tick "Git Bash" option.

### Python 3.11+
Download from https://www.python.org/downloads/  
**Important:** tick **"Add Python to PATH"** during install.

Verify in Command Prompt:
```
python --version
```
Should show `3.11.x` or higher.

---

## Step 2 — Clone the repo

Open Command Prompt or Git Bash:

```bash
cd C:\Users\YourName\Documents
git clone https://github.com/shaobird/johnny.git
cd Johnny
```

---

## Step 3 — Install Python dependencies

```bash
pip install -r requirements.txt
```

This installs: Anthropic SDK, Telegram bot, MCP server, sentence-transformers, and everything else.

First time takes 2–5 minutes (sentence-transformers is ~1GB).

---

## Step 4 — Install Ollama

Download the Windows installer from **https://ollama.com/download/windows**

Run it. Ollama installs as a background service — you'll see it in the system tray.

---

## Step 5 — Pull a local LLM

Open Command Prompt and run **one** of these based on your RTX card:

| Your GPU | VRAM | Command |
|---|---|---|
| RTX 4090 | 24 GB | `ollama pull llama3.3:70b` — best quality, ~40 GB |
| RTX 3090 / 4080 | 16–24 GB | `ollama pull qwen2.5:32b` — excellent |
| RTX 3080 / 4070 Ti | 10–12 GB | `ollama pull qwen2.5:14b` ← **recommended default** |
| RTX 4060 / 3070 | 8 GB | `ollama pull qwen2.5:7b` |

The download takes 5–20 minutes depending on model size and your connection.

Test it's working:
```bash
ollama run qwen2.5:14b "say hello"
```

---

## Step 6 — Create your `.env` file

In the Johnny folder, copy the example:
```bash
copy .env.example .env
```

Then open `.env` in Notepad and fill in your keys:

```
ANTHROPIC_API_KEY=sk-ant-...     ← required (claude.ai/settings → API keys)
GEMINI_API_KEY=AIza...           ← for research agent (free at aistudio.google.com)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:14b         ← match what you pulled in Step 5
TELEGRAM_BOT_TOKEN=...           ← from @BotFather (optional, but very useful)
TELEGRAM_CHAT_ID=...             ← your personal chat ID
```

Leave everything else as-is for now. You can fill in Strava, Hevy etc. later.

---

## Step 7 — Backfill semantic embeddings

This embeds your existing 56+ thoughts so the `semantic_search` tool works.
Run once:

```bash
python scripts/backfill_embeddings.py
```

First run downloads the embedding model (~80 MB). Takes about 30 seconds.

---

## Step 8 — Install Claude Desktop

Download from **https://claude.ai/download**

After install, open:
```
C:\Users\YourName\AppData\Roaming\Claude\claude_desktop_config.json
```

If the file doesn't exist, create it. Paste this:

```json
{
  "mcpServers": {
    "johnny-mo": {
      "command": "python",
      "args": ["C:\\Users\\YourName\\Documents\\Johnny\\mcp_server.py"],
      "env": {
        "PYTHONPATH": "C:\\Users\\YourName\\Documents\\Johnny"
      }
    }
  }
}
```

Replace `C:\\Users\\YourName\\Documents\\Johnny` with your actual path.
(Use double backslashes in JSON on Windows.)

Restart Claude Desktop. In the bottom-left corner you should see a 🔌 icon —
click it to verify "johnny-mo" is connected with 16 tools.

---

## Step 9 — Test the MCP server

In Claude Desktop, type:
```
thought_stats
```

You should see stats for your 56+ captured thoughts. If it works, the whole
brain is live and searchable from Claude.

---

## Step 10 (optional) — Start the Telegram bot

Open a Command Prompt in the Johnny folder and run:
```bash
python telegram_bot.py
```

Send a message to your bot on Telegram. You should get a reply.

To keep it running in the background on Windows, see the "Run as background 
service" section below.

---

## Run as background service (optional)

To have the Telegram bot and scheduler start automatically at boot:

### Option A — Task Scheduler (simplest)
1. Open Windows Task Scheduler
2. Create Basic Task → "Johnny Telegram Bot"
3. Trigger: At startup
4. Action: Start a program → `python.exe`
5. Arguments: `C:\Users\YourName\Documents\Johnny\telegram_bot.py`
6. Start in: `C:\Users\YourName\Documents\Johnny`

### Option B — NSSM (cleaner)
Download NSSM from https://nssm.cc/download

```bash
nssm install JohnnyBot python.exe
# In the GUI: set path to telegram_bot.py, startup dir to Johnny folder
nssm start JohnnyBot
```

---

## Folder structure after setup

```
Johnny/
├── .env                  ← your secrets (gitignored)
├── storage/              ← all your data (gitignored)
│   ├── thoughts/
│   │   ├── thoughts.json        ← Open Brain captures
│   │   └── embeddings.json      ← semantic search index
│   ├── ai_sessions/
│   │   └── sessions.json        ← AI session history
│   └── files/                   ← Mo's document warehouse
├── agents/               ← all AI agents
├── docs/                 ← guides and Spark/Review docs
└── scripts/              ← maintenance scripts
```

---

## When Mac Mini arrives

When you migrate to the Mac Mini:

```bash
git clone https://github.com/shaobird/johnny.git
# Copy storage/ folder from Windows to Mac Mini
# (robocopy or just zip + sftp)
pip install -r requirements.txt
python scripts/backfill_embeddings.py  # re-embed on the new machine
```

Update `OLLAMA_BASE_URL` in `.env` on Windows to point at the Mac Mini's IP
if you want to offload the LLM there.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError` | `pip install -r requirements.txt` again |
| Claude Desktop doesn't show MCP tools | Check paths in `claude_desktop_config.json` — must use double backslashes |
| Ollama not responding | Check system tray — Ollama icon should be there; restart if not |
| `semantic_search` returns keyword results | Run `backfill_embeddings.py` first |
| Telegram bot not replying | Check `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env` |
