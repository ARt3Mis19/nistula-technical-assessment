# =============================================================================
# classifier.py — Assigns a query type to every incoming guest message
#
# Approach: keyword scoring, not ML.
# Why: transparent (you can see exactly why a decision was made),
#      fast (no model to load), and editable without touching logic.
#
# How it works:
#   Each category has keywords with weights. The message is lowercased
#   and scored against every category. Highest total score wins.
#   Weight 3.0 = near-certain signal. Weight 0.5 = weak hint.
# =============================================================================

from .models import QueryType


# -- Keyword signal map -------------------------------------------------------
# To add a new keyword: add it to the right category with a weight.
# To add a new category: add a new key here — nothing else needs changing.
# Complaint weights are highest because missing a complaint is the worst failure.

CATEGORY_SIGNALS: dict[str, dict[str, float]] = {

    "complaint": {
        "not working": 3.0, "broken": 2.5, "unacceptable": 3.0,
        "refund": 3.0, "unhappy": 2.5, "disappointed": 2.5,
        "no hot water": 3.0, "no power": 2.5, "not clean": 2.5,
        "want my money back": 3.0, "issue": 1.5, "problem": 1.5,
    },

    "pre_sales_availability": {
        "available": 2.5, "availability": 2.5, "book": 1.5,
        "dates": 2.0, "nights": 1.5, "vacancy": 2.0,
        "from": 0.5, "to": 0.5,  # weak — common words, but hint at date ranges
    },

    "pre_sales_pricing": {
        "rate": 2.5, "price": 2.5, "how much": 2.5, "cost": 2.0,
        "per night": 2.5, "inr": 2.0, "charge": 2.0, "adults": 1.5,
    },

    "post_sales_checkin": {
        "wifi": 3.0, "wi-fi": 3.0, "password": 2.5,   # wifi is a near-certain signal
        "check in": 2.5, "check-in": 2.5, "checkin": 2.5,
        "check out": 2.0, "arrival": 1.5, "time": 0.8,
    },

    "special_request": {
        "early check": 2.5, "late check": 2.5, "airport": 2.0,
        "transfer": 2.0, "pickup": 2.0, "chef": 2.0,
        "birthday": 1.5, "anniversary": 1.5, "arrange": 1.5,
    },

    "general_enquiry": {
        "pets": 2.5, "parking": 2.5, "pool": 1.5,
        "amenities": 2.0, "beach": 1.5, "do you": 1.0,
        "is there": 1.0, "can we": 1.0,
    },
}


# -- Classifier ---------------------------------------------------------------

def classify_query(message: str) -> tuple[QueryType, float]:
    """
    Returns (query_type, classifier_confidence).

    Confidence logic:
      Blends two factors — absolute score strength and margin over runner-up.
        score_factor  = top_score / 8.0  (how many keywords matched)
        margin_factor = margin / 6.0     (how far ahead of 2nd place)
      final = 0.6 * score_factor + 0.4 * margin_factor, clamped to 0.40–0.99

    A clear unambiguous message scores high on both → high confidence.
    A vague or mixed message scores low on margin → lower confidence.
    """
    text   = message.lower()
    scores = {cat: 0.0 for cat in CATEGORY_SIGNALS}

    # Add up weights for every keyword that appears in the message
    for category, signals in CATEGORY_SIGNALS.items():
        for keyword, weight in signals.items():
            if keyword in text:
                scores[category] += weight

    ranked       = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_cat, top = ranked[0]
    second       = ranked[1][1] if len(ranked) > 1 else 0.0

    # Nothing matched at all → default to general_enquiry with low confidence
    if top == 0.0:
        return "general_enquiry", 0.55

    margin     = top - second
    confidence = min(1.0, (top / 8.0) * 0.6 + (margin / 6.0) * 0.4)
    confidence = round(max(0.40, min(0.99, confidence)), 4)

    return top_cat, confidence  # type: ignore[return-value]