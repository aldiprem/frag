# b.py - Fragment Stars Bot - VERSION ALL-IN-ONE WITH DATABASE
import os
import json
import asyncio
import logging
import sqlite3
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
from telethon.extensions.markdown import DEFAULT_DELIMITERS
from telethon.tl.types import MessageEntityBlockquote
from dotenv import load_dotenv
from telethon import TelegramClient, events, Button

# Import dari folder api
from api.fragment import (
    encoded,
    post,
    get_user_address,
    init_buy_stars,
    get_buy_stars
)

from api.wallet import send_transfer, get_balance

# Import dari folder database
from database.data import (
    init_database,
    save_user,
    log_activity,
    save_purchase,
    save_pending_purchase,
    get_pending_purchase,
    delete_pending_purchase,
    update_bot_config,
    get_bot_config,
    get_user_stats,
    get_all_stats,
    get_recent_purchases
)

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

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===================== WRAPPER FUNCTIONS =====================

async def get_user(username: str) -> Optional[dict]:
    """Dapatkan informasi user dari Fragment."""
    try:
        logger.info(f"Searching for user: {username}")
        user = await get_user_address(COOKIES, HASH, username)
        
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
        user = await get_user_address(COOKIES, HASH, username)
        if not user or not user.get("found"):
            logger.error("User not found")
            return None
            
        address = user.get("found").get("recipient")
        if not address:
            logger.error("Invalid user address")
            return None

        # 2. Init buy
        init = await init_buy_stars(COOKIES, HASH, address, quantity)
        if not init:
            logger.error("Failed to init buy")
            return None
            
        req_id = init.get("req_id")
        if not req_id:
            logger.error("No req_id in response")
            return None

        # 3. Get buy details dengan parameter show_sender
        show_sender_value = "1" if show_sender else "0"
        
        buy = await get_buy_stars(COOKIES, HASH, req_id, show_sender_value)
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
        tx_hash = await send_transfer(
            api_key=WALLET_API_KEY,
            mnemonic=WALLET_MNEMONIC,
            address=pay_address,
            amount=int(amount),
            payload=decoded_payload
        )

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
        last_name=user.last_name,
        admin_ids=ADMIN_IDS
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
    
    # Handler untuk memilih TAMPILKAN NAMA
    if data.startswith("sender_show_"):
        user_data[user_id]['show_sender'] = True
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
    
    # Handler untuk memilih SEMBUNYIKAN NAMA
    elif data.startswith("sender_hide_"):
        user_data[user_id]['show_sender'] = False
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
    
    # Handler untuk kembali ke opsi sender
    elif data.startswith("sender_back_"):
        if user_id not in user_data:
            await event.answer("Sesi telah berakhir, silakan mulai lagi.", alert=True)
            return
        await ask_sender_option(event, user_id)
        return
    
    # Handler untuk konfirmasi
    elif data.startswith("confirm_"):
        await confirm_purchase(event, user_id)
        return
    
    # Handler untuk cancel
    elif data.startswith("cancel_"):
        await cancel_purchase(event, user_id)
        return
    
    # Menu utama
    elif data == "buy":
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
        
        recent_purchases = await get_recent_purchases(10)
        
        stats_text = "📊 **10 Pembelian Terakhir**\n\n"
        for i, purchase in enumerate(recent_purchases, 1):
            uid, recipient, stars, price, status, ts = purchase
            stats_text += f"{i}. User: {uid}\n   → @{recipient}: {stars} stars ({price:.2f} TON)\n   Status: {status}\n   {ts[:19]}\n\n"
        
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
            balance = await get_balance(WALLET_API_KEY, WALLET_MNEMONIC)
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
        
        user_states.clear()
        user_data.clear()
        
        # Hapus semua pending purchases
        conn = sqlite3.connect("frag.db")
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
    logger.info("Memulai Main Bot...")
    
    # Inisialisasi database
    init_database()
    
    if not API_ID or not API_HASH or not BOT_TOKEN:
        logger.error("❌ Konfigurasi Telegram tidak lengkap")
        return
    
    logger.info(f"📊 COOKIES length: {len(COOKIES)}")
    logger.info(f"📊 HASH length: {len(HASH)}")
    logger.info(f"📊 WALLET_MNEMONIC length: {len(WALLET_MNEMONIC)}")
    
    logger.info("✅ Starting main bot...")
    await bot.start(bot_token=BOT_TOKEN)
    logger.info("✅ Main bot running")
    await bot.run_until_disconnected()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Bot dihentikan oleh user")
    except Exception as e:
        logger.error(f"❌ Error fatal: {e}")
