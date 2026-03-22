# b.py - Fragment Stars Bot Master with Clone System
import os
import json
import base64
import asyncio
import logging
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
from telethon.extensions.markdown import DEFAULT_DELIMITERS
from telethon.tl.types import MessageEntityBlockquote
import aiohttp
from dotenv import load_dotenv
from telethon import TelegramClient, events, Button

# Import tonutils
from tonutils.client import TonapiClient
from tonutils.wallet import WalletV5R1

# ===================== LOAD ENVIRONMENT VARIABLES =====================
env_path = Path('.') / '.env'
load_dotenv(dotenv_path=env_path)
print(f"Loading .env from: {env_path.absolute()}")
print(f"File exists: {env_path.exists()}")

# ===================== KONFIGURASI =====================
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

ADMIN_IDS = [int(id) for id in os.getenv("ADMIN_IDS", "").split(",") if id]

PRICE_PER_STAR = float(os.getenv("PRICE_PER_STAR", 0.01))
MIN_STARS = int(os.getenv("MIN_STARS", 10))
MAX_STARS = int(os.getenv("MAX_STARS", 100000))
DEFAULT_DELIMITERS['^^'] = lambda *a, **k: MessageEntityBlockquote(*a, **k, collapsed=True)
COOKIES = os.getenv("COOKIES", "")
HASH = os.getenv("HASH", "")

WALLET_API_KEY = os.getenv("WALLET_API_KEY", "")
WALLET_MNEMONIC_STR = os.getenv("WALLET_MNEMONIC", "[]")

try:
    WALLET_MNEMONIC = json.loads(WALLET_MNEMONIC_STR)
    print(f"✅ Loaded {len(WALLET_MNEMONIC)} mnemonic words")
except Exception as e:
    print(f"❌ Failed to parse WALLET_MNEMONIC: {e}")
    WALLET_MNEMONIC = []

# Database configuration
DB_PATH = "frag.db"

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Store running bot processes
running_bots: Dict[str, subprocess.Popen] = {}

# ===================== DATABASE FUNCTIONS =====================

def init_database():
    """Inisialisasi database SQLite3."""
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
            price REAL,
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
    
    conn.commit()
    conn.close()
    logger.info("✅ Database initialized successfully")


async def save_user(user_id: int, username: str = None, first_name: str = None, last_name: str = None):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        existing = cursor.fetchone()
        now = datetime.now().isoformat()
        is_admin = 1 if user_id in ADMIN_IDS else 0
        
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
                      (user_id, action, details, ip, datetime.now().isoformat(), bot_token or BOT_TOKEN))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error logging activity: {e}")


async def save_purchase(user_id: int, recipient_username: str, recipient_nickname: str, stars_amount: int, 
                        price_ton: float, tx_hash: str = None, show_sender: bool = True, 
                        status: str = "pending", error_message: str = None, bot_token: str = None):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''INSERT INTO purchases (user_id, recipient_username, recipient_nickname, stars_amount, 
                       price_ton, tx_hash, show_sender, status, error_message, timestamp, bot_token)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                      (user_id, recipient_username, recipient_nickname, stars_amount, price_ton,
                       tx_hash, show_sender, status, error_message, datetime.now().isoformat(), bot_token or BOT_TOKEN))
        conn.commit()
        conn.close()
        await log_activity(user_id, "purchase", f"Stars: {stars_amount}, Recipient: @{recipient_username}, Status: {status}", bot_token=bot_token)
    except Exception as e:
        logger.error(f"Error saving purchase: {e}")


async def get_user_stats(user_id: int) -> Dict:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''SELECT COUNT(*), COALESCE(SUM(stars_amount), 0), COALESCE(SUM(price_ton), 0)
                       FROM purchases WHERE user_id = ? AND status = 'success' ''', (user_id,))
        total_purchases, total_stars, total_spent = cursor.fetchone()
        today = datetime.now().date().isoformat()
        cursor.execute('''SELECT COUNT(*) FROM purchases WHERE user_id = ? AND status = 'success' AND DATE(timestamp) = ?''',
                      (user_id, today))
        today_purchases = cursor.fetchone()[0]
        conn.close()
        return {'total_purchases': total_purchases or 0, 'total_stars': total_stars or 0,
                'total_spent': total_spent or 0, 'today_purchases': today_purchases or 0}
    except Exception as e:
        logger.error(f"Error getting user stats: {e}")
        return {'total_purchases': 0, 'total_stars': 0, 'total_spent': 0, 'today_purchases': 0}


async def get_all_stats() -> Dict:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM users')
        total_users = cursor.fetchone()[0]
        today = datetime.now().date().isoformat()
        cursor.execute('''SELECT COUNT(DISTINCT user_id) FROM activity_log WHERE DATE(timestamp) = ? AND action != 'system' ''', (today,))
        active_today = cursor.fetchone()[0]
        cursor.execute('''SELECT COUNT(*), COALESCE(SUM(stars_amount), 0), COALESCE(SUM(price_ton), 0)
                       FROM purchases WHERE status = 'success' ''')
        total_purchases, total_stars, total_volume = cursor.fetchone()
        cursor.execute('''SELECT COUNT(*), COALESCE(SUM(stars_amount), 0), COALESCE(SUM(price_ton), 0)
                       FROM purchases WHERE status = 'success' AND DATE(timestamp) = ?''', (today,))
        today_purchases, today_stars, today_volume = cursor.fetchone()
        conn.close()
        return {'total_users': total_users or 0, 'active_today': active_today or 0,
                'total_purchases': total_purchases or 0, 'total_stars': total_stars or 0,
                'total_volume': total_volume or 0, 'today_purchases': today_purchases or 0,
                'today_stars': today_stars or 0, 'today_volume': today_volume or 0}
    except Exception as e:
        logger.error(f"Error getting all stats: {e}")
        return {}


# ===================== CLONED BOT DATABASE FUNCTIONS =====================

async def add_cloned_bot(bot_token: str, bot_username: str, bot_name: str, created_by: int) -> bool:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''INSERT OR REPLACE INTO cloned_bots (bot_token, bot_username, bot_name, status, created_by, created_at)
                       VALUES (?, ?, ?, 'stopped', ?, ?)''',
                      (bot_token, bot_username, bot_name, created_by, datetime.now().isoformat()))
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
        now = datetime.now().isoformat()
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
                      (bot_token, log_level, message, datetime.now().isoformat()))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error adding bot log: {e}")


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


# ===================== BOT CLONE MANAGEMENT =====================

def get_bot_script_path() -> str:
    return os.path.abspath(__file__)


async def start_cloned_bot(bot_token: str, bot_username: str) -> bool:
    try:
        if bot_token in running_bots:
            proc = running_bots[bot_token]
            if proc.poll() is None:
                logger.info(f"Bot {bot_username} already running")
                return True
        
        env = os.environ.copy()
        env["BOT_TOKEN"] = bot_token
        env["IS_CLONE"] = "true"
        env["MASTER_BOT_TOKEN"] = BOT_TOKEN
        
        proc = subprocess.Popen([sys.executable, get_bot_script_path()], env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        running_bots[bot_token] = proc
        await update_bot_status(bot_token, 'running', proc.pid)
        logger.info(f"✅ Started cloned bot: {bot_username} (PID: {proc.pid})")
        asyncio.create_task(monitor_bot_process(bot_token, bot_username, proc))
        return True
    except Exception as e:
        logger.error(f"Error starting cloned bot: {e}")
        await update_bot_status(bot_token, 'error')
        return False


async def stop_cloned_bot(bot_token: str, bot_username: str) -> bool:
    try:
        if bot_token in running_bots:
            proc = running_bots[bot_token]
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
            del running_bots[bot_token]
        await update_bot_status(bot_token, 'stopped')
        logger.info(f"✅ Stopped cloned bot: {bot_username}")
        return True
    except Exception as e:
        logger.error(f"Error stopping cloned bot: {e}")
        return False


async def monitor_bot_process(bot_token: str, bot_username: str, proc: subprocess.Popen):
    try:
        async def read_output(pipe, log_level):
            for line in iter(pipe.readline, ''):
                if line:
                    await add_bot_log(bot_token, log_level, line.strip())
        
        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, read_output, proc.stdout, "INFO")
        loop.run_in_executor(None, read_output, proc.stderr, "ERROR")
        
        await loop.run_in_executor(None, proc.wait)
        
        if bot_token in running_bots:
            del running_bots[bot_token]
        await update_bot_status(bot_token, 'stopped')
        logger.info(f"Bot {bot_username} process ended")
    except Exception as e:
        logger.error(f"Error monitoring bot {bot_username}: {e}")
        await update_bot_status(bot_token, 'error')


async def start_all_cloned_bots():
    bots = await get_cloned_bots('running')
    for bot in bots:
        await start_cloned_bot(bot['bot_token'], bot['bot_username'])


async def stop_all_cloned_bots():
    for bot_token, proc in list(running_bots.items()):
        if proc.poll() is None:
            proc.terminate()
    running_bots.clear()


# ===================== FRAGMENT API FUNCTIONS =====================

async def encoded(encoded_string: str) -> str:
    if not encoded_string:
        return ""
    missing_padding = len(encoded_string) % 4
    if missing_padding != 0:
        encoded_string += "=" * (4 - missing_padding)
    try:
        decoded_bytes = base64.b64decode(encoded_string)
        return decoded_bytes.decode("utf-8", errors="ignore")
    except Exception as e:
        logger.error(f"Error decoding: {e}")
        return encoded_string


async def post(cookies: str, _hash: str, data: dict) -> Optional[dict]:
    params = {"hash": _hash}
    if not cookies:
        logger.error("Invalid cookies")
        return None

    headers = {
        "accept": "application/json, text/javascript, */*; q=0.01",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "origin": "https://fragment.com",
        "referer": "https://fragment.com/",
        "cookie": cookies.strip(),
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "x-requested-with": "XMLHttpRequest",
    }

    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post("https://fragment.com/api", params=params, headers=headers, data=data) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    text = await response.text()
                    logger.error(f"HTTP {response.status}: {text[:200]}")
                    return None
    except Exception as e:
        logger.error(f"Connection error: {e}")
        return None


async def get_user_address(username: str) -> Optional[dict]:
    try:
        data = {"query": username, "quantity": "", "method": "searchStarsRecipient"}
        return await post(COOKIES, HASH, data)
    except Exception as e:
        logger.error(f"Error in get_user_address: {e}")
        return None


async def init_buy_stars(recipient: str, quantity: int) -> Optional[dict]:
    try:
        data = {"recipient": recipient, "quantity": quantity, "method": "initBuyStarsRequest"}
        return await post(COOKIES, HASH, data)
    except Exception as e:
        logger.error(f"Error in init_buy_stars: {e}")
        return None


async def get_buy_stars(req_id: str, show_sender: str = "1") -> Optional[dict]:
    try:
        data = {"transaction": "1", "id": req_id, "show_sender": show_sender, "method": "getBuyStarsLink"}
        return await post(COOKIES, HASH, data)
    except Exception as e:
        logger.error(f"Error in get_buy_stars: {e}")
        return None


# ===================== WALLET FUNCTIONS =====================

async def send_transfer(address: str, amount: int, payload: str) -> Optional[str]:
    try:
        client = TonapiClient(api_key=WALLET_API_KEY, is_testnet=False)
        wallet, _, _, _ = WalletV5R1.from_mnemonic(client, WALLET_MNEMONIC)
        amount_in_ton = amount / 1_000_000_000
        logger.info(f"Sending {amount_in_ton} TON to {address}")
        tx_hash = await wallet.transfer(destination=address, amount=amount_in_ton, body=payload)
        return tx_hash
    except Exception as e:
        logger.error(f"Error in send_transfer: {e}")
        return None


async def get_balance() -> float:
    try:
        client = TonapiClient(api_key=WALLET_API_KEY, is_testnet=False)
        wallet, _, _, _ = WalletV5R1.from_mnemonic(client, WALLET_MNEMONIC)
        balance = await wallet.balance()
        return float(balance)
    except Exception as e:
        logger.error(f"Error in get_balance: {e}")
        return 0.0


# ===================== WRAPPER FUNCTIONS =====================

async def get_user(username: str) -> Optional[dict]:
    try:
        logger.info(f"Searching for user: {username}")
        user = await get_user_address(username)
        if user and user.get("found"):
            nickname = user.get("found").get("name")
            address = user.get("found").get("recipient")
            if nickname and address:
                logger.info(f"Found user: {nickname}")
                return {"nickname": nickname, "address": address}
        return None
    except Exception as e:
        logger.error(f"Error in get_user: {e}")
        return None


async def pay_stars_order(username: str, quantity: int, show_sender: bool = True) -> Optional[str]:
    try:
        logger.info(f"Starting payment for @{username} - {quantity} stars (show_sender={show_sender})")
        
        user = await get_user_address(username)
        if not user or not user.get("found"):
            logger.error("User not found")
            return None
        address = user.get("found").get("recipient")
        if not address:
            logger.error("Invalid user address")
            return None

        init = await init_buy_stars(address, quantity)
        if not init:
            logger.error("Failed to init buy")
            return None
        req_id = init.get("req_id")
        if not req_id:
            logger.error("No req_id")
            return None

        show_sender_value = "1" if show_sender else "0"
        buy = await get_buy_stars(req_id, show_sender_value)
        if not buy:
            logger.error("Failed to get buy details")
            return None
            
        messages = buy.get("transaction", {}).get("messages", [])
        if not messages:
            logger.error("No messages")
            return None
            
        pay_address = messages[0].get("address")
        amount = messages[0].get("amount")
        payload = messages[0].get("payload")

        if not all([pay_address, amount, payload]):
            logger.error("Missing transaction data")
            return None

        decoded_payload = await encoded(payload)
        tx_hash = await send_transfer(pay_address, int(amount), decoded_payload)

        if tx_hash:
            logger.info(f"Transaction successful: {tx_hash}")
            return tx_hash
        return None
    except Exception as e:
        logger.error(f"Error in pay_stars_order: {e}")
        return None


# ===================== BOT INITIALIZATION =====================
bot = TelegramClient('fragment_bot_session', API_ID, API_HASH)

user_states: Dict[int, str] = {}
user_data: Dict[int, Dict[str, Any]] = {}

STATE_IDLE = "idle"
STATE_WAITING_USERNAME = "waiting_username"
STATE_WAITING_STARS = "waiting_stars"
STATE_WAITING_SENDER_OPTION = "waiting_sender_option"
STATE_CONFIRM_PURCHASE = "confirm_purchase"


# ===================== HELPER FUNCTIONS =====================

async def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


async def check_config() -> tuple:
    return bool(COOKIES and HASH), bool(WALLET_API_KEY and WALLET_MNEMONIC)


def format_number(num: int) -> str:
    return f"{num:,}".replace(",", ".")


def calculate_price(stars: int) -> float:
    return stars * PRICE_PER_STAR


def clean_username(username: str) -> str:
    return username.strip().replace('@', '')


# ===================== BOT HANDLERS =====================

@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    user = await event.get_sender()
    user_id = event.sender_id
    
    await save_user(user_id, user.username, user.first_name, user.last_name)
    await log_activity(user_id, "start", "User started the bot")
    
    fragment_ok, wallet_ok = await check_config()
    user_stats = await get_user_stats(user_id)
    
    welcome_text = (
        f"🌟 **Selamat Datang di Fragment Stars Bot** 🌟\n\n"
        f"Halo {user.first_name}!\n\n"
        f"**Informasi:**\n"
        f"• 💰 Harga: `{PRICE_PER_STAR}` TON per star\n"
        f"• 📊 Minimal: `{MIN_STARS}` stars\n"
        f"• 📈 Maksimal: `{MAX_STARS}` stars\n\n"
        f"**Statistik Anda:**\n"
        f"• Total Pembelian: {user_stats['total_purchases']}\n"
        f"• Total Stars: {format_number(user_stats['total_stars'])}\n"
        f"• Total Pengeluaran: {user_stats['total_spent']:.2f} TON\n\n"
    )
    
    if not fragment_ok:
        welcome_text += "⚠️ **Fragment API tidak aktif**\n"
    if not wallet_ok:
        welcome_text += "⚠️ **Wallet tidak aktif**\n"
    
    buttons = [
        [Button.inline("🛒 Beli Stars", data="buy")],
        [Button.inline("ℹ️ Cara Pakai", data="howto")],
        [Button.inline("📊 Statistik Saya", data="mystats")],
    ]
    
    if await is_admin(user_id):
        buttons.append([Button.inline("⚙️ Admin Panel", data="admin")])
    
    await event.respond(welcome_text, buttons=buttons, parse_mode='markdown')


@bot.on(events.NewMessage(pattern='/buy'))
async def buy_command(event):
    user_id = event.sender_id
    fragment_ok, wallet_ok = await check_config()
    
    await log_activity(user_id, "buy_command", "User initiated buy command")
    
    if not fragment_ok or not wallet_ok:
        await event.respond("❌ **Bot belum siap digunakan**")
        return
    
    user_states[user_id] = STATE_WAITING_USERNAME
    user_data[user_id] = {}
    
    await event.respond(
        "🛒 **Mulai Pembelian Stars**\n\n"
        "Silakan masukkan **username** penerima:\n"
        "_(Contoh: @username atau username)_\n\n"
        "Ketik /cancel untuk membatalkan.",
        parse_mode='markdown'
    )


@bot.on(events.NewMessage(pattern='/cancel'))
async def cancel_command(event):
    user_id = event.sender_id
    
    await log_activity(user_id, "cancel", "User cancelled operation")
    
    if user_id in user_states:
        del user_states[user_id]
    if user_id in user_data:
        del user_data[user_id]
    
    await event.respond("✅ **Operasi dibatalkan.**", parse_mode='markdown')


@bot.on(events.NewMessage(pattern='/stats'))
async def stats_command(event):
    user_id = event.sender_id
    user_stats = await get_user_stats(user_id)
    
    stats_text = (
        "📊 **Statistik Pengguna**\n\n"
        f"• Total Pembelian: {user_stats['total_purchases']}\n"
        f"• Total Stars: {format_number(user_stats['total_stars'])}\n"
        f"• Total Pengeluaran: {user_stats['total_spent']:.2f} TON\n"
        f"• Pembelian Hari Ini: {user_stats['today_purchases']}"
    )
    
    await event.respond(stats_text, parse_mode='markdown')
    await log_activity(user_id, "stats", "User viewed their stats")


# ===================== CLONE BOT COMMANDS =====================

@bot.on(events.NewMessage(pattern='/clone'))
async def clone_bot_handler(event):
    user_id = event.sender_id
    
    if not await is_admin(user_id):
        await event.respond("❌ Akses ditolak! Hanya admin yang bisa clone bot.")
        return
    
    parts = event.message.text.split()
    if len(parts) < 2:
        await event.respond("❌ **Format salah!**\n\nGunakan: `/clone <bot_token> [bot_username]`\n\nContoh: `/clone 123456:ABCdefg my_bot`", parse_mode='markdown')
        return
    
    bot_token = parts[1]
    bot_username = parts[2] if len(parts) > 2 else None
    
    if not bot_token or ':' not in bot_token:
        await event.respond("❌ Bot token tidak valid! Format: `123456:ABCdefg`")
        return
    
    await event.respond("⏳ **Mengecek bot token...**")
    
    try:
        temp_client = TelegramClient(f'temp_{user_id}', API_ID, API_HASH)
        await temp_client.start(bot_token=bot_token)
        me = await temp_client.get_me()
        await temp_client.disconnect()
        
        bot_username = bot_username or me.username or f"bot_{me.id}"
        bot_name = me.first_name or "Fragment Stars Bot"
        
        success = await add_cloned_bot(bot_token, bot_username, bot_name, user_id)
        
        if success:
            await start_cloned_bot(bot_token, bot_username)
            
            await event.respond(
                f"✅ **Bot Berhasil Di-clone!**\n\n"
                f"**Nama:** {bot_name}\n"
                f"**Username:** @{bot_username}\n"
                f"**Token:** `{bot_token[:20]}...`\n\n"
                f"Bot sedang berjalan. Gunakan `/listbots` untuk melihat semua bot.",
                parse_mode='markdown'
            )
            await log_activity(user_id, "clone_bot", f"Cloned bot: {bot_username}")
        else:
            await event.respond("❌ Gagal menyimpan bot ke database!")
    except Exception as e:
        await event.respond(f"❌ **Error:** Bot token tidak valid!\n\n{str(e)[:100]}")
        logger.error(f"Error validating bot token: {e}")


@bot.on(events.NewMessage(pattern='/listbots'))
async def list_bots_handler(event):
    user_id = event.sender_id
    
    if not await is_admin(user_id):
        await event.respond("❌ Akses ditolak!")
        return
    
    bots = await get_cloned_bots()
    
    if not bots:
        await event.respond("📭 **Belum ada bot yang di-clone.**\n\nGunakan `/clone <token>` untuk menambah bot.")
        return
    
    text = "🤖 **Daftar Bot Clone**\n\n"
    for bot in bots:
        status_emoji = "🟢" if bot['status'] == 'running' else "🔴"
        text += f"{status_emoji} **@{bot['bot_username']}**\n"
        text += f"   • Nama: {bot['bot_name']}\n"
        text += f"   • Status: {bot['status']}\n"
        if bot['pid']:
            text += f"   • PID: {bot['pid']}\n"
        text += "\n"
    
    await event.respond(text, parse_mode='markdown')


@bot.on(events.NewMessage(pattern='/startbot'))
async def start_bot_handler(event):
    user_id = event.sender_id
    
    if not await is_admin(user_id):
        await event.respond("❌ Akses ditolak!")
        return
    
    parts = event.message.text.split()
    if len(parts) < 2:
        await event.respond("❌ Gunakan: `/startbot <bot_username>`")
        return
    
    bot_username = parts[1]
    bots = await get_cloned_bots()
    
    for bot in bots:
        if bot['bot_username'] == bot_username:
            if bot['status'] == 'running':
                await event.respond(f"⚠️ Bot @{bot_username} sudah berjalan!")
                return
            
            success = await start_cloned_bot(bot['bot_token'], bot['bot_username'])
            if success:
                await event.respond(f"✅ Bot @{bot_username} berhasil dijalankan!")
            else:
                await event.respond(f"❌ Gagal menjalankan bot @{bot_username}!")
            return
    
    await event.respond(f"❌ Bot @{bot_username} tidak ditemukan!")


@bot.on(events.NewMessage(pattern='/stopbot'))
async def stop_bot_handler(event):
    user_id = event.sender_id
    
    if not await is_admin(user_id):
        await event.respond("❌ Akses ditolak!")
        return
    
    parts = event.message.text.split()
    if len(parts) < 2:
        await event.respond("❌ Gunakan: `/stopbot <bot_username>`")
        return
    
    bot_username = parts[1]
    bots = await get_cloned_bots()
    
    for bot in bots:
        if bot['bot_username'] == bot_username:
            if bot['status'] != 'running':
                await event.respond(f"⚠️ Bot @{bot_username} tidak sedang berjalan!")
                return
            
            success = await stop_cloned_bot(bot['bot_token'], bot['bot_username'])
            if success:
                await event.respond(f"✅ Bot @{bot_username} berhasil dihentikan!")
            else:
                await event.respond(f"❌ Gagal menghentikan bot @{bot_username}!")
            return
    
    await event.respond(f"❌ Bot @{bot_username} tidak ditemukan!")


@bot.on(events.NewMessage(pattern='/delbot'))
async def delete_bot_handler(event):
    user_id = event.sender_id
    
    if not await is_admin(user_id):
        await event.respond("❌ Akses ditolak!")
        return
    
    parts = event.message.text.split()
    if len(parts) < 2:
        await event.respond("❌ Gunakan: `/delbot <bot_username>`")
        return
    
    bot_username = parts[1]
    bots = await get_cloned_bots()
    
    for bot in bots:
        if bot['bot_username'] == bot_username:
            if bot['status'] == 'running':
                await stop_cloned_bot(bot['bot_token'], bot['bot_username'])
            
            success = await remove_cloned_bot(bot['bot_token'])
            if success:
                await event.respond(f"✅ Bot @{bot_username} berhasil dihapus!")
            else:
                await event.respond(f"❌ Gagal menghapus bot @{bot_username}!")
            return
    
    await event.respond(f"❌ Bot @{bot_username} tidak ditemukan!")


@bot.on(events.NewMessage(pattern='/botlog'))
async def bot_log_handler(event):
    user_id = event.sender_id
    
    if not await is_admin(user_id):
        await event.respond("❌ Akses ditolak!")
        return
    
    parts = event.message.text.split()
    if len(parts) < 2:
        await event.respond("❌ Gunakan: `/botlog <bot_username> [limit]`")
        return
    
    bot_username = parts[1]
    limit = int(parts[2]) if len(parts) > 2 else 20
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''SELECT log_level, message, timestamp FROM bot_logs 
                       WHERE bot_token IN (SELECT bot_token FROM cloned_bots WHERE bot_username = ?)
                       ORDER BY timestamp DESC LIMIT ?''', (bot_username, limit))
        logs = cursor.fetchall()
        conn.close()
        
        if not logs:
            await event.respond(f"📭 Tidak ada log untuk bot @{bot_username}")
            return
        
        text = f"📋 **Log Bot @{bot_username}** (last {len(logs)})\n\n"
        for log_level, message, ts in reversed(logs):
            emoji = "ℹ️" if log_level == "INFO" else "⚠️" if log_level == "WARNING" else "❌"
            text += f"{emoji} {ts[11:19]} [{log_level}] {message[:100]}\n"
        
        if len(text) > 4000:
            text = text[:4000] + "\n\n... (truncated)"
        
        await event.respond(text, parse_mode='markdown')
    except Exception as e:
        await event.respond(f"❌ Error: {str(e)[:100]}")


@bot.on(events.NewMessage(pattern='/admin'))
async def admin_panel(event):
    user_id = event.sender_id
    
    if not await is_admin(user_id):
        await event.respond("❌ Akses ditolak!")
        return
    
    stats = await get_all_stats()
    bots = await get_cloned_bots()
    
    running_bots_count = len([b for b in bots if b['status'] == 'running'])
    total_bots = len(bots)
    
    text = (
        "⚙️ **Panel Admin Bot Master**\n\n"
        f"**Status Bot Master:**\n"
        f"• Fragment API: {'✅' if COOKIES and HASH else '❌'}\n"
        f"• Wallet: {'✅' if WALLET_API_KEY and WALLET_MNEMONIC else '❌'}\n\n"
        f"**Bot Clone:**\n"
        f"• Total Bot: {total_bots}\n"
        f"• Running: {running_bots_count}\n"
        f"• Stopped: {total_bots - running_bots_count}\n\n"
        f"**Statistik Keseluruhan:**\n"
        f"• Total User: {stats['total_users']}\n"
        f"• Total Pembelian: {stats['total_purchases']}\n"
        f"• Total Stars: {format_number(stats['total_stars'])}\n"
        f"• Total Volume: {stats['total_volume']:.2f} TON\n\n"
        f"**Commands:**\n"
        f"/clone <token> - Clone bot baru\n"
        f"/listbots - Lihat semua bot\n"
        f"/startbot <username> - Jalankan bot\n"
        f"/stopbot <username> - Hentikan bot\n"
        f"/delbot <username> - Hapus bot\n"
        f"/botlog <username> - Lihat log bot"
    )
    
    await event.respond(text, parse_mode='markdown')


# ===================== CALLBACK HANDLER =====================

@bot.on(events.CallbackQuery)
async def callback_handler(event):
    user_id = event.sender_id
    data = event.data.decode('utf-8')
    
    if data == "buy":
        await buy_command(event)
    elif data == "howto":
        await event.edit(
            "📖 **Cara Menggunakan Bot**\n\n"
            "1️⃣ Klik 'Beli Stars' atau ketik /buy\n"
            "2️⃣ Masukkan username penerima\n"
            "3️⃣ Masukkan jumlah stars\n"
            "4️⃣ Pilih opsi pengirim (Tampilkan/Sembunyikan nama)\n"
            "5️⃣ Konfirmasi pembelian\n"
            "6️⃣ Tunggu proses selesai\n\n"
            "**Opsi Pengirim:**\n"
            "• **Tampilkan nama** - Penerima melihat nama akun Fragment Anda\n"
            "• **Sembunyikan (Gift)** - Muncul sebagai hadiah dari Telegram (anonim)",
            buttons=[Button.inline("🔙 Kembali", data="start")],
            parse_mode='markdown'
        )
    elif data == "mystats":
        user_stats = await get_user_stats(user_id)
        await event.edit(
            f"📊 **Statistik Anda**\n\n"
            f"• Total Pembelian: {user_stats['total_purchases']}\n"
            f"• Total Stars: {format_number(user_stats['total_stars'])}\n"
            f"• Total Pengeluaran: {user_stats['total_spent']:.2f} TON\n"
            f"• Pembelian Hari Ini: {user_stats['today_purchases']}",
            buttons=[Button.inline("🔙 Kembali", data="start")],
            parse_mode='markdown'
        )
    elif data == "admin":
        await admin_panel(event)
    elif data == "start":
        await start_handler(event)
    elif data.startswith("sender_show_"):
        user_data[user_id]['show_sender'] = True
        await show_confirmation(event, user_id)
    elif data.startswith("sender_hide_"):
        user_data[user_id]['show_sender'] = False
        await show_confirmation(event, user_id)
    elif data.startswith("confirm_"):
        await confirm_purchase(event, user_id)
    elif data.startswith("cancel_"):
        await cancel_purchase(event, user_id)
    elif data.startswith("sender_back_"):
        await ask_sender_option(event, user_id)


# ===================== MESSAGE HANDLER =====================

@bot.on(events.NewMessage)
async def message_handler(event):
    user_id = event.sender_id
    message = event.message.text.strip()
    
    if user_id not in user_states:
        return
    
    state = user_states[user_id]
    
    if message.lower() == '/cancel':
        await cancel_command(event)
        return
    
    if state == STATE_WAITING_USERNAME:
        await process_username(event, user_id, message)
    elif state == STATE_WAITING_STARS:
        await process_stars(event, user_id, message)


async def process_username(event, user_id: int, username: str):
    clean_name = clean_username(username)
    
    if not clean_name:
        await event.respond("❌ Username tidak valid")
        return
    
    async with bot.action(event.chat_id, 'typing'):
        await event.respond("🔍 **Mencari username...**")
        
        try:
            user_info = await get_user(clean_name)
            
            if not user_info:
                await event.respond(f"❌ Username **@{clean_name}** tidak ditemukan.", parse_mode='markdown')
                return
            
            user_data[user_id]['username'] = clean_name
            user_data[user_id]['nickname'] = user_info['nickname']
            user_data[user_id]['address'] = user_info['address']
            
            user_states[user_id] = STATE_WAITING_STARS
            
            await event.respond(
                f"✅ **User Ditemukan:** {user_info['nickname']}\n\n"
                f"Masukkan **jumlah stars** (angka):\n"
                f"Min: {MIN_STARS:,} - Max: {MAX_STARS:,}",
                parse_mode='markdown'
            )
        except Exception as e:
            logger.error(f"Error: {e}")
            await event.respond("❌ Terjadi kesalahan.")


async def process_stars(event, user_id: int, stars_str: str):
    try:
        stars = int(stars_str)
        
        if stars < MIN_STARS:
            await event.respond(f"❌ Minimal {MIN_STARS:,} stars")
            return
        
        if stars > MAX_STARS:
            await event.respond(f"❌ Maksimal {MAX_STARS:,} stars")
            return
        
        user_data[user_id]['stars'] = stars
        user_data[user_id]['price'] = calculate_price(stars)
        
        await ask_sender_option(event, user_id)
        
    except ValueError:
        await event.respond("❌ Masukkan angka yang valid.")


async def ask_sender_option(event, user_id: int):
    option_text = (
        "👤 **Opsi Pengirim**\n\n"
        "Pilih bagaimana nama pengirim ditampilkan:\n\n"
        "✅ **Tampilkan nama saya** - Penerima akan melihat nama akun Fragment Anda\n"
        "❌ **Sembunyikan nama** - Akan muncul sebagai hadiah dari Telegram (anonim)\n\n"
        "Pilih opsi di bawah:"
    )
    
    buttons = [
        [Button.inline("👤 Tampilkan Nama Saya", data=f"sender_show_{user_id}"),
         Button.inline("🎁 Sembunyikan (Gift)", data=f"sender_hide_{user_id}")]
    ]
    
    user_states[user_id] = STATE_WAITING_SENDER_OPTION
    await event.respond(option_text, buttons=buttons, parse_mode='markdown')


async def show_confirmation(event, user_id: int):
    data = user_data[user_id]
    sender_text = "👤 Menampilkan nama saya" if data.get('show_sender', True) else "🎁 Sembunyikan (Gift mode)"
    
    confirm_text = (
        "📝 **Konfirmasi Pembelian**\n\n"
        f"**Penerima:** {data['nickname']}\n"
        f"**Username:** @{data['username']}\n"
        f"**Stars:** {format_number(data['stars'])}\n"
        f"**Harga:** {data['price']:.2f} TON\n"
        f"**Opsi Pengirim:** {sender_text}\n\n"
        "⚠️ Transaksi tidak dapat dibatalkan!\n\n"
        "Setuju?"
    )
    
    buttons = [
        [Button.inline("✅ Ya", data=f"confirm_{user_id}"),
         Button.inline("❌ Tidak", data=f"cancel_{user_id}")],
        [Button.inline("🔙 Ubah Opsi Pengirim", data=f"sender_back_{user_id}")]
    ]
    
    user_states[user_id] = STATE_CONFIRM_PURCHASE
    await event.respond(confirm_text, buttons=buttons, parse_mode='markdown')


async def confirm_purchase(event, user_id: int):
    if user_id not in user_data:
        await event.edit("❌ Sesi kadaluarsa.")
        return
    
    purchase_data = user_data[user_id]
    show_sender = purchase_data.get('show_sender', True)
    
    await event.edit(
        "⏳ **Memproses pembelian...**\n\n"
        f"Penerima: @{purchase_data['username']}\n"
        f"Stars: {format_number(purchase_data['stars'])}\n"
        f"Opsi: {'Tampilkan nama' if show_sender else 'Sembunyikan (Gift)'}",
        parse_mode='markdown'
    )
    
    await save_purchase(user_id, purchase_data['username'], purchase_data['nickname'],
                        purchase_data['stars'], purchase_data['price'], show_sender=show_sender, status="pending")
    
    try:
        tx_hash = await pay_stars_order(purchase_data['username'], purchase_data['stars'], show_sender)
        
        if tx_hash:
            await save_purchase(user_id, purchase_data['username'], purchase_data['nickname'],
                                purchase_data['stars'], purchase_data['price'], tx_hash=tx_hash,
                                show_sender=show_sender, status="success")
            
            success_text = (
                "✅ **Pembelian Berhasil!**\n\n"
                f"**Penerima:** @{purchase_data['username']}\n"
                f"**Stars:** {format_number(purchase_data['stars'])}\n"
                f"**Harga:** {purchase_data['price']:.2f} TON\n"
                f"**Opsi:** {'👤 Nama ditampilkan' if show_sender else '🎁 Gift mode (anonim)'}\n"
                f"**Hash:** `{tx_hash}`\n\n"
                f"[Lihat di TON Viewer](https://tonviewer.com/transaction/{tx_hash})"
            )
            
            await event.edit(success_text, buttons=[Button.inline("🛒 Beli Lagi", data="buy")],
                             parse_mode='markdown', link_preview=False)
            await log_activity(user_id, "purchase_success", f"Stars: {purchase_data['stars']}, Hash: {tx_hash}")
        else:
            await save_purchase(user_id, purchase_data['username'], purchase_data['nickname'],
                                purchase_data['stars'], purchase_data['price'], show_sender=show_sender,
                                status="failed", error_message="Transaction failed")
            
            await event.edit("❌ **Pembelian Gagal**\n\nCoba lagi nanti.",
                             buttons=[Button.inline("🔄 Coba Lagi", data="buy")], parse_mode='markdown')
            await log_activity(user_id, "purchase_failed", f"Stars: {purchase_data['stars']}")
    
    except Exception as e:
        logger.error(f"Error: {e}")
        await save_purchase(user_id, purchase_data['username'], purchase_data['nickname'],
                            purchase_data['stars'], purchase_data['price'], show_sender=show_sender,
                            status="error", error_message=str(e)[:200])
        
        await event.edit(f"❌ **Error:** {str(e)[:100]}",
                         buttons=[Button.inline("🔄 Coba Lagi", data="buy")], parse_mode='markdown')
        await log_activity(user_id, "purchase_error", str(e)[:100])
    finally:
        if user_id in user_states:
            del user_states[user_id]
        if user_id in user_data:
            del user_data[user_id]


async def cancel_purchase(event, user_id: int):
    if user_id in user_states:
        del user_states[user_id]
    if user_id in user_data:
        del user_data[user_id]
    
    await event.edit("❌ **Pembelian Dibatalkan**",
                     buttons=[Button.inline("🛒 Beli Stars", data="buy")], parse_mode='markdown')
    await log_activity(user_id, "purchase_cancelled", "User cancelled purchase")


# ===================== MAIN =====================

async def main():
    is_clone = os.getenv("IS_CLONE", "false").lower() == "true"
    
    if is_clone:
        logger.info("Starting as CLONED BOT...")
        init_database()
        await update_bot_status(BOT_TOKEN, 'running')
        logger.info(f"✅ Cloned bot running")
        await bot.start(bot_token=BOT_TOKEN)
        logger.info("✅ Cloned bot is running")
        await bot.run_until_disconnected()
    else:
        logger.info("Starting as MASTER BOT...")
        init_database()
        
        if not API_ID or not API_HASH or not BOT_TOKEN:
            logger.error("❌ Konfigurasi Telegram tidak lengkap")
            return
        
        logger.info(f"📊 COOKIES length: {len(COOKIES)}")
        logger.info(f"📊 HASH length: {len(HASH)}")
        
        logger.info("✅ Starting master bot...")
        await bot.start(bot_token=BOT_TOKEN)
        logger.info("✅ Master bot running")
        
        await start_all_cloned_bots()
        await bot.run_until_disconnected()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Bot dihentikan oleh user")
        asyncio.run(stop_all_cloned_bots())
    except Exception as e:
        logger.error(f"❌ Error fatal: {e}")
        
