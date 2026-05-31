# Hermes-Inspired Self-Improving Agent — Progress

**Started:** 2026-05-18
**Goal:** Build a personal AI assistant that grows smarter over time, inspired by Hermes Agent (nousresearch.com). Single-user, not commercial.

---

## What Was Built

### `week5_agent.py` ✅
A self-improving personal assistant CLI. Run with:
```bash
pip install anthropic python-dotenv
python3 week5_agent.py
```

**5 core concepts implemented:**

| Concept | How it works | Where in code |
|---------|-------------|---------------|
| Agent loop | `think → tool → observe → repeat` until `end_turn` | `Agent.run()` |
| Episodic memory | Every conversation summarized + saved to SQLite FTS5 | `Memory` class |
| Skill store | Reusable procedures learned from experience | `SkillStore` class |
| Self-reflection | Second LLM call after each task — saves memory, skill, user facts | `_reflect()` |
| User context | Permanent key-value facts about the user | `UserContext` class |

**Tools the agent has:**
- `recall_memory` — FTS5 search on past conversations
- `save_note` — persist user facts permanently
- `list_skills` — see learned procedures
- `run_python` — execute Python in subprocess
- `read_file` / `write_file` — file I/O

**Database:** `agent_memory.db` (SQLite, auto-created on first run)
- Tables: `memories`, `skills`, `user_context`
- FTS5 virtual tables on memories + skills for fast search
- Inspect anytime: `sqlite3 agent_memory.db .tables`

---

## Architecture Decisions & Tradeoffs

### LLM: Claude Haiku 4.5 (default)
`MODEL = "claude-haiku-4-5"` at top of file — change this one line to swap models.

| Model | Speed | Cost | Use when |
|-------|-------|------|----------|
| `claude-haiku-4-5` | ~1s | ~$0.0001/task | Daily assistant tasks (default) |
| `claude-sonnet-4-6` | ~3s | ~$0.001/task | Complex reasoning, coding |
| `claude-opus-4-7` | ~5s | ~$0.01/task | Hard problems, long docs |

### Storage: SQLite FTS5 (not vector DB)
- Zero extra dependencies
- FTS5 = keyword-ranked full-text search (BM25 scoring)
- Good enough for single-user personal assistant scale
- Upgrade path: ChromaDB or pgvector for semantic/fuzzy search

### Skills: stored as text procedures (not code)
- Safer than storing executable code
- Easier to inspect and edit manually
- Hermes uses both — text is the right starting point

### Reflection: runs after response (non-blocking)
- One extra Haiku call per task (~$0.0001)
- Doesn't slow down the hot path
- Extracts: memory summary, optional skill, user facts

---

## Infrastructure Discussion (not yet built)

### Personal assistant for Mac — what's needed

**3 new packages only:**
```bash
pip install rumps pynput pyperclip
# osascript is built into macOS — no install
```

| Layer | Tool | Purpose |
|-------|------|---------|
| Runtime | `rumps` | Menu bar app — always-on, lives in status bar |
| Interface | `pynput` | Global hotkey (e.g. Option+Space) to summon |
| Clipboard | `pyperclip` | Read selection, paste response |
| Notifications | `osascript` (built-in) | Async alerts |
| Screen context | `pyautogui` (optional) | Screenshot → Claude vision |

**Planned file:** `week6_menubar.py` (~80 lines wrapping week5_agent.py)

---

## Ollama Option (local, free, discussed not built)

Using Ollama instead of the Anthropic API:
- **Free forever** — runs on your machine, no API key
- **Private** — nothing leaves your computer
- **Tradeoff** — slower (depends on your hardware), weaker than Claude
- **Best model for agent/tool use:** `qwen2.5:7b` (needs 8GB RAM)

Code change needed — swap the client:
```python
# Current (Anthropic):
client = anthropic.Anthropic(api_key=...)

# Ollama (OpenAI-compatible API):
from openai import OpenAI
client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
```
Tool calling format also needs a rewrite (slightly different schema).

**Idea discussed:** Support both via a flag — `--local` uses Ollama, default uses Claude.

---

## Document Ingestion / RAG (discussed, not built)

Feeding the agent PDFs, docs, notes = RAG (Retrieval-Augmented Generation).

**Pipeline:**
```
PDF/doc → parse text → chunk → store in SQLite FTS5 → search on query → inject into prompt
```

Libraries needed per format:

| Format | Library |
|--------|---------|
| PDF | `pdfplumber` or `PyMuPDF` |
| Word (.docx) | `python-docx` |
| Web pages | `requests` + `beautifulsoup4` |
| CSV/Excel | `pandas` |
| Plain text/MD | Built-in |

**Planned:** `ingest` command in `week5_agent.py` — `ingest my_notes.pdf` → agent can answer from it.

**Limitation:** RAG gives access to documents, doesn't make the model smarter. Quality depends on chunk size and search quality.

---

## Web Search (discussed, not built)

Agent currently has no internet access. Planned tools to add:

| Tool | Library | Purpose |
|------|---------|---------|
| `web_search(query)` | Tavily API (free: 1000/month) | Search and return clean text results |
| `fetch_page(url)` | `requests` + `beautifulsoup4` | Read a specific URL |

**Recommended:** Tavily for search (designed for AI agents) + BS4 for page fetching.

**Limitation:** Cannot handle login-gated sites, JS-heavy SPAs, or Cloudflare-protected pages. For those: Playwright (full browser). Covers 90% of research tasks without it.

---

## Next Steps (in priority order)

- [ ] **Week 6** — `week6_menubar.py`: Mac menu bar app wrapping week5_agent.py
- [ ] Add `web_search` + `fetch_page` tools to week5_agent.py (Tavily + BS4, ~40 lines)
- [ ] Add `ingest` command for PDFs/docs (pdfplumber + chunking into SQLite)
- [ ] Ollama support — `--local` flag to switch between Claude and qwen2.5:7b
- [ ] Voice input/output (speech_recognition + pyttsx3) — optional, for hands-free use

---

## Key Files

| File | Purpose |
|------|---------|
| `week5_agent.py` | Self-improving agent CLI (the brain) |
| `agent_memory.db` | SQLite DB — memories, skills, user context (auto-created) |
| `week6_menubar.py` | Mac menu bar wrapper (planned) |

---

## Reference

- Hermes Agent overview: https://hermes-agent.nousresearch.com/docs/
- Hermes skills hub: https://hermes-agent.nousresearch.com/docs/skills
- Tavily API (web search for agents): https://tavily.com
- Ollama local models: https://ollama.com
