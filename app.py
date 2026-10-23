
import os
import threading
import logging
from flask import Flask, jsonify
import bot as en96_bot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger("EN96")

app = Flask(__name__)


@app.get("/")
def home():
    return """
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <meta name="theme-color" content="#071326">
      <title>EN96 Ice Dragon</title>
      <script src="https://telegram.org/js/telegram-web-app.js"></script>
      <style>
        * { box-sizing: border-box; }
        body {
          margin: 0;
          padding: 22px 16px;
          min-height: 100vh;
          color: #f5f8ff;
          background: radial-gradient(circle at top, #153a68, #071326 65%);
          font-family: Arial, sans-serif;
          text-align: center;
        }
        .wrap { max-width: 480px; margin: auto; }
        .logo {
          width: 100px; height: 100px; margin: 16px auto;
          display: grid; place-items: center;
          border-radius: 28px; border: 2px solid #e6bd62;
          background: linear-gradient(145deg, #174c83, #08142a);
          font-size: 30px; font-weight: 900; color: #f5d681;
          box-shadow: 0 0 30px #1676bd55;
        }
        h1 { color: #f5d681; margin-bottom: 6px; }
        .muted { color: #afc4e5; line-height: 1.8; }
        .card {
          margin-top: 20px; padding: 22px;
          border: 1px solid #29476e; border-radius: 20px;
          background: #0c1a30dd;
        }
        .balance { font-size: 34px; font-weight: bold; color: #f5d681; margin: 12px 0; }
        button {
          width: 100%; padding: 15px; margin-top: 12px;
          border: 0; border-radius: 13px; font-size: 17px;
          font-weight: bold; cursor: pointer;
          background: linear-gradient(90deg, #e6bd62, #ffe7a0);
          color: #10203a;
        }
        .secondary {
          color: #f5f8ff; background: #17365b;
          border: 1px solid #315985;
        }
        #status { margin-top: 16px; color: #c7d8f2; line-height: 1.8; }
        footer { margin: 24px 0; font-size: 12px; color: #8da6c9; }
      </style>
    </head>
    <body>
      <main class="wrap">
        <div class="logo">EN96</div>
        <h1>🐉 EN96 ICE DRAGON</h1>
        <div class="muted">مرحبًا بك في تطبيق EN96</div>

        <section class="card">
          <div class="muted">رصيد EN96</div>
          <div class="balance">— EN96</div>
          <div class="muted">
            واجهة التطبيق جاهزة للتطوير والربط الآمن بحسابك.
          </div>
          <button onclick="showStatus()">⛏️ التعدين</button>
          <button class="secondary" onclick="showStatus()">🎁 الهدايا والأكواد</button>
          <button class="secondary" onclick="showStatus()">👥 المهام والإحالات</button>
          <button class="secondary" onclick="showStatus()">💳 المحفظة والسحب</button>
          <div id="status">جارٍ تجهيز التطبيق...</div>
        </section>

        <footer>
          التعدين المعروض افتراضي، وليس تعدينًا حقيقيًا على الشبكة.
        </footer>
      </main>

      <script>
        const statusBox = document.getElementById("status");
        function showStatus() {
          statusBox.textContent =
            "هذه الواجهة الأولية. سنربط الأزرار ببيانات حسابك في الخطوة التالية.";
        }
        if (window.Telegram && window.Telegram.WebApp) {
          Telegram.WebApp.ready();
          Telegram.WebApp.expand();
          statusBox.textContent = "تم فتح واجهة EN96 داخل تيليغرام.";
        } else {
          statusBox.textContent = "يمكن معاينة الواجهة من المتصفح أيضًا.";
        }
      </script>
    </body>
    </html>
    """, 200


@app.get("/health")
def health():
    return jsonify({"status": "ok", "app": "EN96"}), 200


def run_bot():
    try:
        me = en96_bot.bot.get_me()
        logger.info("Telegram connected to bot username: @%s", me.username)
        en96_bot.bot.infinity_polling(
            skip_pending=True,
            timeout=30
        )
    except Exception:
        logger.exception("Telegram bot polling failed")


if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
