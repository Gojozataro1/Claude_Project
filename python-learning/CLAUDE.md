# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Goal

A weekly learning project building toward a **ServiceNow Incident Classifier**: fetch incidents from a ServiceNow PDI → classify them with Claude AI → using MCP so no Anthropic API credits are needed.

All phases are complete. The MCP is cloud-hosted (managed by claude.ai), not running locally — tool names prefixed with `mcp__servicenow__*` confirm this.

## Running the Scripts

```bash
# Week 2 — fetch a real incident from ServiceNow (interactive, prompts for incident number)
python3 week2_servicenow_fetcher.py

# Week 3 — classify 20 sample tickets (runs without API key in DEMO_MODE)
python3 week3_ticket_classifier.py
```

No build step, no test suite. Dependencies: `requests`, `python-dotenv`, `anthropic`.

## Environment Variables

All credentials live in `.env` (gitignored). The file has two sets of names for the same ServiceNow PDI — one for the Python scripts, one for the MCP server:

```
SNOW_INSTANCE / SERVICENOW_INSTANCE_URL  = https://dev390733.service-now.com
SNOW_USER / SERVICENOW_USERNAME          = admin
SNOW_PASS / SERVICENOW_PASSWORD          = ...
SNOW_CLIENT_ID / SERVICENOW_CLIENT_ID    = ...
SNOW_CLIENT_SECRET / SERVICENOW_CLIENT_SECRET = ...
SERVICENOW_AUTH_TYPE                     = oauth
```

## Architecture

### week2_servicenow_fetcher.py
Standalone script. OAuth 2.0 Resource Owner Password flow: POST to `/oauth_token.do` with form data → receive Bearer token → GET `/api/now/table/incident` with that token. The service account (`svc_python_integration`) has the `itil` role; the OAuth app (`python_oauth_client`) has no scope restriction so it can hit the Table API.

### week3_ticket_classifier.py
Batch classifier with a `DEMO_MODE` flag at the top (default `True`). When `True`, returns `MOCK_CLASSIFICATIONS` without calling the API — useful for iteration without spending API credits.

Key prompt engineering pattern used:
- **System prompt** → persona + strict JSON-only output format (6 fields: category, subcategory, priority, impact, confidence, reasoning)
- **User message** → 5 few-shot examples followed by the live ticket
- **temperature=0** → deterministic output for reliable classification
- **validate_classification()** → guards against malformed JSON before trusting Claude's output

The `impact` field (`High | Medium | Low`) is assessed using ITIL logic: number of users affected × criticality of the business process. Priority is derived from urgency × impact combined.

### MCP Integration
The ServiceNow MCP is cloud-hosted via claude.ai Integrations — no local config needed. The `mcp__servicenow__*` tools are available in any Claude Code session automatically. `PROGRESS.md` contains detailed notes on how MCP works vs. the CLI scripts and how to build a new MCP for other APIs.
