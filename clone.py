# clone.py - Fragment Stars Bot Clone (Cloned Bot Version)
import os
import json
import base64
import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
from telethon.tl.types import MessageEntityCustomEmoji
import aiohttp
from dotenv import load_dotenv
from telethon import TelegramClient, events, Button, types
from telethon.tl.types import MessageEntityTextUrl, MessageEntityPre
from telethon.extensions.markdown import DEFAULT_DELIMITERS
from telethon.tl.types import MessageEntityBlockquote
from telethon.extensions import markdown
from telethon.tl.types import (
    MessageEntityCustomEmoji, 
    MessageEntityTextUrl, 
    MessageEntityPre,
    MessageEntitySpoiler,
    MessageEntityBlockquote,
    MessageEntityItalic,
    MessageEntityUnderline,
    MessageEntityCode,
    MessageEntityStrike,
    MessageEntityBold
)
import secrets
from urllib.parse import urlencode
import pytz
import sqlite3

from database.data import (
    init_database, save_user, log_activity, save_purchase, get_user_stats,
    get_all_stats, update_bot_status,
    add_bot_log, add_bot_log_sync,
    create_deposit, update_deposit_status, get_deposit, get_user_deposits,
    get_user_balance, add_user_balance, deduct_user_balance, 
    get_jakarta_time, get_jakarta_time_iso, get_jakarta_date
)

# Import tonutils
from tonutils.client import TonapiClient
from tonutils.wallet import WalletV5R1

# ===================== LOAD ENVIRONMENT =====================
env_path = Path('.') / '.env'
load_dotenv(dotenv_path=env_path)

# ===================== KONFIGURASI =====================
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
MASTER_BOT_TOKEN = os.getenv("MASTER_BOT_TOKEN", "")

ADMIN_IDS = [int(id) for id in os.getenv("ADMIN_IDS", "").split(",") if id]

PRICE_PER_STAR_IDR = float(os.getenv("PRICE_PER_STAR_IDR", 270))
PRICE_PER_STAR_TON = float(os.getenv("PRICE_PER_STAR_TON", 0.02))

MIN_STARS = int(os.getenv("MIN_STARS", 10))
MAX_STARS = int(os.getenv("MAX_STARS", 100000))
DEFAULT_DELIMITERS['^^'] = lambda *a, **k: MessageEntityBlockquote(*a, **k, collapsed=True)
COOKIES = os.getenv("COOKIES", "")
HASH = os.getenv("HASH", "")

WALLET_API_KEY = os.getenv("WALLET_API_KEY", "")
WALLET_MNEMONIC_STR = os.getenv("WALLET_MNEMONIC", "[]")

try:
    WALLET_MNEMONIC = json.loads(WALLET_MNEMONIC_STR)
except Exception as e:
    print(f"❌ Failed to parse WALLET_MNEMONIC: {e}")
    WALLET_MNEMONIC = []

PAKASIR_SLUG = os.getenv("PAKASIR_SLUG", "")
PAKASIR_API_KEY = os.getenv("PAKASIR_API_KEY", "")
PAKASIR_BASE_URL = "https://app.pakasir.com"

DB_PATH = "frag.db"

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Global state
user_state: Dict[int, Dict[str, Any]] = {}

# State constants
STATE_IDLE = "idle"
STATE_WAITING_USERNAME = "waiting_username"
STATE_WAITING_STARS = "waiting_stars"
STATE_WAITING_SENDER_OPTION = "waiting_sender_option"
STATE_CONFIRM_PURCHASE = "confirm_purchase"
STATE_WAITING_DEPOSIT_AMOUNT = "waiting_deposit_amount"

JAKARTA_TZ = pytz.timezone('Asia/Jakarta')

def get_jakarta_time():
    return datetime.now(JAKARTA_TZ)

def get_jakarta_time_iso():
    return datetime.now(JAKARTA_TZ).isoformat()

def get_jakarta_date():
    return datetime.now(JAKARTA_TZ).date().isoformat()

# ===================== PAKASIR FUNCTIONS =====================

async def create_pakasir_transaction(
    order_id: str,
    amount: int,
    method: str = "qris"
) -> Optional[Dict]:
    try:
        url = f"{PAKASIR_BASE_URL}/api/transactioncreate/{method}"
        payload = {
            "project": PAKASIR_SLUG,
            "order_id": order_id,
            "amount": amount,
            "api_key": PAKASIR_API_KEY
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"Pakasir API error: {response.status}")
                    return None
    except Exception as e:
        logger.error(f"Error creating Pakasir transaction: {e}")
        return None


async def get_pakasir_transaction(order_id: str, amount: int) -> Optional[Dict]:
    try:
        params = {
            "project": PAKASIR_SLUG,
            "order_id": order_id,
            "amount": amount,
            "api_key": PAKASIR_API_KEY
        }
        url = f"{PAKASIR_BASE_URL}/api/transactiondetail?{urlencode(params)}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return None
    except Exception as e:
        logger.error(f"Error getting Pakasir transaction: {e}")
        return None


def generate_order_id(user_id: int) -> str:
    timestamp = get_jakarta_time().strftime("%y%m%d%H%M%S")
    random_suffix = secrets.token_hex(4).upper()
    return f"DEP{timestamp}{user_id}{random_suffix}"

# ===================== HELPER FUNCTIONS =====================

def format_idr(amount: float) -> str:
    return f"Rp{amount:,.0f}".replace(",", ".")

def format_number(num: int) -> str:
    return f"{num:,}".replace(",", ".")

def calculate_price_idr(stars: int) -> float:
    return stars * PRICE_PER_STAR_IDR

def calculate_price_ton(stars: int) -> float:
    return stars * PRICE_PER_STAR_TON

def clean_username(username: str) -> str:
    return username.strip().replace('@', '')

async def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

async def check_config() -> tuple:
    return bool(COOKIES and HASH), bool(WALLET_API_KEY and WALLET_MNEMONIC)

# ===================== STATE FUNCTIONS =====================

def get_user_state(user_id: int) -> Dict[str, Any]:
    if user_id not in user_state:
        user_state[user_id] = {
            'state': STATE_IDLE,
            'data': {},
            'created_at': get_jakarta_time_iso()
        }
    return user_state[user_id]

def set_user_state(user_id: int, state: str, data: Dict[str, Any] = None):
    user = get_user_state(user_id)
    user['state'] = state
    if data:
        user['data'].update(data)
    elif data is not None:
        user['data'] = data

def clear_user_state(user_id: int):
    if user_id in user_state:
        del user_state[user_id]

def get_user_data(user_id: int, key: str = None):
    user = get_user_state(user_id)
    if key is None:
        return user['data']
    return user['data'].get(key)

def set_user_data(user_id: int, key: str, value: Any):
    user = get_user_state(user_id)
    user['data'][key] = value

# ===================== DEPOSIT FUNCTIONS =====================

async def process_deposit(event, amount: int = None):
    user_id = event.sender_id
    
    if amount is None:
        set_user_state(user_id, STATE_WAITING_DEPOSIT_AMOUNT, {})
        await event.respond(
            "💰 **Masukkan jumlah deposit**\n\n"
            "Contoh: `50000`\n"
            "Minimal: Rp10.000\n"
            "Maksimal: Rp10.000.000",
            parse_mode='markdown'
        )
        return
    
    try:
        if amount < 10000:
            await event.respond("❌ Minimal deposit adalah Rp10.000")
            return
        
        if amount > 10000000:
            await event.respond("❌ Maksimal deposit adalah Rp10.000.000")
            return
        
        order_id = generate_order_id(user_id)
        
        async with event.client.action(event.chat_id, 'typing'):
            result = await create_pakasir_transaction(order_id, amount, "qris")
            
            if not result or "payment" not in result:
                await event.respond("❌ Gagal membuat transaksi. Silakan coba lagi nanti.")
                return
            
            payment = result["payment"]
            
            expired_at_str = payment.get("expired_at")
            if expired_at_str:
                try:
                    expired_at_clean = expired_at_str.replace('Z', '+00:00')
                    expired_dt = datetime.fromisoformat(expired_at_clean)
                    expired_dt_jakarta = expired_dt.astimezone(JAKARTA_TZ)
                    expired_at = expired_dt_jakarta.isoformat()
                except:
                    expired_at = expired_at_str
            else:
                expired_at = None
            
            qr_string = payment.get("payment_number")
            
            msg_qr = f"""
💰 **DEPOSIT VIA QRIS**

**Order ID:** `{order_id}`
**Nominal:** Rp{amount:,.0f}
**Total Dibayar:** Rp{payment.get('total_payment', amount):,.0f}
**Metode:** QRIS

**Scan QR Code berikut untuk melakukan pembayaran:**
            """
            
            try:
                import qrcode
                from io import BytesIO
                
                qr = qrcode.QRCode(box_size=10, border=4)
                qr.add_data(qr_string)
                qr.make(fit=True)
                
                img = qr.make_image(fill_color="black", back_color="white")
                bio = BytesIO()
                img.save(bio, 'PNG')
                bio.seek(0)
                
                await event.respond(msg_qr, file=bio, parse_mode='markdown')
            except Exception as e:
                logger.error(f"Error generating QR: {e}")
                msg_qr += f"\n\n```\n{qr_string}\n```"
                await event.respond(msg_qr, parse_mode='markdown')
            
            waiting_msg = await event.respond(
                f"⏳ **Menunggu Pembayaran**\n\n"
                f"Silakan scan QR code di atas dan lakukan pembayaran.\n"
                f"Transaksi akan kadaluarsa pada: {expired_at or '-'}\n\n"
                f"Setelah membayar, klik tombol 'Cek Status' untuk memverifikasi.",
                buttons=[
                    [Button.inline("✅ Cek Status", data=f"check_deposit_{order_id}"),
                     Button.inline("📜 Riwayat Deposit", data="deposit_history")],
                    [Button.inline("💰 Cek Saldo", data="check_balance"),
                     Button.inline("🔙 Kembali", data="back_start")]
                ],
                parse_mode='markdown'
            )
            
            await create_deposit(
                user_id=user_id,
                order_id=order_id,
                amount=amount,
                payment_method=payment.get("payment_method", "qris"),
                qr_string=qr_string,
                total_payment=payment.get("total_payment", amount),
                expired_at=expired_at,
                waiting_msg_id=waiting_msg.id,
                bot_token=BOT_TOKEN
            )
            
    except ValueError:
        await event.respond("❌ Masukkan nominal yang valid (angka saja)")
    except Exception as e:
        logger.error(f"Error in deposit command: {e}")
        await event.respond(f"❌ Terjadi kesalahan: {str(e)[:100]}")

async def check_deposit_status(event, order_id: str):
    user_id = event.sender_id
    
    deposit = await get_deposit(order_id)
    
    if not deposit:
        await event.answer("Transaksi tidak ditemukan", alert=True)
        return
    
    if deposit['status'] == 'completed':
        await event.answer("✅ Deposit sudah selesai!", alert=True)
        await event.edit("✅ **Deposit sudah dikonfirmasi!**\n\nSaldo Anda telah bertambah.")
        
        waiting_msg_id = deposit.get('waiting_msg_id')
        if waiting_msg_id:
            try:
                await event.client.delete_messages(user_id, waiting_msg_id)
            except Exception as e:
                logger.error(f"Error deleting waiting message: {e}")
        return
    
    result = await get_pakasir_transaction(order_id, deposit['amount'])
    
    if result and result.get('transaction', {}).get('status') == 'completed':
        await update_deposit_status(order_id, 'completed')
        balance = await get_user_balance(user_id, BOT_TOKEN)
        
        await event.edit(
            f"✅ **DEPOSIT BERHASIL!**\n\n"
            f"Order ID: `{order_id}`\n"
            f"Nominal: Rp{deposit['amount']:,.0f}\n"
            f"Saldo saat ini: Rp{balance:,.0f}\n\n"
            f"Terima kasih telah melakukan deposit!",
            parse_mode='markdown'
        )
        
        waiting_msg_id = deposit.get('waiting_msg_id')
        if waiting_msg_id:
            try:
                await event.client.delete_messages(user_id, waiting_msg_id)
            except Exception as e:
                logger.error(f"Error deleting waiting message: {e}")
    elif deposit['status'] == 'pending':
        await event.answer("⏳ Masih menunggu pembayaran...", alert=True)
    else:
        await event.answer("❌ Deposit gagal atau kadaluarsa", alert=True)

async def show_deposit_history(event):
    user_id = event.sender_id
    
    deposits = await get_user_deposits(user_id, BOT_TOKEN, limit=10)
    
    if not deposits:
        await event.answer("Belum ada riwayat deposit", alert=True)
        return
    
    msg = "📜 **RIWAYAT DEPOSIT**\n\n"
    for d in deposits:
        status_emoji = "✅" if d['status'] == 'completed' else "⏳" if d['status'] == 'pending' else "❌"
        msg += f"{status_emoji} **{d['order_id']}**\n"
        msg += f"   Nominal: Rp{d['amount']:,.0f}\n"
        msg += f"   Status: {d['status'].upper()}\n"
        msg += f"   Tanggal: {d['created_at'][:19]}\n\n"
    
    buttons = [[Button.inline("💰 Cek Saldo", data="check_balance"),
                Button.inline("💳 Deposit Lagi", data="deposit")]]
    
    await event.edit(msg, buttons=buttons, parse_mode='markdown')

async def monitor_deposit():
    while True:
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT order_id, user_id, amount, expired_at, waiting_msg_id, bot_token 
                FROM deposits 
                WHERE status = 'pending'
            ''')
            pending_deposits = cursor.fetchall()
            conn.close()
            
            current_time = datetime.now(JAKARTA_TZ)
            
            for order_id, user_id, amount, expired_at_str, waiting_msg_id, bot_token in pending_deposits:
                if expired_at_str:
                    try:
                        expired_at_str_clean = expired_at_str.replace('Z', '+00:00')
                        expired_at = datetime.fromisoformat(expired_at_str_clean)
                        expired_at = expired_at.astimezone(JAKARTA_TZ)
                    except:
                        expired_at = datetime.fromisoformat(expired_at_str)
                
                if expired_at and current_time > expired_at:
                    await update_deposit_status(order_id, 'expired', bot_token=bot_token)
                    logger.info(f"Deposit {order_id} expired")
                    
                    if waiting_msg_id:
                        try:
                            await client.delete_messages(user_id, waiting_msg_id)
                        except Exception as e:
                            logger.error(f"Error deleting waiting message: {e}")
                    
                    await notify_user_deposit_expired(user_id, order_id, amount, bot_token)
                    continue
                
                result = await get_pakasir_transaction(order_id, amount)
                
                if result and result.get('transaction', {}).get('status') == 'completed':
                    completed_at = result.get('transaction', {}).get('completed_at')
                    payment_method = result.get('transaction', {}).get('payment_method')
                    
                    await update_deposit_status(
                        order_id, 'completed', completed_at, payment_method, bot_token=bot_token
                    )
                    
                    if waiting_msg_id:
                        try:
                            await client.delete_messages(user_id, waiting_msg_id)
                        except Exception as e:
                            logger.error(f"Error deleting waiting message: {e}")
                    
                    balance = await get_user_balance(user_id, bot_token)
                    await notify_user_deposit_success(user_id, order_id, amount, balance, bot_token)
                    logger.info(f"Deposit {order_id} completed automatically")
                    
        except Exception as e:
            logger.error(f"Error in monitor_deposit: {e}")
        
        await asyncio.sleep(5)

async def notify_user_deposit_success(user_id: int, order_id: str, amount: int, balance: int, bot_token: str):
    try:
        global client
        if client:
            msg = f"""
✅ **DEPOSIT BERHASIL!** (Otomatis)

Order ID: `{order_id}`
Nominal: Rp{amount:,.0f}
Saldo saat ini: Rp{balance:,.0f}

Terima kasih telah melakukan deposit!
            """
            await client.send_message(user_id, msg, parse_mode='markdown')
            await log_activity(user_id, "deposit_auto_success", f"Order: {order_id}, Amount: {amount}", bot_token=bot_token)
    except Exception as e:
        logger.error(f"Error notifying user deposit success: {e}")

async def notify_user_deposit_expired(user_id: int, order_id: str, amount: int, bot_token: str):
    try:
        global client
        if client:
            msg = f"""
❌ **DEPOSIT KADALUARSA!**

Order ID: `{order_id}`
Nominal: Rp{amount:,.0f}

Waktu pembayaran telah habis. Silakan lakukan deposit ulang jika masih ingin top up saldo.
            """
            await client.send_message(user_id, msg, parse_mode='markdown')
            await log_activity(user_id, "deposit_expired", f"Order: {order_id}, Amount: {amount}", bot_token=bot_token)
    except Exception as e:
        logger.error(f"Error notifying user deposit expired: {e}")

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

# ===================== CLONED BOT HANDLERS =====================

client = None

async def setup_cloned_bot_handlers(bot_client):
    global client
    client = bot_client

    @bot_client.on(events.NewMessage(pattern='^/deposit(?:\\s+(\\d+))?$'))
    async def deposit_command(event):
        user_id = event.sender_id
        parts = event.message.text.split()
        
        if len(parts) >= 2:
            try:
                amount = int(parts[1])
                await process_deposit(event, amount)
            except ValueError:
                await event.respond("❌ Masukkan nominal yang valid (angka saja)")
        else:
            set_user_state(user_id, STATE_WAITING_DEPOSIT_AMOUNT, {})
            await event.respond(
                "💰 **Masukkan jumlah deposit**\n\n"
                "Contoh: `50000`\n"
                "Minimal: Rp10.000\n"
                "Maksimal: Rp10.000.000",
                parse_mode='markdown'
            )

    @bot_client.on(events.NewMessage(pattern='^/saldo$'))
    async def check_balance_command(event):
        user_id = event.sender_id
        balance = await get_user_balance(user_id, BOT_TOKEN)
        
        msg = f"💰 **SALDO ANDA**\n\n**Total Saldo:** Rp{balance:,.0f}\n\n**Cara Top Up:**\nGunakan perintah `/deposit <amount>`\n\n**Contoh:** `/deposit 50000`"
        
        buttons = [[Button.inline("💳 Deposit", data="deposit"),
                    Button.inline("📜 Riwayat", data="deposit_history")]]
        
        await event.respond(msg, buttons=buttons, parse_mode='markdown')

    @bot_client.on(events.NewMessage(pattern='^/start$'))
    async def cloned_start_handler(event):
        user = await event.get_sender()
        user_id = user.id
        username = user.username or ""
        first_name = user.first_name or ""
        last_name = user.last_name or ""
        fullname = f"{first_name} {last_name}".strip()
        mention = f"[{fullname}](tg://user?id={user_id})"

        await save_user(user_id, username, first_name, last_name, bot_token=BOT_TOKEN, admin_ids=ADMIN_IDS)
        await log_activity(user_id, "start", "User started the bot", bot_token=BOT_TOKEN)
        clear_user_state(user_id)

        fragment_ok, wallet_ok = await check_config()
        
        msg = f"""
[👋](tg://emoji?id=5406577150864159933) **Hallo... {mention} (@{username}) Selamat Datang!**

__Bot ini dapat berfungsi untuk pembelian stars otomatis dengan pembayaran gateway otomatis, silakan klik tombol dibawah ini untuk menggunakan fitur-fitur bot.__
        """
        
        if not fragment_ok:
            msg += "\n⚠️ **Fragment API tidak aktif**"
        if not wallet_ok:
            msg += "\n⚠️ **Wallet tidak aktif**"
        
        buttons = [
            [Button.inline("🛒 Beli Stars", data="buy"),
             Button.inline("💌 Confess Gift", data="confess")],
            [Button.inline("📊 Statistik", data="mystats"),
             Button.inline("ℹ️ Cara Pakai", data="howto")],
        ]

        if await is_admin(user_id):
            buttons.append([Button.inline("⚙️ Admin Panel", data="admin")])
        
        await event.respond(msg, buttons=buttons)

    @bot_client.on(events.NewMessage(pattern='^/cancel$'))
    async def cloned_cancel_command(event):
        user_id = event.sender_id
        await log_activity(user_id, "cancel", "User cancelled operation", bot_token=BOT_TOKEN)
        clear_user_state(user_id)
        await event.respond("✅ **Operasi dibatalkan.**", parse_mode='markdown')

    @bot_client.on(events.CallbackQuery)
    async def cloned_callback_handler(event):
        user_id = event.sender_id
        data = event.data.decode('utf-8')
        
        if data == "back_start":
            await event.delete()
            await cloned_start_handler(event)
        
        elif data == "howto":
            msg = """
[📖](tg://emoji?id=5226512880362332956) **PANDUAN & CARA MENGGUNAKAN BOT**

1. [⭐️](tg://emoji?id=5346309121794659890) **Cara order stars**
2. [🧸](tg://emoji?id=5397915559037785261) **Cara order confess gift** 
3. [💸](tg://emoji?id=5472030678633684592) **Cara deposit**
4. [🏦](tg://emoji?id=5264895611517300926) **Bayar qris vs saldo**

__Klik tombol dibawah ini untuk melihat sesuai dengan tutorial diatas ini sesuai dengan emoji.__
            """
            buttons = [
                [Button.inline("🌠", data="howto_stars"),
                 Button.inline("🧸", data="howto_confess"),
                 Button.inline("💸", data="howto_deposit"),
                 Button.inline("🏦", data="howto_qris")],
                [Button.inline("🔙 Kembali", data="back_start")]
            ]
            await event.delete()
            await event.respond(msg, buttons=buttons)
        
        elif data == "mystats":
            user_stats = await get_user_stats(user_id, bot_token=BOT_TOKEN)
            msg = f"""
[📊](tg://emoji?id=5190806721286657692) **STATISTIK ANDA DI BOT**

[🛒](tg://emoji?id=5312361253610475399) **Total pembelian:** {user_stats['total_purchases']}
[⭐️](tg://emoji?id=5346309121794659890) **Total stars:** {format_number(user_stats['total_stars'])}
[💰](tg://emoji?id=5278467510604160626) **Total pengeluaran:** {format_idr(user_stats['total_spent_idr'])}
[⏰](tg://emoji?id=4972104946464851033) **Pembelian hari ini:** {user_stats['today_purchases']}
            """
            buttons = [[Button.inline("🔙 Kembali", data="back_start")]]
            await event.delete()
            await event.respond(msg, buttons=buttons)
        
        elif data == "admin":
            await cloned_admin_panel(event, user_id)
        
        elif data == "buy":
            set_user_state(user_id, STATE_WAITING_USERNAME)
            msg = """
[⭐️](tg://emoji?id=5346309121794659890) **PEMBELIAN STARS TELEGRAM**

__Untuk melanjutkan pembelian, sialkan kirim username akun tujuan yang akan menerima stars, gunakan username seperti contoh:__
`@username` atau `username` (tanpa @)`
            """
            buttons = [[Button.inline("🔙 Batal", data="back_start")]]
            await event.delete()
            await event.respond(msg, buttons=buttons)
        
        elif data.startswith("sender_show_"):
            set_user_data(user_id, 'show_sender', True)
            await cloned_show_confirmation(event, user_id)
        
        elif data.startswith("sender_hide_"):
            set_user_data(user_id, 'show_sender', False)
            await cloned_show_confirmation(event, user_id)
        
        elif data.startswith("confirm_"):
            await cloned_confirm_purchase(event, user_id)
        
        elif data.startswith("cancel_"):
            await cloned_cancel_purchase(event, user_id)
        
        elif data.startswith("sender_back_"):
            await cloned_ask_sender_option(event, user_id)
        
        elif data == "deposit":
            await event.answer("💳 Memproses deposit...")
            set_user_state(user_id, STATE_WAITING_DEPOSIT_AMOUNT, {})
            await event.respond(
                "💰 **Masukkan jumlah deposit**\n\n"
                "Contoh: `50000`\n"
                "Minimal: Rp10.000\n"
                "Maksimal: Rp10.000.000",
                parse_mode='markdown'
            )
            await event.delete()
        
        elif data == "deposit_history":
            await show_deposit_history(event)
        
        elif data == "check_balance":
            await check_balance_command(event)
        
        elif data.startswith("check_deposit_"):
            order_id = data.replace("check_deposit_", "")
            await check_deposit_status(event, order_id)

    @bot_client.on(events.NewMessage)
    async def cloned_message_handler(event):
        user_id = event.sender_id
        message = event.message.text.strip()
        state = get_user_state(user_id)['state']
        
        if message.lower() == '/cancel':
            await cloned_cancel_command(event)
            return
        
        if state == STATE_WAITING_DEPOSIT_AMOUNT:
            try:
                amount = int(message)
                await process_deposit(event, amount)
                clear_user_state(user_id)
            except ValueError:
                await event.respond("❌ Masukkan nominal yang valid (angka saja)")
            return
        
        if state == STATE_WAITING_USERNAME:
            await cloned_process_username(event, user_id, message)
        elif state == STATE_WAITING_STARS:
            await cloned_process_stars(event, user_id, message)

# ===================== CLONED BOT ADDITIONAL FUNCTIONS =====================

async def cloned_admin_panel(event, user_id):
    if not await is_admin(user_id):
        await event.answer("❌ Akses ditolak!", alert=True)
        return
    
    stats = await get_all_stats(bot_token=BOT_TOKEN)
    balance = await get_balance()
    balance_idr = balance * (PRICE_PER_STAR_IDR / PRICE_PER_STAR_TON / 1)
    
    msg = f"""
⚙️ **ADMIN PANEL - CLONE BOT**

📊 **STATISTIK BOT INI**
• Total Users: {stats['total_users']}
• Active Today: {stats['active_today']}
• Total Purchases: {stats['total_purchases']}
• Total Stars Sold: {format_number(stats['total_stars'])}
• Total Volume: {format_idr(stats['total_volume_idr'])}

💰 **WALLET**
• Balance: {balance:.4f} TON (≈ {format_idr(balance_idr)})

📈 **TODAY**
• Purchases: {stats['today_purchases']}
• Stars: {format_number(stats['today_stars'])}
• Volume: {format_idr(stats['today_volume_idr'])}

💡 **Harga per star:** {format_idr(PRICE_PER_STAR_IDR)}
    """
    
    buttons = [
        [Button.inline("📝 Logs", data="admin_logs")],
        [Button.inline("🔙 Kembali", data="back_start")]
    ]
    
    await event.delete()
    await event.respond(msg, buttons=buttons, parse_mode='markdown')

async def cloned_show_confirmation(event, user_id: int):
    data = get_user_data(user_id)
    sender_text = "Dikirim dari akun" if data.get('show_sender', True) else "🎁 Gift mode (Anonymous)"
    
    price_idr = calculate_price_idr(data['stars'])
    price_ton = calculate_price_ton(data['stars'])
    
    msg = f"""
[🌀](tg://emoji?id=5370715282044100355) **KONFIRMASI PEMBELIAN**

**Penerima:** {data['nickname']} (@{data['username']})
**Stars:** {format_number(data['stars'])}
**Harga:** {format_idr(price_idr)} ≈ {price_ton:.4f} TON
**Opsi Pengirim:** {sender_text}

__Silakan klik tombol dibawah ini untuk melanjutkan tindakan pembelian anda di bot.__
    """
    
    buttons = [
        [Button.inline("✅ Konfirmasi", data=f"confirm_{user_id}"),
         Button.inline("🔄 Ubah Opsi", data=f"sender_back_{user_id}")],
        [Button.inline("❌ Batalkan", data=f"cancel_{user_id}")]
    ]
    
    set_user_state(user_id, STATE_CONFIRM_PURCHASE)
    await event.edit(msg, buttons=buttons)

async def cloned_ask_sender_option(event, user_id: int):
    data = get_user_data(user_id)
    
    price_idr = calculate_price_idr(data['stars'])
    price_ton = calculate_price_ton(data['stars'])
    
    msg = f"""
[✅](tg://emoji?id=4972316727007249049) **Persiapan pembelian telah tersimpan!**

**Jumlah Stars:** {format_number(data['stars'])}
**Harga:** {format_idr(price_idr)} ≈ {price_ton:.4f} TON
**Penerima:** {data['nickname']} (@{data['username']})

__Sebelum melanjutkan ke pembayaran, silakan pilih opsi mode pengiriman untuk stars yang akan diterima oleh user di atas.__

👤 **Dari Akun**: Yang akan mengirim stars ke akun tujuan anda adalah dari akun sistem bot.
🎁 **Anonymous**: Yang akan mengirim stars ke akun tujuan adalah secara anonymous, jadi, pengirim stars adalah akun resmi Telegram>
    """
    
    buttons = [
        [Button.inline("👤 Dari Akun", data=f"sender_show_{user_id}"),
         Button.inline("🎁 Anonymous", data=f"sender_hide_{user_id}")],
        [Button.inline("🛑 Batalkan", data=f"cancel_{user_id}")]
    ]
    
    set_user_state(user_id, STATE_WAITING_SENDER_OPTION)
    await event.respond(msg, buttons=buttons)

async def cloned_confirm_purchase(event, user_id: int):
    data = get_user_data(user_id)
    if not data:
        await event.edit("❌ Sesi kadaluarsa. Silakan ulangi lagi.")
        clear_user_state(user_id)
        return
    
    show_sender = data.get('show_sender', True)
    price_idr = calculate_price_idr(data['stars'])
    price_ton = calculate_price_ton(data['stars'])
    
    msg_wait = f"""
[⏳](tg://emoji?id=5451732530048802485) **Memproses pembelian...**

**Penerima:** @{data['username']}
**Stars:** {format_number(data['stars'])}
**Harga:** {format_idr(price_idr)} ≈ {price_ton:.4f} TON
**Opsi Pengirim:** {'Dikirim dari akun' if show_sender else 'Anonymous (dari Telegram)'}
    """
    
    await event.edit(msg_wait, parse_mode='markdown')
    
    await save_purchase(user_id, data['username'], data['nickname'],
                        data['stars'], price_idr, price_ton, show_sender=show_sender, 
                        status="pending", bot_token=BOT_TOKEN)
    
    try:
        tx_hash = await pay_stars_order(data['username'], data['stars'], show_sender)
        
        if tx_hash:
            await save_purchase(user_id, data['username'], data['nickname'],
                                data['stars'], price_idr, price_ton, tx_hash=tx_hash,
                                show_sender=show_sender, status="success", bot_token=BOT_TOKEN)
            
            msg_success = f"""
[🎉](tg://emoji?id=5193209274452425995) **PEMBELIAN STARS BERHASIL!**

**Penerima:** @{data['username']}
**Stars:** {format_number(data['stars'])}
**Harga:** {format_idr(price_idr)} ≈ {price_ton:.4f} TON
**Opsi Pengirim:** {'Dikirim dari akun' if show_sender else 'Anonymous (dari Telegram)'}
**Tx Hash:** `{tx_hash[:20]}...`
            """
            
            buttons = [[Button.inline("🛒 Beli Lagi", data="buy")],
                      [Button.inline("🔙 Menu Utama", data="back_start")]]
            
            await event.edit(msg_success, buttons=buttons)
            await log_activity(user_id, "purchase_success", f"Stars: {data['stars']}, Hash: {tx_hash}", bot_token=BOT_TOKEN)
        else:
            await save_purchase(user_id, data['username'], data['nickname'],
                                data['stars'], price_idr, price_ton, show_sender=show_sender,
                                status="failed", error_message="Transaction failed", bot_token=BOT_TOKEN)
            
            buttons = [[Button.inline("🔄 Coba Lagi", data="buy")]]
            await event.edit("❌ **Pembelian Gagal**\n\nCoba lagi nanti.", buttons=buttons, parse_mode='markdown')
            await log_activity(user_id, "purchase_failed", f"Stars: {data['stars']}", bot_token=BOT_TOKEN)
    
    except Exception as e:
        logger.error(f"Error: {e}")
        await save_purchase(user_id, data['username'], data['nickname'],
                            data['stars'], price_idr, price_ton, show_sender=show_sender,
                            status="error", error_message=str(e)[:200], bot_token=BOT_TOKEN)
        
        buttons = [[Button.inline("🔄 Coba Lagi", data="buy")]]
        await event.edit(f"❌ **Error:** {str(e)[:100]}", buttons=buttons, parse_mode='markdown')
        await log_activity(user_id, "purchase_error", str(e)[:100], bot_token=BOT_TOKEN)
    
    finally:
        clear_user_state(user_id)

async def cloned_cancel_purchase(event, user_id: int):
    clear_user_state(user_id)
    await event.edit("❌ **Pembelian Dibatalkan**",
                     buttons=[Button.inline("🛒 Beli Stars", data="buy")], parse_mode='markdown')
    await log_activity(user_id, "purchase_cancelled", "User cancelled purchase", bot_token=BOT_TOKEN)

async def cloned_process_username(event, user_id: int, username: str):
    clean_name = clean_username(username)
    
    if not clean_name:
        await event.respond("❌ Username tidak valid")
        return
    
    async with event.client.action(event.chat_id, 'typing'):
        msg_search = await event.respond("🔍 **Mencari username...**")
        
        try:
            user_info = await get_user(clean_name)
            
            if not user_info:
                buttons = [[Button.inline("🔙 Kembali", data="back_start")]]
                await event.reply(f"❌ Username **@{clean_name}** tidak ditemukan.", buttons=buttons)
                return
            
            set_user_data(user_id, 'username', clean_name)
            set_user_data(user_id, 'nickname', user_info['nickname'])
            set_user_data(user_id, 'address', user_info['address'])
            
            set_user_state(user_id, STATE_WAITING_STARS)
            
            msg = f"""
✅ **USER DITEMUKAN**

**Nama penerima:** {user_info['nickname']}
**Username:** @{clean_name}

Silakan masukkan jumlah stars yang ingin Anda beli.

💡 **Harga:** {format_idr(PRICE_PER_STAR_IDR)} per star
            """
            
            buttons = [[Button.inline("🔙 Kembali", data="back_start")]]
            
            await msg_search.delete()
            await event.respond(msg, buttons=buttons, parse_mode='markdown')
            
        except Exception as e:
            logger.error(f"Error: {e}")
            await event.respond("❌ Terjadi kesalahan.")

async def cloned_process_stars(event, user_id: int, stars_str: str):
    try:
        stars = int(stars_str)
        
        if stars < MIN_STARS:
            await event.respond(f"❌ Jumlah stars tidak boleh kurang dari {format_number(MIN_STARS)} stars.")
            return
        
        if stars > MAX_STARS:
            await event.respond(f"❌ Jumlah stars tidak boleh lebih dari {format_number(MAX_STARS)} stars.")
            return
        
        set_user_data(user_id, 'stars', stars)
        
        await cloned_ask_sender_option(event, user_id)
        
    except ValueError:
        await event.respond("❌ Masukkan angka yang valid.")

# ===================== MAIN =====================

async def main():
    global client
    logger.info("Starting as CLONED BOT...")
    init_database()
    await update_bot_status(BOT_TOKEN, 'running')
    
    client = TelegramClient(f'clone_bot_{BOT_TOKEN}', API_ID, API_HASH)
    await setup_cloned_bot_handlers(client)
    
    asyncio.create_task(monitor_deposit())
    logger.info("✅ Deposit monitor started")
    
    logger.info(f"✅ Cloned bot running")
    await client.start(bot_token=BOT_TOKEN)
    logger.info("✅ Cloned bot is running")
    await client.run_until_disconnected()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Bot dihentikan oleh user")
    except Exception as e:
        logger.error(f"❌ Error fatal: {e}")
