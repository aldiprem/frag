# database/data.py - Database Functions for Fragment Stars Bot
import sqlite3
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
import pytz

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

def get_jakarta_time():
    """Get current datetime in Asia/Jakarta timezone"""
    return datetime.now(JAKARTA_TZ)

def get_jakarta_time_iso():
    """Get current datetime in ISO format with Asia/Jakarta timezone"""
    return datetime.now(JAKARTA_TZ).isoformat()

def get_jakarta_date():
    """Get current date in Asia/Jakarta timezone"""
    return datetime.now(JAKARTA_TZ).date().isoformat()

async def create_deposit(
    user_id: int,
    order_id: str,
    amount: int,
    payment_method: str,
    qr_string: str = None,
    payment_number: str = None,
    total_payment: int = None,
    expired_at: str = None,
    waiting_msg_id: int = None,
    bot_token: str = None
) -> bool:
    """Create a new deposit record"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now = get_jakarta_time_iso()
        cursor.execute('''
            INSERT INTO deposits (
                user_id, order_id, amount, total_payment, payment_method,
                payment_number, qr_string, status, expired_at, created_at, 
                updated_at, waiting_msg_id, bot_token
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id, order_id, amount, total_payment, payment_method,
            payment_number, qr_string, 'pending', expired_at, now, now,
            waiting_msg_id, bot_token
        ))
        conn.commit()
        conn.close()
        await log_activity(user_id, "deposit_created", f"Amount: {amount}, Order: {order_id}", bot_token=bot_token)
        return True
    except Exception as e:
        logger.error(f"Error creating deposit: {e}")
        return False

async def update_deposit_status(
    order_id: str,
    status: str,
    completed_at: str = None,
    payment_method: str = None,
    bot_token: str = None
) -> bool:
    """Update deposit status when payment completed"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now = get_jakarta_time_iso()
        
        if status == 'completed':
            cursor.execute('''
                UPDATE deposits SET status=?, completed_at=?, updated_at=?, payment_method=COALESCE(?, payment_method)
                WHERE order_id=?
            ''', (status, completed_at or now, now, payment_method, order_id))
        else:
            cursor.execute('''
                UPDATE deposits SET status=?, updated_at=? WHERE order_id=?
            ''', (status, now, order_id))
        
        conn.commit()
        
        # If completed, update user balance
        if status == 'completed':
            cursor.execute('SELECT user_id, amount FROM deposits WHERE order_id=?', (order_id,))
            deposit = cursor.fetchone()
            if deposit:
                user_id, amount = deposit
                # Update balance
                await add_user_balance(user_id, amount, bot_token)
        
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error updating deposit status: {e}")
        return False

def parse_pakasir_time(time_str: str) -> datetime:
    """Parse Pakasir time format to datetime object"""
    try:
        # Format: 2026-03-27T07:25:08.608551003Z
        # Hapus Z dan parse
        time_str_clean = time_str.replace('Z', '+00:00')
        dt = datetime.fromisoformat(time_str_clean)
        # Konversi ke Jakarta timezone
        return dt.astimezone(JAKARTA_TZ)
    except:
        try:
            return datetime.fromisoformat(time_str)
        except:
            return get_jakarta_time()

async def get_deposit(order_id: str) -> Optional[Dict]:
    """Get deposit by order_id"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, user_id, order_id, amount, total_payment, payment_method,
                   payment_number, qr_string, status, expired_at, completed_at,
                   created_at, updated_at, waiting_msg_id, bot_token
            FROM deposits WHERE order_id=?
        ''', (order_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {
                'id': row[0], 'user_id': row[1], 'order_id': row[2], 'amount': row[3],
                'total_payment': row[4], 'payment_method': row[5], 'payment_number': row[6],
                'qr_string': row[7], 'status': row[8], 'expired_at': row[9],
                'completed_at': row[10], 'created_at': row[11], 'updated_at': row[12],
                'waiting_msg_id': row[13], 'bot_token': row[14]
            }
        return None
    except Exception as e:
        logger.error(f"Error getting deposit: {e}")
        return None

async def get_user_deposits(user_id: int, bot_token: str = None, limit: int = 20) -> List[Dict]:
    """Get user's deposit history"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        if bot_token:
            cursor.execute('''
                SELECT order_id, amount, total_payment, payment_method, status,
                       created_at, completed_at
                FROM deposits WHERE user_id=? AND bot_token=?
                ORDER BY created_at DESC LIMIT ?
            ''', (user_id, bot_token, limit))
        else:
            cursor.execute('''
                SELECT order_id, amount, total_payment, payment_method, status,
                       created_at, completed_at
                FROM deposits WHERE user_id=?
                ORDER BY created_at DESC LIMIT ?
            ''', (user_id, limit))
        rows = cursor.fetchall()
        conn.close()
        return [{
            'order_id': r[0], 'amount': r[1], 'total_payment': r[2],
            'payment_method': r[3], 'status': r[4], 'created_at': r[5],
            'completed_at': r[6]
        } for r in rows]
    except Exception as e:
        logger.error(f"Error getting user deposits: {e}")
        return []


async def get_user_balance(user_id: int, bot_token: str = None) -> int:
    """Get user's current balance"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        if bot_token:
            cursor.execute('''
                SELECT balance FROM user_balances
                WHERE user_id=? AND bot_token=?
            ''', (user_id, bot_token))
        else:
            # Perbaiki baris ini juga
            cursor.execute('SELECT balance FROM user_balances WHERE user_id=?', (user_id,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else 0
    except Exception as e:
        logger.error(f"Error getting user balance: {e}")
        return 0

async def add_user_balance(user_id: int, amount: int, bot_token: str = None) -> bool:
    """Add balance to user"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now = get_jakarta_time_iso()
        
        # Check if exists
        if bot_token:
            cursor.execute('''
                SELECT balance FROM user_balances
                WHERE user_id=? AND bot_token=?
            ''', (user_id, bot_token))
        else:
            # Perbaiki baris ini - gunakan single quote
            cursor.execute('SELECT balance FROM user_balances WHERE user_id=?', (user_id,))
        
        row = cursor.fetchone()
        
        if row:
            new_balance = row[0] + amount
            if bot_token:
                cursor.execute('''
                    UPDATE user_balances SET balance=?, last_updated=?
                    WHERE user_id=? AND bot_token=?
                ''', (new_balance, now, user_id, bot_token))
            else:
                cursor.execute('''
                    UPDATE user_balances SET balance=?, last_updated=?
                    WHERE user_id=?
                ''', (new_balance, now, user_id))
        else:
            if bot_token:
                cursor.execute('''
                    INSERT INTO user_balances (user_id, balance, last_updated, bot_token)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, amount, now, bot_token))
            else:
                cursor.execute('''
                    INSERT INTO user_balances (user_id, balance, last_updated)
                    VALUES (?, ?, ?)
                ''', (user_id, amount, now))
        
        conn.commit()
        conn.close()
        await log_activity(user_id, "balance_added", f"Added {amount}, New balance: {new_balance if row else amount}", bot_token=bot_token)
        return True
    except Exception as e:
        logger.error(f"Error adding user balance: {e}")
        return False


async def deduct_user_balance(user_id: int, amount: int, bot_token: str = None) -> bool:
    """Deduct balance from user"""
    try:
        current = await get_user_balance(user_id, bot_token)
        if current < amount:
            return False
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now = get_jakarta_time_iso()
        new_balance = current - amount
        
        if bot_token:
            cursor.execute('''
                UPDATE user_balances SET balance=?, last_updated=?
                WHERE user_id=? AND bot_token=?
            ''', (new_balance, now, user_id, bot_token))
        else:
            cursor.execute('''
                UPDATE user_balances SET balance=?, last_updated=?
                WHERE user_id=?
            ''', (new_balance, now, user_id))
        
        conn.commit()
        conn.close()
        await log_activity(user_id, "balance_deducted", f"Deducted {amount}, New balance: {new_balance}", bot_token=bot_token)
        return True
    except Exception as e:
        logger.error(f"Error deducting user balance: {e}")
        return False

async def save_user(user_id: int, username: str = None, first_name: str = None, last_name: str = None, bot_token: str = None, admin_ids: list = None):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        existing = cursor.fetchone()
        now = get_jakarta_time_iso()
        is_admin = 1 if admin_ids and user_id in admin_ids else 0
        
        if existing:
            cursor.execute('''UPDATE users SET username=?, first_name=?, last_name=?, last_seen=?, is_admin=? WHERE user_id=?''',
                          (username, first_name, last_name, now, is_admin, user_id))
        else:
            cursor.execute('''INSERT INTO users (user_id, username, first_name, last_name, is_admin, first_seen, last_seen)
                           VALUES (?, ?, ?, ?, ?, ?, ?)''',
                          (user_id, username, first_name, last_name, is_admin, now, now))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error saving user: {e}")


async def log_activity(user_id: int, action: str, details: str = None, ip: str = None, bot_token: str = None):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''INSERT INTO activity_log (user_id, action, details, ip_address, timestamp, bot_token)
                       VALUES (?, ?, ?, ?, ?, ?)''',
                      (user_id, action, details, ip, get_jakarta_time_iso(), bot_token))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error logging activity: {e}")


async def save_purchase(user_id: int, recipient_username: str, recipient_nickname: str, stars_amount: int, 
                        price_idr: float, price_ton: float, tx_hash: str = None, show_sender: bool = True, 
                        status: str = "pending", error_message: str = None, bot_token: str = None):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''INSERT INTO purchases (user_id, recipient_username, recipient_nickname, stars_amount, 
                       price_idr, price_ton, tx_hash, show_sender, status, error_message, timestamp, bot_token)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                      (user_id, recipient_username, recipient_nickname, stars_amount, price_idr, price_ton,
                       tx_hash, show_sender, status, error_message, get_jakarta_time_iso(), bot_token))
        conn.commit()
        conn.close()
        await log_activity(user_id, "purchase", f"Stars: {stars_amount}, Recipient: @{recipient_username}, Status: {status}", bot_token=bot_token)
    except Exception as e:
        logger.error(f"Error saving purchase: {e}")


async def get_user_stats(user_id: int, bot_token: str = None) -> Dict:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        if bot_token:
            cursor.execute('''SELECT COUNT(*), COALESCE(SUM(stars_amount), 0), COALESCE(SUM(price_idr), 0)
                           FROM purchases WHERE user_id = ? AND status = 'success' AND bot_token = ?''', (user_id, bot_token))
        else:
            cursor.execute('''SELECT COUNT(*), COALESCE(SUM(stars_amount), 0), COALESCE(SUM(price_idr), 0)
                           FROM purchases WHERE user_id = ? AND status = 'success' ''', (user_id,))
        total_purchases, total_stars, total_spent_idr = cursor.fetchone()
        today = get_jakarta_date()
        if bot_token:
            cursor.execute('''SELECT COUNT(*) FROM purchases WHERE user_id = ? AND status = 'success' 
                           AND DATE(timestamp) = ? AND bot_token = ?''', (user_id, today, bot_token))
        else:
            cursor.execute('''SELECT COUNT(*) FROM purchases WHERE user_id = ? AND status = 'success' 
                           AND DATE(timestamp) = ?''', (user_id, today))
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
            cursor.execute('''SELECT COUNT(DISTINCT user_id) FROM activity_log 
                           WHERE DATE(timestamp) = ? AND action != 'system' AND bot_token = ?''', (today, bot_token))
            active_today = cursor.fetchone()[0]
            cursor.execute('''SELECT COUNT(*), COALESCE(SUM(stars_amount), 0), COALESCE(SUM(price_idr), 0)
                           FROM purchases WHERE status = 'success' AND bot_token = ?''', (bot_token,))
            total_purchases, total_stars, total_volume_idr = cursor.fetchone()
            cursor.execute('''SELECT COUNT(*), COALESCE(SUM(stars_amount), 0), COALESCE(SUM(price_idr), 0)
                           FROM purchases WHERE status = 'success' AND DATE(timestamp) = ? AND bot_token = ?''', (today, bot_token))
            today_purchases, today_stars, today_volume_idr = cursor.fetchone()
        else:
            cursor.execute('''SELECT COUNT(DISTINCT user_id) FROM activity_log 
                           WHERE DATE(timestamp) = ? AND action != 'system' ''', (today,))
            active_today = cursor.fetchone()[0]
            cursor.execute('''SELECT COUNT(*), COALESCE(SUM(stars_amount), 0), COALESCE(SUM(price_idr), 0)
                           FROM purchases WHERE status = 'success' ''')
            total_purchases, total_stars, total_volume_idr = cursor.fetchone()
            cursor.execute('''SELECT COUNT(*), COALESCE(SUM(stars_amount), 0), COALESCE(SUM(price_idr), 0)
                           FROM purchases WHERE status = 'success' AND DATE(timestamp) = ?''', (today,))
            today_purchases, today_stars, today_volume_idr = cursor.fetchone()
        
        conn.close()
        return {'total_users': total_users or 0, 'active_today': active_today or 0,
                'total_purchases': total_purchases or 0, 'total_stars': total_stars or 0,
                'total_volume_idr': total_volume_idr or 0, 'today_purchases': today_purchases or 0,
                'today_stars': today_stars or 0, 'today_volume_idr': today_volume_idr or 0}
    except Exception as e:
        logger.error(f"Error getting all stats: {e}")
        return {}


async def add_cloned_bot(bot_token: str, bot_username: str, bot_name: str, created_by: int) -> bool:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''INSERT OR REPLACE INTO cloned_bots (bot_token, bot_username, bot_name, status, created_by, created_at)
                       VALUES (?, ?, ?, 'stopped', ?, ?)''',
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
            cursor.execute('''SELECT id, bot_token, bot_username, bot_name, status, created_by, created_at, 
                           last_started, last_stopped, pid FROM cloned_bots WHERE status = ? ORDER BY created_at DESC''', (status,))
        else:
            cursor.execute('''SELECT id, bot_token, bot_username, bot_name, status, created_by, created_at, 
                           last_started, last_stopped, pid FROM cloned_bots ORDER BY created_at DESC''')
        rows = cursor.fetchall()
        conn.close()
        return [{'id': r[0], 'bot_token': r[1], 'bot_username': r[2], 'bot_name': r[3], 'status': r[4],
                 'created_by': r[5], 'created_at': r[6], 'last_started': r[7], 'last_stopped': r[8], 'pid': r[9]} for r in rows]
    except Exception as e:
        logger.error(f"Error getting cloned bots: {e}")
        return []


async def update_bot_status(bot_token: str, status: str, pid: int = None):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now = get_jakarta_time_iso()
        if status == 'running':
            cursor.execute('''UPDATE cloned_bots SET status=?, last_started=?, pid=? WHERE bot_token=?''',
                          (status, now, pid, bot_token))
        elif status == 'stopped':
            cursor.execute('''UPDATE cloned_bots SET status=?, last_stopped=?, pid=NULL WHERE bot_token=?''',
                          (status, now, bot_token))
        else:
            cursor.execute('''UPDATE cloned_bots SET status=? WHERE bot_token=?''', (status, bot_token))
        conn.commit()
        conn.close()
        await add_bot_log(bot_token, "INFO", f"Status changed to {status}")
    except Exception as e:
        logger.error(f"Error updating bot status: {e}")


async def add_bot_log(bot_token: str, log_level: str, message: str):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''INSERT INTO bot_logs (bot_token, log_level, message, timestamp) VALUES (?, ?, ?, ?)''',
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
        cursor.execute('''INSERT INTO bot_logs (bot_token, log_level, message, timestamp) 
                       VALUES (?, ?, ?, ?)''',
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
    """Get total users who purchased from specific bot"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(DISTINCT user_id) FROM purchases WHERE bot_token = ? AND status = "success"', (bot_token,))
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
        cursor.execute('''SELECT COUNT(*), COALESCE(SUM(stars_amount), 0), COALESCE(SUM(price_idr), 0)
                       FROM purchases WHERE bot_token = ? AND status = "success"''', (bot_token,))
        total_purchases, total_stars, total_volume = cursor.fetchone()
        
        cursor.execute('SELECT COUNT(DISTINCT user_id) FROM purchases WHERE bot_token = ? AND status = "success"', (bot_token,))
        total_users = cursor.fetchone()[0]
        
        today = get_jakarta_date()
        cursor.execute('''SELECT COUNT(*), COALESCE(SUM(stars_amount), 0)
                       FROM purchases WHERE bot_token = ? AND status = "success" AND DATE(timestamp) = ?''', 
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
    """Get logs for a specific bot"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''SELECT log_level, message, timestamp FROM bot_logs 
                       WHERE bot_token IN (SELECT bot_token FROM cloned_bots WHERE bot_username = ?)
                       ORDER BY timestamp DESC LIMIT ?''', (bot_username, limit))
        logs = cursor.fetchall()
        conn.close()
        return logs
    except Exception as e:
        logger.error(f"Error getting bot logs: {e}")
        return []
