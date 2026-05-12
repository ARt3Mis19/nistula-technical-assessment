# =============================================================================
# test_webhook.py — Smoke tests for the webhook endpoint
#
# Sends three realistic messages through the full pipeline and checks that
# each response has the correct query_type, action, and a valid confidence score.
#
# Run the server first (python run.py), then in a second terminal: python test_webhook.py
# =============================================================================

import httpx
import json

BASE_URL = "http://localhost:8000"

# Three cases covering the key behaviours:
#   Test 1 — clear pre-sales query → should classify correctly and auto_send
#   Test 2 — post-booking checkin + WiFi → strong keywords, should auto_send
#   Test 3 — complaint with refund demand → must always escalate (hard rule)

TEST_CASES = [
    {
        "label":                "Test 1 — Pre-sales availability (WhatsApp)",
        "expected_query_type":  "pre_sales_pricing",
        "expected_action":      "agent_review",
        "payload": {
            "source": "whatsapp", "guest_name": "Rahul Sharma",
            "message": "Is the villa available from April 20 to 24? What is the rate for 2 adults?",
            "timestamp": "2026-05-05T10:30:00Z", "booking_ref": "NIS-2024-0891", "property_id": "villa-b1",
        },
    },
    {
        "label":                "Test 2 — Check-in + WiFi password (Airbnb)",
        "expected_query_type":  "post_sales_checkin",
        "expected_action":      "auto_send",
        "payload": {
            "source": "airbnb", "guest_name": "Priya Menon",
            "message": "Hi! We arrive tomorrow afternoon. What time can we check in and what is the WiFi password?",
            "timestamp": "2026-05-06T08:00:00Z", "booking_ref": "NIS-2024-0910", "property_id": "villa-b1",
        },
    },
    {
        "label":                "Test 3 — Complaint + refund demand (Direct)",
        "expected_query_type":  "complaint",
        "expected_action":      "escalate",  # complaints always escalate regardless of confidence
        "payload": {
            "source": "direct", "guest_name": "James Holden",
            "message": "The AC in the master bedroom is not working and it is 35 degrees. This is completely unacceptable. I want a refund for tonight.",
            "timestamp": "2026-05-06T23:45:00Z", "booking_ref": "NIS-2024-0923", "property_id": "villa-b1",
        },
    },
]


def run_tests():
    print("\n" + "=" * 60)
    print("  Nistula — Webhook Test Suite")
    print("=" * 60)

    passed, failed = 0, 0

    for i, test in enumerate(TEST_CASES, 1):
        print(f"\n{test['label']}")
        print("-" * 60)

        try:
            res = httpx.post(f"{BASE_URL}/webhook/message", json=test["payload"], timeout=30.0)
            res.raise_for_status()
            result = res.json()

            print(json.dumps(result, indent=2))

            # Checks: query type, action, non-empty reply, valid confidence range
            checks = {
                "query_type correct":    result.get("query_type")        == test["expected_query_type"],
                "action correct":        result.get("action")            == test["expected_action"],
                "reply non-empty":       bool(result.get("drafted_reply")),
                "confidence is 0–1":     0.0 <= result.get("confidence_score", -1) <= 1.0,
            }

            all_ok = True
            for name, ok in checks.items():
                print(f"  {'✓' if ok else '✗'} {name}")
                if not ok: all_ok = False

            if all_ok: passed += 1
            else:       failed += 1

        except httpx.ConnectError:
            print("  ERROR — Server not running. Start it with: python run.py")
            failed += 1
        except httpx.HTTPStatusError as e:
            print(f"  HTTP {e.response.status_code}: {e.response.text}")
            failed += 1

        print("=" * 60)

    print(f"\n  {passed} passed · {failed} failed · {len(TEST_CASES)} total\n")


if __name__ == "__main__":
    run_tests()