"""SQLite database for TwinSync Spot."""

import json
import os
from datetime import datetime
from typing import Optional

import aiosqlite

from app.config import settings
from app.core.models import (
    Spot, SpotType, SpotStatus, 
    CheckResult, ToSortItem, SpotMemory
)
from app.core.memory import MemoryEngine


class Database:
    """SQLite database manager."""
    
    def __init__(self):
        self.db_path = settings.db_path
        self._conn: Optional[aiosqlite.Connection] = None
    
    async def init(self):
        """Initialize database and create tables."""
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        
        await self._create_tables()
    
    async def close(self):
        """Close database connection."""
        if self._conn:
            await self._conn.close()
    
    async def _create_tables(self):
        """Create database tables."""
        await self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS spots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                camera_entity TEXT NOT NULL,
                definition TEXT NOT NULL,
                spot_type TEXT NOT NULL DEFAULT 'custom',
                voice TEXT NOT NULL DEFAULT 'supportive',
                custom_voice_prompt TEXT,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'unknown',
                last_check TEXT,
                current_streak INTEGER DEFAULT 0,
                longest_streak INTEGER DEFAULT 0,
                snoozed_until TEXT,
                total_resets INTEGER DEFAULT 0,
                last_reset TEXT
            );
            
            CREATE TABLE IF NOT EXISTS checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                spot_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                status TEXT NOT NULL,
                to_sort_json TEXT NOT NULL DEFAULT '[]',
                looking_good_json TEXT NOT NULL DEFAULT '[]',
                notes_main TEXT,
                notes_pattern TEXT,
                notes_encouragement TEXT,
                error_message TEXT,
                api_response_time REAL DEFAULT 0,
                FOREIGN KEY (spot_id) REFERENCES spots(id) ON DELETE CASCADE
            );
            
            CREATE INDEX IF NOT EXISTS idx_checks_spot_id ON checks(spot_id);
            CREATE INDEX IF NOT EXISTS idx_checks_timestamp ON checks(timestamp);
        """)
        await self._conn.commit()
    
    # ==========================================================================
    # SPOTS
    # ==========================================================================
    
    async def create_spot(
        self,
        name: str,
        camera_entity: str,
        definition: str,
        spot_type: str = "custom",
        voice: str = "supportive",
        custom_voice_prompt: str = None,
    ) -> Spot:
        """Create a new spot."""
        now = datetime.now().isoformat()
        
        cursor = await self._conn.execute(
            """INSERT INTO spots 
               (name, camera_entity, definition, spot_type, voice, custom_voice_prompt, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (name, camera_entity, definition, spot_type, voice, custom_voice_prompt, now)
        )
        await self._conn.commit()
        
        return await self.get_spot(cursor.lastrowid)
    
    async def get_spot(self, spot_id: int) -> Optional[Spot]:
        """Get a spot by ID."""
        cursor = await self._conn.execute(
            "SELECT * FROM spots WHERE id = ?", (spot_id,)
        )
        row = await cursor.fetchone()
        
        if not row:
            return None
        
        return self._row_to_spot(row)
    
    async def get_all_spots(self) -> list[Spot]:
        """Get all spots."""
        cursor = await self._conn.execute(
            "SELECT * FROM spots ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        return [self._row_to_spot(row) for row in rows]
    
    async def update_spot(self, spot_id: int, **kwargs) -> Optional[Spot]:
        """Update a spot."""
        allowed = {
            "name", "camera_entity", "definition", "spot_type", 
            "voice", "custom_voice_prompt", "status", "last_check",
            "current_streak", "longest_streak", "snoozed_until",
            "total_resets", "last_reset"
        }
        
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return await self.get_spot(spot_id)
        
        # Convert datetime to string
        for key in ["last_check", "snoozed_until", "last_reset"]:
            if key in updates and isinstance(updates[key], datetime):
                updates[key] = updates[key].isoformat()
        
        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        values = list(updates.values()) + [spot_id]
        
        await self._conn.execute(
            f"UPDATE spots SET {set_clause} WHERE id = ?", values
        )
        await self._conn.commit()
        
        return await self.get_spot(spot_id)
    
    async def delete_spot(self, spot_id: int) -> bool:
        """Delete a spot and all its checks."""
        cursor = await self._conn.execute(
            "DELETE FROM spots WHERE id = ?", (spot_id,)
        )
        await self._conn.commit()
        return cursor.rowcount > 0
    
    def _row_to_spot(self, row: aiosqlite.Row) -> Spot:
        """Convert database row to Spot object."""
        return Spot(
            id=row["id"],
            name=row["name"],
            camera_entity=row["camera_entity"],
            definition=row["definition"],
            spot_type=SpotType(row["spot_type"]),
            voice=row["voice"],
            created_at=datetime.fromisoformat(row["created_at"]),
            status=SpotStatus(row["status"]),
            last_check=datetime.fromisoformat(row["last_check"]) if row["last_check"] else None,
            current_streak=row["current_streak"] or 0,
            longest_streak=row["longest_streak"] or 0,
            snoozed_until=datetime.fromisoformat(row["snoozed_until"]) if row["snoozed_until"] else None,
        )
    
    # ==========================================================================
    # CHECKS
    # ==========================================================================
    
    async def save_check(
        self,
        spot_id: int,
        status: str,
        to_sort: list[dict],
        looking_good: list[str],
        notes_main: str = None,
        notes_pattern: str = None,
        notes_encouragement: str = None,
        error_message: str = None,
        api_response_time: float = 0,
    ) -> CheckResult:
        """Save a check result."""
        now = datetime.now().isoformat()
        
        cursor = await self._conn.execute(
            """INSERT INTO checks 
               (spot_id, timestamp, status, to_sort_json, looking_good_json,
                notes_main, notes_pattern, notes_encouragement, 
                error_message, api_response_time)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                spot_id, now, status, 
                json.dumps(to_sort), json.dumps(looking_good),
                notes_main, notes_pattern, notes_encouragement,
                error_message, api_response_time
            )
        )
        await self._conn.commit()
        
        # Update spot status
        await self.update_spot(spot_id, status=status, last_check=now)
        
        return await self.get_check(cursor.lastrowid)
    
    async def get_check(self, check_id: int) -> Optional[CheckResult]:
        """Get a check by ID."""
        cursor = await self._conn.execute(
            "SELECT * FROM checks WHERE id = ?", (check_id,)
        )
        row = await cursor.fetchone()
        
        if not row:
            return None
        
        return self._row_to_check(row)
    
    async def get_recent_checks(
        self, spot_id: int, limit: int = 30
    ) -> list[CheckResult]:
        """Get recent checks for a spot."""
        cursor = await self._conn.execute(
            """SELECT * FROM checks 
               WHERE spot_id = ? 
               ORDER BY timestamp DESC 
               LIMIT ?""",
            (spot_id, limit)
        )
        rows = await cursor.fetchall()
        return [self._row_to_check(row) for row in rows]
    
    async def get_checks_since(
        self, spot_id: int, since: datetime
    ) -> list[CheckResult]:
        """Get checks since a date."""
        cursor = await self._conn.execute(
            """SELECT * FROM checks 
               WHERE spot_id = ? AND timestamp >= ?
               ORDER BY timestamp DESC""",
            (spot_id, since.isoformat())
        )
        rows = await cursor.fetchall()
        return [self._row_to_check(row) for row in rows]
    
    def _row_to_check(self, row: aiosqlite.Row) -> CheckResult:
        """Convert database row to CheckResult object."""
        to_sort_data = json.loads(row["to_sort_json"])
        to_sort = [
            ToSortItem(
                item=item.get("item", ""),
                location=item.get("location"),
                recurring=item.get("recurring", False),
                recurring_count=item.get("recurring_count", 0),
            )
            for item in to_sort_data
        ]
        
        return CheckResult(
            id=row["id"],
            spot_id=row["spot_id"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            status=SpotStatus(row["status"]),
            to_sort=to_sort,
            looking_good=json.loads(row["looking_good_json"]),
            notes_main=row["notes_main"],
            notes_pattern=row["notes_pattern"],
            notes_encouragement=row["notes_encouragement"],
            error_message=row["error_message"],
            api_response_time=row["api_response_time"] or 0,
        )
    
    # ==========================================================================
    # MEMORY
    # ==========================================================================
    
    async def get_spot_memory(self, spot_id: int) -> SpotMemory:
        """Calculate memory/patterns for a spot."""
        from datetime import timedelta
        
        # Get checks from last 30 days
        since = datetime.now() - timedelta(days=30)
        checks = await self.get_checks_since(spot_id, since)
        
        # Calculate patterns
        engine = MemoryEngine(checks)
        memory = engine.calculate_patterns()
        memory.spot_id = spot_id
        
        # Get reset stats from spot
        spot = await self.get_spot(spot_id)
        if spot:
            memory.current_streak = spot.current_streak
            memory.longest_streak = spot.longest_streak
        
        return memory
    
    async def record_reset(self, spot_id: int) -> Spot:
        """Record that user reset a spot."""
        spot = await self.get_spot(spot_id)
        if not spot:
            raise ValueError(f"Spot {spot_id} not found")
        
        new_streak = spot.current_streak + 1
        longest = max(spot.longest_streak, new_streak)
        
        return await self.update_spot(
            spot_id,
            status="sorted",
            current_streak=new_streak,
            longest_streak=longest,
            last_reset=datetime.now(),
            total_resets=(spot.total_resets if hasattr(spot, 'total_resets') else 0) + 1,
        )
