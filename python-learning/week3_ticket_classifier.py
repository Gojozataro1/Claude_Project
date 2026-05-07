# ============================================================
# WEEK 3 PROJECT: Intelligent Ticket Classifier
# ============================================================
# CONCEPTS COVERED:
#   1. System prompts vs user prompts — when to use each
#   2. Few-shot prompting — giving examples inside the prompt
#   3. Structured output — asking Claude to respond in JSON
#   4. Temperature and max_tokens — what they control
#   5. Chain of thought — asking the model to reason step by step
#
# HOW TO RUN:
#   python3 week3_ticket_classifier.py
#
# TO RUN WITH REAL CLAUDE (when you have an API key):
#   Add to your .env file:   ANTHROPIC_API_KEY=sk-ant-...
#   Set DEMO_MODE = False below
# ============================================================

import os
import json
import anthropic
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────────────────────
# DEMO_MODE = True  → runs without API key, shows mock output
# DEMO_MODE = False → calls real Claude API (needs API key in .env)
# ─────────────────────────────────────────────────────────────
DEMO_MODE = True


# ─────────────────────────────────────────────────────────────
# CONCEPT 1: SYSTEM PROMPT
# ─────────────────────────────────────────────────────────────
#
# The system prompt is like the "job description" you give Claude
# BEFORE the conversation starts. It shapes how Claude behaves
# for the ENTIRE session.
#
# Rule of thumb:
#   system prompt → who Claude IS, rules it must follow, output format
#   user prompt   → the actual data you want Claude to process
#
# Think of it like hiring a contractor:
#   system = the contract (skills required, deliverable format)
#   user   = each individual work request

SYSTEM_PROMPT = """You are a ITSM (IT Service Management) expert with 15+ years
of experience triaging incidents/major incidents at a banking company. You have deep expertise in
ServiceNow Incident management and ITIL v4.0 best practices.

Your job: classify IT support tickets into categories, assess priority and impact.

RULES YOU MUST FOLLOW:
1. Respond with valid JSON only — no text before or after the JSON
2. Use exactly these 6 fields (no more, no less)
3. Confidence must be a decimal between 0.0 and 1.0
4. Think through your reasoning before assigning priority — accuracy matters for this use urgency and impact as the parameters

OUTPUT FORMAT (use this exactly):
{
  "category": "Hardware | Software | Network | Security | Access | Other",
  "subcategory": "<specific area — e.g. VPN, Email, Laptop, Password>",
  "priority": "1 | 2 | 3 | 4",
  "impact": "High | Medium | Low",
  "confidence": 0.95,
  "reasoning": "<one/two sentence explaining your classification decision>"
}

PRIORITY GUIDE:
  1 = Critical : business stopped, many users affected, revenue at risk
  2 = High     : significant impact, key service degraded or single user blocked
  3 = Medium   : moderate impact, workaround exists, normal SLA applies
  4 = Low      : minor issue, cosmetic problem, or routine request"""


# ─────────────────────────────────────────────────────────────
# CONCEPT 2: FEW-SHOT PROMPTING
# ─────────────────────────────────────────────────────────────
#
# Instead of just describing what you want, SHOW Claude examples.
# "Few-shot" means giving a few example input→output pairs.
#
# Why it works:
#   Zero examples → Claude guesses the format
#   5 examples    → Claude learns the exact pattern you want
#
# Where to put examples: in the USER message (not system),
# right before the actual ticket you want classified.
#
# The examples below are your 5 "training shots":

FEW_SHOT_EXAMPLES = """Here are 5 correctly classified tickets to learn from:

--- EXAMPLE 1 ---
Ticket: "My laptop won't start after installing the Windows update last night"
Classification: {"category": "Software", "subcategory": "Operating System", "priority": "2", "impact": "Low", "confidence": 0.95, "reasoning": "OS update caused system failure on a single machine — high urgency as user is completely blocked, but impact is low as only one user is affected"}

--- EXAMPLE 2 ---
Ticket: "Printer on floor 3 keeps jamming and won't print any documents"
Classification: {"category": "Hardware", "subcategory": "Printer", "priority": "4", "impact": "Low", "confidence": 0.98, "reasoning": "Physical hardware issue with a single shared device — email is a workaround and business impact is low"}

--- EXAMPLE 3 ---
Ticket: "Entire sales team cannot connect to VPN from home — CRM is inaccessible"
Classification: {"category": "Network", "subcategory": "VPN", "priority": "1", "impact": "High", "confidence": 0.97, "reasoning": "Critical outage affecting the entire sales team and blocking revenue-generating CRM operations — high urgency and high impact"}

--- EXAMPLE 4 ---
Ticket: "I received an alert that someone logged into my account from Russia at 3am"
Classification: {"category": "Security", "subcategory": "Account Compromise", "priority": "1", "impact": "High", "confidence": 0.99, "reasoning": "Active account compromise poses a high risk of lateral movement across banking systems — immediate lockdown and investigation required"}

--- EXAMPLE 5 ---
Ticket: "New hire Michael Chen needs access to the HR portal and payroll system"
Classification: {"category": "Access", "subcategory": "User Provisioning", "priority": "3", "impact": "Low", "confidence": 0.96, "reasoning": "Standard onboarding access request affecting one user — follows normal SLA with no urgency or broad business impact"}

---
Now classify this ticket using the exact same JSON format. Return JSON only:"""


# ─────────────────────────────────────────────────────────────
# 20 SAMPLE SERVICENOW TICKETS
# ─────────────────────────────────────────────────────────────
# Realistic tickets covering all categories and priority levels.
# In a real project, you would fetch these from ServiceNow using
# the OAuth code from week2_servicenow_fetcher.py

SAMPLE_TICKETS = [
    "My Outlook email stopped syncing after the Office 365 update this morning",          # Software / Email / P2
    "The main database server is down — all customer-facing applications are offline",     # Software / Database / P1
    "Laptop screen has a crack after it was dropped, need a replacement",                  # Hardware / Laptop / P3
    "Cannot access the company SharePoint intranet site from any browser",                 # Network / Intranet / P2
    "New employee Lisa Park needs a laptop provisioned and all standard software access",  # Access / Onboarding / P3
    "Ransomware alert triggered on workstation WS-0042 in the accounting department",      # Security / Malware / P1
    "WiFi in conference room B drops connection every 10 minutes during meetings",         # Network / WiFi / P3
    "Need to install Adobe Acrobat Pro on my MacBook for PDF editing",                    # Software / Installation / P4
    "Keyboard is not working — several keys are stuck and unresponsive",                  # Hardware / Keyboard / P3
    "All users in the London office cannot reach the internal HR portal since 9am",        # Network / WAN / P1
    "Forgot my Windows login password, completely locked out of my computer",              # Access / Password Reset / P2
    "The nightly automated backup job failed with error code 5003 — no backup taken",     # Software / Backup / P2
    "Mouse pointer is moving on its own when I am not touching it — possible malware",    # Security / Malware / P2
    "Printer on floor 2 is out of toner and needs a replacement cartridge",               # Hardware / Printer / P4
    "Our customer-facing public website is returning 503 Service Unavailable errors",      # Network / Web / P1
    "Need to remove all system access for contractor James Wu who left last week",         # Access / Offboarding / P2
    "Microsoft Teams video calls are freezing and dropping after 5 minutes",              # Software / Video Conf / P2
    "Dual monitor setup stopped working after desk move to a new office",                 # Hardware / Monitor / P3
    "Finance team cannot open or edit Excel files from the shared network drive",          # Software / File Share / P2
    "CEO laptop battery drains completely in under 1 hour, need urgent replacement",      # Hardware / Laptop / P2
]


# ─────────────────────────────────────────────────────────────
# MOCK RESPONSES FOR DEMO MODE
# ─────────────────────────────────────────────────────────────
# These are the realistic responses Claude would return.
# When DEMO_MODE = True, we return these instead of calling the API.
# This lets you run the full script and see all output without an API key.

MOCK_CLASSIFICATIONS = [
    {"category": "Software",  "subcategory": "Email Client",     "priority": "2", "impact": "Low",    "confidence": 0.94, "reasoning": "Email sync failure after update blocks one user's communication — high urgency but low impact as only a single user is affected"},
    {"category": "Software",  "subcategory": "Database",         "priority": "1", "impact": "High",   "confidence": 0.99, "reasoning": "All customer-facing banking apps offline — critical urgency and high impact, immediate major incident response required"},
    {"category": "Hardware",  "subcategory": "Laptop",           "priority": "3", "impact": "Low",    "confidence": 0.97, "reasoning": "Physical damage from drop affects one user — loaner device available, low impact and medium urgency"},
    {"category": "Network",   "subcategory": "Intranet Access",  "priority": "2", "impact": "Medium", "confidence": 0.88, "reasoning": "SharePoint inaccessible blocks document collaboration for multiple teams — medium impact with high urgency"},
    {"category": "Access",    "subcategory": "User Onboarding",  "priority": "3", "impact": "Low",    "confidence": 0.96, "reasoning": "Standard new hire provisioning for one user — follows normal SLA with no critical urgency or broad impact"},
    {"category": "Security",  "subcategory": "Ransomware",       "priority": "1", "impact": "High",   "confidence": 0.99, "reasoning": "Active ransomware on a banking workstation risks lateral spread across financial systems — isolate immediately and escalate to security team"},
    {"category": "Network",   "subcategory": "WiFi",             "priority": "3", "impact": "Medium", "confidence": 0.92, "reasoning": "Intermittent WiFi affects multiple meeting room users — wired connection is a workaround, medium impact"},
    {"category": "Software",  "subcategory": "Installation",     "priority": "4", "impact": "Low",    "confidence": 0.98, "reasoning": "Routine software install for one user — low urgency and low impact, schedule during next maintenance window"},
    {"category": "Hardware",  "subcategory": "Keyboard",         "priority": "3", "impact": "Low",    "confidence": 0.96, "reasoning": "Peripheral failure for one user — spare USB keyboard from IT stores is an immediate workaround"},
    {"category": "Network",   "subcategory": "WAN Connectivity", "priority": "1", "impact": "High",   "confidence": 0.98, "reasoning": "Entire London office offline since 9am — high impact major incident affecting all staff and banking operations in that site"},
    {"category": "Access",    "subcategory": "Password Reset",   "priority": "2", "impact": "Low",    "confidence": 0.99, "reasoning": "Single user locked out of workstation — high urgency to restore access, but impact limited to one person"},
    {"category": "Software",  "subcategory": "Backup System",    "priority": "2", "impact": "High",   "confidence": 0.93, "reasoning": "Failed nightly backup puts all bank data at risk of unrecoverable loss — high impact, must resolve before next backup window"},
    {"category": "Security",  "subcategory": "Malware",          "priority": "2", "impact": "Medium", "confidence": 0.91, "reasoning": "Suspicious mouse behavior suggests possible remote access trojan — medium impact with high urgency, scan and isolate immediately"},
    {"category": "Hardware",  "subcategory": "Printer",          "priority": "4", "impact": "Low",    "confidence": 0.99, "reasoning": "Routine toner replacement for one floor printer — low urgency and low impact, email is a workaround"},
    {"category": "Network",   "subcategory": "Web Server",       "priority": "1", "impact": "High",   "confidence": 0.99, "reasoning": "Public banking website returning 503 errors — high impact on customers and direct reputational and revenue risk"},
    {"category": "Access",    "subcategory": "Offboarding",      "priority": "2", "impact": "Medium", "confidence": 0.97, "reasoning": "Ex-contractor retains active system access — medium impact security risk in a banking environment, revoke promptly"},
    {"category": "Software",  "subcategory": "Video Conferencing","priority": "2", "impact": "Medium", "confidence": 0.93, "reasoning": "Teams calls failing disrupts remote collaboration across the organization — medium impact affecting multiple users"},
    {"category": "Hardware",  "subcategory": "Monitor",          "priority": "3", "impact": "Low",    "confidence": 0.95, "reasoning": "Dual monitor failure after desk move affects one user — single screen workaround available, low impact"},
    {"category": "Software",  "subcategory": "File Share",       "priority": "2", "impact": "High",   "confidence": 0.94, "reasoning": "Entire finance team blocked from shared drive — high impact on critical banking workflows, requires urgent resolution"},
    {"category": "Hardware",  "subcategory": "Laptop Battery",   "priority": "2", "impact": "Low",    "confidence": 0.96, "reasoning": "CEO laptop battery critically degraded — high urgency due to executive escalation, but impact is limited to one user"},
]


# ─────────────────────────────────────────────────────────────
# CONCEPT 3: STRUCTURED OUTPUT + JSON VALIDATION
# ─────────────────────────────────────────────────────────────
#
# We ask Claude to return JSON. But Claude is a language model —
# it could make a typo and return invalid JSON.
#
# So we VALIDATE the output with json.loads() and check that all
# required fields exist. If validation fails, we record the error
# and move on (never crash the whole batch because of one ticket).

def validate_classification(data):
    """
    Checks that the JSON from Claude has all required fields
    with correct types. Returns (True, None) or (False, error_message).
    """
    required_fields = {"category", "subcategory", "priority", "impact", "confidence", "reasoning"}
    missing = required_fields - data.keys()
    if missing:
        return False, f"Missing fields: {missing}"

    valid_categories = {"Hardware", "Software", "Network", "Security", "Access", "Other"}
    if data["category"] not in valid_categories:
        return False, f"Invalid category: {data['category']}"

    if data["priority"] not in {"1", "2", "3", "4"}:
        return False, f"Invalid priority: {data['priority']}"

    if data["impact"] not in {"High", "Medium", "Low"}:
        return False, f"Invalid impact: {data['impact']}"

    try:
        conf = float(data["confidence"])
        if not 0.0 <= conf <= 1.0:
            return False, f"Confidence out of range: {conf}"
    except (ValueError, TypeError):
        return False, f"Confidence must be a number: {data['confidence']}"

    return True, None


def classify_with_claude(client, ticket_text):
    """
    Calls the real Claude API to classify one ticket.

    CONCEPT 4: TEMPERATURE AND MAX_TOKENS
    - temperature=0  → deterministic, reproducible (essential for classification)
    - temperature=1  → creative, varied (good for writing/brainstorming)
    - max_tokens=300 → caps response length → controls cost and prevents long rambling

    CONCEPT 5: CHAIN OF THOUGHT
    - The "reasoning" field we requested in the system prompt IS chain of thought.
    - Claude explains its logic before committing to a category.
    - This makes results auditable: you can see WHY it said Priority 1.
    """
    user_message = f'{FEW_SHOT_EXAMPLES}\n\nTicket: "{ticket_text}"\nClassification:'

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",  # Cheapest + fastest — perfect for bulk tasks
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": user_message}
        ],
        temperature=0,     # 0 = same answer every time → essential for reliable classification
        max_tokens=200    # Our JSON is ~150 tokens; 300 gives headroom
    )

    raw_text = response.content[0].text.strip()
    return json.loads(raw_text)  # Raises json.JSONDecodeError if Claude returned invalid JSON


def classify_ticket(client, ticket_text, ticket_index):
    """
    Routes to real API or mock depending on DEMO_MODE.
    Wraps classification in error handling so one bad ticket
    does not crash the whole batch of 20.
    """
    try:
        if DEMO_MODE:
            return MOCK_CLASSIFICATIONS[ticket_index]
        else:
            return classify_with_claude(client, ticket_text)

    except json.JSONDecodeError as e:
        return {"error": f"Claude returned invalid JSON: {e}"}
    except anthropic.AuthenticationError:
        return {"error": "Invalid API key — check ANTHROPIC_API_KEY in your .env"}
    except anthropic.RateLimitError:
        return {"error": "Rate limit hit — add a sleep() between requests"}
    except Exception as e:
        return {"error": str(e)}


# ─────────────────────────────────────────────────────────────
# MAIN: Classify all 20 tickets and save results
# ─────────────────────────────────────────────────────────────

def main():
    mode_label = "DEMO MODE (mock responses)" if DEMO_MODE else "LIVE MODE (real Claude API)"
    print("=" * 65)
    print("  INTELLIGENT TICKET CLASSIFIER — ServiceNow Edition")
    print(f"  {mode_label}")
    print("=" * 65)

    # Set up the Anthropic client
    # In DEMO_MODE we still create the client object but never call .messages.create()
    api_key = os.environ.get("ANTHROPIC_API_KEY", "demo-key-not-used")
    client = anthropic.Anthropic(api_key=api_key)

    results = []
    errors = 0

    for i, ticket in enumerate(SAMPLE_TICKETS):
        print(f"\n[{i+1:02d}/20] Ticket: {ticket[:65]}...")

        classification = classify_ticket(client, ticket, i)

        if "error" in classification:
            print(f"       ERROR: {classification['error']}")
            errors += 1
        else:
            # CONCEPT 3: Validate the JSON structure before trusting it
            valid, error_msg = validate_classification(classification)
            if not valid:
                print(f"       VALIDATION ERROR: {error_msg}")
                errors += 1
            else:
                priority_labels = {"1": "CRITICAL", "2": "HIGH", "3": "MEDIUM", "4": "LOW"}
                p = classification["priority"]
                print(f"       Category   : {classification['category']} / {classification['subcategory']}")
                print(f"       Priority   : P{p} ({priority_labels[p]})")
                print(f"       Impact     : {classification['impact']}")
                print(f"       Confidence : {float(classification['confidence']):.0%}")
                print(f"       Reasoning  : {classification['reasoning']}")  # ← Concept 5: Chain of Thought

        results.append({"ticket": ticket, "classification": classification})

    # ─── Save full results to JSON file ───
    output_file = "ticket_classifications.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)

    print("\n" + "=" * 65)
    print(f"  Done. {len(results)} tickets processed, {errors} errors.")
    print(f"  Full results saved to: {output_file}")
    print("=" * 65)

    # ─── Summary statistics ───
    successful = [r for r in results if "error" not in r["classification"]]
    if successful:
        categories = {}
        priorities = {}
        for r in successful:
            c = r["classification"]["category"]
            p = r["classification"]["priority"]
            categories[c] = categories.get(c, 0) + 1
            priorities[p] = priorities.get(p, 0) + 1

        print("\n  CATEGORY BREAKDOWN:")
        for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
            bar = "█" * count
            print(f"    {cat:<12} {bar} ({count})")

        print("\n  PRIORITY BREAKDOWN:")
        priority_labels = {"1": "P1 Critical", "2": "P2 High", "3": "P3 Medium", "4": "P4 Low"}
        for pri in sorted(priorities.keys()):
            count = priorities[pri]
            bar = "█" * count
            print(f"    {priority_labels[pri]:<14} {bar} ({count})")

    print()
    if DEMO_MODE:
        print("  To run with real Claude AI:")
        print("  1. Get an API key at: console.anthropic.com")
        print("  2. Add to your .env:  ANTHROPIC_API_KEY=sk-ant-...")
        print("  3. Set DEMO_MODE = False at the top of this file")
        print()


if __name__ == "__main__":
    main()
