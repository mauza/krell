-- Entities table for people, places, things
CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL CHECK(type IN ('person', 'place', 'thing')),
    name TEXT NOT NULL,
    description TEXT,
    metadata TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type);
CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);

-- Events table
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    event_date TIMESTAMP,
    participants TEXT,
    location TEXT,
    metadata TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_events_date ON events(event_date DESC);

-- New journals table (replaces journal_entries)
CREATE TABLE IF NOT EXISTS journals (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    related_entities TEXT,
    related_event_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (related_event_id) REFERENCES events(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_journals_created ON journals(created_at DESC);

-- Updated ratings table
CREATE TABLE IF NOT EXISTS ratings_new (
    id TEXT PRIMARY KEY,
    target_type TEXT NOT NULL CHECK(target_type IN ('entity', 'event')),
    target_id TEXT NOT NULL,
    category TEXT NOT NULL,
    score INTEGER NOT NULL CHECK(score >= 1 AND score <= 5),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ratings_target ON ratings_new(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_ratings_category ON ratings_new(category);

-- Migrate existing journal_entries to journals
INSERT INTO journals (id, content, created_at)
SELECT id, content, created_at FROM journal_entries;

-- Migrate existing ratings to ratings_new
-- Existing ratings don't have target_type/target_id, so we'll create generic entities for them
INSERT INTO ratings_new (id, target_type, target_id, category, score, notes, created_at)
SELECT 
    id,
    'entity' as target_type,
    id as target_id,
    category,
    score,
    notes,
    created_at
FROM ratings;

-- Drop old tables
DROP TABLE IF EXISTS journal_entries;
DROP TABLE IF EXISTS ratings;

-- Rename new ratings table
ALTER TABLE ratings_new RENAME TO ratings;
