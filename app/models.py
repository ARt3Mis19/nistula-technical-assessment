# =============================================================================
# models.py — Data shapes for every stage of the pipeline
# Pydantic validates each shape automatically — bad data is rejected at the
# door before it reaches any logic, AI call, or database write.
# =============================================================================

from pydantic import BaseModel, Field
from typing import Literal, Optional
from datetime import datetime
import uuid


# -- Allowed string values ----------------------------------------------------
# Literal types lock down exactly which strings are valid.
# Anything outside this list (e.g. "telegram") triggers a 422 error instantly.

SourceChannel = Literal["whatsapp", "booking_com", "airbnb", "instagram", "direct"]

QueryType = Literal[
    "pre_sales_availability",  # "Is the villa free April 20–24?"
    "pre_sales_pricing",       # "What is the rate for 2 adults?"
    "post_sales_checkin",      # "What time is check-in? WiFi password?"
    "special_request",         # "Can you arrange an airport pickup?"
    "complaint",               # "The AC is broken. I want a refund."
    "general_enquiry",         # "Do you allow pets?"
]

ActionType = Literal[
    "auto_send",     # confidence >= 0.85 → safe to send without human review
    "agent_review",  # confidence 0.60–0.84 → human should verify before sending
    "escalate",      # confidence < 0.60 or complaint → human must take over
]


# -- Inbound payload ----------------------------------------------------------
# Shape of the raw JSON that arrives at POST /webhook/message.
# booking_ref and property_id are optional — pre-booking guests won't have them.

class InboundMessage(BaseModel):
    source:      SourceChannel
    guest_name:  str
    message:     str
    timestamp:   datetime
    booking_ref: Optional[str] = None
    property_id: Optional[str] = None


# -- Normalised message -------------------------------------------------------
# Every inbound message is converted into this shape before any processing.
# Keeps all downstream code channel-agnostic — it never cares if the message
# came from WhatsApp or Airbnb, it just sees one clean format.
# message_id is auto-generated here so the whole pipeline shares one trace ID.

class NormalisedMessage(BaseModel):
    message_id:   str     = Field(default_factory=lambda: str(uuid.uuid4()))
    source:       SourceChannel
    guest_name:   str
    message_text: str      # renamed from 'message' for clarity
    timestamp:    datetime
    booking_ref:  Optional[str] = None
    property_id:  Optional[str] = None
    query_type:   QueryType    # added by classifier, not present in raw input


# -- Webhook response ---------------------------------------------------------
# What we send back. The 'action' field means the caller never needs to
# re-implement threshold logic — we tell it exactly what to do.

class WebhookResponse(BaseModel):
    message_id:       str
    query_type:       QueryType
    drafted_reply:    str
    confidence_score: float      # 0.0–1.0, see claude_client.py for scoring logic
    action:           ActionType