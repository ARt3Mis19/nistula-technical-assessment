# =============================================================================
# main.py — FastAPI app and webhook endpoint
#
# This file is the conductor — it calls each module in order and returns
# the final response. It contains no classification, AI, or data logic itself.
#
# Request flow:
#   POST /webhook/message
#     → validate payload (Pydantic, automatic)
#     → classify query type (classifier.py)
#     → normalise into unified schema (models.py)
#     → load property context (property_data.py)
#     → get Claude reply + confidence (claude_client.py)
#     → determine action from confidence score
#     → return WebhookResponse
# =============================================================================

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import logging

from .models        import InboundMessage, NormalisedMessage, WebhookResponse, ActionType
from .classifier    import classify_query
from .property_data import get_property_context, format_context_for_prompt
from .claude_client import get_claude_reply


# -- Logging ------------------------------------------------------------------
# Timestamps every step so failures can be traced without adding print statements.

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


# -- App ----------------------------------------------------------------------
# title/description populate the /docs page so anyone testing the API
# immediately understands what it does.

app = FastAPI(
    title="Nistula Guest Message Handler",
    description="Receives guest messages, classifies them, and drafts AI replies.",
    version="1.0.0",
)


# -- Action routing -----------------------------------------------------------
# Converts confidence score + query type → one of three action labels.
#
# Logic:
#   complaint         → always escalate (hard rule, ignores confidence)
#   score >= 0.85     → auto_send   (both signals were strong)
#   score 0.60–0.84   → agent_review (one signal was uncertain)
#   score < 0.60      → escalate    (system not confident enough to act)

def determine_action(confidence: float, query_type: str) -> ActionType:
    if query_type == "complaint":  return "escalate"
    if confidence >= 0.85:         return "auto_send"
    if confidence >= 0.60:         return "agent_review"
    return "escalate"


# -- Health check -------------------------------------------------------------
# Standard endpoint for load balancers and monitoring tools.

@app.get("/health", tags=["System"])
async def health():
    return {"status": "ok"}


# -- Webhook endpoint ---------------------------------------------------------

@app.post("/webhook/message", response_model=WebhookResponse, tags=["Webhook"])
async def handle_message(payload: InboundMessage):
    """
    Receive a guest message → classify → draft reply → return with action.

    Errors:
      500 — missing API key or config problem (our fault)
      502 — Claude API unreachable or failed (retry may work)
      422 — bad request payload (caller's fault)
    """
    logger.info("Received | source=%s | guest=%s | property=%s",
                payload.source, payload.guest_name, payload.property_id)

    # Step 1 — Classify
    query_type, classifier_confidence = classify_query(payload.message)
    logger.info("Classified | type=%s | conf=%.2f", query_type, classifier_confidence)

    # Step 2 — Normalise
    # Converts raw payload → internal schema. All downstream code uses this.
    normalised = NormalisedMessage(
        source=payload.source,
        guest_name=payload.guest_name,
        message_text=payload.message,
        timestamp=payload.timestamp,
        booking_ref=payload.booking_ref,
        property_id=payload.property_id,
        query_type=query_type,
    )

    # Step 3 — Load property context
    ctx_str = format_context_for_prompt(get_property_context(payload.property_id))

    # Step 4 — Call Claude
    try:
        drafted_reply, confidence_score = await get_claude_reply(
            guest_name=payload.guest_name,
            message_text=payload.message,
            query_type=query_type,
            property_context_str=ctx_str,
            classifier_confidence=classifier_confidence,
        )
    except ValueError as e:
        logger.error("Config error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error("Claude API failed: %s", e)
        raise HTTPException(status_code=502, detail=f"AI service unavailable: {e}")

    # Step 5 — Decide action
    action = determine_action(confidence_score, query_type)
    logger.info("Done | id=%s | score=%.2f | action=%s",
                normalised.message_id, confidence_score, action)

    return WebhookResponse(
        message_id=normalised.message_id,
        query_type=query_type,
        drafted_reply=drafted_reply,
        confidence_score=confidence_score,
        action=action,
    )


# -- Global error handler -----------------------------------------------------
# Catches anything not handled above and returns a clean error — never leaks
# internal stack traces to the caller.

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s: %s", request.url.path, exc)
    return JSONResponse(status_code=500,
                        content={"detail": "An unexpected error occurred."})