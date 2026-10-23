
import os
import hmac
import json
import time
import hashlib
import threading
import logging
from urllib.parse import parse_qsl

from flask import Flask, jsonify, request
import bot as en96_bot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger("EN96")

app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")


def telegram_user():
    """Verify Telegram Mini App initData on the server."""
    if not BOT_TOKEN:
        return None, "إعدادات البوت غير مكتملة على الخادم."

    init_data = request.headers.get("X-Telegram-Init-Data", "")
    if not init_data:
        return None, "افتح التطبيق من داخل بوت EN96 على تيليغرام."

    try:
        fields = dict(parse_qsl(init_data, keep_blank_values=True))
        received_hash = fields.pop("hash", None)

        if not received_hash:
            return None, "تعذر التحقق من هوية تيليغرام."

        check_string = "\n".join(
            f"{key}={value}" for key, value in sorted(fields.items())
        )

        secret_key = hmac.new(
            b"WebAppData",
            BOT_TOKEN.encode(),
            hashlib.sha256
        ).digest()

        calculated_hash = hmac.new(
            secret_key,
            check_string.encode(),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(calculated_hash, received_hash):
            return None, "فشل التحقق من هوية تيليغرام."

        auth_date = int(fields.get("auth_date", "0"))
        now = int(time.time())

        if auth_date <= 0 or auth_date > now + 60 or now - auth_date > 86400:
            return None, "انتهت صلاحية جلسة تيليغرام. أغلق التطبيق وافتحه مجددًا."

        user = json.loads(fields.get("user", "{}"))
        telegram_id = user.get("id")

        if not telegram_id:
            return None, "لم يتم العثور على حساب تيليغرام."

        return {
            "id": str(telegram_id),
            "first_name": user.get("first_name", "")
        }, None

    except Exception:
        logger.exception("Telegram identity verification failed")
        return None, "تعذر التحقق من الجلسة. حاول فتح التطبيق مجددًا."


def get_balance(telegram_id):
    """Read the existing profile and balance without changing either."""
    profile_result = (
        en96_bot.db.table("profiles")
        .select("id,telegram_id")
        .eq("telegram_id", str(telegram_id))
        .limit(1)
        .execute()
    )

    profiles = profile_result.data or []
    if not profiles:
        return None, "لم يتم العثور على حسابك. افتح البوت واضغط /start."

    profile = profiles[0]

    balance_result = (
        en96_bot.db.table("balances")
        .select("available,reserved")
        .eq("user_id", profile["id"])
        .limit(1)
        .execute()
    )

    balances = balance_result.data or []
    if not balances:
        return None, "لم يُعثر على سجل الرصيد لهذا الحساب."

    balance = balances[0]
    return {
        "telegram_id": str(telegram_id),
        "available": balance.get("available", 0),
        "reserved": balance.get("reserved", 0)
    }, None


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
      margin: 0; padding: 22px 16px; min-height: 100vh;
      color: #f5f8ff;
      background: radial-gradient(circle at top, #153a68, #071326 65%);
      font-family: Arial, sans-serif; text-align: center;
    }
    .wrap { max-width: 480px; margin: auto; }
    .logo {
      width: 100px; height: 100px; margin: 16px auto;
      display: grid; place-items: center; border-radius: 28px;
      border: 2px solid #e6bd62;
      background: linear-gradient(145deg, #174c83, #08142a);
      font-size: 30px; font-weight: 900; color: #f5d681;
    }
    h1 { color: #f5d681; margin-bottom: 6px; }
    .muted { color: #afc4e5; line-height: 1.8; }
    .card {
      margin-top: 20px; padding: 22px;
      border: 1px solid #29476e; border-radius: 20px;
      background: #0c1a30dd;
    }
    .balance {
      font-size: 32px; font-weight: bold;
      color: #f5d681; margin: 12px 0;
      overflow-wrap: anywhere;
    }
    button, input {
      width: 100%; padding: 15px; margin-top: 12px;
      border-radius: 13px; font-size: 16px;
    }
    button {
      border: 0; font-weight: bold; cursor: pointer;
      background: linear-gradient(90deg, #e6bd62, #ffe7a0);
      color: #10203a;
    }
    .secondary {
      color: #f5f8ff; background: #17365b;
      border: 1px solid #315985;
    }
    input {
      border: 1px solid #315985;
      background: #071326; color: white;
    }
    #status { margin-top: 16px; color: #c7d8f2; line-height: 1.8; }
    footer { margin: 24px 0; font-size: 12px; color: #8da6c9; }
  </style>
</head>
<body>
<main class="wrap">
  <div class="logo">EN96</div>
  <h1>🐉 EN96 ICE DRAGON</h1>
  <div class="muted" id="welcome">مرحبًا بك في تطبيق EN96</div>

  <section class="card">
    <div class="muted">الرصيد المتاح</div>
    <div class="balance" id="balance">جارٍ تحميل الرصيد...</div>
    <div class="muted" id="reserved">الرصيد المحجوز: —</div>

    <button id="miningButton" onclick="doMining()">⛏️ بدء التعدين / استلام المكافأة</button>

    <input id="giftCode" maxlength="100"
      placeholder="أدخل كود هدية EN96">
    <button class="secondary" onclick="redeemGift()">🎁 استلام الهدية</button>

    <button class="secondary" onclick="loadBalance()">🔄 تحديث الرصيد</button>
    <div id="status">جارٍ الاتصال بالتطبيق...</div>
  </section>

  <footer>
    التعدين هنا افتراضي، وليس تعدينًا حقيقيًا على الشبكة.
  </footer>
</main>

<script>
const tg = window.Telegram && window.Telegram.WebApp;
const statusBox = document.getElementById("status");
const balanceBox = document.getElementById("balance");
const reservedBox = document.getElementById("reserved");

if (tg) {
  tg.ready();
  tg.expand();
}

function showMessage(message) {
  statusBox.textContent = message;
}

async function api(path, body) {
  if (!tg || !tg.initData) {
    throw new Error("افتح التطبيق من زر فتح تطبيق EN96 داخل تيليغرام.");
  }

  const options = {
    method: body === undefined ? "GET" : "POST",
    headers: {
      "X-Telegram-Init-Data": tg.initData
    }
  };

  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }

  const response = await fetch(path, options);
  const data = await response.json();

  if (!response.ok || data.error) {
    throw new Error(data.error || "حدث خطأ في الاتصال.");
  }
  return data;
}

async function loadBalance() {
  try {
    showMessage("جارٍ تحميل رصيد حسابك...");
    const data = await api("/api/me");

    balanceBox.textContent = Number(data.available).toLocaleString(
      "en-US", { maximumFractionDigits: 8 }
    ) + " EN96";

    reservedBox.textContent =
      "الرصيد المحجوز: " + Number(data.reserved).toLocaleString(
        "en-US", { maximumFractionDigits: 8 }
      ) + " EN96";

    if (data.first_name) {
      document.getElementById("welcome").textContent =
        "مرحبًا " + data.first_name + " في تطبيق EN96";
    }
    showMessage("تم تحميل رصيد حسابك المحفوظ بنجاح.");
  } catch (error) {
    balanceBox.textContent = "غير متاح";
    showMessage(error.message);
  }
}

async function doMining() {
  const button = document.getElementById("miningButton");
  button.disabled = true;
  try {
    showMessage("جارٍ تنفيذ طلب التعدين...");
    const data = await api("/api/mining", {});
    showMessage(data.message || "تم إرسال طلب التعدين إلى النظام.");
    await loadBalance();
  } catch (error) {
    showMessage(error.message);
  } finally {
    button.disabled = false;
  }
}

async function redeemGift() {
  const input = document.getElementById("giftCode");
  const code = input.value.trim();

  if (!code) {
    showMessage("أدخل كود الهدية أولًا.");
    return;
  }

  try {
    showMessage("جارٍ التحقق من كود الهدية...");
    const data = await api("/api/redeem-gift", {code});
    showMessage(data.message || "تم إرسال طلب استلام الهدية.");
    if (data.success) {
      input.value = "";
      await loadBalance();
    }
  } catch (error) {
    showMessage(error.message);
  }
}

if (tg && tg.initData) {
  loadBalance();
} else {
  balanceBox.textContent = "افتح تيليغرام";
  showMessage("افتح البوت واضغط زر فتح تطبيق EN96 لعرض رصيدك.");
}
</script>
</body>
</html>
"""


@app.get("/api/me")
def api_me():
    user, error = telegram_user()
    if error:
        return jsonify({"error": error}), 401

    try:
        data, error = get_balance(user["id"])
        if error:
            return jsonify({"error": error}), 404

        data["first_name"] = user["first_name"]
        return jsonify(data), 200
    except Exception:
        logger.exception("Could not load user balance")
        return jsonify({"error": "تعذر تحميل الرصيد. حاول لاحقًا."}), 500


@app.post("/api/mining")
def api_mining():
    user, error = telegram_user()
    if error:
        return jsonify({"error": error}), 401

    try:
        result = en96_bot.db.rpc(
            "en96_mining_action",
            {"p_telegram_id": user["id"]}
        ).execute()

        logger.info("Mining RPC completed for Telegram user %s", user["id"])
        return jsonify({
            "success": True,
            "message": "تم إرسال طلب التعدين. حدّث الرصيد للتحقق من النتيجة.",
            "result": result.data
        }), 200
    except Exception:
        logger.exception("Mining RPC failed")
        return jsonify({"error": "تعذر تنفيذ التعدين. حاول لاحقًا."}), 500


@app.post("/api/redeem-gift")
def api_redeem_gift():
    user, error = telegram_user()
    if error:
        return jsonify({"error": error}), 401

    body = request.get_json(silent=True) or {}
    code = body.get("code", "")

    if not isinstance(code, str) or not code.strip() or len(code) > 100:
        return jsonify({"error": "أدخل كود هدية صالحًا."}), 400

    try:
        result = en96_bot.db.rpc(
            "redeem_en96_video_gift",
            {
                "p_telegram_id": user["id"],
                "p_code": code.strip()
            }
        ).execute()

        logger.info("Gift RPC completed for Telegram user %s", user["id"])
        return jsonify({
            "success": True,
            "message": "تم إرسال الكود للتحقق. إذا لم تُقبل الهدية، راجع رسالة البوت.",
            "result": result.data
        }), 200
    except Exception:
        logger.exception("Gift redemption RPC failed")
        return jsonify({"error": "تعذر التحقق من الكود. حاول لاحقًا."}), 500


@app.get("/health")
def health():
    return jsonify({"status": "ok", "app": "EN96"}), 200


def run_bot():
    try:
        me = en96_bot.bot.get_me()
        logger.info("Telegram connected to bot username: @%s", me.username)
        en96_bot.bot.infinity_polling(skip_pending=True, timeout=30)
    except Exception:
        logger.exception("Telegram bot polling failed")


if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
