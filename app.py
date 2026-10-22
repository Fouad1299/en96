
import os
import threading
import logging
from flask import Flask
import bot as en96_bot

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

@app.get("/")
def home():
    return "EN96 Bot is running!", 200

def run_bot():
    en96_bot.bot.infinity_polling(
        skip_pending=True,
        timeout=30
    )

if __name__ == "__main__":
    threading.Thread(
        target=run_bot,
        daemon=True
    ).start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
