-- Channel posts: draft channel monitoring + publishing to public channel

CREATE TABLE IF NOT EXISTS channel_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_message_id INTEGER NOT NULL,
    draft_chat_id INTEGER NOT NULL,
    draft_text TEXT,
    media_group_id TEXT,
    media_files TEXT,
    public_message_id INTEGER,
    public_chat_id INTEGER,
    cta_buttons TEXT,
    hashtags TEXT,
    scheduled_at TEXT,
    published_at TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
