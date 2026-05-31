# Python Learning Projects

Weekly projects built while learning AI engineering with Python and the Claude API. Each week introduces a new concept — from REST APIs and OAuth to few-shot prompting, structured output, and self-improving agents.

---

## Week 2 — ServiceNow Incident Fetcher

**File:** `week2_servicenow_fetcher.py`

Connects to a ServiceNow instance and fetches incident details via the REST API using OAuth 2.0 authentication.

**Concepts covered:**
- OAuth 2.0 Resource Owner Password flow — exchange credentials for a short-lived token
- Making authenticated REST API calls with `requests`
- Reading secrets from environment variables (never hardcoded)

**How to run:**

```bash
# Set up your .env with ServiceNow credentials first
python3 week2_servicenow_fetcher.py
# → prompts for an incident number, e.g. INC0010034
```

**Required `.env` variables:**
```
SNOW_INSTANCE=https://dev123456.service-now.com
SNOW_USER=admin
SNOW_PASS=your-password
SNOW_CLIENT_ID=your-oauth-client-id
SNOW_CLIENT_SECRET=your-oauth-client-secret
```

---

## Week 3 — Intelligent Ticket Classifier

**File:** `week3_ticket_classifier.py`  
**Output:** `ticket_classifications.json`

Classifies 20 sample ITSM support tickets using Claude AI. Demonstrates core prompting concepts used in production AI systems.

**Concepts covered:**

| Concept | What it does |
|---|---|
| System prompt | Sets Claude's role and output format before the conversation starts |
| Few-shot prompting | Provides 5 labelled examples so Claude learns the exact pattern |
| Structured output | Forces Claude to return valid JSON with 6 required fields |
| Temperature | Set to `0` for deterministic, reproducible classifications |
| Chain of thought | The `reasoning` field asks Claude to explain its logic before committing |

**Output format (per ticket):**
```json
{
  "category": "Hardware | Software | Network | Security | Access | Other",
  "subcategory": "specific area, e.g. VPN, Email, Laptop",
  "priority": "1 | 2 | 3 | 4",
  "impact": "High | Medium | Low",
  "confidence": 0.95,
  "reasoning": "one sentence explaining the classification decision"
}
```

**How to run:**

```bash
# Demo mode (no API key needed — uses realistic mock responses)
python3 week3_ticket_classifier.py

# Live mode — set DEMO_MODE = False in the file and add your API key
ANTHROPIC_API_KEY=sk-ant-... python3 week3_ticket_classifier.py
```

---

## Week 5 — Self-Improving Personal Assistant (Hermes Agent)

**File:** `week5_agent.py`

A personal AI assistant that gets smarter the more you use it. After every task it reflects on what happened, saves a memory, and optionally stores a reusable skill — so it can do similar tasks faster next time.

**Concepts covered:**
- Agentic tool-use loop (Claude calls tools, results feed back into context)
- Episodic memory with SQLite FTS5 full-text search
- Self-improvement via post-task reflection (the Hermes pattern)
- Persistent user context (facts about you that survive across sessions)
- Skill store — learned procedures injected into future prompts

**Architecture:**

```
Agent.run(task)
  ├── search memory + skills for relevant context
  ├── build system prompt injecting that context
  ├── Claude tool-use loop (up to 12 iterations)
  │     tools: recall_memory, save_note, list_skills,
  │            run_python, read_file, write_file
  └── _reflect() — saves memory, maybe saves a skill, saves user facts
```

**Key design tradeoffs:**

| Tradeoff | Decision | Why |
|---|---|---|
| Speed vs power | `claude-haiku-4-5` | 5× cheaper/faster; swap to Sonnet for harder tasks |
| FTS5 vs vectors | SQLite FTS5 | Zero extra packages; good enough for a single-user assistant |
| Skills as text | Natural-language steps | Safer than `exec`, easy to inspect and edit |
| Reflection timing | After response | Non-blocking — doesn't slow down the main response |

**How to run:**

```bash
pip install anthropic python-dotenv
# Add ANTHROPIC_API_KEY to .env
python3 week5_agent.py

# Interactive commands once running:
# skills    → list learned skills
# memories  → show recent conversations
# quit      → exit
```

---

## Otto — SaaS Marketing Mockup

**Location:** `../otto/`

A two-page marketing site mockup for a fictional web software company. Single self-contained `index.html` — no build step, no dependencies, no framework.

See [`../otto/README.md`](../otto/README.md) for details.

---

## Design Grill References

**Location:** `../design-grill-extracted/`

Reference notes used by the design grill skill — principles from Robert C. Martin's Clean Architecture + SOLID and Eric Evans' Domain-Driven Design. Used to interrogate software designs before building.

---

## Progress

See [`PROGRESS.md`](PROGRESS.md) for the full week-by-week learning log.
