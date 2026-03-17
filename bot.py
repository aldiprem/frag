#!/usr/bin/env python3
"""
Telegram Stars Bot - Auto Buy Telegram Stars via Fragment.com
Dibuat dengan Telethon dan Fragment-API-Py
"""

import os
import sys
import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from dataclasses import dataclass

from telethon import TelegramClient, events, Button
from telethon.tl.types import User
from telethon.errors import FloodWaitError
import fragment_api_py
from fragment_api_py import AsyncFragmentAPI, FragmentAPIError

from config import Config, logger

# ==================== DATA CLASSES ====================

@dataclass
class UserState:
    """Menyimpan state user sementara"""
    step: str  # 'username', 'amount', 'confirm'
    username: str = ''
    amount: int = 0
    user_entity: Any = None
    timestamp: float = 0

# ==================== BOT CLASS ====================

class StarsBot:
    """Main bot class"""
    
    def __init__(self):
        self.client = None
        self.fragment_api = None
        self.user_states: Dict[int, UserState] = {}
        self.start_time = datetime.now()
        self.total_purchases = 0
        self.total_stars = 0
        
    async def init_fragment_api(self) -> bool:
        """Inisialisasi Fragment API"""
        try:
            logger.info("🔄 Inisialisasi Fragment API...")
            
            self.fragment_api = AsyncFragmentAPI(
                cookies=Config.FRAGMENT_COOKIES,
                hash_value=Config.FRAGMENT_HASH,
                wallet_mnemonic=Config.WALLET_MNEMONIC if Config.WALLET_MNEMONIC != 'abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon' else None,
                wallet_api_key=Config.TON_API_KEY if Config.TON_API_KEY != 'your_ton_api_key_here' else None,
                wallet_version=Config.WALLET_VERSION
            )
            
            # Test koneksi dengan get balance
            try:
                balance = await self.fragment_api.get_wallet_balance()
                logger.info(f"✅ Fragment API siap!")
                logger.info(f"💰 Wallet Balance: {balance.get('balance_ton', 'Unknown')} TON")
                logger.info(f"🏦 Wallet Address: {balance.get('address', 'Unknown')[:10]}...")
                return True
            except Exception as e:
                logger.warning(f"⚠️ Wallet not configured: {e}")
                logger.info("✅ Fragment API siap (mode terbatas - wallet perlu dikonfigurasi)")
                return True
                
        except Exception as e:
            logger.error(f"❌ Gagal init Fragment API: {e}")
            return False
    
    async def start(self):
        """Start the bot"""
        print("\n" + "="*60)
        print("🚀 TELEGRAM STARS BOT - AUTO BUY VIA FRAGMENT")
        print("="*60)
        
        # Validasi config
        errors, warnings = Config.validate()
        
        if errors:
            print("\n❌ ERROR KONFIGURASI:")
            for error in errors:
                print(f"  {error}")
            print("\n📝 Silakan perbaiki file .env terlebih dahulu!")
            return
        
        if warnings:
            print("\n⚠️ PERINGATAN:")
            for warning in warnings:
                print(f"  {warning}")
        
        Config.display_config()
        
        # Inisialisasi Fragment API
        if not await self.init_fragment_api():
            print("\n❌ Gagal inisialisasi Fragment API. Bot tidak bisa jalan.")
            return
        
        # Inisialisasi Telegram Client
        print("\n🔄 Menghubungkan ke Telegram...")
        self.client = TelegramClient('stars_bot_session', Config.API_ID, Config.API_HASH)
        
        # Register handlers
        self.register_handlers()
        
        try:
            await self.client.start(bot_token=Config.BOT_TOKEN)
            
            # Get bot info
            me = await self.client.get_me()
            print(f"\n✅ Bot started successfully!")
            print(f"🤖 Bot: @{me.username}")
            print(f"📅 Started at: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print("-"*60)
            print("Commands: /start, /buy, /balance, /stats, /help")
            print("="*60 + "\n")
            
            await self.client.run_until_disconnected()
            
        except Exception as e:
            logger.error(f"Fatal error: {e}")
        finally:
            await self.cleanup()
    
    def register_handlers(self):
        """Register all event handlers"""
        
        @self.client.on(events.NewMessage(pattern='/start'))
        async def start_handler(event):
            await self.handle_start(event)
        
        @self.client.on(events.NewMessage(pattern='/buy'))
        async def buy_handler(event):
            await self.handle_buy(event)
        
        @self.client.on(events.NewMessage(pattern='/balance'))
        async def balance_handler(event):
            await self.handle_balance(event)
        
        @self.client.on(events.NewMessage(pattern='/stats'))
        async def stats_handler(event):
            await self.handle_stats(event)
        
        @self.client.on(events.NewMessage(pattern='/help'))
        async def help_handler(event):
            await self.handle_help(event)
        
        @self.client.on(events.NewMessage(pattern='/cancel'))
        async def cancel_handler(event):
            await self.handle_cancel(event)
        
        @self.client.on(events.CallbackQuery)
        async def callback_handler(event):
            await self.handle_callback(event)
        
        @self.client.on(events.NewMessage)
        async def message_handler(event):
            if event.message.text and not event.message.text.startswith('/'):
                await self.handle_user_input(event)
    
    # ==================== COMMAND HANDLERS ====================
    
    async def handle_start(self, event):
        """Handler untuk /start"""
        user = await event.get_sender()
        
        welcome_text = f"""
🌟 **SELAMAT DATANG DI STARS BOT** 🌟

Halo {user.first_name}! Saya adalah bot pembeli Telegram Stars otomatis via Fragment.com.

✨ **Fitur Utama:**
• Beli Telegram Stars untuk user lain
• Cek saldo wallet TON
• Auto-konfirmasi transaksi
• Aman dan cepat

📌 **Cara Penggunaan:**
1️⃣ Ketik /buy untuk mulai beli Stars
2️⃣ Masukkan username penerima
3️⃣ Masukkan jumlah Stars
4️⃣ Konfirmasi pembelian

💰 **Batasan:**
• Min: {Config.MIN_STARS} Stars
• Max: {Config.MAX_STARS} Stars

📚 **Command List:**
/start - Tampilkan pesan ini
/buy - Beli Telegram Stars
/balance - Cek saldo wallet
/stats - Statistik bot
/help - Bantuan lengkap
/cancel - Batalkan proses

⚠️ Pastikan wallet TON Anda memiliki saldo cukup!
        """
        
        buttons = [
            [Button.inline("🛒 BELI STARS", b"buy")],
            [Button.inline("💰 CEK SALDO", b"balance"), 
             Button.inline("📊 STATS", b"stats")],
            [Button.inline("❓ BANTUAN", b"help")]
        ]
        
        await event.reply(welcome_text, buttons=buttons, parse_mode='markdown')
    
    async def handle_buy(self, event):
        """Handler untuk /buy"""
        user_id = event.sender_id
        
        # Buat state baru
        self.user_states[user_id] = UserState(
            step='username',
            timestamp=datetime.now().timestamp()
        )
        
        msg = """
🛒 **PROSES PEMBELIAN STARS**

Langkah 1/3: Masukkan username Telegram penerima

📝 **Contoh:**
• @username
• username (tanpa @)

Ketik /cancel untuk membatalkan
        """
        
        await event.reply(msg, parse_mode='markdown')
    
    async def handle_balance(self, event):
        """Handler untuk /balance"""
        try:
            if not self.fragment_api:
                await event.reply("❌ Fragment API tidak tersedia")
                return
            
            balance = await self.fragment_api.get_wallet_balance()
            
            msg = f"""
💰 **INFORMASI WALLET**

**Balance:** `{balance.get('balance_ton', 'Unknown')} TON`
**Address:** `{balance.get('address', 'Unknown')}`
**Version:** `{balance.get('wallet_version', 'Unknown')}`

💡 Gunakan /buy untuk membeli Stars
            """
            
            await event.reply(msg, parse_mode='markdown')
            
        except Exception as e:
            logger.error(f"Balance error: {e}")
            await event.reply("❌ Gagal mendapatkan informasi saldo")
    
    async def handle_stats(self, event):
        """Handler untuk /stats"""
        uptime = datetime.now() - self.start_time
        hours, remainder = divmod(int(uptime.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        
        msg = f"""
📊 **STATISTIK BOT**

**Uptime:** {hours}h {minutes}m {seconds}s
**Total Pembelian:** {self.total_purchases}
**Total Stars:** {self.total_stars} ⭐
**User Active:** {len(self.user_states)}

**Status Fragment:** {'✅ Online' if self.fragment_api else '❌ Offline'}
**Wallet Version:** {Config.WALLET_VERSION}

🕐 Started: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}
        """
        
        await event.reply(msg, parse_mode='markdown')
    
    async def handle_help(self, event):
        """Handler untuk /help"""
        help_text = """
📚 **BANTUAN LENGKAP**

**📋 COMMANDS:**
/start - Mulai bot
/buy - Beli Telegram Stars
/balance - Cek saldo wallet
/stats - Lihat statistik
/help - Tampilkan bantuan ini
/cancel - Batalkan proses

**🛒 CARA BELI STARS:**
1. Ketik /buy
2. Masukkan username (contoh: @username)
3. Masukkan jumlah Stars (min 1, max 1000)
4. Konfirmasi pembelian
5. Tunggu proses selesai

**⚠️ PENTING:**
• Pastikan wallet TON memiliki saldo
• Proses bisa memakan waktu 1-2 menit
• Transaction hash akan ditampilkan setelah sukses

**❓ PROBLEM:**
• "Insufficient balance" → Top up wallet TON
• "Invalid username" → Username tidak ditemukan
• "Transaction failed" → Coba lagi nanti

Ada pertanyaan lain? Hubungi @support
        """
        
        await event.reply(help_text, parse_mode='markdown')
    
    async def handle_cancel(self, event):
        """Handler untuk /cancel"""
        user_id = event.sender_id
        
        if user_id in self.user_states:
            del self.user_states[user_id]
            await event.reply("❌ Proses dibatalkan. Ketik /buy untuk mulai lagi.")
        else:
            await event.reply("❌ Tidak ada proses aktif. Ketik /buy untuk mulai.")
    
    # ==================== CALLBACK HANDLER ====================
    
    async def handle_callback(self, event):
        """Handler untuk button callbacks"""
        data = event.data.decode()
        user_id = event.sender_id
        
        if data == "buy":
            await self.handle_buy(event)
        elif data == "balance":
            await self.handle_balance(event)
        elif data == "stats":
            await self.handle_stats(event)
        elif data == "help":
            await self.handle_help(event)
        elif data.startswith("confirm_"):
            await self.process_purchase(event, data)
        elif data == "cancel":
            if user_id in self.user_states:
                del self.user_states[user_id]
            await event.edit("❌ Pembelian dibatalkan.")
    
    # ==================== USER INPUT HANDLER ====================
    
    async def handle_user_input(self, event):
        """Handle input dari user"""
        user_id = event.sender_id
        text = event.message.text.strip()
        
        if user_id not in self.user_states:
            return
        
        state = self.user_states[user_id]
        
        try:
            if state.step == 'username':
                await self.process_username_input(event, state, text)
            elif state.step == 'amount':
                await self.process_amount_input(event, state, text)
                
        except Exception as e:
            logger.error(f"Input error for {user_id}: {e}")
            await event.reply("❌ Terjadi error. Ketik /cancel dan coba lagi.")
            if user_id in self.user_states:
                del self.user_states[user_id]
    
    async def process_username_input(self, event, state, text):
        """Proses input username"""
        username = text.replace('@', '').strip()
        
        if not username or len(username) < 3:
            await event.reply("❌ Username tidak valid. Masukkan username yang benar:")
            return
        
        # Validasi user di Telegram
        try:
            entity = await self.client.get_entity(username)
            
            if not isinstance(entity, User):
                await event.reply("❌ Username bukan milik user Telegram.")
                return
            
            # Update state
            state.username = username
            state.user_entity = entity
            state.step = 'amount'
            
            # Tampilkan info user
            name = f"{entity.first_name} {entity.last_name or ''}".strip()
            user_info = f"""
✅ **USER DITEMUKAN!**

**Nama:** {name}
**Username:** @{username}
**ID:** {entity.id}

📝 Langkah 2/3: Masukkan jumlah Stars yang ingin dibeli
(min: {Config.MIN_STARS}, max: {Config.MAX_STARS})

Contoh: 100
            """
            
            await event.reply(user_info, parse_mode='markdown')
            
        except FloodWaitError as e:
            await event.reply(f"⚠️ Terlalu banyak request. Tunggu {e.seconds} detik.")
        except Exception as e:
            logger.error(f"User lookup error: {e}")
            await event.reply("❌ Username tidak ditemukan di Telegram. Masukkan username valid:")
    
    async def process_amount_input(self, event, state, text):
        """Proses input jumlah stars"""
        try:
            amount = int(text)
            
            if amount < Config.MIN_STARS or amount > Config.MAX_STARS:
                await event.reply(f"❌ Jumlah harus antara {Config.MIN_STARS}-{Config.MAX_STARS}:")
                return
            
            # Update state
            state.amount = amount
            state.step = 'confirm'
            
            # Tampilkan konfirmasi
            confirm_msg = f"""
🔄 **KONFIRMASI PEMBELIAN**

**Penerima:** @{state.username}
**Jumlah:** {amount} ⭐

Apakah data sudah benar?
            """
            
            buttons = [
                [Button.inline("✅ YA, BELI", data=f"confirm_{amount}")],
                [Button.inline("❌ BATAL", data="cancel")]
            ]
            
            await event.reply(confirm_msg, buttons=buttons, parse_mode='markdown')
            
        except ValueError:
            await event.reply(f"❌ Masukkan angka valid (1-{Config.MAX_STARS}):")
    
    # ==================== PURCHASE PROCESSOR ====================
    
    async def process_purchase(self, event, data):
        """Proses pembelian Stars"""
        user_id = event.sender_id
        
        if user_id not in self.user_states:
            await event.edit("❌ Sesi telah berakhir. Ketik /buy untuk mulai lagi.")
            return
        
        state = self.user_states[user_id]
        
        # Update pesan ke processing
        await event.edit("⏱️ **MEMPROSES PEMBELIAN...**\n\nMohon tunggu, transaksi sedang diproses.", parse_mode='markdown')
        
        try:
            # Cek apakah wallet dikonfigurasi
            if not self.fragment_api or not Config.WALLET_MNEMONIC or Config.WALLET_MNEMONIC.startswith('abandon'):
                await event.edit("❌ **WALLET BELUM DIKONFIGURASI**\n\nWallet TON belum diatur di file .env.\nGanti WALLET_MNEMONIC dengan seed phrase asli Anda!")
                return
            
            # Proses pembelian
            logger.info(f"Processing purchase: {state.amount} stars for @{state.username}")
            
            result = await self.fragment_api.buy_stars(
                username=state.username,
                quantity=state.amount,
                show_sender=True
            )
            
            if result and hasattr(result, 'success') and result.success:
                # Update statistik
                self.total_purchases += 1
                self.total_stars += state.amount
                
                success_msg = f"""
✅ **PEMBELIAN BERHASIL!**

**Penerima:** @{state.username}
**Jumlah:** {state.amount} ⭐
**Transaction Hash:** `{getattr(result, 'transaction_hash', 'N/A')}`

✨ Stars akan segera masuk ke akun penerima.
Terima kasih telah menggunakan bot ini!
                """
                
                await event.edit(success_msg, parse_mode='markdown')
                logger.info(f"Purchase successful: {state.amount} stars for @{state.username}")
                
            else:
                error = getattr(result, 'error', 'Unknown error')
                error_msg = f"""
❌ **PEMBELIAN GAGAL**

**Error:** {error}

Kemungkinan penyebab:
• Saldo TON tidak cukup
• Wallet tidak terhubung dengan Fragment
• Rate limit dari Fragment

Ketik /buy untuk mencoba lagi.
                """
                
                await event.edit(error_msg, parse_mode='markdown')
                logger.error(f"Purchase failed: {error}")
                
        except Exception as e:
            logger.error(f"Purchase exception: {e}")
            await event.edit(f"❌ **ERROR:** {str(e)[:200]}\n\nKetik /buy untuk coba lagi.")
        
        # Hapus state
        if user_id in self.user_states:
            del self.user_states[user_id]
    
    async def cleanup(self):
        """Cleanup resources"""
        logger.info("Shutting down bot...")
        if self.fragment_api:
            await self.fragment_api.close()
        if self.client:
            await self.client.disconnect()

# ==================== MAIN ====================

async def main():
    """Main function"""
    bot = StarsBot()
    await bot.start()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
