#!/usr/bin/env python3
"""
week5_agent.py — Self-Improving Personal Assistant
Inspired by Hermes Agent (nousresearch.com/hermes)

HOW IT WORKS (read this first):
  1. You give it a task.
  2. It searches its memory and learned skills for relevant context.
  3. It calls tools (run_python, read_file, recall_memory, etc.) in a loop.
  4. When it finishes, it REFLECTS: "Was this novel? Should I save a skill?"
  5. Next time you give a similar task, it already knows how to do it faster.

KEY DESIGN TRADEOFFS:
  Speed vs Power    → claude-haiku-4-5 is 5x cheaper/faster than Sonnet.
                      Fine for most tasks; swap MODEL below for harder ones.

  FTS5 vs Vectors   → SQLite FTS5 (full-text search) needs zero extra packages.
                      A vector DB like ChromaDB is better for fuzzy semantic
                      similarity but adds complexity. FTS5 is "good enough" for
                      a personal assistant used by one person.

  Skills as text    → Procedures are stored as plain natural-language steps,
                      not Python code. Safer (no arbitrary exec), more flexible,
                      easier to inspect and edit. Hermes uses both — we start simple.

  Reflection delay  → Self-improvement runs AFTER the response is shown to you.
                      If it ran in the middle, every task would be 20% slower.
                      Non-blocking reflection is standard in production agents.

  Single SQLite DB  → Memory + Skills + User context all in one file.
                      Easy to back up (cp agent_memory.db ~/backup/).
                      Easy to inspect: `sqlite3 agent_memory.db .tables`

USAGE:
  pip install anthropic python-dotenv
  python3 week5_agent.py

  # Or import as a module:
  from week5_agent import Agent
  agent = Agent()
  print(agent.run("What's 25 * 37?"))
"""

import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────────────────────
# CONFIG — change these to tune the agent's behavior
# ─────────────────────────────────────────────────────────────
MODEL = "claude-haiku-4-5"     # Fast + cheap. Swap to "claude-sonnet-4-6" for complex tasks.
DB_PATH = Path("agent_memory.db")
MAX_ITERATIONS = 12            # Hard cap on tool-call loops (prevents runaway agents)
MAX_MEMORY_INJECT = 5          # How many past memories to load into context per task
MAX_SKILL_INJECT = 3           # How many learned skills to load into context per task


# ─────────────────────────────────────────────────────────────
# DATABASE SETUP
# SQLite with FTS5 (full-text search) for fast memory lookup.
# Three tables: memories, skills, user_context.
# ─────────────────────────────────────────────────────────────
def init_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")  # Better for frequent writes

    conn.executescript("""
        -- Episodic memory: one row per conversation, stored forever
        CREATE TABLE IF NOT EXISTS memories (
            id      INTEGER PRIMARY KEY,
            created TEXT NOT NULL,
            task    TEXT NOT NULL,
            summary TEXT NOT NULL,
            tags    TEXT DEFAULT ''
        );

        -- FTS5 virtual table: lets us do "search WHERE text MATCH query"
        -- content= means it mirrors the memories table (no duplicate storage)
        CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
            task, summary, tags,
            content=memories,
            content_rowid=id
        );

        -- Keep FTS index in sync when rows are added/deleted
        CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
            INSERT INTO memories_fts(rowid, task, summary, tags)
            VALUES (new.id, new.task, new.summary, new.tags);
        END;
        CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, task, summary, tags)
            VALUES ('delete', old.id, old.task, old.summary, old.tags);
        END;

        -- Skills: reusable procedures the agent discovers and stores
        CREATE TABLE IF NOT EXISTS skills (
            id          INTEGER PRIMARY KEY,
            name        TEXT UNIQUE NOT NULL,
            description TEXT NOT NULL,
            procedure   TEXT NOT NULL,
            use_count   INTEGER DEFAULT 0,
            created     TEXT NOT NULL,
            updated     TEXT NOT NULL
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS skills_fts USING fts5(
            name, description, procedure,
            content=skills,
            content_rowid=id
        );

        CREATE TRIGGER IF NOT EXISTS skills_ai AFTER INSERT ON skills BEGIN
            INSERT INTO skills_fts(rowid, name, description, procedure)
            VALUES (new.id, new.name, new.description, new.procedure);
        END;
        CREATE TRIGGER IF NOT EXISTS skills_ad AFTER DELETE ON skills BEGIN
            INSERT INTO skills_fts(skills_fts, rowid, name, description, procedure)
            VALUES ('delete', old.id, old.name, old.description, old.procedure);
        END;

        -- User context: key-value facts about the user that persist forever
        -- e.g. preferred_language=Python, timezone=IST, name=Abhishek
        CREATE TABLE IF NOT EXISTS user_context (
            key     TEXT PRIMARY KEY,
            value   TEXT NOT NULL,
            updated TEXT NOT NULL
        );
    """)
    conn.commit()
    return conn


# ─────────────────────────────────────────────────────────────
# MEMORY — stores + retrieves past conversation summaries
# ─────────────────────────────────────────────────────────────
class Memory:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def save(self, task: str, summary: str, tags: str = "") -> int:
        cur = self.conn.execute(
            "INSERT INTO memories (created, task, summary, tags) VALUES (?, ?, ?, ?)",
            (datetime.now().isoformat(), task, summary, tags),
        )
        self.conn.commit()
        return cur.lastrowid

    def search(self, query: str, limit: int = MAX_MEMORY_INJECT) -> list[dict]:
        """FTS5 full-text search. Relevance-ranked by SQLite's built-in BM25."""
        try:
            rows = self.conn.execute(
                """SELECT m.id, m.created, m.task, m.summary
                   FROM memories m
                   JOIN memories_fts f ON m.id = f.rowid
                   WHERE memories_fts MATCH ?
                   ORDER BY rank LIMIT ?""",
                (query, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            # FTS MATCH can throw on special characters — fall back to recent
            rows = []
        return [{"id": r[0], "created": r[1], "task": r[2], "summary": r[3]} for r in rows]

    def recent(self, limit: int = 5) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, created, task, summary FROM memories ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [{"id": r[0], "created": r[1], "task": r[2], "summary": r[3]} for r in rows]

    def format_for_prompt(self, memories: list[dict]) -> str:
        if not memories:
            return "(none)"
        return "\n".join(
            f"[{m['created'][:10]}] {m['task']}\n  → {m['summary']}" for m in memories
        )


# ─────────────────────────────────────────────────────────────
# SKILL STORE — learned procedures that improve over time
#
# Self-improvement loop (the Hermes insight):
#   After every task, the agent reflects and asks:
#   "Was this non-obvious? Could it be reused?" → saves/updates a skill.
#   The skill is injected into context on future similar tasks,
#   so the agent does it right without re-deriving the steps.
# ─────────────────────────────────────────────────────────────
class SkillStore:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def save(self, name: str, description: str, procedure: str) -> bool:
        """Upsert a skill. Returns True if new, False if updated."""
        now = datetime.now().isoformat()
        existing = self.conn.execute(
            "SELECT id FROM skills WHERE name = ?", (name,)
        ).fetchone()

        if existing:
            self.conn.execute(
                "UPDATE skills SET description=?, procedure=?, updated=?, use_count=use_count+1 WHERE name=?",
                (description, procedure, now, name),
            )
            self.conn.commit()
            return False

        self.conn.execute(
            "INSERT INTO skills (name, description, procedure, created, updated) VALUES (?,?,?,?,?)",
            (name, description, procedure, now, now),
        )
        self.conn.commit()
        return True

    def search(self, query: str, limit: int = MAX_SKILL_INJECT) -> list[dict]:
        try:
            rows = self.conn.execute(
                """SELECT s.name, s.description, s.procedure, s.use_count
                   FROM skills s
                   JOIN skills_fts f ON s.id = f.rowid
                   WHERE skills_fts MATCH ?
                   ORDER BY rank LIMIT ?""",
                (query, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []
        return [{"name": r[0], "description": r[1], "procedure": r[2], "use_count": r[3]} for r in rows]

    def list_all(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT name, description, use_count FROM skills ORDER BY use_count DESC"
        ).fetchall()
        return [{"name": r[0], "description": r[1], "use_count": r[2]} for r in rows]

    def format_for_prompt(self, skills: list[dict]) -> str:
        if not skills:
            return "(none)"
        return "\n\n".join(
            f"SKILL [{s['name']}] — {s['description']}\n{s['procedure']}" for s in skills
        )


# ─────────────────────────────────────────────────────────────
# USER CONTEXT — persistent facts about this specific user
# ─────────────────────────────────────────────────────────────
class UserContext:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def set(self, key: str, value: str):
        self.conn.execute(
            "INSERT OR REPLACE INTO user_context (key, value, updated) VALUES (?,?,?)",
            (key, value, datetime.now().isoformat()),
        )
        self.conn.commit()

    def get_all(self) -> dict:
        rows = self.conn.execute("SELECT key, value FROM user_context").fetchall()
        return {r[0]: r[1] for r in rows}

    def format_for_prompt(self) -> str:
        ctx = self.get_all()
        if not ctx:
            return "(none yet — use save_note to remember things about the user)"
        return "\n".join(f"- {k}: {v}" for k, v in ctx.items())


# ─────────────────────────────────────────────────────────────
# TOOLS — what the agent can do
#
# These are declared as JSON schemas (the Claude API format).
# Each tool has: name, description (tells Claude when to use it),
# and input_schema (what parameters it takes).
# ─────────────────────────────────────────────────────────────
TOOL_DEFINITIONS = [
    {
        "name": "recall_memory",
        "description": (
            "Search your episodic memory for past conversations relevant to the current task. "
            "Call this at the start of any task that might relate to previous work or context."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keywords to search for in memory"}
            },
            "required": ["query"],
        },
    },
    {
        "name": "save_note",
        "description": (
            "Permanently save an important fact, preference, or piece of information about the user. "
            "Use this whenever the user tells you something about themselves, their preferences, "
            "or their context (e.g. 'I prefer Python', 'I'm in IST timezone', 'My project is X')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "Short identifier, e.g. 'preferred_language', 'timezone', 'name'",
                },
                "value": {"type": "string", "description": "The value to store"},
            },
            "required": ["key", "value"],
        },
    },
    {
        "name": "list_skills",
        "description": "Show all learned skills and procedures you have acquired over time.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "run_python",
        "description": (
            "Execute Python code in a subprocess and return its stdout. "
            "Use for: math, data processing, file operations, API calls, anything requiring computation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python code to run"},
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default 15)",
                    "default": 15,
                },
            },
            "required": ["code"],
        },
    },
    {
        "name": "read_file",
        "description": "Read the text contents of a file on disk.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute or relative file path"}
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write text content to a file on disk (creates parent directories if needed).",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to write"},
                "content": {"type": "string", "description": "Text content to write"},
            },
            "required": ["path", "content"],
        },
    },
]


def execute_tool(
    name: str,
    inputs: dict,
    memory: Memory,
    skills: SkillStore,
    user_ctx: UserContext,
) -> str:
    """Dispatch a tool call to its implementation. Returns a string result."""

    if name == "recall_memory":
        results = memory.search(inputs["query"])
        return memory.format_for_prompt(results) if results else "No relevant memories found."

    if name == "save_note":
        user_ctx.set(inputs["key"], inputs["value"])
        return f"Saved: {inputs['key']} = {inputs['value']}"

    if name == "list_skills":
        all_skills = skills.list_all()
        if not all_skills:
            return "No skills learned yet. Complete a few tasks and they'll appear here."
        return "\n".join(
            f"  • {s['name']} (used {s['use_count']}x): {s['description']}" for s in all_skills
        )

    if name == "run_python":
        timeout = inputs.get("timeout", 15)
        try:
            result = subprocess.run(
                [sys.executable, "-c", inputs["code"]],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode != 0:
                return f"Error (exit {result.returncode}):\n{result.stderr.strip()}"
            return result.stdout.strip() or "(ran successfully, no output)"
        except subprocess.TimeoutExpired:
            return f"Error: timed out after {timeout}s"
        except Exception as e:
            return f"Error: {e}"

    if name == "read_file":
        try:
            return Path(inputs["path"]).read_text(encoding="utf-8")
        except FileNotFoundError:
            return f"File not found: {inputs['path']}"
        except Exception as e:
            return f"Error: {e}"

    if name == "write_file":
        try:
            p = Path(inputs["path"])
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(inputs["content"], encoding="utf-8")
            return f"Written {len(inputs['content'])} chars to {inputs['path']}"
        except Exception as e:
            return f"Error: {e}"

    return f"Unknown tool: {name}"


# ─────────────────────────────────────────────────────────────
# SELF-REFLECTION — the core of Hermes-style self-improvement
#
# After every task, the agent calls the LLM a second time and asks:
#   "Was this novel? Should it be a reusable skill?"
#   "Did I learn any facts about the user?"
#   "How should I summarize this for future recall?"
#
# This is the "closed learning loop":
#   Task → Agent loop → Response → Reflect → Save skill/memory → Next task
#
# TRADEOFF: one extra LLM call per task (small, ~200 tokens).
# Cost: ~$0.0001 per reflection at Haiku pricing. Worth it.
# ─────────────────────────────────────────────────────────────
_REFLECTION_PROMPT = """\
You just completed a task. Review the conversation and extract structured learning.

Respond with ONLY valid JSON (no markdown fences, no extra text):
{{
  "memory_summary": "One sentence: what was accomplished",
  "memory_tags": "space separated keywords for future search",
  "save_skill": true,
  "skill": {{
    "name": "snake_case_name_under_40_chars",
    "description": "One sentence: what this skill does",
    "procedure": "1. First step\\n2. Second step\\n3. Third step"
  }},
  "user_facts": {{
    "key": "value"
  }}
}}

Rules:
- Set save_skill=true only if the task required multiple non-obvious steps that would be useful to repeat
- Set save_skill=false for simple Q&A, lookups, or one-liners
- user_facts: only facts explicitly stated or clearly implied by the user — not guesses
- If save_skill=false, the "skill" field can be null
- If no user facts were revealed, user_facts can be an empty object {{}}

Task: {task}
"""


def _reflect(
    client: anthropic.Anthropic,
    task: str,
    messages: list,
    memory: Memory,
    skills: SkillStore,
    user_ctx: UserContext,
    verbose: bool,
) -> None:
    """Post-task reflection. Saves memory, optional skill, optional user facts."""

    # Condense the conversation to last 10 messages to keep token cost low
    snippet = "\n".join(
        f"{m['role'].upper()}: "
        + (m["content"] if isinstance(m["content"], str) else json.dumps(m["content"])[:300])
        for m in messages[-10:]
    )

    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=600,
            messages=[
                {
                    "role": "user",
                    "content": _REFLECTION_PROMPT.format(task=task)
                    + f"\n\nConversation snippet:\n{snippet}",
                }
            ],
        )

        raw = resp.content[0].text.strip()
        # Strip accidental markdown fences
        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json").strip()

        data = json.loads(raw)

        # 1. Always save an episodic memory
        memory.save(
            task,
            data.get("memory_summary", task),
            data.get("memory_tags", ""),
        )

        # 2. Optionally save a new/improved skill
        if data.get("save_skill") and data.get("skill"):
            s = data["skill"]
            if s and s.get("name") and s.get("procedure"):
                is_new = skills.save(s["name"], s["description"], s["procedure"])
                if verbose:
                    status = "New skill learned" if is_new else "Skill improved"
                    print(f"\n[reflect] {status}: {s['name']}")

        # 3. Save any user facts
        for k, v in data.get("user_facts", {}).items():
            if k and v:
                user_ctx.set(str(k), str(v))

    except json.JSONDecodeError:
        # Bad JSON from LLM — save bare-minimum memory and move on
        memory.save(task, task)
        if verbose:
            print("[reflect] Could not parse reflection JSON — saved bare memory")
    except Exception as e:
        memory.save(task, task)
        if verbose:
            print(f"[reflect] Error (non-fatal): {e}")


# ─────────────────────────────────────────────────────────────
# AGENT — the main orchestration class
# ─────────────────────────────────────────────────────────────
class Agent:
    """
    A self-improving personal assistant.

    The agent loop (each task):
      1. Search memory + skills for relevant context
      2. Build a system prompt injecting that context
      3. Call Claude with tools available
      4. Execute tool calls, loop until end_turn
      5. Reflect: save memory, maybe save skill, save user facts

    Over time, the agent becomes personalized to you and gains
    reusable procedures — without any manual configuration.
    """

    def __init__(self, db_path: Path = DB_PATH, verbose: bool = True):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "ANTHROPIC_API_KEY not found. Add it to your .env file or export it."
            )
        self.client = anthropic.Anthropic(api_key=api_key)
        self.conn = init_db(db_path)
        self.memory = Memory(self.conn)
        self.skills = SkillStore(self.conn)
        self.user_ctx = UserContext(self.conn)
        self.verbose = verbose

    def _build_system(self, task: str) -> str:
        mem = self.memory.search(task)
        skl = self.skills.search(task)
        ctx = self.user_ctx.format_for_prompt()
        return f"""You are a personal AI assistant that grows more capable the longer you work with this user.
You have persistent memory, learned skills, and deep context about who this user is.

## User context (permanent facts you know about this user)
{ctx}

## Relevant past memories
{self.memory.format_for_prompt(mem)}

## Relevant skills you've learned
{self.skills.format_for_prompt(skl)}

## How to behave
- At the start of any non-trivial task, call recall_memory to surface relevant past work
- When the user mentions a preference, fact, or context about themselves, call save_note immediately
- Use run_python for any calculation, data work, or file processing
- Apply relevant skills from memory — don't re-derive what you already know
- Be concise and direct; you know this user's history so skip unnecessary preamble"""

    def run(self, task: str) -> str:
        """
        Run a single task through the full agent loop.
        Returns the final assistant response as a string.
        """

        if self.verbose:
            relevant_mem = len(self.memory.search(task))
            relevant_skills = len(self.skills.search(task))
            print(f"[agent] {relevant_mem} memories, {relevant_skills} skills relevant")

        system = self._build_system(task)
        messages = [{"role": "user", "content": task}]
        final_text = ""

        for i in range(MAX_ITERATIONS):
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=2048,
                system=system,
                tools=TOOL_DEFINITIONS,
                messages=messages,
            )

            # Collect any text in this response
            text_parts = [b.text for b in response.content if hasattr(b, "text") and b.text]
            if text_parts:
                final_text = "\n".join(text_parts)

            if response.stop_reason == "end_turn":
                break

            if response.stop_reason == "tool_use":
                # Append assistant turn (may contain text + tool_use blocks)
                messages.append({"role": "assistant", "content": response.content})

                # Execute every tool call and collect results
                results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    if self.verbose:
                        print(f"[tool]  {block.name}({json.dumps(block.input)[:100]})")
                    output = execute_tool(
                        block.name, block.input, self.memory, self.skills, self.user_ctx
                    )
                    if self.verbose:
                        print(f"        → {output[:120]}")
                    results.append(
                        {"type": "tool_result", "tool_use_id": block.id, "content": output}
                    )

                messages.append({"role": "user", "content": results})

        # Reflect after the response — non-blocking from the user's perspective
        _reflect(self.client, task, messages, self.memory, self.skills, self.user_ctx, self.verbose)

        return final_text


# ─────────────────────────────────────────────────────────────
# MAIN — interactive CLI
# ─────────────────────────────────────────────────────────────
def main():
    print("━" * 58)
    print("  Self-Improving Personal Assistant (Hermes-inspired)")
    print(f"  Model: {MODEL}  |  DB: {DB_PATH}")
    print("  Commands: 'skills'  'memories'  'quit'")
    print("━" * 58)

    agent = Agent(verbose=True)

    recent = agent.memory.recent(3)
    if recent:
        print("\nLast 3 sessions:")
        for m in recent:
            print(f"  [{m['created'][:10]}] {m['task'][:60]}")
    print()

    while True:
        try:
            task = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nBye!")
            break

        if not task:
            continue

        if task.lower() in ("quit", "exit", "q"):
            break

        if task.lower() == "skills":
            skills = agent.skills.list_all()
            if not skills:
                print("  No skills learned yet.")
            else:
                for s in skills:
                    print(f"  [{s['use_count']}x] {s['name']}: {s['description']}")
            continue

        if task.lower() == "memories":
            mems = agent.memory.recent(10)
            for m in mems:
                print(f"  [{m['created'][:10]}] {m['task'][:50]} — {m['summary'][:60]}")
            continue

        answer = agent.run(task)
        print(f"\nAssistant: {answer}\n")


if __name__ == "__main__":
    main()
