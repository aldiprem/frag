# b.py - Fragment Stars Bot Master with Clone System
import os
import json
import base64
import asyncio
import logging
import sqlite3
import subprocess
import sys
import signal
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
from telethon.extensions.markdown import DEFAULT_DELIMITERS
from telethon.tl.types import MessageEntityBlockquote
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

# ===================== DATABASE FUNCTIONS (EXTENDED) =====================

def init_database():
    """Inisialisasi database SQLite3 dengan tabel untuk bot clone."""
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
            bot_token TEXT,
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
            bot_token TEXT,
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
            bot_token TEXT,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    # ========== TABEL BARU UNTUK BOT CLONE ==========
    
    # Tabel untuk menyimpan bot clone
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
            pid INTEGER,
            FOREIGN KEY (created_by) REFERENCES users (user_id)
        )
    ''')
    
    # Tabel untuk menyimpan log bot clone
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bot_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_token TEXT,
            log_level TEXT,
            message TEXT,
            timestamp TIMESTAMP,
            FOREIGN KEY (bot_token) REFERENCES cloned_bots (bot_token)
        )
    ''')
    
    conn.commit()
    conn.close()
    logger.info("✅ Database initialized successfully")


# ===================== DATABASE FUNCTIONS FOR CLONED BOTS =====================

async def add_cloned_bot(bot_token: str, bot_username: str, bot_name: str, created_by: int) -> bool:
    """Tambahkan bot clone ke database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO cloned_bots 
            (bot_token, bot_username, bot_name, status, created_by, created_at)
            VALUES (?, ?, ?, 'stopped', ?, ?)
        ''', (bot_token, bot_username, bot_name, created_by, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        logger.info(f"✅ Bot clone {bot_username} added to database")
        return True
    except Exception as e:
        logger.error(f"Error adding cloned bot: {e}")
        return False


async def get_cloned_bots(status: str = None) -> List[Dict]:
    """Ambil daftar bot clone."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        if status:
            cursor.execute('''
                SELECT id, bot_token, bot_username, bot_name, status, created_by, created_at, 
                       last_started, last_stopped, pid
                FROM cloned_bots WHERE status = ?
                ORDER BY created_at DESC
            ''', (status,))
        else:
            cursor.execute('''
                SELECT id, bot_token, bot_username, bot_name, status, created_by, created_at, 
                       last_started, last_stopped, pid
                FROM cloned_bots ORDER BY created_at DESC
            ''')
        
        rows = cursor.fetchall()
        conn.close()
        
        bots = []
        for row in rows:
            bots.append({
                'id': row[0],
                'bot_token': row[1],
                'bot_username': row[2],
                'bot_name': row[3],
                'status': row[4],
                'created_by': row[5],
                'created_at': row[6],
                'last_started': row[7],
                'last_stopped': row[8],
                'pid': row[9]
            })
        return bots
    except Exception as e:
        logger.error(f"Error getting cloned bots: {e}")
        return []


async def update_bot_status(bot_token: str, status: str, pid: int = None):
    """Update status bot clone."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        if status == 'running':
            cursor.execute('''
                UPDATE cloned_bots 
                SET status = ?, last_started = ?, pid = ?
                WHERE bot_token = ?
            ''', (status, now, pid, bot_token))
        elif status == 'stopped':
            cursor.execute('''
                UPDATE cloned_bots 
                SET status = ?, last_stopped = ?, pid = NULL
                WHERE bot_token = ?
            ''', (status, now, bot_token))
        else:
            cursor.execute('''
                UPDATE cloned_bots SET status = ? WHERE bot_token = ?
            ''', (status, bot_token))
        
        conn.commit()
        conn.close()
        
        # Log ke bot_logs
        await add_bot_log(bot_token, "INFO", f"Bot status changed to {status}")
        
    except Exception as e:
        logger.error(f"Error updating bot status: {e}")


async def add_bot_log(bot_token: str, log_level: str, message: str):
    """Tambah log untuk bot clone."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO bot_logs (bot_token, log_level, message, timestamp)
            VALUES (?, ?, ?, ?)
        ''', (bot_token, log_level, message, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error adding bot log: {e}")


async def remove_cloned_bot(bot_token: str) -> bool:
    """Hapus bot clone dari database."""
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
    """Dapatkan path script bot clone."""
    return os.path.abspath(__file__)


async def start_cloned_bot(bot_token: str, bot_username: str) -> bool:
    """Jalankan bot clone sebagai proses terpisah."""
    try:
        # Cek apakah bot sudah berjalan
        if bot_token in running_bots:
            proc = running_bots[bot_token]
            if proc.poll() is None:
                logger.info(f"Bot {bot_username} already running")
                return True
        
        # Buat environment untuk bot clone
        env = os.environ.copy()
        env["BOT_TOKEN"] = bot_token
        env["IS_CLONE"] = "true"
        env["MASTER_BOT_TOKEN"] = BOT_TOKEN
        
        # Jalankan proses baru
        proc = subprocess.Popen(
            [sys.executable, get_bot_script_path()],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        running_bots[bot_token] = proc
        await update_bot_status(bot_token, 'running', proc.pid)
        
        logger.info(f"✅ Started cloned bot: {bot_username} (PID: {proc.pid})")
        
        # Monitor proses secara async
        asyncio.create_task(monitor_bot_process(bot_token, bot_username, proc))
        
        return True
        
    except Exception as e:
        logger.error(f"Error starting cloned bot: {e}")
        await update_bot_status(bot_token, 'error')
        return False


async def stop_cloned_bot(bot_token: str, bot_username: str) -> bool:
    """Hentikan bot clone."""
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
    """Monitor proses bot clone."""
    try:
        # Monitor stdout
        async def read_output(pipe, log_level):
            for line in iter(pipe.readline, ''):
                if line:
                    await add_bot_log(bot_token, log_level, line.strip())
        
        # Jalankan monitoring di thread pool
        loop = asyncio.get_event_loop()
        
        stdout_task = loop.run_in_executor(None, read_output, proc.stdout, "INFO")
        stderr_task = loop.run_in_executor(None, read_output, proc.stderr, "ERROR")
        
        # Tunggu proses selesai
        await asyncio.get_event_loop().run_in_executor(None, proc.wait)
        
        # Proses selesai, update status
        if bot_token in running_bots:
            del running_bots[bot_token]
        
        await update_bot_status(bot_token, 'stopped')
        logger.info(f"Bot {bot_username} process ended")
        
    except Exception as e:
        logger.error(f"Error monitoring bot {bot_username}: {e}")
        await update_bot_status(bot_token, 'error')


async def start_all_cloned_bots():
    """Jalankan semua bot clone yang statusnya running."""
    bots = await get_cloned_bots('running')
    for bot in bots:
        await start_cloned_bot(bot['bot_token'], bot['bot_username'])


async def stop_all_cloned_bots():
    """Hentikan semua bot clone."""
    for bot_token, proc in list(running_bots.items()):
        if proc.poll() is None:
            proc.terminate()
    running_bots.clear()


# ===================== FRAGMENT API FUNCTIONS (SAME AS ORIGINAL) =====================
# [Keep all your existing Fragment API functions - they remain the same]
# encoded(), post(), get_user_address(), init_buy_stars(), get_buy_stars()

# ===================== WALLET FUNCTIONS =====================
# [Keep all your existing wallet functions]

# ===================== WRAPPER FUNCTIONS =====================
# [Keep all your existing wrapper functions]

# ===================== HELPER FUNCTIONS =====================
# [Keep all your existing helper functions]

# ===================== BOT HANDLERS (EXTENDED) =====================

@bot.on(events.NewMessage(pattern='/clone'))
async def clone_bot_handler(event):
    """Handler untuk clone bot baru."""
    user_id = event.sender_id
    
    if not await is_admin(user_id):
        await event.respond("❌ Akses ditolak! Hanya admin yang bisa clone bot.")
        return
    
    # Parse command: /clone <bot_token> [bot_username]
    parts = event.message.text.split()
    if len(parts) < 2:
        await event.respond(
            "❌ **Format salah!**\n\n"
            "Gunakan: `/clone <bot_token> [bot_username]`\n\n"
            "Contoh: `/clone 123456:ABCdefg my_bot`",
            parse_mode='markdown'
        )
        return
    
    bot_token = parts[1]
    bot_username = parts[2] if len(parts) > 2 else None
    
    # Validasi bot token
    if not bot_token or ':' not in bot_token:
        await event.respond("❌ Bot token tidak valid! Format: `123456:ABCdefg`")
        return
    
    await event.respond("⏳ **Mengecek bot token...**")
    
    # Cek apakah bot token valid dengan mencoba connect
    try:
        temp_client = TelegramClient(f'temp_{user_id}', API_ID, API_HASH)
        await temp_client.start(bot_token=bot_token)
        me = await temp_client.get_me()
        await temp_client.disconnect()
        
        bot_username = bot_username or me.username or f"bot_{me.id}"
        bot_name = me.first_name or "Fragment Stars Bot"
        
        # Simpan ke database
        success = await add_cloned_bot(bot_token, bot_username, bot_name, user_id)
        
        if success:
            # Jalankan bot
            await start_cloned_bot(bot_token, bot_username)
            
            await event.respond(
                f"✅ **Bot Berhasil Di-clone!**\n\n"
                f"**Nama:** {bot_name}\n"
                f"**Username:** @{bot_username}\n"
                f"**Token:** `{bot_token[:20]}...`\n\n"
                f"Bot sedang berjalan. Gunakan `/listbots` untuk melihat semua bot.",
                parse_mode='markdown'
            )
            
            # Log aktivitas
            await log_activity(user_id, "clone_bot", f"Cloned bot: {bot_username}")
        else:
            await event.respond("❌ Gagal menyimpan bot ke database!")
            
    except Exception as e:
        await event.respond(f"❌ **Error:** Bot token tidak valid!\n\n{str(e)[:100]}")
        logger.error(f"Error validating bot token: {e}")


@bot.on(events.NewMessage(pattern='/listbots'))
async def list_bots_handler(event):
    """Handler untuk menampilkan daftar bot clone."""
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
        text += f"   • ID: {bot['id']}\n"
        if bot['pid']:
            text += f"   • PID: {bot['pid']}\n"
        text += "\n"
    
    await event.respond(text, parse_mode='markdown')


@bot.on(events.NewMessage(pattern='/startbot'))
async def start_bot_handler(event):
    """Handler untuk menjalankan bot clone tertentu."""
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
    """Handler untuk menghentikan bot clone tertentu."""
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
    """Handler untuk menghapus bot clone."""
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
            # Hentikan bot jika berjalan
            if bot['status'] == 'running':
                await stop_cloned_bot(bot['bot_token'], bot['bot_username'])
            
            # Hapus dari database
            success = await remove_cloned_bot(bot['bot_token'])
            if success:
                await event.respond(f"✅ Bot @{bot_username} berhasil dihapus!")
            else:
                await event.respond(f"❌ Gagal menghapus bot @{bot_username}!")
            return
    
    await event.respond(f"❌ Bot @{bot_username} tidak ditemukan!")


@bot.on(events.NewMessage(pattern='/botlog'))
async def bot_log_handler(event):
    """Handler untuk melihat log bot clone."""
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
        
        cursor.execute('''
            SELECT log_level, message, timestamp FROM bot_logs 
            WHERE bot_token IN (SELECT bot_token FROM cloned_bots WHERE bot_username = ?)
            ORDER BY timestamp DESC LIMIT ?
        ''', (bot_username, limit))
        
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
        logger.error(f"Error getting bot logs: {e}")


# ===================== MODIFIED ADMIN PANEL =====================

@bot.on(events.NewMessage(pattern='/admin'))
async def admin_panel(event):
    """Panel admin dengan informasi bot clone."""
    user_id = event.sender_id
    
    if not await is_admin(user_id):
        await event.respond("❌ Akses ditolak!")
        return
    
    # Ambil statistik
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
    
    buttons = [
        [Button.inline("💰 Cek Saldo", data="balance")],
        [Button.inline("📊 Detail Statistik", data="admin_stats")],
        [Button.inline("🔄 Restart All Bots", data="restart_all")],
        [Button.inline("🔙 Kembali", data="start")]
    ]
    
    await event.respond(text, buttons=buttons, parse_mode='markdown')


@bot.on(events.CallbackQuery)
async def callback_handler(event):
    """Extended callback handler untuk admin panel."""
    user_id = event.sender_id
    data = event.data.decode('utf-8')
    
    if data == "restart_all":
        if not await is_admin(user_id):
            await event.answer("Akses ditolak!", alert=True)
            return
        
        await event.edit("⏳ **Merestart semua bot...**")
        
        # Stop all bots
        await stop_all_cloned_bots()
        
        # Start all bots that should be running
        await start_all_cloned_bots()
        
        await event.edit(
            "✅ **Semua bot telah direstart!**",
            buttons=[Button.inline("🔙 Kembali ke Admin", data="admin")]
        )
        return
    
    # Call other callback handlers...
    # [Keep all existing callback handlers]


# ===================== MAIN FUNCTION =====================

async def main():
    """Main function dengan deteksi mode clone."""
    # Cek apakah ini bot clone atau bot master
    is_clone = os.getenv("IS_CLONE", "false").lower() == "true"
    master_token = os.getenv("MASTER_BOT_TOKEN", "")
    
    if is_clone:
        # Mode: Bot Clone
        logger.info("Starting as CLONED BOT...")
        
        # Inisialisasi database
        init_database()
        
        # Update status bot
        await update_bot_status(BOT_TOKEN, 'running')
        
        logger.info(f"✅ Cloned bot running with token: {BOT_TOKEN[:20]}...")
        
        # Jalankan bot clone dengan handler yang sama
        await bot.start(bot_token=BOT_TOKEN)
        logger.info("✅ Cloned bot is running")
        await bot.run_until_disconnected()
        
    else:
        # Mode: Bot Master
        logger.info("Starting as MASTER BOT...")
        
        # Inisialisasi database
        init_database()
        
        if not API_ID or not API_HASH or not BOT_TOKEN:
            logger.error("❌ Konfigurasi Telegram tidak lengkap")
            return
        
        logger.info(f"📊 COOKIES length: {len(COOKIES)}")
        logger.info(f"📊 HASH length: {len(HASH)}")
        logger.info(f"📊 WALLET_MNEMONIC length: {len(WALLET_MNEMONIC)}")
        
        # Start bot master
        logger.info("✅ Starting master bot...")
        await bot.start(bot_token=BOT_TOKEN)
        logger.info("✅ Master bot running")
        
        # Start all cloned bots that should be running
        await start_all_cloned_bots()
        
        await bot.run_until_disconnected()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Bot dihentikan oleh user")
        # Cleanup: stop all cloned bots
        asyncio.run(stop_all_cloned_bots())
    except Exception as e:
        logger.error(f"❌ Error fatal: {e}")
