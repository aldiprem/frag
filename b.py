# b.py - Fragment Stars Bot - VERSION FINAL (SUDAH DIUJI)
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
from dotenv import load_dotenv
from telethon import TelegramClient, events, Button

from tonutils.client import TonapiClient
from tonutils.wallet import WalletV5R1

# ===================== LOAD ENVIRONMENT =====================
env_path = Path('.') / '.env'
load_dotenv(dotenv_path=env_path)
print(f"Loading .env from: {env_path.absolute()}")

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

DB_PATH = "frag.db"

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===================== DATABASE FUNCTIONS =====================

def init_database():
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
            FOREIGN KEY (user_id) REFERENCES users (user_id)
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
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bot_clones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_user_id INTEGER NOT NULL,
            owner_username TEXT,
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
            last_active TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    logger.info("✅ Database initialized")


async def save_user(user_id: int, username: str = None, first_name: str = None, last_name: str = None):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        existing = cursor.fetchone()
        now = datetime.now().isoformat()
        is_admin = 1 if user_id in ADMIN_IDS else 0
        
        if existing:
            cursor.execute('''
                UPDATE users SET username=?, first_name=?, last_name=?, last_seen=?, is_admin=?
                WHERE user_id=?
            ''', (username, first_name, last_name, now, is_admin, user_id))
        else:
            cursor.execute('''
                INSERT INTO users (user_id, username, first_name, last_name, is_admin, first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, username, first_name, last_name, is_admin, now, now))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error saving user: {e}")


async def log_activity(user_id: int, action: str, details: str = None):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO activity_log (user_id, action, details, timestamp)
            VALUES (?, ?, ?, ?)
        ''', (user_id, action, details, datetime.now().isoformat()))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error logging activity: {e}")


async def get_user_bots(user_id: int) -> List[Dict]:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, bot_token, status, port, created_at, last_active
            FROM bot_clones WHERE owner_user_id = ? ORDER BY created_at DESC
        ''', (user_id,))
        bots = []
        for row in cursor.fetchall():
            bots.append({
                'id': row[0],
                'bot_token': row[1][:10] + '...',
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


async def register_bot_clone(owner_user_id: int, owner_username: str, bot_token: str, api_id: int,
                            api_hash: str, cookies: str, hash: str, wallet_api_key: str,
                            wallet_mnemonic: list, price_per_star: float = 0.02,
                            min_stars: int = 10, max_stars: int = 100000) -> Optional[int]:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM bot_clones WHERE bot_token = ?", (bot_token,))
        if cursor.fetchone():
            conn.close()
            return None
        
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
        ''', (owner_user_id, owner_username, bot_token, api_id, api_hash, cookies, hash,
              wallet_api_key, json.dumps(wallet_mnemonic), price_per_star, min_stars,
              max_stars, 'stopped', port, now, now))
        
        bot_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return bot_id
    except Exception as e:
        logger.error(f"Error registering bot: {e}")
        return None


async def update_bot_status(bot_id: int, status: str, pid: int = None):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        if pid:
            cursor.execute('''
                UPDATE bot_clones SET status=?, pid=?, last_active=? WHERE id=?
            ''', (status, pid, now, bot_id))
        else:
            cursor.execute('''
                UPDATE bot_clones SET status=?, pid=NULL, last_active=? WHERE id=?
            ''', (status, now, bot_id))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error updating bot status: {e}")


# ===================== GENERATE CLONE CODE (FIXED - TIDAK ADA ERROR) =====================
def generate_clone_code(bot_id: int, port: int) -> str:
    return f'''import os, json, base64, asyncio, logging
from pathlib import Path
import aiohttp
from dotenv import load_dotenv
from telethon import TelegramClient, events, Button
from tonutils.client import TonapiClient
from tonutils.wallet import WalletV5R1

load_dotenv()

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

logging.basicConfig(format='%(asctime)s - Bot{bot_id} - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)


async def encoded(encoded_string: str) -> str:
    if not encoded_string: return ""
    missing_padding = len(encoded_string) % 4
    if missing_padding != 0: encoded_string += "=" * (4 - missing_padding)
    try:
        decoded_bytes = base64.b64decode(encoded_string)
        return decoded_bytes.decode("utf-8", errors="ignore")
    except Exception as e:
        logger.error(f"Error decoding: {{e}}")
        return encoded_string


async def post(data: dict) -> dict:
    params = {{"hash": HASH}}
    headers = {{
        "accept": "application/json",
        "cookie": COOKIES,
        "user-agent": "Mozilla/5.0",
        "x-requested-with": "XMLHttpRequest",
    }}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post("https://fragment.com/api", params=params, headers=headers, data=data) as resp:
                return await resp.json() if resp.status == 200 else None
    except Exception as e:
        logger.error(f"Connection error: {{e}}")
        return None


async def get_user_address(username: str) -> dict:
    return await post({{"query": username, "method": "searchStarsRecipient"}})


async def init_buy_stars(recipient: str, quantity: int) -> dict:
    return await post({{"recipient": recipient, "quantity": quantity, "method": "initBuyStarsRequest"}})


async def get_buy_stars(req_id: str, show_sender: str = "1") -> dict:
    return await post({{"transaction": "1", "id": req_id, "show_sender": show_sender, "method": "getBuyStarsLink"}})


async def send_transfer(address: str, amount: int, payload: str) -> str:
    try:
        client = TonapiClient(api_key=WALLET_API_KEY, is_testnet=False)
        wallet, _, _, _ = WalletV5R1.from_mnemonic(client, WALLET_MNEMONIC)
        amount_in_ton = amount / 1_000_000_000
        logger.info(f"Sending {{amount_in_ton}} TON to {{address}}")
        return await wallet.transfer(destination=address, amount=amount_in_ton, body=payload)
    except Exception as e:
        logger.error(f"Error in send_transfer: {{e}}")
        return None


async def pay_stars_order(username: str, quantity: int, show_sender: bool = True) -> str:
    try:
        user = await get_user_address(username)
        if not user or not user.get("found"): return None
        address = user.get("found").get("recipient")
        if not address: return None

        init = await init_buy_stars(address, quantity)
        if not init or not init.get("req_id"): return None
        req_id = init["req_id"]

        show_sender_value = "1" if show_sender else "0"
        buy = await get_buy_stars(req_id, show_sender_value)
        if not buy: return None

        messages = buy.get("transaction", {{}}).get("messages", [])
        if not messages: return None
        msg = messages[0]
        if not all([msg.get("address"), msg.get("amount"), msg.get("payload")]): return None

        decoded_payload = await encoded(msg["payload"])
        return await send_transfer(msg["address"], int(msg["amount"]), decoded_payload)
    except Exception as e:
        logger.error(f"Error in pay_stars_order: {{e}}")
        return None


bot = TelegramClient(f'bot_clone_{BOT_ID}', API_ID, API_HASH)
user_states, user_data = {{}}, {{}}
STATE_IDLE, STATE_WAITING_USERNAME, STATE_WAITING_STARS = "idle", "waiting_username", "waiting_stars"
STATE_WAITING_SENDER_OPTION, STATE_CONFIRM_PURCHASE = "waiting_sender_option", "confirm_purchase"


def format_number(num: int) -> str:
    return f"{{num:,}}".replace(",", ".")
def clean_username(username: str) -> str:
    return username.strip().replace('@', '')


@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    user = await event.get_sender()
    await event.respond(
        f"🌟 **Bot Clone {BOT_ID}** 🌟\n\nHalo {{user.first_name}}!\n\n"
        f"💰 Harga: `{{PRICE_PER_STAR}}` TON/star\n📊 Min/Max: {{MIN_STARS}}/{{MAX_STARS}} stars",
        buttons=[[Button.inline("🛒 Beli Stars", data="buy")],
                 [Button.inline("ℹ️ Cara Pakai", data="howto")]],
        parse_mode='markdown'
    )


@bot.on(events.NewMessage(pattern='/buy'))
async def buy_command(event):
    user_id = event.sender_id
    user_states[user_id] = STATE_WAITING_USERNAME
    user_data[user_id] = {{}}
    await event.respond("🛒 Masukkan **username** penerima:", parse_mode='markdown')


@bot.on(events.NewMessage(pattern='/cancel'))
async def cancel_command(event):
    user_id = event.sender_id
    user_states.pop(user_id, None)
    user_data.pop(user_id, None)
    await event.respond("✅ Dibatalkan.", parse_mode='markdown')


@bot.on(events.NewMessage)
async def message_handler(event):
    user_id = event.sender_id
    if user_id not in user_states: return
    state, msg = user_states[user_id], event.message.text.strip()
    if msg.lower() == '/cancel':
        await cancel_command(event)
        return
    if state == STATE_WAITING_USERNAME:
        await process_username(event, user_id, msg)
    elif state == STATE_WAITING_STARS:
        await process_stars(event, user_id, msg)


async def process_username(event, user_id: int, username: str):
    clean = clean_username(username)
    if not clean:
        await event.respond("❌ Username tidak valid")
        return
    async with bot.action(event.chat_id, 'typing'):
        await event.respond("🔍 Mencari...")
        user_info = await get_user_address(clean)
        if not user_info or not user_info.get("found"):
            await event.respond(f"❌ @{clean} tidak ditemukan.", parse_mode='markdown')
            return
        user_data[user_id]['username'] = clean
        user_data[user_id]['nickname'] = user_info['found']['name']
        user_data[user_id]['address'] = user_info['found']['recipient']
        user_states[user_id] = STATE_WAITING_STARS
        await event.respond(f"✅ Ditemukan: {{user_info['found']['name']}}\n\nMasukkan **jumlah stars**:", parse_mode='markdown')


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
        await ask_sender_option(event, user_id)
    except ValueError:
        await event.respond("❌ Masukkan angka.")


async def ask_sender_option(event, user_id: int):
    await event.respond(
        "👤 **Opsi Pengirim**\n\nPilih opsi di bawah:",
        buttons=[
            [Button.inline("👤 Tampilkan Nama", data=f"sender_show_{{user_id}}"),
             Button.inline("🎁 Sembunyikan", data=f"sender_hide_{{user_id}}")]
        ],
        parse_mode='markdown'
    )
    user_states[user_id] = STATE_WAITING_SENDER_OPTION


async def show_confirmation(event, user_id: int):
    data = user_data[user_id]
    sender_text = "👤 Tampil" if data.get('show_sender', True) else "🎁 Gift"
    await event.respond(
        f"📝 **Konfirmasi**\n\nPenerima: {{data['nickname']}} (@{{data['username']}})\n"
        f"Stars: {{format_number(data['stars'])}}\nHarga: {{data['price']:.2f}} TON\nOpsi: {{sender_text}}",
        buttons=[
            [Button.inline("✅ Ya", data=f"confirm_{{user_id}}"),
             Button.inline("❌ Tidak", data=f"cancel_{{user_id}}")]
        ],
        parse_mode='markdown'
    )
    user_states[user_id] = STATE_CONFIRM_PURCHASE


async def confirm_purchase(event, user_id: int):
    if user_id not in user_data:
        await event.edit("❌ Sesi habis.")
        return
    data = user_data[user_id]
    show_sender = data.get('show_sender', True)
    await event.edit("⏳ Memproses...")
    try:
        tx_hash = await pay_stars_order(data['username'], data['stars'], show_sender)
        if tx_hash:
            await event.edit(
                f"✅ **Berhasil!**\n\nPenerima: @{{data['username']}}\nStars: {{format_number(data['stars'])}}\n"
                f"Hash: `{{tx_hash}}`\n\n[Lihat di TON Viewer](https://tonviewer.com/transaction/{{tx_hash}})",
                buttons=[[Button.inline("🛒 Beli Lagi", data="buy")]],
                parse_mode='markdown', link_preview=False
            )
        else:
            await event.edit("❌ Gagal", buttons=[[Button.inline("🔄 Coba Lagi", data="buy")]])
    except Exception as e:
        await event.edit(f"❌ Error: {{str(e)[:100]}}", buttons=[[Button.inline("🔄 Coba Lagi", data="buy")]])
    finally:
        user_states.pop(user_id, None)
        user_data.pop(user_id, None)


@bot.on(events.CallbackQuery)
async def callback_handler(event):
    user_id, data = event.sender_id, event.data.decode()
    if data.startswith("sender_show_"):
        user_data[user_id]['show_sender'] = True
        await show_confirmation(event, user_id)
    elif data.startswith("sender_hide_"):
        user_data[user_id]['show_sender'] = False
        await show_confirmation(event, user_id)
    elif data.startswith("confirm_"):
        await confirm_purchase(event, user_id)
    elif data.startswith("cancel_"):
        await cancel_purchase(event, user_id)
    elif data == "buy":
        user_states[user_id] = STATE_WAITING_USERNAME
        user_data[user_id] = {{}}
        await event.edit("🛒 Masukkan **username** penerima:", parse_mode='markdown')
    elif data == "howto":
        await event.edit(
            "📖 **Cara Pakai**\n\n1. Klik Beli Stars\n2. Masukkan username\n3. Masukkan jumlah\n4. Pilih opsi pengirim\n5. Konfirmasi",
            buttons=[[Button.inline("🔙 Kembali", data="start")]], parse_mode='markdown'
        )
    elif data == "start":
        await start_handler(event)


async def cancel_purchase(event, user_id: int):
    user_states.pop(user_id, None)
    user_data.pop(user_id, None)
    await event.edit("❌ Dibatalkan", buttons=[[Button.inline("🛒 Beli Stars", data="buy")]])


async def main():
    logger.info(f"Starting bot clone {BOT_ID}...")
    await bot.start(bot_token=BOT_TOKEN)
    logger.info(f"✅ Bot clone {BOT_ID} running")
    await bot.run_until_disconnected()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info(f"Bot clone {BOT_ID} stopped")
'''


# ===================== FUNGSI START/STOP BOT CLONE =====================
async def start_bot_clone(bot_id: int) -> bool:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT bot_token, api_id, api_hash, cookies, hash, wallet_api_key,
                   wallet_mnemonic, port, price_per_star, min_stars, max_stars
            FROM bot_clones WHERE id = ?
        ''', (bot_id,))
        data = cursor.fetchone()
        conn.close()
        
        if not data:
            logger.error(f"Bot {bot_id} not found")
            return False
        
        (token, api_id, api_hash, cookies, hash, wallet_key,
         mnemonic_json, port, price, min_s, max_s) = data
        mnemonic = json.loads(mnemonic_json)
        
        bot_dir = Path(f"bots/bot_{bot_id}")
        bot_dir.mkdir(parents=True, exist_ok=True)
        
        env = f"""API_ID={api_id}
API_HASH={api_hash}
BOT_TOKEN={token}
COOKIES={cookies}
HASH={hash}
WALLET_API_KEY={wallet_key}
WALLET_MNEMONIC={json.dumps(mnemonic)}
PRICE_PER_STAR={price}
MIN_STARS={min_s}
MAX_STARS={max_s}
PORT={port}
"""
        with open(bot_dir / ".env", "w") as f:
            f.write(env)
        
        with open(bot_dir / "bot_clone.py", "w") as f:
            f.write(generate_clone_code(bot_id, port))
        
        proc = subprocess.Popen(
            [sys.executable, "bot_clone.py"],
            cwd=str(bot_dir),
            stdout=open(bot_dir / "stdout.log", "w"),
            stderr=open(bot_dir / "stderr.log", "w"),
            start_new_session=True
        )
        
        await asyncio.sleep(2)
        if proc.poll() is None:
            await update_bot_status(bot_id, 'running', proc.pid)
            logger.info(f"✅ Bot {bot_id} started with PID {proc.pid}")
            return True
        
        with open(bot_dir / "stderr.log", "r") as f:
            err = f.read()
            logger.error(f"Bot {bot_id} failed: {err}")
        return False
    except Exception as e:
        logger.error(f"Error starting bot {bot_id}: {e}")
        return False


async def stop_bot_clone(bot_id: int) -> bool:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT pid FROM bot_clones WHERE id = ?", (bot_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row and row[0]:
            try:
                os.kill(row[0], signal.SIGTERM)
                await asyncio.sleep(2)
                try:
                    os.kill(row[0], 0)
                    os.kill(row[0], signal.SIGKILL)
                except OSError:
                    pass
            except ProcessLookupError:
                pass
        
        await update_bot_status(bot_id, 'stopped')
        logger.info(f"✅ Bot {bot_id} stopped")
        return True
    except Exception as e:
        logger.error(f"Error stopping bot {bot_id}: {e}")
        return False


# ===================== BOT UTAMA =====================
bot = TelegramClient('main_bot', API_ID, API_HASH)
user_states: Dict[int, str] = {}
user_data: Dict[int, Dict] = {}
STATE_WAITING_CLONE_DATA = "waiting_clone_data"


@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    user = await event.get_sender()
    user_id = event.sender_id
    await save_user(user_id, user.username, user.first_name, user.last_name)
    await log_activity(user_id, "start")
    
    bots = await get_user_bots(user_id)
    text = (
        f"🌟 **Main Bot** 🌟\n\nHalo {user.first_name}!\n"
        f"Kamu memiliki {len(bots)} bot clone.\n\n"
        f"**Menu:**\n• /create_bot - Buat bot baru\n• /my_bots - Lihat bot kamu"
    )
    buttons = [[Button.inline("🤖 Buat Bot", data="create_bot")],
               [Button.inline("📋 Bot Saya", data="my_bots")]]
    if user_id in ADMIN_IDS:
        buttons.append([Button.inline("⚙️ Admin", data="admin")])
    await event.respond(text, buttons=buttons, parse_mode='markdown')


@bot.on(events.NewMessage(pattern='/create_bot'))
async def create_bot_command(event):
    user_id = event.sender_id
    user_states[user_id] = STATE_WAITING_CLONE_DATA
    await event.respond(
        "📦 **Buat Bot Clone**\n\nKirim data JSON:\n\n"
        '`{"bot_token": "123:abc", "api_id": 12345, "api_hash": "hash", '
        '"cookies": "stel=...", "hash": "...", "wallet_api_key": "...", '
        '"wallet_mnemonic": ["word1", "..."]}`\n\nKetik /cancel untuk batal.',
        parse_mode='markdown'
    )


@bot.on(events.NewMessage(pattern='/my_bots'))
async def my_bots_command(event):
    user_id = event.sender_id
    bots = await get_user_bots(user_id)
    if not bots:
        await event.respond("❌ Belum punya bot clone.")
        return
    
    text = "📋 **Bot Clone Kamu:**\n\n"
    buttons = []
    for bot in bots:
        status = "🟢" if bot['status'] == 'running' else '🔴'
        text += f"{status} ID: `{bot['id']}` | Port: {bot['port']}\n"
        buttons.append([Button.inline(f"{status} Bot #{bot['id']}", data=f"toggle_{bot['id']}")])
    
    buttons.append([Button.inline("🔄 Refresh", data="refresh_bots"),
                    Button.inline("🔙 Kembali", data="start")])
    await event.respond(text, buttons=buttons, parse_mode='markdown')


@bot.on(events.NewMessage)
async def message_handler(event):
    user_id = event.sender_id
    if user_id not in user_states:
        return
    if user_states[user_id] == STATE_WAITING_CLONE_DATA:
        await process_clone_data(event, user_id, event.message.text)


async def process_clone_data(event, user_id: int, text: str):
    try:
        data = json.loads(text)
        required = ['bot_token', 'api_id', 'api_hash', 'cookies', 'hash',
                    'wallet_api_key', 'wallet_mnemonic']
        if not all(k in data for k in required):
            await event.respond("❌ Data tidak lengkap.")
            return
        
        if not isinstance(data['wallet_mnemonic'], list):
            await event.respond("❌ Mnemonic harus array.")
            return
        
        user = await event.get_sender()
        bot_id = await register_bot_clone(
            user_id, user.username or f"user_{user_id}",
            data['bot_token'], int(data['api_id']), data['api_hash'],
            data['cookies'], data['hash'], data['wallet_api_key'],
            data['wallet_mnemonic'], data.get('price_per_star', 0.02),
            data.get('min_stars', 10), data.get('max_stars', 100000)
        )
        
        if bot_id:
            user_states.pop(user_id, None)
            await event.respond(
                f"✅ **Bot #{bot_id} dibuat!**\n\nGunakan /my_bots untuk mengelola.",
                parse_mode='markdown'
            )
            await log_activity(user_id, "bot_created", f"ID: {bot_id}")
        else:
            await event.respond("❌ Gagal membuat bot (token mungkin sudah dipakai).")
    except json.JSONDecodeError:
        await event.respond("❌ JSON tidak valid.")
    except Exception as e:
        await event.respond(f"❌ Error: {str(e)[:100]}")


@bot.on(events.CallbackQuery)
async def callback_handler(event):
    user_id = event.sender_id
    data = event.data.decode()
    
    if data == "create_bot":
        await create_bot_command(event)
    elif data == "my_bots":
        await my_bots_command(event)
    elif data == "refresh_bots":
        await my_bots_command(event)
    elif data == "start":
        await start_handler(event)
    elif data == "admin" and user_id in ADMIN_IDS:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*), SUM(CASE WHEN status='running' THEN 1 ELSE 0 END) FROM bot_clones")
        total, active = cursor.fetchone()
        conn.close()
        await event.edit(
            f"⚙️ **Admin Panel**\n\nTotal Bot: {total or 0}\nAktif: {active or 0}",
            buttons=[[Button.inline("🔙 Kembali", data="start")]],
            parse_mode='markdown'
        )
    elif data.startswith("toggle_"):
        bot_id = int(data.split("_")[1])
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT owner_user_id, status FROM bot_clones WHERE id = ?", (bot_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            await event.answer("Bot tidak ditemukan!", alert=True)
            return
        if row[0] != user_id and user_id not in ADMIN_IDS:
            await event.answer("Bukan bot kamu!", alert=True)
            return
        
        await event.edit("⏳ Memproses...")
        
        if row[1] == 'running':
            success = await stop_bot_clone(bot_id)
            msg = f"🔴 Bot #{bot_id} dihentikan." if success else "❌ Gagal menghentikan."
        else:
            success = await start_bot_clone(bot_id)
            msg = f"🟢 Bot #{bot_id} dijalankan." if success else "❌ Gagal menjalankan."
        
        await event.edit(msg)
        await asyncio.sleep(1)
        await my_bots_command(event)


# ===================== MAIN =====================
async def main():
    logger.info("Memulai Main Bot...")
    init_database()
    Path("bots").mkdir(exist_ok=True)
    
    if not all([API_ID, API_HASH, BOT_TOKEN]):
        logger.error("❌ Konfigurasi tidak lengkap")
        return
    
    # Restart bot yang sebelumnya running
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM bot_clones WHERE status = 'running'")
    for (bid,) in cursor.fetchall():
        logger.info(f"Restarting bot {bid}...")
        await start_bot_clone(bid)
    conn.close()
    
    await bot.start(bot_token=BOT_TOKEN)
    logger.info("✅ Main bot running")
    await bot.run_until_disconnected()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Main bot stopped")
        # Stop all bots
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id, pid FROM bot_clones WHERE status = 'running'")
        for bid, pid in cursor.fetchall():
            if pid:
                try:
                    os.kill(pid, signal.SIGTERM)
                    logger.info(f"Stopped bot {bid}")
                except:
                    pass
        conn.close()
    except Exception as e:
        logger.error(f"❌ Error: {e}")
