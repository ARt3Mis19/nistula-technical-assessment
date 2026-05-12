-- ============================================================
-- Nistula Unified Messaging Platform — PostgreSQL Schema
-- Part 2 of Technical Assessment
-- ============================================================
-- Design philosophy:
--   One guest profile per real person (across all channels)
--   One messages table for every inbound/outbound message
--   Conversations group related messages for a booking
--   AI metadata stored on each inbound message row
-- ============================================================


-- ------------------------------------------------------------
-- 1. GUEST PROFILES
--    One row per real guest, regardless of which channel they
--    first contacted us from. Channels are stored as an array
--    so we can see every platform a guest has used.
-- ------------------------------------------------------------

CREATE TABLE guests (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Core identity
    full_name           VARCHAR(255) NOT NULL,
    email               VARCHAR(255) UNIQUE,                    -- nullable: WhatsApp guests may never share email
    phone               VARCHAR(30)  UNIQUE,                    -- E.164 format e.g. +919876543210

    -- Channel identifiers (one guest may contact via multiple platforms)
    whatsapp_id         VARCHAR(100) UNIQUE,
    booking_com_id      VARCHAR(100) UNIQUE,
    airbnb_id           VARCHAR(100) UNIQUE,
    instagram_handle    VARCHAR(100) UNIQUE,

    -- Channels this guest has used (e.g. ARRAY['whatsapp','airbnb'])
    channels_used       TEXT[]       NOT NULL DEFAULT '{}',

    -- Metadata
    first_contact_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    -- At least one contact method must exist
    CONSTRAINT guest_has_contact CHECK (
        email IS NOT NULL OR phone IS NOT NULL OR
        whatsapp_id IS NOT NULL OR booking_com_id IS NOT NULL OR
        airbnb_id IS NOT NULL OR instagram_handle IS NOT NULL
    )
);

-- Index for fast lookup by phone or email at message ingestion time
CREATE INDEX idx_guests_phone ON guests (phone);
CREATE INDEX idx_guests_email ON guests (email);


-- ------------------------------------------------------------
-- 2. PROPERTIES
--    Simple reference table. Keeps messages normalised —
--    we store property_id everywhere instead of repeating
--    property details in every row.
-- ------------------------------------------------------------

CREATE TABLE properties (
    id              VARCHAR(50)  PRIMARY KEY,                   -- e.g. 'villa-b1'
    name            VARCHAR(255) NOT NULL,
    location        VARCHAR(255),
    bedrooms        SMALLINT,
    max_guests      SMALLINT,
    base_rate_inr   INTEGER,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);


-- ------------------------------------------------------------
-- 3. RESERVATIONS
--    Links a guest to a property for specific dates.
--    A conversation is always tied to a reservation where
--    possible (pre-sales enquiries may not have one yet).
-- ------------------------------------------------------------

CREATE TABLE reservations (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_ref     VARCHAR(50)  UNIQUE NOT NULL,               -- e.g. 'NIS-2024-0891'
    guest_id        UUID         NOT NULL REFERENCES guests(id) ON DELETE RESTRICT,
    property_id     VARCHAR(50)  NOT NULL REFERENCES properties(id) ON DELETE RESTRICT,

    check_in        DATE         NOT NULL,
    check_out       DATE         NOT NULL,
    num_guests      SMALLINT     NOT NULL DEFAULT 1,
    total_amount_inr INTEGER,

    status          VARCHAR(30)  NOT NULL DEFAULT 'confirmed'
                    CHECK (status IN ('enquiry','confirmed','checked_in','checked_out','cancelled')),

    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT valid_dates CHECK (check_out > check_in)
);

CREATE INDEX idx_reservations_guest    ON reservations (guest_id);
CREATE INDEX idx_reservations_property ON reservations (property_id);
CREATE INDEX idx_reservations_ref      ON reservations (booking_ref);


-- ------------------------------------------------------------
-- 4. CONVERSATIONS
--    A conversation groups all messages for one guest around
--    one topic or stay. A single reservation may have multiple
--    conversations (pre-sales, then post-sales, then complaint).
-- ------------------------------------------------------------

CREATE TABLE conversations (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    guest_id        UUID         NOT NULL REFERENCES guests(id) ON DELETE CASCADE,
    reservation_id  UUID         REFERENCES reservations(id) ON DELETE SET NULL,   -- nullable for pre-sales
    property_id     VARCHAR(50)  REFERENCES properties(id) ON DELETE SET NULL,

    subject         VARCHAR(255),                               -- short human label e.g. "Check-in query Apr 20"
    status          VARCHAR(30)  NOT NULL DEFAULT 'open'
                    CHECK (status IN ('open','resolved','escalated')),

    opened_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_conversations_guest        ON conversations (guest_id);
CREATE INDEX idx_conversations_reservation  ON conversations (reservation_id);


-- ------------------------------------------------------------
-- 5. MESSAGES
--    Every inbound and outbound message across all channels
--    lives in this one table.
--
--    AI metadata columns (query_type, confidence_score, etc.)
--    are only populated for inbound messages that went through
--    the AI pipeline. Outbound rows leave them NULL.
-- ------------------------------------------------------------

CREATE TYPE message_direction  AS ENUM ('inbound', 'outbound');
CREATE TYPE source_channel     AS ENUM ('whatsapp', 'booking_com', 'airbnb', 'instagram', 'direct');
CREATE TYPE query_type_enum    AS ENUM (
    'pre_sales_availability',
    'pre_sales_pricing',
    'post_sales_checkin',
    'special_request',
    'complaint',
    'general_enquiry'
);
CREATE TYPE send_action        AS ENUM ('auto_send', 'agent_review', 'escalate');
CREATE TYPE reply_origin       AS ENUM ('ai_drafted', 'agent_edited', 'agent_written', 'auto_sent');

CREATE TABLE messages (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id     UUID            NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    guest_id            UUID            NOT NULL REFERENCES guests(id) ON DELETE CASCADE,

    -- Channel routing
    source              source_channel  NOT NULL,
    direction           message_direction NOT NULL,

    -- Content
    body                TEXT            NOT NULL,
    sent_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    -- ── AI pipeline metadata (inbound messages only) ──────────
    query_type          query_type_enum,                        -- classified category
    confidence_score    NUMERIC(4,3)                            -- 0.000 – 1.000
                        CHECK (confidence_score BETWEEN 0 AND 1),
    ai_drafted_reply    TEXT,                                   -- the raw draft Claude returned
    action_taken        send_action,                            -- what the system decided

    -- ── Reply tracking (outbound messages only) ───────────────
    reply_origin        reply_origin,                           -- how was this reply produced?
    agent_id            UUID,                                   -- which human agent sent/edited it (nullable)

    -- External message IDs from channel APIs (for dedup & threading)
    external_message_id VARCHAR(255)    UNIQUE,

    -- Soft delete support
    deleted_at          TIMESTAMPTZ
);

-- Indexes for common query patterns
CREATE INDEX idx_messages_conversation  ON messages (conversation_id);
CREATE INDEX idx_messages_guest         ON messages (guest_id);
CREATE INDEX idx_messages_sent_at       ON messages (sent_at DESC);
CREATE INDEX idx_messages_query_type    ON messages (query_type)    WHERE query_type IS NOT NULL;
CREATE INDEX idx_messages_action        ON messages (action_taken)  WHERE action_taken IS NOT NULL;
CREATE INDEX idx_messages_confidence    ON messages (confidence_score) WHERE confidence_score IS NOT NULL;


-- ------------------------------------------------------------
-- 6. AGENTS
--    Human team members who review or send messages.
--    Kept simple — extend with roles/permissions as needed.
-- ------------------------------------------------------------

CREATE TABLE agents (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(255) NOT NULL,
    email       VARCHAR(255) NOT NULL UNIQUE,
    role        VARCHAR(50)  NOT NULL DEFAULT 'agent'
                CHECK (role IN ('agent','supervisor','admin')),
    active      BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);


-- ------------------------------------------------------------
-- 7. USEFUL VIEWS
-- ------------------------------------------------------------

-- Full conversation thread with guest name and channel
CREATE VIEW conversation_feed AS
SELECT
    m.id              AS message_id,
    c.id              AS conversation_id,
    g.full_name       AS guest_name,
    m.source,
    m.direction,
    m.body,
    m.query_type,
    m.confidence_score,
    m.action_taken,
    m.reply_origin,
    m.sent_at
FROM messages m
JOIN conversations c ON c.id = m.conversation_id
JOIN guests       g ON g.id = m.guest_id
ORDER BY m.sent_at;

-- Dashboard: all inbound messages needing agent review
CREATE VIEW agent_review_queue AS
SELECT
    m.id              AS message_id,
    g.full_name       AS guest_name,
    m.source,
    m.body,
    m.query_type,
    m.confidence_score,
    m.ai_drafted_reply,
    m.sent_at
FROM messages m
JOIN guests g ON g.id = m.guest_id
WHERE m.direction   = 'inbound'
  AND m.action_taken IN ('agent_review', 'escalate')
  AND m.deleted_at IS NULL
ORDER BY m.sent_at ASC;


-- ============================================================
-- DESIGN DECISIONS
-- ============================================================
--
-- 1. GUESTS TABLE — one row per real person
--    Hardest part: a guest might WhatsApp us as "Rahul Sharma"
--    and also book on Airbnb under a slightly different name.
--    We store one nullable channel-specific ID per platform
--    (whatsapp_id, airbnb_id, etc.) so we can merge records
--    when we confirm it's the same person. Email/phone are the
--    canonical dedup keys when available.
--
-- 2. AI METADATA ON THE MESSAGES TABLE (not a separate table)
--    Keeping confidence_score, query_type, and ai_drafted_reply
--    on the messages row avoids a join for the most common
--    queries (the review queue, audit trail). The columns are
--    simply NULL for outbound messages — clean and fast.
--
-- 3. CONVERSATIONS vs MESSAGES split
--    Without conversations, you'd have to infer threads from
--    timestamps and booking_refs — fragile. A conversations
--    table lets one guest have separate threads (pre-sales
--    enquiry → post-booking → complaint) without mixing them.
--
-- 4. HARDEST DESIGN DECISION
--    Whether to store query_type and confidence_score on the
--    messages table directly, or in a separate ai_analysis
--    table. A separate table is cleaner in theory (single
--    responsibility) but in practice every agent-facing query
--    needs this data alongside the message body. The join cost
--    and added complexity outweigh the purity benefit for a
--    messaging platform at this scale. If AI analysis ever
--    becomes multi-model or versioned, splitting it out would
--    make sense — but not now.
--
-- ============================================================
