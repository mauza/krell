#!/usr/bin/env python3
"""
Database migration script for Krell entity system.

This script migrates existing Krell databases to the new entity-based schema.
Run this on existing installations to preserve data.
"""

import asyncio
import aiosqlite
import os
import sys
from datetime import datetime


async def migrate_database(db_path: str):
    """
    Migrate existing database to entity-based schema.

    Args:
        db_path: Path to existing database
    """
    print(f"Starting migration for: {db_path}")

    # Backup existing database
    backup_path = f"{db_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print(f"Creating backup: {backup_path}")

    import shutil

    shutil.copy2(db_path, backup_path)

    # Connect to database
    conn = await aiosqlite.connect(db_path)

    try:
        # Check if migration is needed
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='entities'"
        )
        row = await cursor.fetchone()

        if row:
            print("Database already migrated to entity system")
            return

        print("Running migration...")

        # Read and execute migration SQL
        migration_file = os.path.join(
            os.path.dirname(__file__), "database/migrations/001_entity_system.sql"
        )

        with open(migration_file, "r") as f:
            migration_sql = f.read()

        # Execute migration statements
        statements = [s.strip() for s in migration_sql.split(";") if s.strip()]
        for i, statement in enumerate(statements):
            print(f"Executing statement {i + 1}/{len(statements)}...")
            try:
                await conn.execute(statement)
            except Exception as e:
                # Allow certain errors for missing tables (new databases)
                if "no such table" in str(e) and (
                    "journal_entries" in statement or "ratings" in statement
                ):
                    print(f"  Skipping (table doesn't exist): {e}")
                    continue
                else:
                    raise e

        await conn.commit()
        print("Migration completed successfully!")

        # Verify migration
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = await cursor.fetchall()

        print("\nDatabase tables after migration:")
        for table in tables:
            print(f"  - {table[0]}")

    except Exception as e:
        print(f"Migration failed: {e}")
        print(f"Restoring from backup: {backup_path}")
        try:
            await conn.close()
        except:
            pass  # Connection might already be closed
        shutil.copy2(backup_path, db_path)
        sys.exit(1)

    finally:
        await conn.close()


async def main():
    """Main migration entry point."""
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    else:
        db_path = "./data/krell.db"

    if not os.path.exists(db_path):
        print(f"Database not found: {db_path}")
        print("Usage: python migrate_database.py [path/to/database.db]")
        sys.exit(1)

    await migrate_database(db_path)


if __name__ == "__main__":
    asyncio.run(main())
