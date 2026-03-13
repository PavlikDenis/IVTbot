import sqlite3
from typing import List, Tuple, Optional


class Database:
    def __init__(self, db_name: str = "casino_stats.db"):
        self.db_name = db_name
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.cur = self.conn.cursor()

    def init_db(self):
        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            username TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS spins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            dice_value INTEGER,
            points INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        self.conn.commit()

    def add_user(self, user_id: int, first_name: str, username: Optional[str]):
        self.cur.execute("""
        INSERT INTO users(user_id, first_name, username)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            first_name=excluded.first_name,
            username=excluded.username,
            updated_at=CURRENT_TIMESTAMP
        """, (user_id, first_name, username))
        self.conn.commit()

    def add_spin(self, user_id: int, value: int, points: int):
        self.cur.execute("""
        INSERT INTO spins(user_id, dice_value, points)
        VALUES (?, ?, ?)
        """, (user_id, value, points))
        self.conn.commit()

    def get_leaderboard(self, limit: int = 10) -> List[Tuple]:
        self.cur.execute("""
        SELECT users.first_name, users.username,
               COUNT(spins.id),
               SUM(spins.points)
        FROM spins
        JOIN users ON users.user_id = spins.user_id
        GROUP BY spins.user_id
        ORDER BY SUM(spins.points) DESC
        LIMIT ?
        """, (limit,))
        return self.cur.fetchall()

    def get_user_stats(self, user_id: int) -> List[Tuple]:
        self.cur.execute("""
        SELECT dice_value, COUNT(*), SUM(points)
        FROM spins
        WHERE user_id = ?
        GROUP BY dice_value
        """, (user_id,))
        return self.cur.fetchall()
