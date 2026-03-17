# b.py - Fragment Stars Bot - VERSION ALL-IN-ONE WITH DATABASE
import os
import json
import base64
import asyncio
import logging
import sqlite3
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

import aiohttp
from aiohttp import ClientResponse, ClientConnectorError
from dotenv import load_dotenv
from telethon import TelegramClient, events, Button

# Import tonutils
from tonutils.client import TonapiClient
from tonutils.utils import to_amount
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

# ===================== DATABASE FUNCTIONS =====================

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


async def save_user(user_id: int, username: str = None, first_name: str = None, last_name: str = None):
    """Simpan atau update data pengguna."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Cek apakah user sudah ada
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        existing = cursor.fetchone()
        
        now = datetime.now().isoformat()
        is_admin = 1 if user_id in ADMIN_IDS else 0
        
        if existing:
            # Update last_seen
            cursor.execute('''
                UPDATE users 
                SET username = ?, first_name = ?, last_name = ?, last_seen = ?, is_admin = ?
                WHERE user_id = ?
            ''', (username, first_name, last_name, now, is_admin, user_id))
        else:
            # Insert new user
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
        
        # Log aktivitas pembelian
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
        
        # Total pembelian
        cursor.execute('''
            SELECT COUNT(*), COALESCE(SUM(stars_amount), 0), COALESCE(SUM(price_ton), 0)
            FROM purchases WHERE user_id = ? AND status = 'success'
        ''', (user_id,))
        total_purchases, total_stars, total_spent = cursor.fetchone()
        
        # Pembelian hari ini
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
        
        # Total user
        cursor.execute('SELECT COUNT(*) FROM users')
        total_users = cursor.fetchone()[0]
        
        # User aktif hari ini
        today = datetime.now().date().isoformat()
        cursor.execute('''
            SELECT COUNT(DISTINCT user_id) FROM activity_log 
            WHERE DATE(timestamp) = ? AND action != 'system'
        ''', (today,))
        active_today = cursor.fetchone()[0]
        
        # Total pembelian
        cursor.execute('''
            SELECT COUNT(*), COALESCE(SUM(stars_amount), 0), COALESCE(SUM(price_ton), 0)
            FROM purchases WHERE status = 'success'
        ''')
        total_purchases, total_stars, total_volume = cursor.fetchone()
        
        # Pembelian hari ini
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


# ===================== FRAGMENT API FUNCTIONS =====================

async def encoded(encoded_string: str) -> str:
    """Decode base64 string."""
    if not encoded_string:
        return ""
    
    missing_padding = len(encoded_string) % 4
    if missing_padding != 0:
        encoded_string += "=" * (4 - missing_padding)

    try:
        decoded_bytes = base64.b64decode(encoded_string)
        decoded_string = decoded_bytes.decode("utf-8", errors="ignore")
        return decoded_string
    except Exception as e:
        logger.error(f"Error decoding: {e}")
        return encoded_string


async def post(cookies: str, _hash: str, data: dict) -> Optional[dict]:
    """POST request ke Fragment API."""
    params = {"hash": _hash}
    
    if not cookies or not isinstance(cookies, str):
        logger.error("Invalid cookies format")
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
            async with session.post(
                "https://fragment.com/api", 
                params=params, 
                headers=headers, 
                data=data
            ) as response:
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
    """Cari user di Fragment."""
    try:
        data = {
            "query": username,
            "quantity": "",
            "method": "searchStarsRecipient",
        }
        return await post(COOKIES, HASH, data)
    except Exception as e:
        logger.error(f"Error in get_user_address: {e}")
        return None


async def init_buy_stars(recipient: str, quantity: int) -> Optional[dict]:
    """Inisialisasi pembelian stars."""
    try:
        data = {
            "recipient": recipient,
            "quantity": quantity,
            "method": "initBuyStarsRequest",
        }
        return await post(COOKIES, HASH, data)
    except Exception as e:
        logger.error(f"Error in init_buy_stars: {e}")
        return None


async def get_buy_stars(req_id: str, show_sender: str = "1") -> Optional[dict]:
    """Dapatkan detail pembayaran dengan opsi show_sender."""
    try:
        data = {
            "transaction": "1",
            "id": req_id,
            "show_sender": show_sender,
            "method": "getBuyStarsLink",
        }
        return await post(COOKIES, HASH, data)
    except Exception as e:
        logger.error(f"Error in get_buy_stars: {e}")
        return None


# ===================== WALLET FUNCTIONS =====================

async def send_transfer(address: str, amount: int, payload: str) -> Optional[str]:
    """Kirim transfer TON."""
    try:
        client = TonapiClient(api_key=WALLET_API_KEY, is_testnet=False)
        wallet, _, _, _ = WalletV5R1.from_mnemonic(client, WALLET_MNEMONIC)

        # Convert amount from nano TON to TON
        amount_in_ton = amount / 1_000_000_000
        logger.info(f"Sending {amount_in_ton} TON to {address}")
        
        tx_hash = await wallet.transfer(
            destination=address,
            amount=amount_in_ton,
            body=payload,
        )
        return tx_hash
    except Exception as e:
        logger.error(f"Error in send_transfer: {e}")
        return None


async def get_balance() -> float:
    """Dapatkan saldo wallet."""
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
    """Dapatkan informasi user dari Fragment."""
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
    """Proses pembayaran stars dengan opsi menampilkan/menyembunyikan pengirim."""
    try:
        logger.info(f"Starting payment for @{username} - {quantity} stars (show_sender={show_sender})")
        
        # 1. Cari user
        user = await get_user_address(username)
        if not user or not user.get("found"):
            logger.error("User not found")
            return None
            
        address = user.get("found").get("recipient")
        if not address:
            logger.error("Invalid user address")
            return None

        # 2. Init buy
        init = await init_buy_stars(address, quantity)
        if not init:
            logger.error("Failed to init buy")
            return None
            
        req_id = init.get("req_id")
        if not req_id:
            logger.error("No req_id in response")
            return None

        # 3. Get buy details dengan parameter show_sender
        show_sender_value = "1" if show_sender else "0"
        
        buy = await get_buy_stars(req_id, show_sender_value)
        if not buy:
            logger.error("Failed to get buy details")
            return None
            
        # 4. Parse transaction data
        messages = buy.get("transaction", {}).get("messages", [])
        if not messages:
            logger.error("No messages in transaction")
            return None
            
        pay_address = messages[0].get("address")
        amount = messages[0].get("amount")
        payload = messages[0].get("payload")

        if not all([pay_address, amount, payload]):
            logger.error("Missing transaction data")
            return None

        # 5. Decode payload
        decoded_payload = await encoded(payload)

        # 6. Send transfer
        tx_hash = await send_transfer(pay_address, int(amount), decoded_payload)

        if tx_hash:
            logger.info(f"Transaction successful: {tx_hash}")
            return tx_hash
        return None
        
    except Exception as e:
        logger.error(f"Error in pay_stars_order: {e}")
        return None


# ===================== BOT INITIALIZATION =====================
print("Starting bot...")
bot = TelegramClient('fragment_bot_session', API_ID, API_HASH)

# State management
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


async def check_config() -> tuple[bool, bool]:
    fragment_ok = bool(COOKIES and HASH)
    wallet_ok = bool(WALLET_API_KEY and WALLET_MNEMONIC)
    return fragment_ok, wallet_ok


def format_number(num: int) -> str:
    return f"{num:,}".replace(",", ".")


def calculate_price(stars: int) -> float:
    return stars * PRICE_PER_STAR


def clean_username(username: str) -> str:
    return username.strip().replace('@', '')


# ===================== HANDLERS =====================

@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    user = await event.get_sender()
    user_id = event.sender_id
    
    # Simpan user ke database
    await save_user(
        user_id=user_id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )
    
    # Log aktivitas
    await log_activity(user_id, "start", "User started the bot")
    
    fragment_ok, wallet_ok = await check_config()
    
    # Ambil statistik user
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
    
    # Hapus pending purchase sebelumnya
    await delete_pending_purchase(user_id)
    
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
    
    # Hapus pending purchase dari database
    await delete_pending_purchase(user_id)
    
    if user_id in user_states:
        del user_states[user_id]
    if user_id in user_data:
        del user_data[user_id]
    
    await event.respond(
        "✅ **Operasi dibatalkan.**",
        parse_mode='markdown'
    )


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


@bot.on(events.CallbackQuery)
async def callback_handler(event):
    user_id = event.sender_id
    data = event.data.decode('utf-8')
    
    # ===================== HANDLER UNTUK OPSI SENDER =====================
    
    # Handler untuk memilih TAMPILKAN NAMA (show_sender = True)
    if data.startswith("sender_show_"):
        user_data[user_id]['show_sender'] = True
        # Simpan ke pending purchase
        await save_pending_purchase(
            user_id=user_id,
            username=user_data[user_id]['username'],
            nickname=user_data[user_id]['nickname'],
            address=user_data[user_id]['address'],
            stars=user_data[user_id]['stars'],
            price=user_data[user_id]['price'],
            show_sender=True,
            state=STATE_WAITING_SENDER_OPTION
        )
        await show_confirmation(event, user_id)
        await log_activity(user_id, "sender_option", "User chose to show sender name")
        return
    
    # Handler untuk memilih SEMBUNYIKAN NAMA (show_sender = False)
    elif data.startswith("sender_hide_"):
        user_data[user_id]['show_sender'] = False
        # Simpan ke pending purchase
        await save_pending_purchase(
            user_id=user_id,
            username=user_data[user_id]['username'],
            nickname=user_data[user_id]['nickname'],
            address=user_data[user_id]['address'],
            stars=user_data[user_id]['stars'],
            price=user_data[user_id]['price'],
            show_sender=False,
            state=STATE_WAITING_SENDER_OPTION
        )
        await show_confirmation(event, user_id)
        await log_activity(user_id, "sender_option", "User chose to hide sender name")
        return
    
    # Handler untuk kembali ke opsi sender dari halaman konfirmasi
    elif data.startswith("sender_back_"):
        if user_id not in user_data:
            await event.answer("Sesi telah berakhir, silakan mulai lagi.", alert=True)
            return
        
        # Kembali ke halaman pilihan sender
        await ask_sender_option(event, user_id)
        return
    
    # ===================== HANDLER UNTUK KONFIRMASI/CANCEL =====================
    
    elif data.startswith("confirm_"):
        await confirm_purchase(event, user_id)
        return
    
    elif data.startswith("cancel_"):
        await cancel_purchase(event, user_id)
        return
    
    # ===================== HANDLER UNTUK MENU UTAMA =====================
    
    elif data == "buy":
        # Reset state untuk pembelian baru
        user_states[user_id] = STATE_WAITING_USERNAME
        user_data[user_id] = {}
        await delete_pending_purchase(user_id)
        await event.edit(
            "🛒 **Mulai Pembelian Stars**\n\n"
            "Silakan masukkan **username** penerima:\n"
            "_(Contoh: @username atau username)_\n\n"
            "Ketik /cancel untuk membatalkan.",
            parse_mode='markdown'
        )
        await log_activity(user_id, "buy", "User started new purchase")
    
    elif data == "howto":
        await event.edit(
            "📖 **Cara Menggunakan Bot**\n\n"
            "1️⃣ Klik 'Beli Stars' atau ketik /buy\n"
            "2️⃣ Masukkan username penerima\n"
            "3️⃣ Masukkan jumlah stars\n"
            "4️⃣ Pilih opsi pengirim (Tampilkan/Sembunyikan nama)\n"
            "5️⃣ Konfirmasi pembelian\n"
            "6️⃣ Tunggu proses selesai\n\n"
            "**Penting:**\n"
            "• Pastikan wallet memiliki saldo cukup\n"
            "• Transaksi tidak dapat dibatalkan\n\n"
            "**Opsi Pengirim:**\n"
            "• **Tampilkan nama** - Penerima melihat nama akun Fragment Anda\n"
            "• **Sembunyikan (Gift)** - Muncul sebagai hadiah dari Telegram (anonim)",
            buttons=[Button.inline("🔙 Kembali", data="start")],
            parse_mode='markdown'
        )
        await log_activity(user_id, "howto", "User viewed how-to guide")
    
    elif data == "mystats":
        user_stats = await get_user_stats(user_id)
        
        stats_text = (
            "📊 **Statistik Anda**\n\n"
            f"• Total Pembelian: {user_stats['total_purchases']}\n"
            f"• Total Stars: {format_number(user_stats['total_stars'])}\n"
            f"• Total Pengeluaran: {user_stats['total_spent']:.2f} TON\n"
            f"• Pembelian Hari Ini: {user_stats['today_purchases']}\n\n"
            f"_Terakhir update: {datetime.now().strftime('%H:%M:%S')}_"
        )
        
        await event.edit(
            stats_text,
            buttons=[Button.inline("🔙 Kembali", data="start")],
            parse_mode='markdown'
        )
        await log_activity(user_id, "mystats", "User viewed their stats")
    
    elif data == "admin":
        if not await is_admin(user_id):
            await event.answer("Akses ditolak!", alert=True)
            return
        
        # Ambil statistik keseluruhan
        stats = await get_all_stats()
        
        admin_text = (
            "⚙️ **Panel Admin**\n\n"
            f"• Status: Aktif\n"
            f"• Fragment API: {'✅' if COOKIES and HASH else '❌'}\n"
            f"• Wallet: {'✅' if WALLET_API_KEY and WALLET_MNEMONIC else '❌'}\n\n"
            f"**Statistik Bot:**\n"
            f"• Total User: {stats['total_users']}\n"
            f"• User Aktif Hari Ini: {stats['active_today']}\n"
            f"• Total Pembelian: {stats['total_purchases']}\n"
            f"• Total Stars: {format_number(stats['total_stars'])}\n"
            f"• Total Volume: {stats['total_volume']:.2f} TON\n"
            f"• Pembelian Hari Ini: {stats['today_purchases']}\n"
            f"• Stars Hari Ini: {format_number(stats['today_stars'])}\n"
            f"• Volume Hari Ini: {stats['today_volume']:.2f} TON\n\n"
            f"• Pengguna Aktif Saat Ini: {len(user_states)}"
        )
        buttons = [
            [Button.inline("💰 Cek Saldo", data="balance")],
            [Button.inline("📊 Detail Statistik", data="admin_stats")],
            [Button.inline("🔄 Restart Bot", data="restart")],
            [Button.inline("🔙 Kembali", data="start")]
        ]
        await event.edit(admin_text, buttons=buttons, parse_mode='markdown')
        await log_activity(user_id, "admin", "Admin accessed admin panel")
    
    elif data == "admin_stats":
        if not await is_admin(user_id):
            await event.answer("Akses ditolak!", alert=True)
            return
        
        # Ambil 10 pembelian terakhir
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT user_id, recipient_username, stars_amount, price_ton, status, timestamp
            FROM purchases
            ORDER BY timestamp DESC LIMIT 10
        ''')
        recent_purchases = cursor.fetchall()
        conn.close()
        
        stats_text = "📊 **10 Pembelian Terakhir**\n\n"
        for i, purchase in enumerate(recent_purchases, 1):
            user_id, recipient, stars, price, status, ts = purchase
            stats_text += f"{i}. User: {user_id}\n   → @{recipient}: {stars} stars ({price:.2f} TON)\n   Status: {status}\n   {ts[:19]}\n\n"
        
        await event.edit(
            stats_text,
            buttons=[Button.inline("🔙 Kembali", data="admin")],
            parse_mode='markdown'
        )
    
    elif data == "balance":
        if not await is_admin(user_id):
            await event.answer("Akses ditolak!", alert=True)
            return
        
        try:
            await event.edit("⏳ **Mengambil saldo...**")
            balance = await get_balance()
            await event.edit(
                f"💰 **Saldo Wallet**\n\n"
                f"Saldo: `{balance:.2f}` TON\n\n"
                f"_Update terakhir: {datetime.now().strftime('%H:%M:%S')}_",
                buttons=[
                    [Button.inline("🔄 Refresh", data="balance")],
                    [Button.inline("🔙 Kembali", data="admin")]
                ],
                parse_mode='markdown'
            )
            await log_activity(user_id, "check_balance", f"Balance: {balance:.2f} TON")
        except Exception as e:
            logger.error(f"Error cek saldo: {e}")
            await event.edit(
                "❌ Gagal cek saldo",
                buttons=[Button.inline("🔙 Kembali", data="admin")]
            )
    
    elif data == "restart":
        if not await is_admin(user_id):
            await event.answer("Akses ditolak!", alert=True)
            return
        
        # Reset semua state
        user_states.clear()
        user_data.clear()
        
        # Hapus semua pending purchases
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM pending_purchases')
        conn.commit()
        conn.close()
        
        await event.edit(
            "✅ **Bot telah di-restart**\n\n"
            "Semua sesi pengguna telah dihapus.",
            buttons=[Button.inline("🏠 Kembali ke Menu", data="start")],
            parse_mode='markdown'
        )
        await log_activity(user_id, "restart", "Bot was restarted by admin")
    
    elif data == "start":
        await start_handler(event)
    
    # ===================== HANDLER UNTUK DATA TIDAK DIKENAL =====================
    
    else:
        logger.warning(f"Unknown callback data: {data} from user {user_id}")
        await event.answer("Perintah tidak dikenal!", alert=True)


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


# ===================== PROSES PEMBELIAN =====================

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
                await event.respond(
                    f"❌ Username **@{clean_name}** tidak ditemukan.",
                    parse_mode='markdown'
                )
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
        
        # Tanyakan opsi show sender
        await ask_sender_option(event, user_id)
        
    except ValueError:
        await event.respond("❌ Masukkan angka yang valid.")


async def ask_sender_option(event, user_id: int):
    """Tanya user apakah ingin menampilkan nama pengirim atau tidak."""
    
    option_text = (
        "👤 **Opsi Pengirim**\n\n"
        "Pilih bagaimana nama pengirim ditampilkan:\n\n"
        "✅ **Tampilkan nama saya** - Penerima akan melihat nama akun Fragment Anda sebagai pengirim\n"
        "❌ **Sembunyikan nama** - Akan muncul sebagai hadiah dari Telegram (anonim)\n\n"
        "Pilih opsi di bawah:"
    )
    
    buttons = [
        [
            Button.inline("👤 Tampilkan Nama Saya", data=f"sender_show_{user_id}"),
            Button.inline("🎁 Sembunyikan (Gift)", data=f"sender_hide_{user_id}")
        ]
    ]
    
    user_states[user_id] = STATE_WAITING_SENDER_OPTION
    await event.respond(option_text, buttons=buttons, parse_mode='markdown')


async def show_confirmation(event, user_id: int):
    data = user_data[user_id]
    
    # Tentukan teks berdasarkan opsi sender
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
        [
            Button.inline("✅ Ya", data=f"confirm_{user_id}"),
            Button.inline("❌ Tidak", data=f"cancel_{user_id}")
        ],
        [Button.inline("🔙 Ubah Opsi Pengirim", data=f"sender_back_{user_id}")]
    ]
    
    user_states[user_id] = STATE_CONFIRM_PURCHASE
    await event.respond(confirm_text, buttons=buttons, parse_mode='markdown')


async def confirm_purchase(event, user_id: int):
    if user_id not in user_data:
        await event.edit("❌ Sesi kadaluarsa.")
        return
    
    purchase_data = user_data[user_id]
    
    # Pastikan show_sender memiliki nilai default True
    show_sender = purchase_data.get('show_sender', True)
    
    await event.edit(
        "⏳ **Memproses pembelian...**\n\n"
        f"Penerima: @{purchase_data['username']}\n"
        f"Stars: {format_number(purchase_data['stars'])}\n"
        f"Opsi: {'Tampilkan nama' if show_sender else 'Sembunyikan (Gift)'}",
        parse_mode='markdown'
    )
    
    # Catat pembelian dengan status pending
    await save_purchase(
        user_id=user_id,
        recipient_username=purchase_data['username'],
        recipient_nickname=purchase_data['nickname'],
        stars_amount=purchase_data['stars'],
        price_ton=purchase_data['price'],
        show_sender=show_sender,
        status="pending"
    )
    
    try:
        tx_hash = await pay_stars_order(
            username=purchase_data['username'],
            quantity=purchase_data['stars'],
            show_sender=show_sender
        )
        
        if tx_hash:
            # Update status menjadi success
            await save_purchase(
                user_id=user_id,
                recipient_username=purchase_data['username'],
                recipient_nickname=purchase_data['nickname'],
                stars_amount=purchase_data['stars'],
                price_ton=purchase_data['price'],
                tx_hash=tx_hash,
                show_sender=show_sender,
                status="success"
            )
            
            success_text = (
                "✅ **Pembelian Berhasil!**\n\n"
                f"**Penerima:** @{purchase_data['username']}\n"
                f"**Stars:** {format_number(purchase_data['stars'])}\n"
                f"**Harga:** {purchase_data['price']:.2f} TON\n"
                f"**Opsi:** {'👤 Nama ditampilkan' if show_sender else '🎁 Gift mode (anonim)'}\n"
                f"**Hash:** `{tx_hash}`\n\n"
                f"[Lihat di TON Viewer](https://tonviewer.com/transaction/{tx_hash})"
            )
            
            await event.edit(
                success_text,
                buttons=[Button.inline("🛒 Beli Lagi", data="buy")],
                parse_mode='markdown',
                link_preview=False
            )
            
            await notify_admins(purchase_data, tx_hash, show_sender)
            await log_activity(user_id, "purchase_success", f"Stars: {purchase_data['stars']}, Hash: {tx_hash}")
        else:
            # Update status menjadi failed
            await save_purchase(
                user_id=user_id,
                recipient_username=purchase_data['username'],
                recipient_nickname=purchase_data['nickname'],
                stars_amount=purchase_data['stars'],
                price_ton=purchase_data['price'],
                show_sender=show_sender,
                status="failed",
                error_message="Transaction failed"
            )
            
            await event.edit(
                "❌ **Pembelian Gagal**\n\n"
                "Coba lagi nanti.",
                buttons=[Button.inline("🔄 Coba Lagi", data="buy")],
                parse_mode='markdown'
            )
            await log_activity(user_id, "purchase_failed", f"Stars: {purchase_data['stars']}")
    
    except Exception as e:
        logger.error(f"Error: {e}")
        
        # Update status menjadi error
        await save_purchase(
            user_id=user_id,
            recipient_username=purchase_data['username'],
            recipient_nickname=purchase_data['nickname'],
            stars_amount=purchase_data['stars'],
            price_ton=purchase_data['price'],
            show_sender=show_sender,
            status="error",
            error_message=str(e)[:200]
        )
        
        await event.edit(
            f"❌ **Error:** {str(e)[:100]}",
            buttons=[Button.inline("🔄 Coba Lagi", data="buy")],
            parse_mode='markdown'
        )
        await log_activity(user_id, "purchase_error", str(e)[:100])
    finally:
        # Hapus pending purchase
        await delete_pending_purchase(user_id)
        
        if user_id in user_states:
            del user_states[user_id]
        if user_id in user_data:
            del user_data[user_id]


async def cancel_purchase(event, user_id: int):
    if user_id in user_states:
        del user_states[user_id]
    if user_id in user_data:
        del user_data[user_id]
    
    # Hapus pending purchase
    await delete_pending_purchase(user_id)
    
    await event.edit(
        "❌ **Pembelian Dibatalkan**",
        buttons=[Button.inline("🛒 Beli Stars", data="buy")],
        parse_mode='markdown'
    )
    await log_activity(user_id, "purchase_cancelled", "User cancelled purchase")


async def notify_admins(purchase_data: dict, tx_hash: str, show_sender: bool):
    notif = (
        "💰 **Pembelian Baru**\n\n"
        f"**User:** @{purchase_data['username']}\n"
        f"**Stars:** {format_number(purchase_data['stars'])}\n"
        f"**Harga:** {purchase_data['price']:.2f} TON\n"
        f"**Opsi:** {'👤 Tampil' if show_sender else '🎁 Gift'}\n"
        f"**Tx Hash:** `{tx_hash}`"
    )
    
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, notif, parse_mode='markdown')
        except Exception as e:
            logger.error(f"Gagal notifikasi admin {admin_id}: {e}")


# ===================== MAIN =====================

async def main():
    logger.info("Memulai Fragment Stars Bot...")
    
    # Inisialisasi database
    init_database()
    
    if not API_ID or not API_HASH or not BOT_TOKEN:
        logger.error("❌ Konfigurasi Telegram tidak lengkap")
        return
    
    logger.info(f"📊 COOKIES length: {len(COOKIES)}")
    logger.info(f"📊 HASH length: {len(HASH)}")
    logger.info(f"📊 WALLET_MNEMONIC length: {len(WALLET_MNEMONIC)}")
    
    logger.info("✅ Starting bot...")
    await bot.start(bot_token=BOT_TOKEN)
    logger.info("✅ Bot berjalan. Tekan Ctrl+C untuk berhenti.")
    await bot.run_until_disconnected()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Bot dihentikan oleh user")
    except Exception as e:
        logger.error(f"❌ Error fatal: {e}")
