# =============================================================================
# property_data.py — Villa details passed to Claude as context
#
# Currently mock data. In production, replace get_property_context() with
# a database query — nothing else in the codebase needs to change.
# =============================================================================


# -- Property store -----------------------------------------------------------
# Keyed by property_id (matches the field in the webhook payload).
# To add a new property, add a new key here following the same structure.

PROPERTY_CONTEXT: dict[str, dict] = {
    "villa-b1": {
        "name":                 "Villa B1",
        "location":             "Assagao, North Goa",
        "bedrooms":             3,
        "max_guests":           6,
        "private_pool":         True,
        "check_in_time":        "2:00 PM",
        "check_out_time":       "11:00 AM",
        "base_rate_inr":        18000,      # per night, covers up to 4 guests
        "base_rate_guests":     4,
        "extra_guest_rate_inr": 2000,       # per extra guest per night
        "wifi_password":        "Nistula@2024",
        "caretaker_hours":      "8 AM – 10 PM",
        "chef_on_call":         True,
        "chef_note":            "Pre-booking required",
        "availability":         {"April 20-24": "Available"},
        "cancellation_policy":  "Free cancellation up to 7 days before check-in",
    }
}

# Fallback used when property_id is missing or not found in the store.
# Claude can still give a partial helpful reply instead of crashing.
GENERIC_CONTEXT = {
    "name":            "Nistula Villa",
    "check_in_time":   "2:00 PM",
    "check_out_time":  "11:00 AM",
    "caretaker_hours": "8 AM – 10 PM",
}


# -- Helpers ------------------------------------------------------------------

def get_property_context(property_id: str | None) -> dict:
    """Returns property details by ID, falls back to generic if not found."""
    if property_id and property_id in PROPERTY_CONTEXT:
        return PROPERTY_CONTEXT[property_id]
    return GENERIC_CONTEXT


def format_context_for_prompt(ctx: dict) -> str:
    """
    Converts property dict → plain text block for the Claude system prompt.
    Plain English works better in prompts than raw JSON because Claude is
    trained on human-written text, not key-value dumps.
    """
    lines = []
    for key, value in ctx.items():
        if isinstance(value, dict):
            lines.append(f"{key}:")
            for k2, v2 in value.items():
                lines.append(f"  {k2}: {v2}")
        else:
            lines.append(f"{key}: {value}")
    return "\n".join(lines)
