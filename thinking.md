# Part 3 — Thinking Questions

**Scenario:** It is 3am. A guest at Villa B1 sends a WhatsApp message:
> "There is no hot water and we have guests arriving for breakfast in 4 hours. This is unacceptable. I want a refund for tonight."

---

## Question A — The Immediate Response

**Message sent by the AI at 3am:**

> Hi [Guest Name], I'm really sorry — I completely understand how stressful this is, especially with guests arriving in just a few hours. This is not the experience we want for you at all.
>
> I've already alerted our caretaker and the property team right now, and someone will be in touch with you within the next 15 minutes to fix this tonight.
>
> We will absolutely make this right. Please hold tight — help is on the way.

**Why this wording:**
The message does three things immediately: it validates the guest's frustration without being defensive, it gives a concrete next step with a real time commitment (15 minutes), and it signals accountability without making a financial promise the AI has no authority to keep. Saying "we will make this right" keeps the refund conversation open for a human to handle, while the guest feels heard and helped right now — at 3am when they are most anxious.

---

## Question B — The System Design

Beyond sending the message, the platform should trigger the following sequence automatically:

1. **Classify and flag as complaint + urgent** — The message is routed with `action: escalate` and tagged `urgent` because it mentions a time constraint ("4 hours"). Confidence is capped at 0.55 so no auto-send happens without human sign-off on the resolution.

2. **Notify the caretaker immediately** — An automated WhatsApp or SMS is sent to the Villa B1 caretaker with the guest's name, the issue, and a prompt to call the guest within 15 minutes.

3. **Notify the on-call supervisor** — A push notification and SMS goes to the Nistula duty manager with the full message, booking ref, and a link to the conversation thread.

4. **Log everything** — The inbound message, the AI reply, the caretaker alert, and the supervisor notification are all written to the `messages` and `conversations` tables with timestamps, so there is a complete audit trail.

5. **Start a 30-minute escalation timer** — If no agent or caretaker marks the issue as "acknowledged" in the platform within 30 minutes, the system escalates automatically: it sends a second alert to the supervisor's personal number and flags the conversation as `critical` in the dashboard.

6. **If still no response after 45 minutes** — The system sends the guest a follow-up message: *"We're still working on reaching our team. I want to assure you this is our top priority right now."* This stops the guest from feeling abandoned.

---

## Question C — The Learning

This is the third hot water complaint at Villa B1 in two months. The system should stop treating it as a one-off and start treating it as a property maintenance pattern.

**What the system should do now:**
- Automatically tag all three incidents with a shared label: `hot_water_villa_b1`
- Generate a maintenance alert and send it to the property manager: *"Villa B1 has had 3 hot water complaints in 60 days. Preventive inspection recommended before next check-in."*
- Log the pattern in a `property_issues` table with frequency, dates, and affected booking refs

**What I would build to prevent a fourth complaint:**

1. **Automated pre-stay maintenance checklist** — Before every check-in, the caretaker receives a checklist that includes a hot water verification item. They must confirm it via the platform before the check-in is marked ready. If they don't, the duty manager is notified.

2. **Pattern detection job** — A scheduled job (runs nightly) queries the `messages` table for complaints with similar `query_type = complaint` and keywords grouped by `property_id`. If the same issue appears 2+ times in 60 days, it triggers a maintenance escalation automatically — no human needs to spot the pattern manually.

3. **Guest compensation tracking** — Each complaint incident is linked to the reservation so the finance team can see if the same property is generating repeat refund requests. This creates accountability at the property level and makes the business cost of deferred maintenance visible.

The goal is to move from reactive (fix it when a guest complains at 3am) to proactive (the system already knows there is a pattern and has triggered an inspection before the next guest arrives).
