# =============================================================================
# claude_client.py — Sends guest messages to Claude, returns reply + score
#
# Confidence scoring logic (the core of this file):
#   final = 0.5 * classifier_confidence + 0.5 * ai_confidence
#
#   Two signals are blended so neither alone can produce a falsely high score.
#   Example: WiFi question → classifier=0.92, Claude=0.97 → final=0.95 → auto_send
#   Example: Vague question → classifier=0.55, Claude=0.40 → final=0.48 → escalate
#
#   Complaints are hard-capped at 0.55 regardless — they always escalate.
# =============================================================================

import json
import os
import httpx
from .models import QueryType

CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
MODEL          = "claude-sonnet-4-20250514"


# -- System prompt ------------------------------------------------------------
# Tells Claude who it is, what it knows, and how to behave.
# {property_context} is injected at runtime with the specific villa's details.
#
# Why ask for JSON output:
#   We need both a reply string AND a confidence float from one API call.
#   JSON lets us parse both reliably without string splitting or regex.
#   "no markdown, no extra text" stops Claude wrapping it in ```json fences.

SYSTEM_PROMPT = """
You are a warm, professional guest-relations assistant for Nistula villas.
Reply on behalf of the property team.

PROPERTY DETAILS:
{property_context}

RULES:
1. Be friendly and concise. Use the guest's first name.
2. Only use information from the property details above.
3. If something isn't covered above, say you will check and follow up.
4. For complaints: acknowledge warmly, apologise, say help is on the way. Never admit liability.

Respond with ONLY a valid JSON object — no markdown, no extra text:
{{
  "reply": "<guest-facing message>",
  "confidence": <float 0.0–1.0, how fully you answered using the context above>
}}
""".strip()


# -- Main function ------------------------------------------------------------

async def get_claude_reply(
    guest_name:            str,
    message_text:          str,
    query_type:            QueryType,
    property_context_str:  str,
    classifier_confidence: float,
) -> tuple[str, float]:
    """
    Calls Claude and returns (drafted_reply, final_confidence).

    Steps:
      1. Load API key from environment — fails fast with clear message if missing
      2. Build system prompt with property context injected
      3. POST to Claude API with 30s timeout
      4. Parse JSON response — fallback to raw text at 0.50 if parsing fails
      5. Blend classifier + AI confidence into final score
      6. Cap complaints at 0.55
    """

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set. Copy .env.example → .env and add your key.")

    system_prompt = SYSTEM_PROMPT.format(property_context=property_context_str)

    # Include query_type so Claude can match its tone to the situation
    # (availability reply reads differently from a complaint acknowledgement)
    user_message = (
        f"Guest name: {guest_name}\n"
        f"Query type: {query_type}\n"
        f"Message: {message_text}"
    )

    headers = {
        "x-api-key":         api_key,
        "anthropic-version": "2023-06-01",
        "content-type":      "application/json",
    }

    payload = {
        "model":    MODEL,
        "max_tokens": 1000,
        "system":   system_prompt,
        "messages": [{"role": "user", "content": user_message}],
    }

    # timeout=30s prevents hanging if Claude API is slow
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(CLAUDE_API_URL, headers=headers, json=payload)
        response.raise_for_status()

    raw_text = response.json()["content"][0]["text"].strip()

    # Parse Claude's JSON response
    # Fallback: if Claude ignored the JSON instruction, treat full text as reply
    # and assign 0.50 confidence so it always routes to agent_review or escalate
    try:
        parsed        = json.loads(raw_text)
        drafted_reply = parsed["reply"]
        ai_confidence = float(parsed["confidence"])
    except (json.JSONDecodeError, KeyError, ValueError):
        drafted_reply = raw_text
        ai_confidence = 0.50

    # Blend: equal weight to classifier certainty and Claude's self-assessed completeness
    final = round(0.5 * classifier_confidence + 0.5 * ai_confidence, 4)

    # Hard rule: complaints must always escalate — cap below agent_review threshold
    if query_type == "complaint":
        final = min(final, 0.55)

    return drafted_reply, final
