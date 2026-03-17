# b.py - Fragment Stars Bot - VERSION ALL-IN-ONE FIXED
import os
import json
import base64
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, Any

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

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
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


async def get_buy_stars(req_id: str) -> Optional[dict]:
    """Dapatkan detail pembayaran."""
    try:
        data = {
            "transaction": "1",
            "id": req_id,
            "show_sender": "0",
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
        # balance sudah dalam TON, tidak perlu konversi
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



# ===================== FUNGSI PAYMENT DENGAN OPSI SHOW SENDER =====================

async def pay_stars_order(username: str, quantity: int, show_sender: bool = True) -> Optional[str]:
    """Proses pembayaran stars dengan opsi menampilkan/menyembunyikan pengirim.
    
    Args:
        username: Username penerima
        quantity: Jumlah stars
        show_sender: True = tampilkan nama pengirim (akun Fragment Anda)
                     False = sembunyikan nama (gift mode dari Telegram resmi)
    """
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
        # show_sender = "1" jika True, "0" jika False
        show_sender_value = "1" if show_sender else "0"
        
        buy = await get_buy_stars_with_sender(req_id, show_sender_value)
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


async def get_buy_stars_with_sender(req_id: str, show_sender: str = "1") -> Optional[dict]:
    """Dapatkan detail pembayaran dengan opsi show_sender.
    
    Args:
        req_id: Request ID dari init_buy_stars
        show_sender: "1" = tampilkan pengirim, "0" = sembunyikan pengirim
    """
    try:
        data = {
            "transaction": "1",
            "id": req_id,
            "show_sender": show_sender,  # Parameter penting!
            "method": "getBuyStarsLink",
        }
        return await post(COOKIES, HASH, data)
    except Exception as e:
        logger.error(f"Error in get_buy_stars_with_sender: {e}")
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
STATE_CONFIRM_PURCHASE = "confirm_purchase"
STATE_WAITING_SENDER_OPTION = "waiting_sender_option"

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
    
    fragment_ok, wallet_ok = await check_config()
    
    welcome_text = (
        f"🌟 **Selamat Datang di Fragment Stars Bot** 🌟\n\n"
        f"Halo {user.first_name}!\n\n"
        f"**Informasi:**\n"
        f"• 💰 Harga: `{PRICE_PER_STAR}` TON per star\n"
        f"• 📊 Minimal: `{MIN_STARS}` stars\n"
        f"• 📈 Maksimal: `{MAX_STARS}` stars\n\n"
    )
    
    if not fragment_ok:
        welcome_text += "⚠️ **Fragment API tidak aktif**\n"
    if not wallet_ok:
        welcome_text += "⚠️ **Wallet tidak aktif**\n"
    
    buttons = [
        [Button.inline("🛒 Beli Stars", data="buy")],
        [Button.inline("ℹ️ Cara Pakai", data="howto")],
    ]
    
    if await is_admin(user_id):
        buttons.append([Button.inline("⚙️ Admin Panel", data="admin")])
    
    await event.respond(welcome_text, buttons=buttons, parse_mode='markdown')


@bot.on(events.NewMessage(pattern='/buy'))
async def buy_command(event):
    user_id = event.sender_id
    fragment_ok, wallet_ok = await check_config()
    
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
    
    if user_id in user_states:
        del user_states[user_id]
    if user_id in user_data:
        del user_data[user_id]
    
    await event.respond(
        "✅ **Operasi dibatalkan.**",
        parse_mode='markdown'
    )


@bot.on(events.CallbackQuery)
async def callback_handler(event):
    user_id = event.sender_id
    data = event.data.decode('utf-8')
    
    # ===================== HANDLER UNTUK OPSI SENDER =====================
    
    # Handler untuk memilih TAMPILKAN NAMA (show_sender = True)
    if data.startswith("sender_show_"):
        # Ekstrak user_id dari data jika perlu, tapi kita sudah punya user_id
        user_data[user_id]['show_sender'] = True
        await show_confirmation(event, user_id)
        return
    
    # Handler untuk memilih SEMBUNYIKAN NAMA (show_sender = False)
    elif data.startswith("sender_hide_"):
        user_data[user_id]['show_sender'] = False
        await show_confirmation(event, user_id)
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
        await event.edit(
            "🛒 **Mulai Pembelian Stars**\n\n"
            "Silakan masukkan **username** penerima:\n"
            "_(Contoh: @username atau username)_\n\n"
            "Ketik /cancel untuk membatalkan.",
            parse_mode='markdown'
        )
    
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
    
    elif data == "admin":
        if not await is_admin(user_id):
            await event.answer("Akses ditolak!", alert=True)
            return
        
        fragment_ok, wallet_ok = await check_config()
        admin_text = (
            "⚙️ **Panel Admin**\n\n"
            f"• Status: Aktif\n"
            f"• Fragment API: {'✅' if fragment_ok else '❌'}\n"
            f"• Wallet: {'✅' if wallet_ok else '❌'}\n"
            f"• Pengguna Aktif: {len(user_states)}\n"
            f"• Total Sesi: {len(user_data)}"
        )
        buttons = [
            [Button.inline("💰 Cek Saldo", data="balance")],
            [Button.inline("🔄 Restart Bot", data="restart")],
            [Button.inline("🔙 Kembali", data="start")]
        ]
        await event.edit(admin_text, buttons=buttons, parse_mode='markdown')
    
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
        await event.edit(
            "✅ **Bot telah di-restart**\n\n"
            "Semua sesi pengguna telah dihapus.",
            buttons=[Button.inline("🏠 Kembali ke Menu", data="start")],
            parse_mode='markdown'
        )
    
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
    
    try:
        # Panggil pay_stars_order dengan parameter show_sender
        tx_hash = await pay_stars_order(
            username=purchase_data['username'],
            quantity=purchase_data['stars'],
            show_sender=show_sender
        )
        
        if tx_hash:
            success_text = (
                "✅ **Pembelian Berhasil!**\n\n"
                f"**Penerima:** @{purchase_data['username']}\n"
                f"**Stars:** {format_number(purchase_data['stars'])}\n"
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
            
            await notify_admins(purchase_data, tx_hash)
        else:
            await event.edit(
                "❌ **Pembelian Gagal**\n\n"
                "Coba lagi nanti.",
                buttons=[Button.inline("🔄 Coba Lagi", data="buy")],
                parse_mode='markdown'
            )
    
    except Exception as e:
        logger.error(f"Error: {e}")
        await event.edit(
            f"❌ **Error:** {str(e)[:100]}",
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


async def notify_admins(purchase_data: dict, tx_hash: str):
    notif = (
        "💰 **Pembelian Baru**\n\n"
        f"**User:** @{purchase_data['username']}\n"
        f"**Stars:** {format_number(purchase_data['stars'])}\n"
        f"**Harga:** {purchase_data['price']:.2f} TON\n"
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
