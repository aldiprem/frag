# database/data.py
import sqlite3
import logging
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

# Database configuration
DB_PATH = "frag.db"


def init_database():
    """Inisialisasi database SQLite3."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Tabel untuk menyimpan data pengguna
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            is_admin BOOLEAN DEFAULT 0,
            first_seen TIMESTAMP,
            last_seen TIMESTAMP
        )
    ''')
    
    # Tabel untuk menyimpan riwayat pembelian
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            recipient_username TEXT,
            recipient_nickname TEXT,
            stars_amount INTEGER,
            price_ton REAL,
            tx_hash TEXT,
            show_sender BOOLEAN,
            status TEXT,
            error_message TEXT,
            timestamp TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    # Tabel untuk menyimpan log aktivitas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT,
            details TEXT,
            ip_address TEXT,
            timestamp TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    # Tabel untuk menyimpan konfigurasi bot
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bot_config (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP
        )
    ''')
    
    # Tabel untuk menyimpan sesi pembelian yang belum selesai
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pending_purchases (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            nickname TEXT,
            address TEXT,
            stars INTEGER,
            price REAL,
            show_sender BOOLEAN DEFAULT 1,
            state TEXT,
            created_at TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    conn.commit()
    conn.close()
    logger.info("✅ Database initialized successfully")


async def save_user(user_id: int, username: str = None, first_name: str = None, last_name: str = None, admin_ids: list = None):
    """Simpan atau update data pengguna."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        existing = cursor.fetchone()
        
        now = datetime.now().isoformat()
        is_admin = 1 if admin_ids and user_id in admin_ids else 0
        
        if existing:
            cursor.execute('''
                UPDATE users 
                SET username = ?, first_name = ?, last_name = ?, last_seen = ?, is_admin = ?
                WHERE user_id = ?
            ''', (username, first_name, last_name, now, is_admin, user_id))
        else:
            cursor.execute('''
                INSERT INTO users (user_id, username, first_name, last_name, is_admin, first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, username, first_name, last_name, is_admin, now, now))
        
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error saving user to database: {e}")


async def log_activity(user_id: int, action: str, details: str = None, ip: str = None):
    """Catat aktivitas pengguna."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO activity_log (user_id, action, details, ip_address, timestamp)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, action, details, ip, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error logging activity: {e}")


async def save_purchase(
    user_id: int, 
    recipient_username: str, 
    recipient_nickname: str, 
    stars_amount: int, 
    price_ton: float,
    tx_hash: str = None,
    show_sender: bool = True,
    status: str = "pending",
    error_message: str = None
):
    """Simpan riwayat pembelian."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO purchases 
            (user_id, recipient_username, recipient_nickname, stars_amount, price_ton, 
             tx_hash, show_sender, status, error_message, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id, recipient_username, recipient_nickname, stars_amount, price_ton,
            tx_hash, show_sender, status, error_message, datetime.now().isoformat()
        ))
        
        conn.commit()
        conn.close()
        
        await log_activity(
            user_id, 
            "purchase", 
            f"Stars: {stars_amount}, Recipient: @{recipient_username}, Status: {status}"
        )
        
    except Exception as e:
        logger.error(f"Error saving purchase: {e}")


async def save_pending_purchase(
    user_id: int,
    username: str,
    nickname: str,
    address: str,
    stars: int,
    price: float,
    show_sender: bool = True,
    state: str = None
):
    """Simpan sesi pembelian yang belum selesai."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        cursor.execute('''
            INSERT OR REPLACE INTO pending_purchases 
            (user_id, username, nickname, address, stars, price, show_sender, state, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, COALESCE(
                (SELECT created_at FROM pending_purchases WHERE user_id = ?), ?
            ), ?)
        ''', (
            user_id, username, nickname, address, stars, price, show_sender, state,
            user_id, now, now
        ))
        
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error saving pending purchase: {e}")


async def get_pending_purchase(user_id: int) -> Optional[Dict]:
    """Ambil sesi pembelian yang belum selesai."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT username, nickname, address, stars, price, show_sender, state
            FROM pending_purchases WHERE user_id = ?
        ''', (user_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                'username': row[0],
                'nickname': row[1],
                'address': row[2],
                'stars': row[3],
                'price': row[4],
                'show_sender': bool(row[5]),
                'state': row[6]
            }
        return None
    except Exception as e:
        logger.error(f"Error getting pending purchase: {e}")
        return None


async def delete_pending_purchase(user_id: int):
    """Hapus sesi pembelian yang sudah selesai/dibatalkan."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM pending_purchases WHERE user_id = ?', (user_id,))
        
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error deleting pending purchase: {e}")


async def update_bot_config(key: str, value: str):
    """Update konfigurasi bot."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO bot_config (key, value, updated_at)
            VALUES (?, ?, ?)
        ''', (key, value, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error updating bot config: {e}")


async def get_bot_config(key: str) -> Optional[str]:
    """Ambil konfigurasi bot."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('SELECT value FROM bot_config WHERE key = ?', (key,))
        row = cursor.fetchone()
        
        conn.close()
        return row[0] if row else None
    except Exception as e:
        logger.error(f"Error getting bot config: {e}")
        return None


async def get_user_stats(user_id: int) -> Dict:
    """Dapatkan statistik pengguna."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT COUNT(*), COALESCE(SUM(stars_amount), 0), COALESCE(SUM(price_ton), 0)
            FROM purchases WHERE user_id = ? AND status = 'success'
        ''', (user_id,))
        total_purchases, total_stars, total_spent = cursor.fetchone()
        
        today = datetime.now().date().isoformat()
        cursor.execute('''
            SELECT COUNT(*)
            FROM purchases 
            WHERE user_id = ? AND status = 'success' AND DATE(timestamp) = ?
        ''', (user_id, today))
        today_purchases = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total_purchases': total_purchases or 0,
            'total_stars': total_stars or 0,
            'total_spent': total_spent or 0,
            'today_purchases': today_purchases or 0
        }
    except Exception as e:
        logger.error(f"Error getting user stats: {e}")
        return {
            'total_purchases': 0,
            'total_stars': 0,
            'total_spent': 0,
            'today_purchases': 0
        }


async def get_all_stats() -> Dict:
    """Dapatkan statistik keseluruhan bot."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM users')
        total_users = cursor.fetchone()[0]
        
        today = datetime.now().date().isoformat()
        cursor.execute('''
            SELECT COUNT(DISTINCT user_id) FROM activity_log 
            WHERE DATE(timestamp) = ? AND action != 'system'
        ''', (today,))
        active_today = cursor.fetchone()[0]
        
        cursor.execute('''
            SELECT COUNT(*), COALESCE(SUM(stars_amount), 0), COALESCE(SUM(price_ton), 0)
            FROM purchases WHERE status = 'success'
        ''')
        total_purchases, total_stars, total_volume = cursor.fetchone()
        
        cursor.execute('''
            SELECT COUNT(*), COALESCE(SUM(stars_amount), 0), COALESCE(SUM(price_ton), 0)
            FROM purchases WHERE status = 'success' AND DATE(timestamp) = ?
        ''', (today,))
        today_purchases, today_stars, today_volume = cursor.fetchone()
        
        conn.close()
        
        return {
            'total_users': total_users or 0,
            'active_today': active_today or 0,
            'total_purchases': total_purchases or 0,
            'total_stars': total_stars or 0,
            'total_volume': total_volume or 0,
            'today_purchases': today_purchases or 0,
            'today_stars': today_stars or 0,
            'today_volume': today_volume or 0
        }
    except Exception as e:
        logger.error(f"Error getting all stats: {e}")
        return {}


async def get_recent_purchases(limit: int = 10):
    """Dapatkan daftar pembelian terbaru."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT user_id, recipient_username, stars_amount, price_ton, status, timestamp
            FROM purchases
            ORDER BY timestamp DESC LIMIT ?
        ''', (limit,))
        
        purchases = cursor.fetchall()
        conn.close()
        
        return purchases
    except Exception as e:
        logger.error(f"Error getting recent purchases: {e}")
        return []
