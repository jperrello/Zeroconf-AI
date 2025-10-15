"""
Persistent usage tracking with SQLite
Provides atomic operations and automatic cleanup
"""
import sqlite3
import time
from typing import Dict, Optional
from threading import Lock
from datetime import datetime

class UsageTracker:
    """
    Thread-safe usage tracking with SQLite persistence
    """
    
    def __init__(self, db_path: str = "zeroconf_ai_usage.db"):
        self.db_path = db_path
        self._lock = Lock()  # Thread safety for concurrent requests
        self._init_database()
    
    def _init_database(self) -> None:
        """Initialize database schema"""
        with sqlite3.connect(self.db_path) as conn:
            # Main usage log table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS usage_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    app_id TEXT NOT NULL,
                    model TEXT NOT NULL,
                    input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL,
                    cost_usd REAL NOT NULL,
                    prompt_preview TEXT
                )
            """)
            
            # Index for time-based queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp 
                ON usage_log(timestamp DESC)
            """)
            
            # Index for app-based analytics
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_app_id 
                ON usage_log(app_id)
            """)
    
    def record_usage(
        self,
        app_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        prompt_preview: Optional[str] = None
    ) -> None:
        """Record a single API usage atomically"""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO usage_log 
                    (timestamp, app_id, model, input_tokens, output_tokens, cost_usd, prompt_preview)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    time.time(),
                    app_id,
                    model,
                    input_tokens,
                    output_tokens,
                    cost_usd,
                    prompt_preview[:100] if prompt_preview else None
                ))
    
    def get_hourly_request_count(self) -> int:
        """Count requests in the last hour"""
        one_hour_ago = time.time() - 3600
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM usage_log WHERE timestamp > ?",
                (one_hour_ago,)
            )
            return cursor.fetchone()[0]
    
    def get_daily_stats(self) -> Dict[str, float]:
        """Get today's usage statistics (UTC)"""
        # Calculate midnight UTC
        now = time.time()
        midnight_utc = now - (now % 86400)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT 
                    COUNT(*) as request_count,
                    SUM(input_tokens + output_tokens) as total_tokens,
                    SUM(cost_usd) as total_cost
                FROM usage_log 
                WHERE timestamp > ?
            """, (midnight_utc,))
            
            row = cursor.fetchone()
            return {
                "requests": row[0] or 0,
                "tokens": row[1] or 0,
                "cost_usd": row[2] or 0.0
            }
    
    def get_app_breakdown(self, hours: int = 24) -> Dict[str, Dict]:
        """Get usage breakdown by app"""
        cutoff = time.time() - (hours * 3600)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT
                    app_id,
                    COUNT(*) as requests,
                    SUM(input_tokens + output_tokens) as tokens,
                    SUM(cost_usd) as cost
                FROM usage_log
                WHERE timestamp > ?
                GROUP BY app_id
                ORDER BY cost DESC
            """, (cutoff,))

            return {
                row[0]: {"requests": row[1], "tokens_used": row[2] or 0, "cost_usd": row[3]}
                for row in cursor.fetchall()
            }
    
    def cleanup_old_records(self, days_to_keep: int = 30) -> None:
        cutoff = time.time() - (days_to_keep * 86400)

        with self._lock:
            # 1) Do deletions in a normal transaction
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.execute("DELETE FROM usage_log WHERE timestamp < ?", (cutoff,))
                deleted = cur.rowcount
                # leaving this 'with' commits the transaction

            # 2) Only VACUUM if we actually deleted anything (optional, but faster)
            if deleted and deleted > 0:
                # Open a new connection in autocommit mode
                # (isolation_level=None => autocommit; required for VACUUM)
                with sqlite3.connect(self.db_path, isolation_level=None) as vconn:
                    vconn.execute("VACUUM")