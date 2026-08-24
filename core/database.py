"""
KTHSHOP — Base de données SQLite
Stocke le calendrier, les posts, métriques, et apprentissages.
"""

import sqlite3
import json
import os
from datetime import datetime, timezone
from typing import Optional
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

from .config import config


class Database:
    """Gestionnaire de base SQLite avec cache et écritures batch."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or config.database_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._write_queue = []
        self._batch_size = 10
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=OFF")
        return conn

    def _init_db(self):
        """Crée les tables si elles n'existent pas."""
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scheduled_at TEXT,
                    published_at TEXT,
                    status TEXT DEFAULT 'scheduled',
                    platform TEXT DEFAULT 'facebook',
                    content_type TEXT,
                    product_id TEXT,
                    product_name TEXT,
                    caption TEXT,
                    image_url TEXT,
                    media_urls TEXT,
                    performance_data TEXT,
                    error TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS products (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    vendor TEXT,
                    price REAL,
                    stock INTEGER DEFAULT 0,
                    tags TEXT,
                    image_url TEXT,
                    last_synced TEXT
                );

                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id INTEGER,
                    platform TEXT,
                    impressions INTEGER DEFAULT 0,
                    reach INTEGER DEFAULT 0,
                    clicks INTEGER DEFAULT 0,
                    likes INTEGER DEFAULT 0,
                    comments INTEGER DEFAULT 0,
                    shares INTEGER DEFAULT 0,
                    saves INTEGER DEFAULT 0,
                    collected_at TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS learnings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT,
                    key TEXT,
                    value REAL,
                    sample_size INTEGER DEFAULT 1,
                    updated_at TEXT DEFAULT (datetime('now')),
                    UNIQUE(category, key)
                );

                CREATE TABLE IF NOT EXISTS calendar (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT,
                    time TEXT,
                    platform TEXT DEFAULT 'facebook',
                    content_type TEXT,
                    product_name TEXT,
                    product_id TEXT,
                    angle TEXT,
                    caption_template TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS config_store (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TEXT DEFAULT (datetime('now'))
                );
            """)
            conn.commit()

    # ─── Posts ──────────────────────────────────────────────

    def add_post(self, **kwargs) -> int:
        with self._get_conn() as conn:
            cur = conn.execute("""
                INSERT INTO posts (scheduled_at, status, platform, content_type,
                                   product_id, product_name, caption, image_url, media_urls)
                VALUES (:scheduled_at, :status, :platform, :content_type,
                        :product_id, :product_name, :caption, :image_url, :media_urls)
            """, {
                "scheduled_at": kwargs.get("scheduled_at"),
                "status": kwargs.get("status", "scheduled"),
                "platform": kwargs.get("platform", "facebook"),
                "content_type": kwargs.get("content_type", "photo"),
                "product_id": kwargs.get("product_id"),
                "product_name": kwargs.get("product_name"),
                "caption": kwargs.get("caption", ""),
                "image_url": kwargs.get("image_url"),
                "media_urls": json.dumps(kwargs.get("media_urls", [])),
            })
            conn.commit()
            return cur.lastrowid

    def update_post(self, post_id: int, **kwargs):
        sets = []
        values = {}
        for k, v in kwargs.items():
            sets.append(f"{k} = :{k}")
            values[k] = v
        values["id"] = post_id
        with self._get_conn() as conn:
            conn.execute(
                f"UPDATE posts SET {', '.join(sets)} WHERE id = :id",
                values
            )
            conn.commit()

    def get_pending_posts(self) -> list:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM posts WHERE status = 'scheduled' AND scheduled_at <= datetime('now')"
                " ORDER BY scheduled_at ASC LIMIT 10"
            ).fetchall()
            return [dict(r) for r in rows]

    def get_scheduled_posts(self, date: str = None) -> list:
        with self._get_conn() as conn:
            if date:
                rows = conn.execute(
                    "SELECT * FROM calendar WHERE date = ? ORDER BY time ASC", (date,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM calendar WHERE status = 'pending' ORDER BY date ASC, time ASC"
                ).fetchall()
            return [dict(r) for r in rows]

    def get_recent_posts(self, limit: int = 20) -> list:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM posts ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    # ─── Calendrier ─────────────────────────────────────────

    def add_calendar_entry(self, **kwargs) -> int:
        with self._get_conn() as conn:
            cur = conn.execute("""
                INSERT INTO calendar (date, time, platform, content_type,
                                      product_name, product_id, angle, caption_template, status)
                VALUES (:date, :time, :platform, :content_type,
                        :product_name, :product_id, :angle, :caption_template, :status)
            """, {
                "date": kwargs["date"],
                "time": kwargs["time"],
                "platform": kwargs.get("platform", "facebook"),
                "content_type": kwargs.get("content_type", "photo"),
                "product_name": kwargs.get("product_name", ""),
                "product_id": kwargs.get("product_id", ""),
                "angle": kwargs.get("angle", "desir"),
                "caption_template": kwargs.get("caption_template", ""),
                "status": kwargs.get("status", "pending"),
            })
            conn.commit()
            return cur.lastrowid

    def mark_calendar_done(self, entry_id: int):
        with self._get_conn() as conn:
            conn.execute("UPDATE calendar SET status = 'done' WHERE id = ?", (entry_id,))
            conn.commit()

    # ─── Produits ───────────────────────────────────────────

    def upsert_product(self, **kwargs):
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO products (id, title, vendor, price, stock, tags, image_url, last_synced)
                VALUES (:id, :title, :vendor, :price, :stock, :tags, :image_url, datetime('now'))
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title,
                    vendor=excluded.vendor,
                    price=excluded.price,
                    stock=excluded.stock,
                    tags=excluded.tags,
                    image_url=excluded.image_url,
                    last_synced=excluded.last_synced
            """, kwargs)
            conn.commit()

    def get_products(self, limit: int = 100) -> list:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM products ORDER BY last_synced DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    # ─── Métriques ──────────────────────────────────────────

    def add_metrics(self, post_id: int, platform: str, **kwargs):
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO metrics (post_id, platform, impressions, reach, clicks,
                                     likes, comments, shares, saves)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                post_id, platform,
                kwargs.get("impressions", 0),
                kwargs.get("reach", 0),
                kwargs.get("clicks", 0),
                kwargs.get("likes", 0),
                kwargs.get("comments", 0),
                kwargs.get("shares", 0),
                kwargs.get("saves", 0),
            ))
            conn.commit()

    def get_post_metrics(self, post_id: int) -> list:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM metrics WHERE post_id = ? ORDER BY collected_at DESC",
                (post_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_summary_metrics(self, days: int = 7) -> dict:
        """Moyennes des métriques sur N jours."""
        with self._get_conn() as conn:
            row = conn.execute("""
                SELECT
                    COALESCE(AVG(impressions), 0) as avg_impressions,
                    COALESCE(AVG(clicks), 0) as avg_clicks,
                    COALESCE(AVG(likes), 0) as avg_likes,
                    COALESCE(AVG(comments), 0) as avg_comments,
                    COALESCE(AVG(shares), 0) as avg_shares,
                    COUNT(*) as total_posts,
                    SUM(CASE WHEN likes > 0 THEN 1 ELSE 0 END) as posts_with_engagement
                FROM metrics
                WHERE collected_at >= datetime('now', '-' || ? || ' days')
            """, (days,))
            return dict(row.fetchone())

    # ─── Apprentissages ─────────────────────────────────────

    def update_learning(self, category: str, key: str, value: float):
        """Met à jour la moyenne glissante d'un apprentissage."""
        with self._get_conn() as conn:
            existing = conn.execute(
                "SELECT * FROM learnings WHERE category = ? AND key = ?",
                (category, key)
            ).fetchone()
            if existing:
                n = existing["sample_size"] + 1
                new_val = (existing["value"] * existing["sample_size"] + value) / n
                conn.execute("""
                    UPDATE learnings SET value = ?, sample_size = ?, updated_at = datetime('now')
                    WHERE category = ? AND key = ?
                """, (new_val, n, category, key))
            else:
                conn.execute("""
                    INSERT INTO learnings (category, key, value, sample_size)
                    VALUES (?, ?, ?, 1)
                """, (category, key, value))
            conn.commit()

    def get_learnings(self, category: Optional[str] = None) -> dict:
        """Récupère les apprentissages, optionnellement filtrés par catégorie."""
        with self._get_conn() as conn:
            if category:
                rows = conn.execute(
                    "SELECT * FROM learnings WHERE category = ? ORDER BY value DESC",
                    (category,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM learnings ORDER BY category, value DESC"
                ).fetchall()
            result = {}
            for r in rows:
                d = dict(r)
                if d["category"] not in result:
                    result[d["category"]] = []
                result[d["category"]].append({
                    "key": d["key"],
                    "value": d["value"],
                    "sample_size": d["sample_size"],
                })
            return result

    # ─── Configuration persistée ────────────────────────────

    def set_config(self, key: str, value: str):
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO config_store (key, value, updated_at)
                VALUES (?, ?, datetime('now'))
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """, (key, value))
            conn.commit()

    def get_config(self, key: str, default: str = "") -> str:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT value FROM config_store WHERE key = ?", (key,)
            ).fetchone()
            return row["value"] if row else default

    # ─── Utilitaires ────────────────────────────────────────

    def get_stats(self) -> dict:
        with self._get_conn() as conn:
            return {
                "total_posts": conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0],
                "published": conn.execute("SELECT COUNT(*) FROM posts WHERE status='published'").fetchone()[0],
                "pending_calendar": conn.execute("SELECT COUNT(*) FROM calendar WHERE status='pending'").fetchone()[0],
                "total_products": conn.execute("SELECT COUNT(*) FROM products").fetchone()[0],
                "learning_rules": conn.execute("SELECT COUNT(*) FROM learnings").fetchone()[0],
            }


# Singleton
db = Database()