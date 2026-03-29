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

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bot_bank_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_token TEXT NOT NULL,
            bank_name TEXT,
            account_number TEXT,
            account_name TEXT,
            is_active BOOLEAN DEFAULT 0,
            created_at TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY (bot_token) REFERENCES cloned_bots(bot_token)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bot_qris (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_token TEXT NOT NULL,
            qr_string TEXT,
            qr_name TEXT,
            qr_note TEXT,
            fee REAL DEFAULT 0,
            is_active BOOLEAN DEFAULT 0,
            created_at TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY (bot_token) REFERENCES cloned_bots(bot_token)
        )
    ''')
    
    conn.commit()
    logger.info("✅ Database initialized successfully")


JAKARTA_TZ = pytz.timezone('Asia/Jakarta')


def get_jakarta_time():
    return datetime.now(JAKARTA_TZ)


def get_jakarta_time_iso():
    return datetime.now(JAKARTA_TZ).isoformat()


def get_jakarta_date():
    return datetime.now(JAKARTA_TZ).date().isoformat()

# ===================== BANK ACCOUNT FUNCTIONS =====================

async def add_bank_account(bot_token: str, bank_name: str, account_number: str, account_name: str) -> bool:
    """Add bank account for bot"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now = get_jakarta_time_iso()
        cursor.execute("""
            INSERT INTO bot_bank_accounts (bot_token, bank_name, account_number, account_name, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (bot_token, bank_name, account_number, account_name, now, now))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error adding bank account: {e}")
        return False


async def delete_bank_account(bot_token: str, account_id: int) -> bool:
    """Delete bank account"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM bot_bank_accounts WHERE id = ? AND bot_token = ?", (account_id, bot_token))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error deleting bank account: {e}")
        return False


async def get_bank_accounts(bot_token: str) -> List[Dict]:
    """Get all bank accounts for bot"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, bank_name, account_number, account_name, is_active, created_at, updated_at
            FROM bot_bank_accounts WHERE bot_token = ? ORDER BY id ASC
        """, (bot_token,))
        rows = cursor.fetchall()
        conn.close()
        return [{
            'id': r[0], 'bank_name': r[1], 'account_number': r[2],
            'account_name': r[3], 'is_active': r[4], 'created_at': r[5], 'updated_at': r[6]
        } for r in rows]
    except Exception as e:
        logger.error(f"Error getting bank accounts: {e}")
        return []


async def set_active_bank_account(bot_token: str, account_id: int) -> bool:
    """Set active bank account (deactivate others first)"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now = get_jakarta_time_iso()
        # Deactivate all
        cursor.execute("UPDATE bot_bank_accounts SET is_active = 0, updated_at = ? WHERE bot_token = ?", (now, bot_token))
        # Activate selected
        cursor.execute("UPDATE bot_bank_accounts SET is_active = 1, updated_at = ? WHERE id = ? AND bot_token = ?", 
                      (now, account_id, bot_token))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error setting active bank account: {e}")
        return False


# ===================== QRIS FUNCTIONS =====================

async def add_qris(bot_token: str, qr_string: str, qr_name: str = None) -> bool:
    """Add or update QRIS for bot (only one QRIS per bot)"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now = get_jakarta_time_iso()
        
        # Cek apakah sudah ada QRIS untuk bot ini
        cursor.execute("SELECT id FROM bot_qris WHERE bot_token = ?", (bot_token,))
        existing = cursor.fetchone()
        
        if existing:
            # Update QRIS yang sudah ada
            cursor.execute("""
                UPDATE bot_qris 
                SET qr_string = ?, qr_name = ?, updated_at = ? 
                WHERE bot_token = ?
            """, (qr_string, qr_name, now, bot_token))
            logger.info(f"QRIS updated for bot {bot_token}")
        else:
            # Insert QRIS baru
            cursor.execute("""
                INSERT INTO bot_qris (bot_token, qr_string, qr_name, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """, (bot_token, qr_string, qr_name, now, now))
            logger.info(f"QRIS added for bot {bot_token}")
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error adding/updating QRIS: {e}")
        return False

async def update_qris_name(bot_token: str, qris_id: int, qr_name: str) -> bool:
    """Update QRIS name"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now = get_jakarta_time_iso()
        cursor.execute("""
            UPDATE bot_qris SET qr_name = ?, updated_at = ? WHERE id = ? AND bot_token = ?
        """, (qr_name, now, qris_id, bot_token))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error updating QRIS name: {e}")
        return False


async def update_qris_note(bot_token: str, qris_id: int, note: str) -> bool:
    """Update QRIS note"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now = get_jakarta_time_iso()
        cursor.execute("""
            UPDATE bot_qris SET qr_note = ?, updated_at = ? WHERE id = ? AND bot_token = ?
        """, (note, now, qris_id, bot_token))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error updating QRIS note: {e}")
        return False


async def update_qris_fee(bot_token: str, qris_id: int, fee: float) -> bool:
    """Update QRIS fee"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now = get_jakarta_time_iso()
        cursor.execute("""
            UPDATE bot_qris SET fee = ?, updated_at = ? WHERE id = ? AND bot_token = ?
        """, (fee, now, qris_id, bot_token))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error updating QRIS fee: {e}")
        return False


async def delete_qris(bot_token: str, qris_id: int) -> bool:
    """Delete QRIS"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM bot_qris WHERE id = ? AND bot_token = ?", (qris_id, bot_token))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error deleting QRIS: {e}")
        return False


async def get_qris_list(bot_token: str) -> List[Dict]:
    """Get all QRIS for bot"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, qr_string, qr_name, qr_note, fee, is_active, created_at, updated_at
            FROM bot_qris WHERE bot_token = ? ORDER BY id ASC
        """, (bot_token,))
        rows = cursor.fetchall()
        conn.close()
        return [{
            'id': r[0], 'qr_string': r[1], 'qr_name': r[2], 'qr_note': r[3],
            'fee': r[4], 'is_active': r[5], 'created_at': r[6], 'updated_at': r[7]
        } for r in rows]
    except Exception as e:
        logger.error(f"Error getting QRIS list: {e}")
        return []

async def get_active_qris(bot_token: str) -> Optional[Dict]:
    """Get active QRIS for bot"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, qr_string, qr_name, qr_note, fee, created_at, updated_at
            FROM bot_qris WHERE bot_token = ? AND is_active = 1
        """, (bot_token,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {
                'id': row[0], 'qr_string': row[1], 'qr_name': row[2],
                'qr_note': row[3], 'fee': row[4], 'created_at': row[5], 'updated_at': row[6]
            }
        return None
    except Exception as e:
        logger.error(f"Error getting active QRIS: {e}")
        return None

async def set_active_qris(bot_token: str, qris_id: int) -> bool:
    """Set active QRIS (deactivate others first)"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now = get_jakarta_time_iso()
        
        if qris_id == 0:
            # Nonaktifkan semua
            cursor.execute("UPDATE bot_qris SET is_active = 0, updated_at = ? WHERE bot_token = ?", (now, bot_token))
        else:
            # Deactivate all
            cursor.execute("UPDATE bot_qris SET is_active = 0, updated_at = ? WHERE bot_token = ?", (now, bot_token))
            # Activate selected
            cursor.execute("UPDATE bot_qris SET is_active = 1, updated_at = ? WHERE id = ? AND bot_token = ?", 
                          (now, qris_id, bot_token))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error setting active QRIS: {e}")
        return False

async def toggle_qris_active(bot_token: str) -> bool:
    """Toggle QRIS active status"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now = get_jakarta_time_iso()
        
        # Cek apakah ada QRIS aktif
        cursor.execute("SELECT id FROM bot_qris WHERE bot_token = ? AND is_active = 1", (bot_token,))
        active = cursor.fetchone()
        
        if active:
            # Jika ada yang aktif, nonaktifkan semua
            cursor.execute("UPDATE bot_qris SET is_active = 0, updated_at = ? WHERE bot_token = ?", (now, bot_token))
        else:
            # Jika tidak ada yang aktif, aktifkan QRIS pertama
            cursor.execute("SELECT id FROM bot_qris WHERE bot_token = ? ORDER BY id ASC LIMIT 1", (bot_token,))
            first_qris = cursor.fetchone()
            if first_qris:
                cursor.execute("UPDATE bot_qris SET is_active = 1, updated_at = ? WHERE id = ?", (now, first_qris[0]))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error toggling QRIS active: {e}")
        return False

# ===================== USER FUNCTIONS =====================

# database/data_clone.py - Pastikan conn.close() dipanggil
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
        logger.info(f"User {user_id} saved successfully")
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
    except Exception as e:
        logger.error(f"Error logging activity: {e}")

# database/data_clone.py - Perbaiki get_user_stats
async def get_user_stats(user_id: int, bot_token: str = None) -> Dict:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Get purchase stats
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
        
        # Get user info
        cursor.execute("SELECT username, first_name, last_name FROM users WHERE user_id = ?", (user_id,))
        user_row = cursor.fetchone()
        
        conn.close()
        
        return {
            'total_purchases': total_purchases or 0, 
            'total_stars': total_stars or 0,
            'total_spent_idr': total_spent_idr or 0, 
            'today_purchases': today_purchases or 0,
            'username': user_row[0] if user_row else None,
            'first_name': user_row[1] if user_row else None,
            'last_name': user_row[2] if user_row else None
        }
    except Exception as e:
        logger.error(f"Error getting user stats: {e}")
        return {'total_purchases': 0, 'total_stars': 0, 'total_spent_idr': 0, 'today_purchases': 0}

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
        
        # Ambil user_id dan amount sebelum update
        cursor.execute('SELECT user_id, amount FROM deposits WHERE order_id=?', (order_id,))
        deposit_data = cursor.fetchone()
        
        if status == 'completed':
            cursor.execute("""
                UPDATE deposits SET status=?, completed_at=?, updated_at=?, 
                payment_method=COALESCE(?, payment_method) WHERE order_id=?
            """, (status, completed_at or now, now, payment_method, order_id))
        else:
            cursor.execute("""
                UPDATE deposits SET status=?, updated_at=? WHERE order_id=?
            """, (status, now, order_id))
        
        conn.commit()
        
        # If completed, update user balance
        if status == 'completed' and deposit_data:
            user_id, amount = deposit_data
            logger.info(f"Updating balance for user {user_id} with amount {amount}")
            success = await add_user_balance(user_id, amount, bot_token)
            logger.info(f"Balance update result: {success}")
        
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
            cursor.execute("""
                SELECT balance FROM user_balances
                WHERE user_id=? AND bot_token=?
            """, (user_id, bot_token))
        else:
            cursor.execute("SELECT balance FROM user_balances WHERE user_id=?", (user_id,))
        row = cursor.fetchone()

        balance = row[0] if row else 0
        logger.info(f"Balance for user {user_id}: {balance}")
        return balance
    except Exception as e:
        logger.error(f"Error getting user balance: {e}")
        return 0

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
        
        return {'total_users': total_users or 0, 'active_today': active_today or 0,
                'total_purchases': total_purchases or 0, 'total_stars': total_stars or 0,
                'total_volume_idr': total_volume_idr or 0, 'today_purchases': today_purchases or 0,
                'today_stars': today_stars or 0, 'today_volume_idr': today_volume_idr or 0}
    except Exception as e:
        logger.error(f"Error getting all stats: {e}")
        return {}

async def add_user_balance(user_id: int, amount: int, bot_token: str = None) -> bool:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now = get_jakarta_time_iso()
        
        logger.info(f"Adding balance: user={user_id}, amount={amount}, bot_token={bot_token}")
        
        # Check if exists
        if bot_token:
            cursor.execute("""
                SELECT balance FROM user_balances
                WHERE user_id=? AND bot_token=?
            """, (user_id, bot_token))
        else:
            cursor.execute("SELECT balance FROM user_balances WHERE user_id=?", (user_id,))
        
        row = cursor.fetchone()
        
        if row:
            new_balance = row[0] + amount
            if bot_token:
                cursor.execute("""
                    UPDATE user_balances SET balance=?, last_updated=?
                    WHERE user_id=? AND bot_token=?
                """, (new_balance, now, user_id, bot_token))
            else:
                cursor.execute("""
                    UPDATE user_balances SET balance=?, last_updated=?
                    WHERE user_id=?
                """, (new_balance, now, user_id))
            logger.info(f"Updated balance: {row[0]} -> {new_balance}")
        else:
            if bot_token:
                cursor.execute("""
                    INSERT INTO user_balances (user_id, balance, last_updated, bot_token)
                    VALUES (?, ?, ?, ?)
                """, (user_id, amount, now, bot_token))
            else:
                cursor.execute("""
                    INSERT INTO user_balances (user_id, balance, last_updated)
                    VALUES (?, ?, ?)
                """, (user_id, amount, now))
            logger.info(f"Created new balance entry with {amount}")
        
        conn.commit()
        
        # Verify the update
        new_balance_check = await get_user_balance(user_id, bot_token)
        logger.info(f"Verified balance after update: {new_balance_check}")
        
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
        await log_activity(user_id, "purchase", 
                          f"Stars: {stars_amount}, Recipient: @{recipient_username}, Status: {status}", 
                          bot_token=bot_token)
    except Exception as e:
        logger.error(f"Error saving purchase: {e}")
