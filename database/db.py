"""
Krell Backend - Database Models and Setup
New schema supporting conversations, messages, journal entries, and encrypted settings

IMPORTANT: This schema requires a fresh database installation for MVP.
If you have an existing krell.db from a previous version, please back it up
and delete it before running the new backend, as there is no migration script yet.
"""

import aiosqlite
import json
import uuid
import os
from datetime import datetime
from typing import Optional, List, Dict
from pathlib import Path
from cryptography.fernet import Fernet


class Database:
    """SQLite database manager for Krell with new schema"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        # Initialize or load encryption key for settings
        self._init_encryption_key()

    def _init_encryption_key(self):
        """Initialize or load the encryption key for settings"""
        key_path = Path(self.db_path).parent / ".encryption_key"

        if key_path.exists():
            with open(key_path, "rb") as f:
                self.encryption_key = f.read()
        else:
            # Generate new key
            self.encryption_key = Fernet.generate_key()
            with open(key_path, "wb") as f:
                f.write(self.encryption_key)
            # Secure the key file
            os.chmod(key_path, 0o600)

        self.cipher = Fernet(self.encryption_key)

    async def init_db(self):
        """Initialize database schema"""
        async with aiosqlite.connect(self.db_path) as db:
            # Enable foreign key constraints
            await db.execute("PRAGMA foreign_keys = ON")
            # Conversations table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Messages table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tool_calls TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                )
            """)

            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_conversation 
                ON messages(conversation_id, timestamp)
            """)

            # Journal entries table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS journal_entries (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    entry_type TEXT NOT NULL,
                    conversation_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE SET NULL
                )
            """)

            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_journal_created 
                ON journal_entries(created_at DESC)
            """)

            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_journal_type 
                ON journal_entries(entry_type)
            """)

            # Add ratings table for scoring tool
            await db.execute("""
                CREATE TABLE IF NOT EXISTS ratings (
                    id TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    item TEXT NOT NULL,
                    score INTEGER NOT NULL CHECK(score >= 1 AND score <= 5),
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Settings table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await db.commit()

            # Initialize default settings if this is first run
            await self._init_default_settings(db)

        # Run migrations after schema initialization
        await self.run_migrations()

    async def _init_default_settings(self, db):
        """Initialize default settings on first run"""
        cursor = await db.execute("SELECT COUNT(*) FROM settings")
        count = (await cursor.fetchone())[0]

        if count == 0:
            # Add default settings
            defaults = {
                "llm_endpoint": "http://localhost:11434",
                "llm_model": "llama3.2:latest",
                "api_key": "CONFIGURE_IN_DASHBOARD",
            }

            for key, value in defaults.items():
                await db.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?)", (key, value)
                )

            await db.commit()

    async def run_migrations(self):
        """Run database migrations."""
        import os
        from pathlib import Path

        migrations_dir = Path(__file__).parent / "migrations"
        if not migrations_dir.exists():
            return

        migration_files = sorted(
            [f for f in os.listdir(migrations_dir) if f.endswith(".sql")]
        )

        async with aiosqlite.connect(self.db_path) as db:
            # Enable foreign key constraints
            await db.execute("PRAGMA foreign_keys = ON")

            for migration_file in migration_files:
                migration_path = migrations_dir / migration_file

                with open(migration_path, "r") as f:
                    migration_sql = f.read()

                # Execute migration (split by semicolon for multiple statements)
                statements = [s.strip() for s in migration_sql.split(";") if s.strip()]
                for statement in statements:
                    try:
                        await db.execute(statement)
                    except aiosqlite.OperationalError as e:
                        # Skip statements that fail due to missing tables (for fresh installs)
                        if "no such table" in str(e):
                            continue
                        raise

                await db.commit()

    # Conversation CRUD operations

    async def create_conversation(self, title: str) -> str:
        """Create a new conversation and return its ID"""
        conv_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO conversations (id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?)
            """,
                (conv_id, title, timestamp, timestamp),
            )
            await db.commit()

        return conv_id

    async def get_conversation(self, conversation_id: str) -> Optional[Dict]:
        """Get a conversation by ID"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT id, title, created_at, updated_at
                FROM conversations
                WHERE id = ?
            """,
                (conversation_id,),
            )
            row = await cursor.fetchone()

            if row:
                return dict(row)
            return None

    async def list_conversations(self, limit: int = 100) -> List[Dict]:
        """List all conversations ordered by most recent"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT id, title, created_at, updated_at
                FROM conversations
                ORDER BY updated_at DESC
                LIMIT ?
            """,
                (limit,),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def update_conversation_title(self, conversation_id: str, title: str) -> bool:
        """Update a conversation's title"""
        timestamp = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                UPDATE conversations
                SET title = ?, updated_at = ?
                WHERE id = ?
            """,
                (title, timestamp, conversation_id),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation and cascade to messages"""
        async with aiosqlite.connect(self.db_path) as db:
            # Enable foreign key constraints
            await db.execute("PRAGMA foreign_keys = ON")
            cursor = await db.execute(
                """
                DELETE FROM conversations WHERE id = ?
            """,
                (conversation_id,),
            )
            await db.commit()
            return cursor.rowcount > 0

    # Message CRUD operations

    async def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        tool_calls: Optional[List[Dict]] = None,
    ) -> str:
        """Add a message to a conversation"""
        message_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat()

        # Serialize tool_calls to JSON if provided
        tool_calls_json = None
        if tool_calls is not None:
            tool_calls_json = json.dumps(tool_calls)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO messages (id, conversation_id, role, content, tool_calls, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    message_id,
                    conversation_id,
                    role,
                    content,
                    tool_calls_json,
                    timestamp,
                ),
            )

            # Update conversation's updated_at
            await db.execute(
                """
                UPDATE conversations
                SET updated_at = ?
                WHERE id = ?
            """,
                (timestamp, conversation_id),
            )

            await db.commit()

        return message_id

    async def get_conversation_messages(self, conversation_id: str) -> List[Dict]:
        """Get all messages in a conversation"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT id, role, content, tool_calls, timestamp
                FROM messages
                WHERE conversation_id = ?
                ORDER BY timestamp ASC
            """,
                (conversation_id,),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    # Journal entry CRUD operations

    async def create_journal_entry(
        self, content: str, entry_type: str, conversation_id: Optional[str] = None
    ) -> str:
        """Create a journal entry"""
        entry_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO journal_entries (id, content, entry_type, conversation_id, created_at)
                VALUES (?, ?, ?, ?, ?)
            """,
                (entry_id, content, entry_type, conversation_id, timestamp),
            )
            await db.commit()

        return entry_id

    async def get_journal_entry(self, entry_id: str) -> Optional[Dict]:
        """Get a journal entry by ID"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT id, content, entry_type, conversation_id, created_at
                FROM journal_entries
                WHERE id = ?
            """,
                (entry_id,),
            )
            row = await cursor.fetchone()

            if row:
                return dict(row)
            return None

    async def list_journal_entries(
        self, limit: int = 50, entry_type: Optional[str] = None
    ) -> List[Dict]:
        """List journal entries with optional filtering"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            if entry_type:
                cursor = await db.execute(
                    """
                    SELECT id, content, entry_type, conversation_id, created_at
                    FROM journal_entries
                    WHERE entry_type = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """,
                    (entry_type, limit),
                )
            else:
                cursor = await db.execute(
                    """
                    SELECT id, content, entry_type, conversation_id, created_at
                    FROM journal_entries
                    ORDER BY created_at DESC
                    LIMIT ?
                """,
                    (limit,),
                )

            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def delete_journal_entry(self, entry_id: str) -> bool:
        """Delete a journal entry"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                DELETE FROM journal_entries WHERE id = ?
            """,
                (entry_id,),
            )
            await db.commit()
            return cursor.rowcount > 0

    # Rating CRUD operations

    async def create_rating(
        self,
        target_type: str,
        target_id: str,
        category: str,
        score: int,
        notes: str = None,
    ) -> str:
        """
        Create a new rating for an entity or event.

        Args:
            target_type: 'entity' or 'event'
            target_id: ID of entity or event being rated
            category: Rating category (e.g., 'meal', 'meeting', 'workout')
            score: Rating score (1-5)
            notes: Optional notes about the rating

        Returns:
            Rating ID
        """
        if target_type not in ("entity", "event"):
            raise ValueError(f"Invalid target type: {target_type}")

        if not 1 <= score <= 5:
            raise ValueError(f"Score must be between 1 and 5, got {score}")

        rating_id = str(uuid.uuid4())

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO ratings (id, target_type, target_id, category, score, notes)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (rating_id, target_type, target_id, category, score, notes),
            )
            await db.commit()

        return rating_id

    async def get_rating(self, rating_id: str) -> dict:
        """Get a rating by ID."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM ratings WHERE id = ?", (rating_id,)
            ) as cursor:
                row = await cursor.fetchone()

        if not row:
            return None

        return {
            "id": row[0],
            "target_type": row[1],
            "target_id": row[2],
            "category": row[3],
            "score": row[4],
            "notes": row[5],
            "created_at": row[6],
        }

    async def get_ratings_by_target(
        self, target_type: str, target_id: str, limit: int = 50
    ) -> dict:
        """
        Get all ratings for a specific entity or event.

        Args:
            target_type: 'entity' or 'event'
            target_id: ID of target
            limit: Maximum results to return

        Returns:
            Dict with ratings list and statistics
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT * FROM ratings
                WHERE target_type = ? AND target_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (target_type, target_id, limit),
            ) as cursor:
                rows = await cursor.fetchall()

        ratings = []
        total_score = 0

        for row in rows:
            rating = {
                "id": row[0],
                "target_type": row[1],
                "target_id": row[2],
                "category": row[3],
                "score": row[4],
                "notes": row[5],
                "created_at": row[6],
            }
            ratings.append(rating)
            total_score += row[4]

        # Calculate statistics
        stats = {
            "count": len(ratings),
            "average": round(total_score / len(ratings), 2) if ratings else 0,
        }

        return {"ratings": ratings, "statistics": stats}

    async def get_ratings_by_category(self, category: str, limit: int = 50) -> dict:
        """
        Get all ratings for a specific category.

        Args:
            category: Rating category (e.g., 'meal', 'meeting')
            limit: Maximum results to return

        Returns:
            Dict with ratings list and statistics
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT * FROM ratings
                WHERE category = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (category, limit),
            ) as cursor:
                rows = await cursor.fetchall()

        ratings = []
        total_score = 0

        for row in rows:
            rating = {
                "id": row[0],
                "target_type": row[1],
                "target_id": row[2],
                "category": row[3],
                "score": row[4],
                "notes": row[5],
                "created_at": row[6],
            }
            ratings.append(rating)
            total_score += row[4]

        # Calculate statistics
        stats = {
            "count": len(ratings),
            "average": round(total_score / len(ratings), 2) if ratings else 0,
            "category": category,
        }

        return {"ratings": ratings, "statistics": stats}

    # Settings CRUD operations with encryption

    async def set_setting(self, key: str, value: str, encrypt: bool = False) -> None:
        """Set a setting value, optionally encrypting it"""
        timestamp = datetime.utcnow().isoformat()

        # Encrypt if requested
        if encrypt:
            value = self.cipher.encrypt(value.encode()).decode()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO settings (key, value, updated_at)
                VALUES (?, ?, ?)
            """,
                (key, value, timestamp),
            )
            await db.commit()

    async def get_setting(self, key: str, decrypt: bool = False) -> Optional[str]:
        """Get a setting value, optionally decrypting it"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                SELECT value FROM settings WHERE key = ?
            """,
                (key,),
            )
            row = await cursor.fetchone()

            if row:
                value = row[0]
                # Decrypt if requested
                if decrypt:
                    value = self.cipher.decrypt(value.encode()).decode()
                return value
            return None

    async def get_all_settings(self) -> Dict[str, str]:
        """Get all settings as a dictionary"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT key, value FROM settings
            """)
            rows = await cursor.fetchall()
            return {row["key"]: row["value"] for row in rows}

    # Search operations

    async def search_conversations(self, query: str, limit: int = 5) -> List[Dict]:
        """
        Search conversations and messages for a query string.

        Simple text search using LIKE. For MVP, searches in:
        - Conversation titles
        - Message content

        Args:
            query: Search query string
            limit: Maximum number of results to return

        Returns:
            List of conversation snippets with matching content
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            # Search in conversations and messages
            # Use UNION to combine results from title search and message content search
            cursor = await db.execute(
                """
                SELECT DISTINCT 
                    c.id,
                    c.title,
                    c.created_at,
                    c.updated_at,
                    (
                        SELECT GROUP_CONCAT(m.content, ' | ')
                        FROM messages m
                        WHERE m.conversation_id = c.id
                        ORDER BY m.timestamp
                        LIMIT 3
                    ) as snippet
                FROM conversations c
                LEFT JOIN messages m ON c.id = m.conversation_id
                WHERE 
                    c.title LIKE ? 
                    OR m.content LIKE ?
                ORDER BY c.updated_at DESC
                LIMIT ?
            """,
                (f"%{query}%", f"%{query}%", limit),
            )

            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    # Entity CRUD operations

    async def create_entity(
        self,
        entity_type: str,
        name: str,
        description: str = None,
        metadata: dict = None,
    ) -> str:
        """
        Create a new entity (person, place, or thing).

        Args:
            entity_type: Type of entity ('person', 'place', 'thing')
            name: Name of the entity
            description: Optional description
            metadata: Optional metadata dict (stored as JSON)

        Returns:
            Entity ID
        """
        if entity_type not in ("person", "place", "thing"):
            raise ValueError(f"Invalid entity type: {entity_type}")

        entity_id = str(uuid.uuid4())
        metadata_json = json.dumps(metadata) if metadata else None

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO entities (id, type, name, description, metadata)
                VALUES (?, ?, ?, ?, ?)
                """,
                (entity_id, entity_type, name, description, metadata_json),
            )
            await db.commit()

        return entity_id

    async def get_entity(self, entity_id: str) -> Optional[Dict]:
        """Get an entity by ID."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT * FROM entities WHERE id = ?", (entity_id,)
            )
            row = await cursor.fetchone()

            if not row:
                return None

            return {
                "id": row[0],
                "type": row[1],
                "name": row[2],
                "description": row[3],
                "metadata": row[4],
                "created_at": row[5],
                "updated_at": row[6],
            }

    async def update_entity(
        self, entity_id: str, description: str = None, metadata: dict = None
    ) -> bool:
        """
        Update an entity's description and/or metadata.

        Args:
            entity_id: Entity ID
            description: New description (if provided)
            metadata: New metadata dict (if provided, replaces existing)

        Returns:
            True if updated, False if entity not found
        """
        # Check if entity exists
        entity = await self.get_entity(entity_id)
        if not entity:
            return False

        # Build update query dynamically
        updates = []
        params = []

        if description is not None:
            updates.append("description = ?")
            params.append(description)

        if metadata is not None:
            updates.append("metadata = ?")
            params.append(json.dumps(metadata))

        if not updates:
            return True  # Nothing to update

        updates.append("updated_at = ?")
        params.append(datetime.utcnow().isoformat())
        params.append(entity_id)

        query = f"UPDATE entities SET {', '.join(updates)} WHERE id = ?"

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(query, tuple(params))
            await db.commit()

        return True

    async def search_entities(
        self, query: str = None, entity_type: str = None, limit: int = 10
    ) -> list:
        """
        Search entities by name, description, or type.

        Args:
            query: Search query (searches name and description)
            entity_type: Filter by entity type ('person', 'place', 'thing')
            limit: Maximum results to return

        Returns:
            List of matching entities
        """
        conditions = []
        params = []

        if query:
            conditions.append("(name LIKE ? OR description LIKE ?)")
            search_pattern = f"%{query}%"
            params.extend([search_pattern, search_pattern])

        if entity_type:
            conditions.append("type = ?")
            params.append(entity_type)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        sql = f"""
            SELECT * FROM entities
            WHERE {where_clause}
            ORDER BY updated_at DESC
            LIMIT ?
        """
        params.append(limit)

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(sql, tuple(params))
            rows = await cursor.fetchall()

        results = []
        for row in rows:
            results.append(
                {
                    "id": row[0],
                    "type": row[1],
                    "name": row[2],
                    "description": row[3],
                    "metadata": row[4],
                    "created_at": row[5],
                    "updated_at": row[6],
                }
            )

        return results

    # Event CRUD operations

    async def create_event(
        self,
        name: str,
        description: Optional[str] = None,
        event_date: Optional[str] = None,
        participants: Optional[list] = None,
        location: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        """
        Create a new event.

        Args:
            name: Event name
            description: Optional description
            event_date: ISO format datetime string
            participants: List of entity IDs
            location: Entity ID or free text location
            metadata: Optional metadata dict

        Returns:
            Event ID
        """
        event_id = str(uuid.uuid4())
        participants_json = json.dumps(participants) if participants else None
        metadata_json = json.dumps(metadata) if metadata else None

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO events (id, name, description, event_date, participants, location, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    name,
                    description,
                    event_date,
                    participants_json,
                    location,
                    metadata_json,
                ),
            )
            await db.commit()

        return event_id

    async def get_event(self, event_id: str) -> Optional[Dict]:
        """Get an event by ID."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT * FROM events WHERE id = ?", (event_id,))
            row = await cursor.fetchone()

            if not row:
                return None

            return {
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "event_date": row[3],
                "participants": row[4],
                "location": row[5],
                "metadata": row[6],
                "created_at": row[7],
                "updated_at": row[8],
            }

    async def search_events(
        self,
        query: Optional[str] = None,
        participant_id: Optional[str] = None,
        limit: int = 10,
    ) -> list:
        """
        Search events by name, description, or participant.

        Args:
            query: Search query (searches name and description)
            participant_id: Filter by participant entity ID
            limit: Maximum results to return

        Returns:
            List of matching events
        """
        conditions = []
        params = []

        if query:
            conditions.append("(name LIKE ? OR description LIKE ?)")
            search_pattern = f"%{query}%"
            params.extend([search_pattern, search_pattern])

        if participant_id:
            # Search in JSON array - SQLite JSON support
            conditions.append("participants LIKE ?")
            params.append(f"%{participant_id}%")

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        sql = f"""
            SELECT * FROM events
            WHERE {where_clause}
            ORDER BY event_date DESC, created_at DESC
            LIMIT ?
        """
        params.append(limit)

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(sql, tuple(params))
            rows = await cursor.fetchall()

        results = []
        for row in rows:
            results.append(
                {
                    "id": row[0],
                    "name": row[1],
                    "description": row[2],
                    "event_date": row[3],
                    "participants": row[4],
                    "location": row[5],
                    "metadata": row[6],
                    "created_at": row[7],
                    "updated_at": row[8],
                }
            )

        return results

    # Journal CRUD operations (new entity-based system)

    async def create_journal(
        self,
        content: str,
        related_entities: Optional[list] = None,
        related_event_id: Optional[str] = None,
    ) -> str:
        """
        Create a new journal entry.

        Args:
            content: Journal entry content
            related_entities: List of entity IDs mentioned
            related_event_id: Optional event ID this journal is about

        Returns:
            Journal entry ID
        """
        journal_id = str(uuid.uuid4())
        entities_json = json.dumps(related_entities) if related_entities else None

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO journals (id, content, related_entities, related_event_id)
                VALUES (?, ?, ?, ?)
                """,
                (journal_id, content, entities_json, related_event_id),
            )
            await db.commit()

        return journal_id

    async def get_journal(self, journal_id: str) -> Optional[Dict]:
        """Get a journal entry by ID."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT * FROM journals WHERE id = ?", (journal_id,)
            )
            row = await cursor.fetchone()

            if not row:
                return None

            return {
                "id": row[0],
                "content": row[1],
                "related_entities": row[2],
                "related_event_id": row[3],
                "created_at": row[4],
            }

    async def search_journals(
        self,
        query: Optional[str] = None,
        entity_id: Optional[str] = None,
        event_id: Optional[str] = None,
        limit: int = 10,
    ) -> list:
        """
        Search journal entries.

        Args:
            query: Search query (searches content)
            entity_id: Filter by related entity ID
            event_id: Filter by related event ID
            limit: Maximum results to return

        Returns:
            List of matching journal entries
        """
        conditions = []
        params = []

        if query:
            conditions.append("content LIKE ?")
            params.append(f"%{query}%")

        if entity_id:
            conditions.append("related_entities LIKE ?")
            params.append(f"%{entity_id}%")

        if event_id:
            conditions.append("related_event_id = ?")
            params.append(event_id)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        sql = f"""
            SELECT * FROM journals
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ?
        """
        params.append(limit)

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(sql, tuple(params))
            rows = await cursor.fetchall()

        results = []
        for row in rows:
            results.append(
                {
                    "id": row[0],
                    "content": row[1],
                    "related_entities": row[2],
                    "related_event_id": row[3],
                    "created_at": row[4],
                }
            )

        return results


# Legacy class for backward compatibility
class ConversationDB:
    """Legacy database class - redirects to new Database class"""

    def __init__(self, db_path: str):
        self.db = Database(db_path)
        self.db_path = db_path

    async def init_db(self):
        """Initialize database schema"""
        await self.db.init_db()

    async def create_session(self, title: Optional[str] = None) -> str:
        """Create a new conversation session"""
        if title is None:
            title = f"Conversation {datetime.utcnow().isoformat()[:10]}"
        return await self.db.create_conversation(title)

    async def add_message(
        self,
        session_id: str,
        user_message: str,
        ai_response: str,
        embedding_id: Optional[str] = None,
    ) -> str:
        """Add a message to a conversation session (legacy format)"""
        # Add user message
        await self.db.add_message(session_id, "user", user_message)
        # Add AI response
        return await self.db.add_message(session_id, "assistant", ai_response)

    async def get_sessions(self, limit: int = 100) -> List[Dict]:
        """Get all conversation sessions"""
        return await self.db.list_conversations(limit)

    async def get_session_messages(self, session_id: str) -> List[Dict]:
        """Get all messages for a specific session (legacy format)"""
        messages = await self.db.get_conversation_messages(session_id)

        # Convert to legacy format (pairs of user/assistant messages)
        legacy_format = []
        for i in range(0, len(messages), 2):
            if i + 1 < len(messages):
                legacy_format.append(
                    {
                        "user_message": messages[i]["content"],
                        "ai_response": messages[i + 1]["content"],
                        "timestamp": messages[i]["timestamp"],
                    }
                )

        return legacy_format

    async def delete_session(self, session_id: str) -> bool:
        """Delete a conversation session"""
        return await self.db.delete_conversation(session_id)

    async def update_session_title(self, session_id: str, title: str) -> bool:
        """Update the title of a conversation session"""
        return await self.db.update_conversation_title(session_id, title)
