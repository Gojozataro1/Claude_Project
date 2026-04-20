import json
import logging
import re

import anthropic

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a macOS system reliability and security expert. You analyze system metrics collected from a macOS machine and provide actionable, prioritized recommendations. Your output must always be valid JSON with no markdown fences or surrounding text.

ANALYSIS FRAMEWORK:
- Critical: Active security risk, imminent disk full, sustained >90% CPU/memory, disabled security features
- Warning: Performance degradation risk, security misconfiguration, bloat accumulation
- Info: Optimization opportunity, maintenance suggestion, best practice reminder

SECURITY RULES:
1. SIP disabled is always Critical
2. FileVault disabled is always Critical
3. World-readable .pem/.key/.p12/.env/id_rsa files are always Critical
4. SSH key permissions not 600/400 are Critical
5. Open ports with unknown process names are Warning

DISK RULES:
1. Any partition > 90% full is Critical
2. Any partition > 75% full is Warning
3. Trash > 1GB is Warning
4. Cache > 5GB is Warning
5. Downloads with files untouched 90+ days: Info

PERFORMANCE RULES:
1. Memory percent > 85%: Warning
2. Swap percent > 50%: Warning
3. Any background process > 20% CPU: Warning
4. Load average > number of CPU cores: Warning

STARTUP RULES:
1. More than 20 launch agents: Warning
2. High-CPU background processes at startup: Warning

OUTPUT SCHEMA — return exactly this JSON, no extra keys, no markdown:
{
  "summary": "string — 2-3 sentences describing overall system health",
  "health_score": integer from 0 to 100,
  "suggestions": [
    {
      "priority": "Critical|Warning|Info",
      "category": "Security|Disk|CPU|Memory|Startup|Network",
      "title": "string under 60 chars",
      "description": "string explaining the issue",
      "action": "string — specific terminal command or UI steps to resolve",
      "estimated_impact": "string — e.g. Free ~3GB disk space"
    }
  ]
}"""


class ClaudeAnalyzer:
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def analyze(self, scan_data: dict, mode_focus: str = "") -> dict:
        user_message = self._build_user_message(scan_data, mode_focus)
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_message}],
            )
            raw = response.content[0].text
            parsed = self._parse_response(raw)
            parsed["model_used"] = self.model
            parsed["tokens_used"] = {
                "input": response.usage.input_tokens,
                "output": response.usage.output_tokens,
                "cache_read": getattr(response.usage, "cache_read_input_tokens", 0),
                "cache_creation": getattr(response.usage, "cache_creation_input_tokens", 0),
            }
            return parsed
        except Exception as e:
            logger.error("Claude API error: %s", e)
            return self._fallback_result(str(e))

    def _build_user_message(self, scan_data: dict, mode_focus: str) -> str:
        focus_note = f"\n\nADDITIONAL FOCUS FOR THIS SCAN: {mode_focus}" if mode_focus else ""
        return (
            f"Analyze this macOS system scan collected at {scan_data.get('scan_timestamp')} "
            f"on {scan_data.get('hostname')} running macOS {scan_data.get('macos_version')}:"
            f"{focus_note}\n\n"
            f"{json.dumps(scan_data, indent=2)}\n\n"
            "Apply all rules from your analysis framework. Return only valid JSON."
        )

    def _parse_response(self, text: str) -> dict:
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Fallback: extract first JSON object
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group())
                logger.warning("Used fallback JSON extraction from Claude response")
                return result
            except json.JSONDecodeError:
                pass
        logger.error("Failed to parse Claude response as JSON")
        return self._fallback_result("Could not parse AI response")

    def _fallback_result(self, error: str) -> dict:
        return {
            "summary": f"AI analysis unavailable: {error}",
            "health_score": 50,
            "suggestions": [],
            "model_used": self.model,
            "tokens_used": {"input": 0, "output": 0},
            "error": error,
        }
