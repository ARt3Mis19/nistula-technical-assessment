# Nistula — Guest Message Handler

A FastAPI backend that receives guest messages from multiple channels, classifies them, and uses Claude AI to draft contextual replies.

---

## Project Structure

```
nistula-assessment/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI app + webhook endpoint
│   ├── models.py        # Pydantic schemas (input / normalised / response)
│   ├── classifier.py    # Keyword-weighted query classifier
│   ├── claude_client.py # Claude API integration
│   └── property_data.py # Mock property context store
├── run.py               # Server entry point
├── test_webhook.py      # 3-scenario test script
├── requirements.txt
├── .env.example
└── README.md
```

---

## Setup & Run

### 1. Clone and install

```bash
git clone https://github.com/your-username/nistula-technical-assessment
cd nistula-technical-assessment
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Open .env and add your Anthropic API key
```

### 3. Start the server

```bash
python run.py
# Server runs at http://localhost:8000
# Interactive docs at http://localhost:8000/docs
```

### 4. Run the test suite

```bash
# In a second terminal
python test_webhook.py
```

---

## API Usage

### `POST /webhook/message`

**Request**
```json
{
  "source": "whatsapp",
  "guest_name": "Rahul Sharma",
  "message": "Is the villa available from April 20 to 24? What is the rate for 2 adults?",
  "timestamp": "2026-05-05T10:30:00Z",
  "booking_ref": "NIS-2024-0891",
  "property_id": "villa-b1"
}
```

**Response**
```json
{
  "message_id": "3f8a1c2d-...",
  "query_type": "pre_sales_availability",
  "drafted_reply": "Hi Rahul! Great news — Villa B1 is available from April 20–24...",
  "confidence_score": 0.91,
  "action": "auto_send"
}
```

### `GET /health`

Returns `{"status": "ok"}`.

---

## Confidence Scoring — How It Works

The final `confidence_score` is a **weighted blend of two independent signals**:

```
final_confidence = 0.5 × classifier_confidence + 0.5 × ai_confidence
```

### Signal 1 — Classifier Confidence (`classifier_confidence`)

Derived from the keyword-scoring classifier in `classifier.py`.

- Every query category has a set of keywords with weights (e.g. "wifi" = 3.0 for `post_sales_checkin`).
- The winning category's score and its margin over the runner-up determine confidence.
- A clear, unambiguous message (e.g. "what's the WiFi password?") → high classifier confidence (~0.90).
- An ambiguous or mixed message (e.g. "available and how much?") → lower confidence (~0.55–0.65).

### Signal 2 — AI Confidence (`ai_confidence`)

Claude is instructed to return a `confidence` float (0–1) alongside its reply, reflecting how completely it could answer from the property context provided.

- If the answer is directly in the property data (WiFi password, check-in time) → Claude returns ~0.95.
- If the guest asks something not in the context (e.g. nearby restaurants) → Claude returns ~0.40–0.50.

### Hard Rules

| Situation | Cap |
|---|---|
| `query_type == "complaint"` | `confidence` capped at **0.55** → always `escalate` |
| No category matched at all | Defaults to `general_enquiry` with confidence **0.55** |

### Action Routing

| Confidence | Action |
|---|---|
| ≥ 0.85 | `auto_send` |
| 0.60 – 0.84 | `agent_review` |
| < 0.60 or complaint | `escalate` |

### Why this approach?

Using two independent signals means a single point of failure cannot produce a falsely high score. A message must be *both* clearly classified *and* well-answered by Claude to reach `auto_send`. This mirrors how a human QA process works — both the routing and the content need to be correct.

---

## Supported Sources

`whatsapp` | `booking_com` | `airbnb` | `instagram` | `direct`

## Query Types

| Type | Example |
|---|---|
| `pre_sales_availability` | "Is the villa free April 20–24?" |
| `pre_sales_pricing` | "What is the rate for 2 adults, 3 nights?" |
| `post_sales_checkin` | "What time can we check in? WiFi password?" |
| `special_request` | "Can you arrange an airport pickup?" |
| `complaint` | "The AC is broken, this is unacceptable." |
| `general_enquiry` | "Do you allow pets? Is there parking?" |

---

## Error Handling

- Missing `ANTHROPIC_API_KEY` → `500` with descriptive message
- Claude API failure → `502` with details
- Invalid payload → `422` (FastAPI auto-validation)
- All unhandled exceptions caught by global handler → `500`
