# backend/bot_client.py
import asyncio
import base64
import json
import aiohttp
from telethon import TelegramClient
from tonutils.client import TonapiClient
from tonutils.wallet import WalletV5R1

class FragmentBotClient:
    def __init__(self, api_id, api_hash, bot_token, cookies, hash, wallet_api_key, wallet_mnemonic):
        self.api_id = api_id
        self.api_hash = api_hash
        self.bot_token = bot_token
        self.cookies = cookies
        self.hash = hash
        self.wallet_api_key = wallet_api_key
        self.wallet_mnemonic = wallet_mnemonic
        
        # Inisialisasi Telegram client (optional)
        self.client = TelegramClient('website_session', api_id, api_hash)
        
    async def ensure_client(self):
        """Pastikan client terhubung"""
        if not self.client.is_connected():
            await self.client.start(bot_token=self.bot_token)
    
    async def post_fragment(self, data):
        """POST request ke Fragment API"""
        params = {"hash": self.hash}
        headers = {
            "accept": "application/json",
            "cookie": self.cookies,
            "user-agent": "Mozilla/5.0",
            "x-requested-with": "XMLHttpRequest",
        }
        
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
    
    async def get_user_info(self, username):
        """Dapatkan informasi user dari Fragment"""
        data = {
            "query": username,
            "quantity": "",
            "method": "searchStarsRecipient"
        }
        
        result = await self.post_fragment(data)
        if result and result.get("found"):
            return {
                'nickname': result["found"]["name"],
                'address': result["found"]["recipient"]
            }
        return None
    
    async def purchase_stars(self, username, quantity, show_sender=True):
        """Proses pembelian stars"""
        # 1. Dapatkan address user
        user_info = await self.get_user_info(username)
        if not user_info:
            raise Exception("User not found")
        
        # 2. Inisialisasi pembelian
        init_data = {
            "recipient": user_info['address'],
            "quantity": quantity,
            "method": "initBuyStarsRequest"
        }
        
        init_result = await self.post_fragment(init_data)
        if not init_result or 'req_id' not in init_result:
            raise Exception("Failed to initialize purchase")
        
        req_id = init_result['req_id']
        
        # 3. Dapatkan detail pembayaran
        buy_data = {
            "transaction": "1",
            "id": req_id,
            "show_sender": "1" if show_sender else "0",
            "method": "getBuyStarsLink"
        }
        
        buy_result = await self.post_fragment(buy_data)
        if not buy_result:
            raise Exception("Failed to get payment details")
        
        messages = buy_result.get("transaction", {}).get("messages", [])
        if not messages:
            raise Exception("No transaction messages")
        
        pay_address = messages[0].get("address")
        amount = messages[0].get("amount")
        payload = messages[0].get("payload")
        
        # 4. Decode payload
        decoded_payload = self.decode_payload(payload)
        
        # 5. Kirim transfer
        tx_hash = await self.send_ton_transfer(pay_address, int(amount), decoded_payload)
        
        return tx_hash
    
    def decode_payload(self, encoded_string):
        """Decode base64 payload"""
        if not encoded_string:
            return ""
        
        missing_padding = len(encoded_string) % 4
        if missing_padding != 0:
            encoded_string += "=" * (4 - missing_padding)
        
        decoded = base64.b64decode(encoded_string)
        return decoded.decode("utf-8", errors="ignore")
    
    async def send_ton_transfer(self, address, amount, payload):
        """Kirim transfer TON"""
        client = TonapiClient(api_key=self.wallet_api_key, is_testnet=False)
        wallet, _, _, _ = WalletV5R1.from_mnemonic(client, self.wallet_mnemonic)
        
        amount_in_ton = amount / 1_000_000_000
        
        tx_hash = await wallet.transfer(
            destination=address,
            amount=amount_in_ton,
            body=payload,
        )
        return tx_hash
