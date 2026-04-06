import mysql.connector
import os

DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', 'Asdf1234_'),
    'database': os.getenv('DB_NAME', 'fragment')
}

def get_bot_config(bot_token: str):
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM bot_config WHERE bot_token = %s", (bot_token,))
    result = cursor.fetchone()
    conn.close()
    return result