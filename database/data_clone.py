# database/data_clone.py - Database Functions for Cloned Bot
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
    return datetime.now(JAKARTA_TZ)


def get_jakarta_time_iso():
    return datetime.now(JAKARTA_TZ).isoformat()


def get_jakarta_date():
    return datetime.now(JAKARTA_TZ).date().isoformat()


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
            cursor.execute('''UPDATE users SET username=?, first_name=?, last_name=?, 
                           last_seen=?, is_admin=? WHERE user_id=?''',
                          (username, first_name, last_name, now, is_admin, user_id))
        else:
            cursor.execute('''INSERT INTO users (user_id, username, first_name, last_name, 
                           is_admin, first_seen, last_seen)
                           VALUES (?, ?, ?, ?, ?, ?, ?)''',
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
        cursor.execute('''INSERT INTO activity_log (user_id, action, details, ip_address, 
                       timestamp, bot_token) VALUES (?, ?, ?, ?, ?, ?)''',
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
            cursor.execute('''SELECT COUNT(*), COALESCE(SUM(stars_amount), 0), 
                           COALESCE(SUM(price_idr), 0) FROM purchases 
                           WHERE user_id = ? AND status = 'success' AND bot_token = ?''', 
                          (user_id, bot_token))
        else:
            cursor.execute('''SELECT COUNT(*), COALESCE(SUM(stars_amount), 0), 
                           COALESCE(SUM(price_idr), 0) FROM purchases 
                           WHERE user_id = ? AND status = 'success' ''', (user_id,))
        total_purchases, total_stars, total_spent_idr = cursor.fetchone()
        today = get_jakarta_date()
        if bot_token:
            cursor.execute('''SELECT COUNT(*) FROM purchases WHERE user_id = ? 
                           AND status = 'success' AND DATE(timestamp) = ? AND bot_token = ?''', 
                          (user_id, today, bot_token))
        else:
            cursor.execute('''SELECT COUNT(*) FROM purchases WHERE user_id = ? 
                           AND status = 'success' AND DATE(timestamp) = ?''', 
                          (user_id, today))
        today_purchases = cursor.fetchone()[0]
        conn.close()
        return {'total_purchases': total_purchases or 0, 'total_stars': total_stars or 0,
                'total_spent_idr': total_spent_idr or 0, 'today_purchases': today_purchases or 0}
    except Exception as e:
        logger.error(f"Error getting user stats: {e}")
        return {'total_purchases': 0, 'total_stars': 0, 'total_spent_idr': 0, 'today_purchases': 0}

async def get_all_stats(bot_token: str = None) -> Dict:
    """Get all statistics for cloned bot"""
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

# ===================== DEPOSIT FUNCTIONS =====================

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
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now = get_jakarta_time_iso()
        
        if status == 'completed':
            cursor.execute('''
                UPDATE deposits SET status=?, completed_at=?, updated_at=?, 
                payment_method=COALESCE(?, payment_method) WHERE order_id=?
            ''', (status, completed_at or now, now, payment_method, order_id))
        else:
            cursor.execute('''
                UPDATE deposits SET status=?, updated_at=? WHERE order_id=?
            ''', (status, now, order_id))
        
        conn.commit()
        
        if status == 'completed':
            cursor.execute('SELECT user_id, amount FROM deposits WHERE order_id=?', (order_id,))
            deposit = cursor.fetchone()
            if deposit:
                user_id, amount = deposit
                await add_user_balance(user_id, amount, bot_token)
        
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error updating deposit status: {e}")
        return False


async def get_deposit(order_id: str) -> Optional[Dict]:
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


# ===================== BALANCE FUNCTIONS =====================

async def get_user_balance(user_id: int, bot_token: str = None) -> int:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        if bot_token:
            cursor.execute('''
                SELECT balance FROM user_balances
                WHERE user_id=? AND bot_token=?
            ''', (user_id, bot_token))
        else:
            cursor.execute('SELECT balance FROM user_balances WHERE user_id=?', (user_id,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else 0
    except Exception as e:
        logger.error(f"Error getting user balance: {e}")
        return 0


async def add_user_balance(user_id: int, amount: int, bot_token: str = None) -> bool:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now = get_jakarta_time_iso()
        
        if bot_token:
            cursor.execute('''
                SELECT balance FROM user_balances
                WHERE user_id=? AND bot_token=?
            ''', (user_id, bot_token))
        else:
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
        await log_activity(user_id, "balance_added", f"Added {amount}, New balance: {new_balance if row else amount}", 
                          bot_token=bot_token)
        return True
    except Exception as e:
        logger.error(f"Error adding user balance: {e}")
        return False


async def deduct_user_balance(user_id: int, amount: int, bot_token: str = None) -> bool:
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
        await log_activity(user_id, "balance_deducted", f"Deducted {amount}, New balance: {new_balance}", 
                          bot_token=bot_token)
        return True
    except Exception as e:
        logger.error(f"Error deducting user balance: {e}")
        return False


# ===================== PURCHASE FUNCTIONS =====================

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
