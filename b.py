# b.py - Fragment Stars Bot - VERSION MULTI-BOT WITH CLONE MANAGEMENT
import os
import json
import base64
import asyncio
import logging
import sqlite3
import subprocess
import signal
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List
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

# ===================== DATABASE FUNCTIONS (DIPERLUAS) =====================

def init_database():
    """Inisialisasi database SQLite3 dengan tabel baru untuk bot clone."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Tabel untuk menyimpan data pengguna (existing)
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
    
    # Tabel untuk menyimpan riwayat pembelian (existing)
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
    
    # Tabel untuk menyimpan log aktivitas (existing)
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
    
    # Tabel untuk menyimpan konfigurasi bot (existing)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bot_config (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP
        )
    ''')
    
    # Tabel untuk menyimpan sesi pembelian yang belum selesai (existing)
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
    
    # ============= TABEL BARU: BOT CLONES =============
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bot_clones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_user_id INTEGER NOT NULL,
            owner_username TEXT,
            bot_name TEXT,
            bot_token TEXT UNIQUE NOT NULL,
            api_id INTEGER NOT NULL,
            api_hash TEXT NOT NULL,
            cookies TEXT NOT NULL,
            hash TEXT NOT NULL,
            wallet_api_key TEXT NOT NULL,
            wallet_mnemonic TEXT NOT NULL,
            price_per_star REAL DEFAULT 0.02,
            min_stars INTEGER DEFAULT 10,
            max_stars INTEGER DEFAULT 100000,
            status TEXT DEFAULT 'stopped',
            pid INTEGER,
            port INTEGER UNIQUE,
            created_at TIMESTAMP,
            last_active TIMESTAMP,
            expires_at TIMESTAMP,
            FOREIGN KEY (owner_user_id) REFERENCES users (user_id)
        )
    ''')
    
    # Tabel untuk menyimpan statistik per bot clone
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bot_stats (
            bot_id INTEGER,
            date DATE,
            total_purchases INTEGER DEFAULT 0,
            total_stars INTEGER DEFAULT 0,
            total_volume REAL DEFAULT 0,
            PRIMARY KEY (bot_id, date),
            FOREIGN KEY (bot_id) REFERENCES bot_clones (id)
        )
    ''')
    
    conn.commit()
    conn.close()
    logger.info("✅ Database initialized successfully with clone management tables")


# ===================== FUNGSI MANAJEMEN BOT CLONE =====================

async def register_bot_clone(
    owner_user_id: int,
    owner_username: str,
    bot_token: str,
    api_id: int,
    api_hash: str,
    cookies: str,
    hash: str,
    wallet_api_key: str,
    wallet_mnemonic: list,
    price_per_star: float = 0.02,
    min_stars: int = 10,
    max_stars: int = 100000
) -> Optional[int]:
    """Mendaftarkan bot clone baru ke database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Cek apakah token sudah digunakan
        cursor.execute("SELECT id FROM bot_clones WHERE bot_token = ?", (bot_token,))
        if cursor.fetchone():
            logger.error(f"Bot token {bot_token} already registered")
            conn.close()
            return None
        
        # Cari port yang tersedia (mulai dari 5001)
        cursor.execute("SELECT port FROM bot_clones ORDER BY port DESC LIMIT 1")
        last_port = cursor.fetchone()
        port = (last_port[0] + 1) if last_port else 5001
        
        now = datetime.now().isoformat()
        
        cursor.execute('''
            INSERT INTO bot_clones (
                owner_user_id, owner_username, bot_token, api_id, api_hash,
                cookies, hash, wallet_api_key, wallet_mnemonic,
                price_per_star, min_stars, max_stars, status, port, created_at, last_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            owner_user_id, owner_username, bot_token, api_id, api_hash,
            cookies, hash, wallet_api_key, json.dumps(wallet_mnemonic),
            price_per_star, min_stars, max_stars, 'stopped', port, now, now
        ))
        
        bot_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        logger.info(f"✅ Bot clone registered with ID: {bot_id}, port: {port}")
        return bot_id
        
    except Exception as e:
        logger.error(f"Error registering bot clone: {e}")
        return None


async def start_bot_clone(bot_id: int) -> bool:
    """Menjalankan bot clone berdasarkan ID."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Ambil data bot
        cursor.execute('''
            SELECT bot_token, api_id, api_hash, cookies, hash, 
                   wallet_api_key, wallet_mnemonic, port,
                   price_per_star, min_stars, max_stars
            FROM bot_clones WHERE id = ?
        ''', (bot_id,))
        
        bot_data = cursor.fetchone()
        conn.close()
        
        if not bot_data:
            logger.error(f"Bot clone {bot_id} not found")
            return False
        
        (bot_token, api_id, api_hash, cookies, hash,
         wallet_api_key, wallet_mnemonic_json, port,
         price_per_star, min_stars, max_stars) = bot_data
        
        wallet_mnemonic = json.loads(wallet_mnemonic_json)
        
        # Buat file konfigurasi untuk bot clone
        config_dir = Path(f"bots/bot_{bot_id}")
        config_dir.mkdir(parents=True, exist_ok=True)
        
        # Buat file .env untuk bot clone
        env_content = f"""
API_ID={api_id}
API_HASH={api_hash}
BOT_TOKEN={bot_token}
COOKIES={cookies}
HASH={hash}
WALLET_API_KEY={wallet_api_key}
WALLET_MNEMONIC={json.dumps(wallet_mnemonic)}
PRICE_PER_STAR={price_per_star}
MIN_STARS={min_stars}
MAX_STARS={max_stars}
ADMIN_IDS={bot_id}
DB_PATH=../frag.db
PORT={port}
"""
        
        with open(config_dir / ".env", "w") as f:
            f.write(env_content)
        
        # Buat file bot_clone.py dari template
        clone_code = generate_clone_bot_code(bot_id, port)
        with open(config_dir / "bot_clone.py", "w") as f:
            f.write(clone_code)
        
        # Jalankan bot clone sebagai subprocess
        process = subprocess.Popen(
            [sys.executable, "bot_clone.py"],
            cwd=str(config_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True
        )
        
        # Update status di database
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE bot_clones 
            SET status = 'running', pid = ?, last_active = ?
            WHERE id = ?
        ''', (process.pid, datetime.now().isoformat(), bot_id))
        conn.commit()
        conn.close()
        
        logger.info(f"✅ Bot clone {bot_id} started with PID {process.pid}")
        return True
        
    except Exception as e:
        logger.error(f"Error starting bot clone {bot_id}: {e}")
        return False


def generate_clone_bot_code(bot_id: int, port: int) -> str:
    """Generate kode untuk bot clone."""
    return f'''# bot_clone.py - Bot Clone for ID {bot_id}
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
from dotenv import load_dotenv
from telethon import TelegramClient, events, Button

# Import tonutils
from tonutils.client import TonapiClient
from tonutils.wallet import WalletV5R1

load_dotenv()

# Konfigurasi dari environment
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
COOKIES = os.getenv("COOKIES")
HASH = os.getenv("HASH")
WALLET_API_KEY = os.getenv("WALLET_API_KEY")
WALLET_MNEMONIC = json.loads(os.getenv("WALLET_MNEMONIC"))
PRICE_PER_STAR = float(os.getenv("PRICE_PER_STAR", 0.02))
MIN_STARS = int(os.getenv("MIN_STARS", 10))
MAX_STARS = int(os.getenv("MAX_STARS", 100000))
PORT = int(os.getenv("PORT", {port}))
BOT_ID = {bot_id}
DB_PATH = os.getenv("DB_PATH", "../frag.db")

# Logging
logging.basicConfig(
    format='%(asctime)s - Bot{bot_id} - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

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
        logger.error(f"Error decoding: {{e}}")
        return encoded_string


async def post(data: dict) -> Optional[dict]:
    """POST request ke Fragment API."""
    params = {{"hash": HASH}}
    headers = {{
        "accept": "application/json",
        "cookie": COOKIES,
        "user-agent": "Mozilla/5.0",
        "x-requested-with": "XMLHttpRequest",
    }}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://fragment.com/api",
                params=params,
                headers=headers,
                data=data
            ) as response:
                if response.status == 200:
                    return await response.json()
                return None
    except Exception as e:
        logger.error(f"Connection error: {{e}}")
        return None


async def get_user_address(username: str) -> Optional[dict]:
    """Cari user di Fragment."""
    data = {{
        "query": username,
        "method": "searchStarsRecipient"
    }}
    return await post(data)


async def init_buy_stars(recipient: str, quantity: int) -> Optional[dict]:
    """Inisialisasi pembelian stars."""
    data = {{
        "recipient": recipient,
        "quantity": quantity,
        "method": "initBuyStarsRequest"
    }}
    return await post(data)


async def get_buy_stars(req_id: str, show_sender: str = "1") -> Optional[dict]:
    """Dapatkan detail pembayaran."""
    data = {{
        "transaction": "1",
        "id": req_id,
        "show_sender": show_sender,
        "method": "getBuyStarsLink"
    }}
    return await post(data)


# ===================== WALLET FUNCTIONS =====================

async def send_transfer(address: str, amount: int, payload: str) -> Optional[str]:
    """Kirim transfer TON."""
    try:
        client = TonapiClient(api_key=WALLET_API_KEY, is_testnet=False)
        wallet, _, _, _ = WalletV5R1.from_mnemonic(client, WALLET_MNEMONIC)

        amount_in_ton = amount / 1_000_000_000
        logger.info(f"Sending {{amount_in_ton}} TON to {{address}}")
        
        tx_hash = await wallet.transfer(
            destination=address,
            amount=amount_in_ton,
            body=payload,
        )
        return tx_hash
    except Exception as e:
        logger.error(f"Error in send_transfer: {{e}}")
        return None


async def pay_stars_order(username: str, quantity: int, show_sender: bool = True) -> Optional[str]:
    """Proses pembayaran stars."""
    try:
        logger.info(f"Starting payment for @{{username}} - {{quantity}} stars (show_sender={{show_sender}})")
        
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

        # 3. Get buy details
        show_sender_value = "1" if show_sender else "0"
        buy = await get_buy_stars(req_id, show_sender_value)
        if not buy:
            logger.error("Failed to get buy details")
            return None
            
        messages = buy.get("transaction", {{}}).get("messages", [])
        if not messages:
            logger.error("No messages in transaction")
            return None
            
        pay_address = messages[0].get("address")
        amount = messages[0].get("amount")
        payload = messages[0].get("payload")

        if not all([pay_address, amount, payload]):
            logger.error("Missing transaction data")
            return None

        # 4. Decode payload and send
        decoded_payload = await encoded(payload)
        tx_hash = await send_transfer(pay_address, int(amount), decoded_payload)

        if tx_hash:
            logger.info(f"Transaction successful: {{tx_hash}}")
            return tx_hash
        return None
        
    except Exception as e:
        logger.error(f"Error in pay_stars_order: {{e}}")
        return None


# ===================== BOT INITIALIZATION =====================
print(f"Starting bot clone {BOT_ID} on port {PORT}...")
bot = TelegramClient(f'bot_clone_{BOT_ID}', API_ID, API_HASH)

# State management
user_states: Dict[int, str] = {{}}
user_data: Dict[int, Dict[str, Any]] = {{}}

STATE_IDLE = "idle"
STATE_WAITING_USERNAME = "waiting_username"
STATE_WAITING_STARS = "waiting_stars"
STATE_WAITING_SENDER_OPTION = "waiting_sender_option"
STATE_CONFIRM_PURCHASE = "confirm_purchase"


# ===================== HELPER FUNCTIONS =====================

def format_number(num: int) -> str:
    return f"{{num:,}}".replace(",", ".")


def clean_username(username: str) -> str:
    return username.strip().replace('@', '')


# ===================== HANDLERS =====================

@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    user = await event.get_sender()
    user_id = event.sender_id
    
    welcome_text = (
        f"🌟 **Selamat Datang di Bot Clone {BOT_ID}** 🌟\n\n"
        f"Halo {{user.first_name}}!\n\n"
        f"**Informasi:**\n"
        f"• 💰 Harga: `{{PRICE_PER_STAR}}` TON per star\n"
        f"• 📊 Minimal: `{{MIN_STARS}}` stars\n"
        f"• 📈 Maksimal: `{{MAX_STARS}}` stars\n\n"
        f"_Bot ini adalah dedicated instance untuk Anda_"
    )
    
    buttons = [
        [Button.inline("🛒 Beli Stars", data="buy")],
        [Button.inline("ℹ️ Cara Pakai", data="howto")]
    ]
    
    await event.respond(welcome_text, buttons=buttons, parse_mode='markdown')


@bot.on(events.NewMessage(pattern='/buy'))
async def buy_command(event):
    user_id = event.sender_id
    user_states[user_id] = STATE_WAITING_USERNAME
    user_data[user_id] = {{}}
    
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
    
    if user_id in user_states:
        del user_states[user_id]
    if user_id in user_data:
        del user_data[user_id]
    
    await event.respond("✅ **Operasi dibatalkan.**", parse_mode='markdown')


@bot.on(events.CallbackQuery)
async def callback_handler(event):
    user_id = event.sender_id
    data = event.data.decode('utf-8')
    
    if data == "buy":
        user_states[user_id] = STATE_WAITING_USERNAME
        user_data[user_id] = {{}}
        await event.edit(
            "🛒 **Mulai Pembelian Stars**\n\n"
            "Silakan masukkan **username** penerima:",
            parse_mode='markdown'
        )
    
    elif data == "howto":
        await event.edit(
            "📖 **Cara Menggunakan Bot**\n\n"
            "1️⃣ Klik 'Beli Stars' atau ketik /buy\n"
            "2️⃣ Masukkan username penerima\n"
            "3️⃣ Masukkan jumlah stars\n"
            "4️⃣ Pilih opsi pengirim\n"
            "5️⃣ Konfirmasi pembelian\n"
            "6️⃣ Tunggu proses selesai",
            buttons=[Button.inline("🔙 Kembali", data="start")],
            parse_mode='markdown'
        )
    
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
            user_info = await get_user_address(clean_name)
            
            if not user_info or not user_info.get("found"):
                await event.respond(
                    f"❌ Username **@{clean_name}** tidak ditemukan.",
                    parse_mode='markdown'
                )
                return
            
            user_data[user_id]['username'] = clean_name
            user_data[user_id]['nickname'] = user_info['found']['name']
            user_data[user_id]['address'] = user_info['found']['recipient']
            
            user_states[user_id] = STATE_WAITING_STARS
            
            await event.respond(
                f"✅ **User Ditemukan:** {{user_info['found']['name']}}\n\n"
                f"Masukkan **jumlah stars** (angka):\n"
                f"Min: {{MIN_STARS:,}} - Max: {{MAX_STARS:,}}",
                parse_mode='markdown'
            )
            
        except Exception as e:
            logger.error(f"Error: {{e}}")
            await event.respond("❌ Terjadi kesalahan.")


async def process_stars(event, user_id: int, stars_str: str):
    try:
        stars = int(stars_str)
        
        if stars < MIN_STARS:
            await event.respond(f"❌ Minimal {{MIN_STARS:,}} stars")
            return
        
        if stars > MAX_STARS:
            await event.respond(f"❌ Maksimal {{MAX_STARS:,}} stars")
            return
        
        user_data[user_id]['stars'] = stars
        user_data[user_id]['price'] = stars * PRICE_PER_STAR
        
        # Tanyakan opsi sender
        await ask_sender_option(event, user_id)
        
    except ValueError:
        await event.respond("❌ Masukkan angka yang valid.")


async def ask_sender_option(event, user_id: int):
    option_text = (
        "👤 **Opsi Pengirim**\n\n"
        "Pilih bagaimana nama pengirim ditampilkan:\n\n"
        "✅ **Tampilkan nama saya**\n"
        "❌ **Sembunyikan nama (Gift)**"
    )
    
    buttons = [
        [
            Button.inline("👤 Tampilkan", data=f"sender_show_{{user_id}}"),
            Button.inline("🎁 Sembunyikan", data=f"sender_hide_{{user_id}}")
        ]
    ]
    
    user_states[user_id] = STATE_WAITING_SENDER_OPTION
    await event.respond(option_text, buttons=buttons, parse_mode='markdown')


async def show_confirmation(event, user_id: int):
    data = user_data[user_id]
    sender_text = "👤 Menampilkan nama" if data.get('show_sender', True) else "🎁 Gift mode"
    
    confirm_text = (
        "📝 **Konfirmasi Pembelian**\n\n"
        f"**Penerima:** {{data['nickname']}}\n"
        f"**Username:** @{{data['username']}}\n"
        f"**Stars:** {{format_number(data['stars'])}}\n"
        f"**Harga:** {{data['price']:.2f}} TON\n"
        f"**Opsi:** {{sender_text}}\n\n"
        "⚠️ Transaksi tidak dapat dibatalkan!\n\n"
        "Setuju?"
    )
    
    buttons = [
        [
            Button.inline("✅ Ya", data=f"confirm_{{user_id}}"),
            Button.inline("❌ Tidak", data=f"cancel_{{user_id}}")
        ],
        [Button.inline("🔙 Ubah Opsi", data=f"sender_back_{{user_id}}")]
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
        f"Penerima: @{{purchase_data['username']}}\n"
        f"Stars: {{format_number(purchase_data['stars'])}}",
        parse_mode='markdown'
    )
    
    try:
        tx_hash = await pay_stars_order(
            username=purchase_data['username'],
            quantity=purchase_data['stars'],
            show_sender=show_sender
        )
        
        if tx_hash:
            success_text = (
                "✅ **Pembelian Berhasil!**\n\n"
                f"**Penerima:** @{{purchase_data['username']}}\n"
                f"**Stars:** {{format_number(purchase_data['stars'])}}\n"
                f"**Hash:** `{{tx_hash}}`\n\n"
                f"[Lihat di TON Viewer](https://tonviewer.com/transaction/{{tx_hash}})"
            )
            
            await event.edit(
                success_text,
                buttons=[Button.inline("🛒 Beli Lagi", data="buy")],
                parse_mode='markdown',
                link_preview=False
            )
        else:
            await event.edit(
                "❌ **Pembelian Gagal**\n\n"
                "Coba lagi nanti.",
                buttons=[Button.inline("🔄 Coba Lagi", data="buy")],
                parse_mode='markdown'
            )
    
    except Exception as e:
        logger.error(f"Error: {{e}}")
        await event.edit(
            f"❌ **Error:** {{str(e)[:100]}}",
            buttons=[Button.inline("🔄 Coba Lagi", data="buy")],
            parse_mode='markdown'
        )
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
    
    await event.edit(
        "❌ **Pembelian Dibatalkan**",
        buttons=[Button.inline("🛒 Beli Stars", data="buy")],
        parse_mode='markdown'
    )


# ===================== MAIN =====================

async def main():
    logger.info(f"Starting bot clone {BOT_ID} on port {PORT}...")
    await bot.start(bot_token=BOT_TOKEN)
    logger.info(f"✅ Bot clone {BOT_ID} is running")
    await bot.run_until_disconnected()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info(f"🛑 Bot clone {BOT_ID} stopped by user")
    except Exception as e:
        logger.error(f"❌ Error fatal: {{e}}")
'''


async def stop_bot_clone(bot_id: int) -> bool:
    """Menghentikan bot clone berdasarkan ID."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("SELECT pid FROM bot_clones WHERE id = ?", (bot_id,))
        result = cursor.fetchone()
        
        if result and result[0]:
            pid = result[0]
            try:
                # Kirim signal termination
                os.kill(pid, signal.SIGTERM)
                await asyncio.sleep(2)
                
                # Force kill if still running
                try:
                    os.kill(pid, 0)  # Check if process exists
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass  # Process already terminated
            except ProcessLookupError:
                pass  # Process not found
            
            # Update status di database
            cursor.execute('''
                UPDATE bot_clones 
                SET status = 'stopped', pid = NULL, last_active = ?
                WHERE id = ?
            ''', (datetime.now().isoformat(), bot_id))
            conn.commit()
        
        conn.close()
        logger.info(f"✅ Bot clone {bot_id} stopped")
        return True
        
    except Exception as e:
        logger.error(f"Error stopping bot clone {bot_id}: {e}")
        return False


async def get_user_bots(user_id: int) -> List[Dict]:
    """Mendapatkan daftar bot milik user."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, bot_token, status, port, created_at, last_active
            FROM bot_clones WHERE owner_user_id = ?
            ORDER BY created_at DESC
        ''', (user_id,))
        
        bots = []
        for row in cursor.fetchall():
            bots.append({
                'id': row[0],
                'bot_token': row[1][:10] + '...',  # Mask token
                'status': row[2],
                'port': row[3],
                'created_at': row[4],
                'last_active': row[5]
            })
        
        conn.close()
        return bots
        
    except Exception as e:
        logger.error(f"Error getting user bots: {e}")
        return []


# ===================== BOT UTAMA (MANAGER) =====================

print("Starting Main Bot (Manager)...")
bot = TelegramClient('fragment_bot_session', API_ID, API_HASH)

# State management untuk main bot
user_states: Dict[int, str] = {}
user_data: Dict[int, Dict[str, Any]] = {}

STATE_IDLE = "idle"
STATE_WAITING_CLONE_DATA = "waiting_clone_data"  # State baru untuk input data clone

# ===================== HANDLERS BOT UTAMA =====================

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
    
    # Cek apakah user sudah punya bot clone
    user_bots = await get_user_bots(user_id)
    
    welcome_text = (
        f"🌟 **Selamat Datang di Fragment Stars Bot Manager** 🌟\n\n"
        f"Halo {user.first_name}!\n\n"
        f"Anda dapat membuat bot clone Anda sendiri untuk membeli Telegram stars.\n\n"
        f"**Menu yang tersedia:**\n"
        f"• /create_bot - Membuat bot clone baru\n"
        f"• /my_bots - Melihat daftar bot clone Anda\n"
        f"• /start_bot <id> - Menjalankan bot clone\n"
        f"• /stop_bot <id> - Menghentikan bot clone\n"
        f"• /delete_bot <id> - Menghapus bot clone\n\n"
    )
    
    if user_bots:
        welcome_text += f"**Anda memiliki {len(user_bots)} bot clone terdaftar.**"
    
    buttons = [
        [Button.inline("🆕 Buat Bot Baru", data="create_bot")],
        [Button.inline("📋 Lihat Bot Saya", data="my_bots")],
    ]
    
    if await is_admin(user_id):
        buttons.append([Button.inline("⚙️ Admin Panel", data="admin")])
    
    await event.respond(welcome_text, buttons=buttons, parse_mode='markdown')


@bot.on(events.NewMessage(pattern='/create_bot'))
async def create_bot_command(event):
    user_id = event.sender_id
    
    await log_activity(user_id, "create_bot", "User initiated bot creation")
    
    user_states[user_id] = STATE_WAITING_CLONE_DATA
    user_data[user_id] = {}
    
    instruction_text = (
        "🤖 **Membuat Bot Clone Baru**\n\n"
        "Silakan kirimkan data berikut dalam format **JSON**:\n\n"
        "```json\n"
        "{\n"
        '    "bot_token": "8609719835:AAEOhr8L4eKIcRfB-Db0BIMMMCasQtVMWPw",\n'
        '    "api_id": 24576633,\n'
        '    "api_hash": "29931cf620fad738ee7f69442c98e2ee",\n'
        '    "cookies": "stel_dt=-420; stel_ssid=...",\n'
        '    "hash": "0394b81a825a9ce9a7",\n'
        '    "wallet_api_key": "AHAGWHBL6PZ6IHYAAA...",\n'
        '    "wallet_mnemonic": ["word1", "word2", ...],\n'
        '    "price_per_star": 0.02,\n'
        '    "min_stars": 10,\n'
        '    "max_stars": 100000\n'
        "}\n"
        "```\n\n"
        "Ketik /cancel untuk membatalkan."
    )
    
    await event.respond(instruction_text, parse_mode='markdown')


@bot.on(events.NewMessage(pattern='/my_bots'))
async def my_bots_command(event):
    user_id = event.sender_id
    user_bots = await get_user_bots(user_id)
    
    if not user_bots:
        await event.respond("❌ Anda belum memiliki bot clone. Gunakan /create_bot untuk membuatnya.")
        return
    
    text = "📋 **Daftar Bot Clone Anda:**\n\n"
    for bot in user_bots:
        text += (
            f"**ID:** `{bot['id']}`\n"
            f"**Token:** `{bot['bot_token']}`\n"
            f"**Status:** {'🟢 Running' if bot['status'] == 'running' else '🔴 Stopped'}\n"
            f"**Port:** {bot['port']}\n"
            f"**Dibuat:** {bot['created_at'][:19]}\n"
            f"**Aktif:** {bot['last_active'][:19]}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
        )
    
    buttons = [
        [Button.inline("🔄 Refresh", data="refresh_bots")],
        [Button.inline("🔙 Kembali", data="start")]
    ]
    
    await event.respond(text, buttons=buttons, parse_mode='markdown')


@bot.on(events.NewMessage(pattern='/start_bot'))
async def start_bot_command(event):
    user_id = event.sender_id
    args = event.message.text.split()
    
    if len(args) < 2:
        await event.respond("❌ Gunakan: `/start_bot <bot_id>`", parse_mode='markdown')
        return
    
    try:
        bot_id = int(args[1])
        
        # Verifikasi kepemilikan
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT owner_user_id FROM bot_clones WHERE id = ?", (bot_id,))
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            await event.respond("❌ Bot ID tidak ditemukan.")
            return
        
        if result[0] != user_id and not await is_admin(user_id):
            await event.respond("❌ Anda tidak memiliki akses ke bot ini.")
            return
        
        await event.respond(f"⏳ **Menjalankan bot {bot_id}...**")
        
        success = await start_bot_clone(bot_id)
        
        if success:
            await event.respond(f"✅ **Bot {bot_id} berhasil dijalankan!**")
        else:
            await event.respond(f"❌ **Gagal menjalankan bot {bot_id}.**")
            
    except ValueError:
        await event.respond("❌ Bot ID harus berupa angka.")


@bot.on(events.NewMessage(pattern='/stop_bot'))
async def stop_bot_command(event):
    user_id = event.sender_id
    args = event.message.text.split()
    
    if len(args) < 2:
        await event.respond("❌ Gunakan: `/stop_bot <bot_id>`", parse_mode='markdown')
        return
    
    try:
        bot_id = int(args[1])
        
        # Verifikasi kepemilikan
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT owner_user_id FROM bot_clones WHERE id = ?", (bot_id,))
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            await event.respond("❌ Bot ID tidak ditemukan.")
            return
        
        if result[0] != user_id and not await is_admin(user_id):
            await event.respond("❌ Anda tidak memiliki akses ke bot ini.")
            return
        
        await event.respond(f"⏳ **Menghentikan bot {bot_id}...**")
        
        success = await stop_bot_clone(bot_id)
        
        if success:
            await event.respond(f"✅ **Bot {bot_id} berhasil dihentikan!**")
        else:
            await event.respond(f"❌ **Gagal menghentikan bot {bot_id}.**")
            
    except ValueError:
        await event.respond("❌ Bot ID harus berupa angka.")


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
    
    if state == STATE_WAITING_CLONE_DATA:
        await process_clone_data(event, user_id, message)


async def process_clone_data(event, user_id: int, data_str: str):
    """Memproses data JSON untuk pembuatan bot clone."""
    try:
        # Parse JSON
        data = json.loads(data_str)
        
        # Validasi field yang diperlukan
        required_fields = ['bot_token', 'api_id', 'api_hash', 'cookies', 'hash', 
                          'wallet_api_key', 'wallet_mnemonic']
        
        missing = [field for field in required_fields if field not in data]
        if missing:
            await event.respond(f"❌ Field berikut tidak ditemukan: {', '.join(missing)}")
            return
        
        # Validasi mnemonic harus list
        if not isinstance(data['wallet_mnemonic'], list):
            await event.respond("❌ wallet_mnemonic harus berupa array/list")
            return
        
        # Validasi API ID harus integer
        try:
            data['api_id'] = int(data['api_id'])
        except:
            await event.respond("❌ api_id harus berupa angka")
            return
        
        # Dapatkan username user
        user = await event.get_sender()
        username = user.username or f"user_{user_id}"
        
        # Register bot clone
        bot_id = await register_bot_clone(
            owner_user_id=user_id,
            owner_username=username,
            bot_token=data['bot_token'],
            api_id=data['api_id'],
            api_hash=data['api_hash'],
            cookies=data['cookies'],
            hash=data['hash'],
            wallet_api_key=data['wallet_api_key'],
            wallet_mnemonic=data['wallet_mnemonic'],
            price_per_star=data.get('price_per_star', 0.02),
            min_stars=data.get('min_stars', 10),
            max_stars=data.get('max_stars', 100000)
        )
        
        if bot_id:
            # Bersihkan state
            if user_id in user_states:
                del user_states[user_id]
            if user_id in user_data:
                del user_data[user_id]
            
            success_text = (
                f"✅ **Bot Clone Berhasil Dibuat!**\n\n"
                f"**ID Bot:** `{bot_id}`\n"
                f"**Token:** `{data['bot_token'][:10]}...`\n\n"
                f"**Perintah:**\n"
                f"• /start_bot {bot_id} - Jalankan bot\n"
                f"• /stop_bot {bot_id} - Hentikan bot\n"
                f"• /delete_bot {bot_id} - Hapus bot\n\n"
                f"Bot akan berjalan di port internal. Gunakan /my_bots untuk melihat status."
            )
            
            await event.respond(success_text, parse_mode='markdown')
            await log_activity(user_id, "bot_created", f"Bot ID: {bot_id}")
        else:
            await event.respond("❌ **Gagal membuat bot clone.** Mungkin token sudah digunakan.")
            
    except json.JSONDecodeError:
        await event.respond("❌ **Format JSON tidak valid.** Pastikan formatnya benar.")
    except Exception as e:
        logger.error(f"Error processing clone data: {e}")
        await event.respond(f"❌ **Error:** {str(e)[:100]}")


@bot.on(events.CallbackQuery)
async def callback_handler(event):
    user_id = event.sender_id
    data = event.data.decode('utf-8')
    
    if data == "create_bot":
        await create_bot_command(event)
    
    elif data == "my_bots":
        await my_bots_command(event)
    
    elif data == "refresh_bots":
        await my_bots_command(event)
    
    elif data == "start":
        await start_handler(event)
    
    elif data == "admin":
        if not await is_admin(user_id):
            await event.answer("Akses ditolak!", alert=True)
            return
        
        # Admin panel dengan statistik bot clones
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*), SUM(CASE WHEN status='running' THEN 1 ELSE 0 END) FROM bot_clones")
        total_bots, active_bots = cursor.fetchone()
        conn.close()
        
        admin_text = (
            "⚙️ **Admin Panel**\n\n"
            f"• Total Bot Clone: {total_bots or 0}\n"
            f"• Bot Aktif: {active_bots or 0}\n"
            f"• Pengguna Aktif: {len(user_states)}\n\n"
            f"**Perintah Admin:**\n"
            f"• /list_all_bots - Lihat semua bot\n"
            f"• /stop_all_bots - Hentikan semua bot\n"
        )
        
        buttons = [
            [Button.inline("📊 Statistik Detail", data="admin_stats")],
            [Button.inline("🔙 Kembali", data="start")]
        ]
        await event.edit(admin_text, buttons=buttons, parse_mode='markdown')
    
    elif data == "admin_stats":
        if not await is_admin(user_id):
            await event.answer("Akses ditolak!", alert=True)
            return
        
        # Tampilkan 10 bot terakhir
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, owner_user_id, status, port, created_at
            FROM bot_clones
            ORDER BY created_at DESC LIMIT 10
        ''')
        recent_bots = cursor.fetchall()
        conn.close()
        
        text = "📊 **10 Bot Clone Terbaru**\n\n"
        for bot in recent_bots:
            text += f"ID: {bot[0]} | Owner: {bot[1]} | Status: {bot[2]} | Port: {bot[3]} | {bot[4][:19]}\n"
        
        await event.edit(
            text,
            buttons=[Button.inline("🔙 Kembali", data="admin")],
            parse_mode='markdown'
        )


# ===================== MAIN =====================

async def main():
    logger.info("Memulai Fragment Stars Bot Manager...")
    
    # Inisialisasi database
    init_database()
    
    # Buat direktori untuk bots jika belum ada
    Path("bots").mkdir(exist_ok=True)
    
    if not API_ID or not API_HASH or not BOT_TOKEN:
        logger.error("❌ Konfigurasi Telegram tidak lengkap")
        return
    
    logger.info("✅ Starting main bot...")
    await bot.start(bot_token=BOT_TOKEN)
    logger.info("✅ Main bot berjalan. Tekan Ctrl+C untuk berhenti.")
    
    # Jalankan ulang bot clone yang statusnya running (recovery)
    await restart_running_bots()
    
    await bot.run_until_disconnected()


async def restart_running_bots():
    """Restart semua bot clone yang statusnya running (untuk recovery)."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM bot_clones WHERE status = 'running'")
        running_bots = cursor.fetchall()
        conn.close()
        
        for (bot_id,) in running_bots:
            logger.info(f"Restarting bot clone {bot_id}...")
            await start_bot_clone(bot_id)
            await asyncio.sleep(1)  # Beri jeda antar bot
            
    except Exception as e:
        logger.error(f"Error restarting bots: {e}")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Main bot dihentikan oleh user")
        
        # Hentikan semua bot clone
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT id, pid FROM bot_clones WHERE status = 'running'")
            running_bots = cursor.fetchall()
            conn.close()
            
            for bot_id, pid in running_bots:
                if pid:
                    try:
                        os.kill(pid, signal.SIGTERM)
                        logger.info(f"Stopped bot clone {bot_id}")
                    except:
                        pass
        except:
            pass
            
    except Exception as e:
        logger.error(f"❌ Error fatal: {e}")
