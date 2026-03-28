# database/data.py - Database Functions for Master Bot
import sqlite3
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
import pytz
import os

logger = logging.getLogger(__name__)

# Database path
DB_PATH = "frag.db"


def init_database():
    """Initialize SQLite3 database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
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
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            recipient_username TEXT,
            recipient_nickname TEXT,
            stars_amount INTEGER,
            price_idr REAL,
            price_ton REAL,
            tx_hash TEXT,
            show_sender BOOLEAN,
            status TEXT,
            error_message TEXT,
            timestamp TIMESTAMP,
            bot_token TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT,
            details TEXT,
            ip_address TEXT,
            timestamp TIMESTAMP,
            bot_token TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bot_config (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pending_purchases (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            nickname TEXT,
            address TEXT,
            stars INTEGER,
            price_idr REAL,
            price_ton REAL,
            show_sender BOOLEAN DEFAULT 1,
            state TEXT,
            created_at TIMESTAMP,
            updated_at TIMESTAMP,
            bot_token TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cloned_bots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_token TEXT UNIQUE NOT NULL,
            bot_username TEXT,
            bot_name TEXT,
            status TEXT DEFAULT 'stopped',
            created_by INTEGER,
            created_at TIMESTAMP,
            last_started TIMESTAMP,
            last_stopped TIMESTAMP,
            pid INTEGER
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bot_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_token TEXT,
            log_level TEXT,
            message TEXT,
            timestamp TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            order_id TEXT UNIQUE NOT NULL,
            amount INTEGER NOT NULL,
            total_payment INTEGER,
            payment_method TEXT,
            payment_number TEXT,
            status TEXT DEFAULT 'pending',
            qr_string TEXT,
            expired_at TIMESTAMP,
            completed_at TIMESTAMP,
            created_at TIMESTAMP,
            updated_at TIMESTAMP,
            waiting_msg_id INTEGER,
            bot_token TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bot_price_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_token TEXT NOT NULL,
            price_per_star REAL NOT NULL DEFAULT 270,
            calculation_mode TEXT DEFAULT 'per_star',
            created_at TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY (bot_token) REFERENCES cloned_bots(bot_token)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bot_price_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_token TEXT NOT NULL,
            stars_amount INTEGER NOT NULL,
            price_idr REAL NOT NULL,
            created_at TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY (bot_token) REFERENCES cloned_bots(bot_token),
            UNIQUE(bot_token, stars_amount)
        )
    ''')
    
    try:
        cursor.execute('ALTER TABLE deposits ADD COLUMN waiting_msg_id INTEGER')
    except sqlite3.OperationalError:
        pass

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_balances (
            user_id INTEGER PRIMARY KEY,
            balance INTEGER DEFAULT 0,
            last_updated TIMESTAMP,
            bot_token TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')
    
    conn.commit()
    conn.close()
    logger.info("✅ Database initialized successfully")


JAKARTA_TZ = pytz.timezone('Asia/Jakarta')
PRICE_PER_STAR_IDR = float(os.getenv("PRICE_PER_STAR_IDR", 270))

def get_jakarta_time():
    return datetime.now(JAKARTA_TZ)


def get_jakarta_time_iso():
    return datetime.now(JAKARTA_TZ).isoformat()


def get_jakarta_date():
    return datetime.now(JAKARTA_TZ).date().isoformat()

# database/data.py - Tambahkan fungsi ini
async def get_bot_id_by_token(bot_token: str) -> Optional[int]:
    """Get bot ID from bot token"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM cloned_bots WHERE bot_token = ?", (bot_token,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception as e:
        logger.error(f"Error getting bot id: {e}")
        return None


async def get_bot_token_by_id(bot_id: int) -> Optional[str]:
    """Get bot token from bot ID"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT bot_token FROM cloned_bots WHERE id = ?", (bot_id,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception as e:
        logger.error(f"Error getting bot token: {e}")
        return None


async def get_bot_detail_by_id(bot_id: int) -> Optional[Dict]:
    """Get bot detail by ID"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""SELECT id, bot_token, bot_username, bot_name, status, created_by, 
                       created_at, last_started, last_stopped, pid FROM cloned_bots 
                       WHERE id = ?""", (bot_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {
                'id': row[0], 'bot_token': row[1], 'bot_username': row[2], 'bot_name': row[3],
                'status': row[4], 'created_by': row[5], 'created_at': row[6],
                'last_started': row[7], 'last_stopped': row[8], 'pid': row[9]
            }
        return None
    except Exception as e:
        logger.error(f"Error getting bot detail: {e}")
        return None

# ===================== BOT PRICE CONFIG FUNCTIONS =====================

async def get_bot_price_config(bot_token: str) -> Dict:
    """Get price configuration for a specific bot"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT price_per_star, calculation_mode, created_at, updated_at 
            FROM bot_price_config WHERE bot_token = ?
        """, (bot_token,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                'price_per_star': row[0],
                'calculation_mode': row[1],
                'created_at': row[2],
                'updated_at': row[3]
            }
        else:
            return {
                'price_per_star': PRICE_PER_STAR_IDR,
                'calculation_mode': 'per_star',
                'created_at': None,
                'updated_at': None
            }
    except Exception as e:
        logger.error(f"Error getting bot price config: {e}")
        return {'price_per_star': PRICE_PER_STAR_IDR, 'calculation_mode': 'per_star'}


async def update_bot_price_config(bot_token: str, price_per_star: float = None, 
                                   calculation_mode: str = None) -> bool:
    """Update price configuration for a specific bot"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now = get_jakarta_time_iso()
        
        cursor.execute("SELECT * FROM bot_price_config WHERE bot_token = ?", (bot_token,))
        existing = cursor.fetchone()
        
        if existing:
            updates = []
            params = []
            if price_per_star is not None:
                updates.append("price_per_star = ?")
                params.append(price_per_star)
            if calculation_mode is not None:
                updates.append("calculation_mode = ?")
                params.append(calculation_mode)
            updates.append("updated_at = ?")
            params.append(now)
            params.append(bot_token)
            
            cursor.execute(f"UPDATE bot_price_config SET {', '.join(updates)} WHERE bot_token = ?", params)
        else:
            cursor.execute("""
                INSERT INTO bot_price_config (bot_token, price_per_star, calculation_mode, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """, (bot_token, price_per_star or PRICE_PER_STAR_IDR, calculation_mode or 'per_star', now, now))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error updating bot price config: {e}")
        return False


async def add_price_template(bot_token: str, stars_amount: int, price_idr: float) -> bool:
    """Add price template for specific stars amount"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now = get_jakarta_time_iso()
        cursor.execute("""
            INSERT OR REPLACE INTO bot_price_templates (bot_token, stars_amount, price_idr, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """, (bot_token, stars_amount, price_idr, now, now))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error adding price template: {e}")
        return False


async def delete_price_template(bot_token: str, stars_amount: int) -> bool:
    """Delete price template for specific stars amount"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM bot_price_templates WHERE bot_token = ? AND stars_amount = ?", 
                      (bot_token, stars_amount))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error deleting price template: {e}")
        return False


async def get_price_templates(bot_token: str) -> List[Dict]:
    """Get all price templates for a bot"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT stars_amount, price_idr, created_at, updated_at 
            FROM bot_price_templates WHERE bot_token = ? ORDER BY stars_amount ASC
        """, (bot_token,))
        rows = cursor.fetchall()
        conn.close()
        return [{'stars': r[0], 'price': r[1], 'created_at': r[2], 'updated_at': r[3]} for r in rows]
    except Exception as e:
        logger.error(f"Error getting price templates: {e}")
        return []


async def calculate_price(bot_token: str, stars: int) -> float:
    """Calculate price based on bot config and templates"""
    config = await get_bot_price_config(bot_token)
    templates = await get_price_templates(bot_token)
    
    if config['calculation_mode'] == 'per_star':
        return stars * config['price_per_star']
    
    elif config['calculation_mode'] == 'interpolation' and len(templates) >= 2:
        sorted_templates = sorted(templates, key=lambda x: x['stars'])
        
        # Jika stars sama persis dengan template
        for t in sorted_templates:
            if t['stars'] == stars:
                return t['price']
        
        # Cari interpolasi antara dua template
        lower = None
        upper = None
        for t in sorted_templates:
            if t['stars'] <= stars:
                lower = t
            if t['stars'] >= stars and upper is None:
                upper = t
        
        if lower and upper:
            ratio = (stars - lower['stars']) / (upper['stars'] - lower['stars'])
            price = lower['price'] + (upper['price'] - lower['price']) * ratio
            return round(price, 0)
        elif lower:
            return lower['price']
        elif upper:
            return upper['price']
        else:
            return stars * config['price_per_star']
    
    else:
        return stars * config['price_per_star']

# ===================== USER FUNCTIONS =====================

async def save_user(user_id: int, username: str = None, first_name: str = None, 
                    last_name: str = None, bot_token: str = None, admin_ids: list = None):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        existing = cursor.fetchone()
        now = get_jakarta_time_iso()
        is_admin = 1 if admin_ids and user_id in admin_ids else 0
        
        if existing:
            cursor.execute("""UPDATE users SET username=?, first_name=?, last_name=?, 
                           last_seen=?, is_admin=? WHERE user_id=?""",
                          (username, first_name, last_name, now, is_admin, user_id))
        else:
            cursor.execute("""INSERT INTO users (user_id, username, first_name, last_name, 
                           is_admin, first_seen, last_seen)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                          (user_id, username, first_name, last_name, is_admin, now, now))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error saving user: {e}")


async def log_activity(user_id: int, action: str, details: str = None, 
                       ip: str = None, bot_token: str = None):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""INSERT INTO activity_log (user_id, action, details, ip_address, 
                       timestamp, bot_token) VALUES (?, ?, ?, ?, ?, ?)""",
                      (user_id, action, details, ip, get_jakarta_time_iso(), bot_token))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error logging activity: {e}")


async def get_user_stats(user_id: int, bot_token: str = None) -> Dict:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        if bot_token:
            cursor.execute("""SELECT COUNT(*), COALESCE(SUM(stars_amount), 0), 
                           COALESCE(SUM(price_idr), 0) FROM purchases 
                           WHERE user_id = ? AND status = 'success' AND bot_token = ?""", 
                          (user_id, bot_token))
        else:
            cursor.execute("""SELECT COUNT(*), COALESCE(SUM(stars_amount), 0), 
                           COALESCE(SUM(price_idr), 0) FROM purchases 
                           WHERE user_id = ? AND status = 'success'""", (user_id,))
        total_purchases, total_stars, total_spent_idr = cursor.fetchone()
        today = get_jakarta_date()
        if bot_token:
            cursor.execute("""SELECT COUNT(*) FROM purchases WHERE user_id = ? 
                           AND status = 'success' AND DATE(timestamp) = ? AND bot_token = ?""", 
                          (user_id, today, bot_token))
        else:
            cursor.execute("""SELECT COUNT(*) FROM purchases WHERE user_id = ? 
                           AND status = 'success' AND DATE(timestamp) = ?""", 
                          (user_id, today))
        today_purchases = cursor.fetchone()[0]
        conn.close()
        return {'total_purchases': total_purchases or 0, 'total_stars': total_stars or 0,
                'total_spent_idr': total_spent_idr or 0, 'today_purchases': today_purchases or 0}
    except Exception as e:
        logger.error(f"Error getting user stats: {e}")
        return {'total_purchases': 0, 'total_stars': 0, 'total_spent_idr': 0, 'today_purchases': 0}


async def get_all_stats(bot_token: str = None) -> Dict:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM users')
        total_users = cursor.fetchone()[0]
        today = get_jakarta_date()
        
        if bot_token:
            cursor.execute("""SELECT COUNT(DISTINCT user_id) FROM activity_log 
                           WHERE DATE(timestamp) = ? AND action != 'system' AND bot_token = ?""", 
                          (today, bot_token))
            active_today = cursor.fetchone()[0]
            cursor.execute("""SELECT COUNT(*), COALESCE(SUM(stars_amount), 0), 
                           COALESCE(SUM(price_idr), 0) FROM purchases 
                           WHERE status = 'success' AND bot_token = ?""", (bot_token,))
            total_purchases, total_stars, total_volume_idr = cursor.fetchone()
            cursor.execute("""SELECT COUNT(*), COALESCE(SUM(stars_amount), 0), 
                           COALESCE(SUM(price_idr), 0) FROM purchases 
                           WHERE status = 'success' AND DATE(timestamp) = ? AND bot_token = ?""", 
                          (today, bot_token))
            today_purchases, today_stars, today_volume_idr = cursor.fetchone()
        else:
            cursor.execute("""SELECT COUNT(DISTINCT user_id) FROM activity_log 
                           WHERE DATE(timestamp) = ? AND action != 'system'""", (today,))
            active_today = cursor.fetchone()[0]
            cursor.execute("""SELECT COUNT(*), COALESCE(SUM(stars_amount), 0), 
                           COALESCE(SUM(price_idr), 0) FROM purchases WHERE status = 'success'""")
            total_purchases, total_stars, total_volume_idr = cursor.fetchone()
            cursor.execute("""SELECT COUNT(*), COALESCE(SUM(stars_amount), 0), 
                           COALESCE(SUM(price_idr), 0) FROM purchases 
                           WHERE status = 'success' AND DATE(timestamp) = ?""", (today,))
            today_purchases, today_stars, today_volume_idr = cursor.fetchone()
        
        conn.close()
        return {'total_users': total_users or 0, 'active_today': active_today or 0,
                'total_purchases': total_purchases or 0, 'total_stars': total_stars or 0,
                'total_volume_idr': total_volume_idr or 0, 'today_purchases': today_purchases or 0,
                'today_stars': today_stars or 0, 'today_volume_idr': today_volume_idr or 0}
    except Exception as e:
        logger.error(f"Error getting all stats: {e}")
        return {}


# ===================== CLONED BOT MANAGEMENT FUNCTIONS =====================

async def add_cloned_bot(bot_token: str, bot_username: str, bot_name: str, created_by: int) -> bool:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""INSERT OR REPLACE INTO cloned_bots 
                       (bot_token, bot_username, bot_name, status, created_by, created_at)
                       VALUES (?, ?, ?, 'stopped', ?, ?)""",
                      (bot_token, bot_username, bot_name, created_by, get_jakarta_time_iso()))
        conn.commit()
        conn.close()
        logger.info(f"✅ Bot clone {bot_username} added")
        return True
    except Exception as e:
        logger.error(f"Error adding cloned bot: {e}")
        return False


async def get_cloned_bots(status: str = None) -> List[Dict]:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        if status:
            cursor.execute("""SELECT id, bot_token, bot_username, bot_name, status, created_by, 
                           created_at, last_started, last_stopped, pid FROM cloned_bots 
                           WHERE status = ? ORDER BY created_at DESC""", (status,))
        else:
            cursor.execute("""SELECT id, bot_token, bot_username, bot_name, status, created_by, 
                           created_at, last_started, last_stopped, pid FROM cloned_bots 
                           ORDER BY created_at DESC""")
        rows = cursor.fetchall()
        conn.close()
        return [{'id': r[0], 'bot_token': r[1], 'bot_username': r[2], 'bot_name': r[3], 
                 'status': r[4], 'created_by': r[5], 'created_at': r[6], 
                 'last_started': r[7], 'last_stopped': r[8], 'pid': r[9]} for r in rows]
    except Exception as e:
        logger.error(f"Error getting cloned bots: {e}")
        return []


async def update_bot_status(bot_token: str, status: str, pid: int = None):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now = get_jakarta_time_iso()
        if status == 'running':
            cursor.execute("""UPDATE cloned_bots SET status=?, last_started=?, pid=? 
                           WHERE bot_token=?""", (status, now, pid, bot_token))
        elif status == 'stopped':
            cursor.execute("""UPDATE cloned_bots SET status=?, last_stopped=?, pid=NULL 
                           WHERE bot_token=?""", (status, now, bot_token))
        else:
            cursor.execute("""UPDATE cloned_bots SET status=? WHERE bot_token=?""", 
                          (status, bot_token))
        conn.commit()
        conn.close()
        await add_bot_log(bot_token, "INFO", f"Status changed to {status}")
    except Exception as e:
        logger.error(f"Error updating bot status: {e}")


async def add_bot_log(bot_token: str, log_level: str, message: str):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""INSERT INTO bot_logs (bot_token, log_level, message, timestamp) 
                       VALUES (?, ?, ?, ?)""",
                      (bot_token, log_level, message, get_jakarta_time_iso()))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error adding bot log: {e}")


def add_bot_log_sync(bot_token: str, log_level: str, message: str):
    """Synchronous version of add_bot_log for use in threads"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""INSERT INTO bot_logs (bot_token, log_level, message, timestamp) 
                       VALUES (?, ?, ?, ?)""",
                       (bot_token, log_level, message[:500], get_jakarta_time_iso()))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error adding bot log sync: {e}")


async def remove_cloned_bot(bot_token: str) -> bool:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM cloned_bots WHERE bot_token = ?', (bot_token,))
        cursor.execute('DELETE FROM bot_logs WHERE bot_token = ?', (bot_token,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error removing cloned bot: {e}")
        return False


async def get_bot_users_count(bot_token: str) -> int:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(DISTINCT user_id) FROM purchases WHERE bot_token = ? AND status = 'success'", (bot_token,))
        count = cursor.fetchone()[0]
        conn.close()
        return count or 0
    except Exception as e:
        logger.error(f"Error getting bot users count: {e}")
        return 0


async def get_bot_stats(bot_token: str) -> Dict:
    """Get detailed stats for a specific bot"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Total users yang start/interact dengan bot ini (dari activity_log)
        cursor.execute("SELECT COUNT(DISTINCT user_id) FROM activity_log WHERE bot_token = ?", (bot_token,))
        total_users = cursor.fetchone()[0] or 0
        
        # Total purchases
        cursor.execute("""SELECT COUNT(*), COALESCE(SUM(stars_amount), 0), 
                       COALESCE(SUM(price_idr), 0) FROM purchases 
                       WHERE bot_token = ? AND status = 'success'""", (bot_token,))
        total_purchases, total_stars, total_volume = cursor.fetchone()
        
        today = get_jakarta_date()
        
        # Today's purchases
        cursor.execute("""SELECT COUNT(*), COALESCE(SUM(stars_amount), 0) FROM purchases 
                       WHERE bot_token = ? AND status = 'success' AND DATE(timestamp) = ?""", 
                      (bot_token, today))
        today_purchases, today_stars = cursor.fetchone()
        
        conn.close()
        
        return {
            'total_purchases': total_purchases or 0,
            'total_stars': total_stars or 0,
            'total_volume': total_volume or 0,
            'total_users': total_users or 0,
            'today_purchases': today_purchases or 0,
            'today_stars': today_stars or 0
        }
    except Exception as e:
        logger.error(f"Error getting bot stats: {e}")
        return {}

async def get_bot_logs(bot_username: str, limit: int = 20) -> List[tuple]:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""SELECT log_level, message, timestamp FROM bot_logs 
                       WHERE bot_token IN (SELECT bot_token FROM cloned_bots 
                       WHERE bot_username = ?) ORDER BY timestamp DESC LIMIT ?""", 
                      (bot_username, limit))
        logs = cursor.fetchall()
        conn.close()
        return logs
    except Exception as e:
        logger.error(f"Error getting bot logs: {e}")
        return []
    
async def save_purchase(user_id: int, recipient_username: str, recipient_nickname: str, 
                        stars_amount: int, price_idr: float, price_ton: float, 
                        tx_hash: str = None, show_sender: bool = True, 
                        status: str = "pending", error_message: str = None, 
                        bot_token: str = None):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''INSERT INTO purchases (user_id, recipient_username, recipient_nickname, 
                       stars_amount, price_idr, price_ton, tx_hash, show_sender, status, 
                       error_message, timestamp, bot_token)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                      (user_id, recipient_username, recipient_nickname, stars_amount, 
                       price_idr, price_ton, tx_hash, show_sender, status, error_message, 
                       get_jakarta_time_iso(), bot_token))
        conn.commit()
        conn.close()
        await log_activity(user_id, "purchase", 
                          f"Stars: {stars_amount}, Recipient: @{recipient_username}, Status: {status}", 
                          bot_token=bot_token)
    except Exception as e:
        logger.error(f"Error saving purchase: {e}")
