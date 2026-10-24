import os
import hmac
import json
import time
import hashlib
from datetime import datetime, timezone

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
    .timer-card {
      margin-top: 16px; padding: 16px;
      border: 1px solid #a78337; border-radius: 16px;
      background: linear-gradient(145deg, #151b22, #090d12);
    }
    .timer { font-size: 30px; font-weight: 800; color: #f5d681; direction: ltr; margin: 8px 0; }
    .progress { height: 9px; background: #273342; border-radius: 99px; overflow: hidden; margin-top: 12px; }
    .progress-fill { height: 100%; width: 0%; background: linear-gradient(90deg, #c18b22, #ffe7a0); transition: width .4s; }
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

    <div class="timer-card">
      <div class="muted" id="miningState">حالة التعدين: متوقف</div>
      <div class="timer" id="miningTimer">24:00:00</div>
      <div id="miningReward" class="muted">المكافأة التقديرية: 0.000000 EN96</div>
      <div class="progress"><div id="miningProgress" class="progress-fill"></div></div>
    </div>
    <button id="startMiningButton" onclick="startMining()">⛏️ بدء التعدين</button>
    <button id="claimMiningButton" class="secondary" onclick="claimMining()" hidden>🎁 استلام المكافأة</button>

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
const miningStateBox = document.getElementById("miningState");
const miningTimerBox = document.getElementById("miningTimer");
const miningRewardBox = document.getElementById("miningReward");
const miningProgressBox = document.getElementById("miningProgress");
const startMiningButton = document.getElementById("startMiningButton");
const claimMiningButton = document.getElementById("claimMiningButton");
let miningState = {status: "idle", remaining_seconds: 86400, elapsed_seconds: 0};
let timerInterval = null;

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
    await refreshMiningStatus();
  } catch (error) {
    balanceBox.textContent = "غير متاح";
    showMessage(error.message);
  }
}

function formatTime(totalSeconds) {
  const seconds = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(seconds / 3600).toString().padStart(2, "0");
  const m = Math.floor((seconds % 3600) / 60).toString().padStart(2, "0");
  const s = (seconds % 60).toString().padStart(2, "0");
  return `${h}:${m}:${s}`;
}

function renderMiningStatus() {
  const remaining = Math.max(0, miningState.remaining_seconds || 0);
  const elapsed = Math.max(0, miningState.elapsed_seconds || 0);
  const rate = 0.001;
  const reward = Math.min(86.4, elapsed * rate);
  miningTimerBox.textContent = formatTime(remaining);
  miningRewardBox.textContent = "المكافأة التقديرية: " + reward.toFixed(6) + " EN96";
  miningProgressBox.style.width = Math.min(100, (elapsed / 86400) * 100) + "%";
  startMiningButton.hidden = miningState.status === "active" || miningState.status === "ready_to_claim";
  claimMiningButton.hidden = miningState.status !== "ready_to_claim";

  if (miningState.status === "active") {
    miningStateBox.textContent = "⛏️ التعدين نشط — لا تغلق الجلسة، وقتك محفوظ";
  } else if (miningState.status === "ready_to_claim") {
    miningStateBox.textContent = "🎉 انتهت الجلسة! يمكنك استلام مكافأة 86.4 EN96";
    miningTimerBox.textContent = "00:00:00";
    miningRewardBox.textContent = "المكافأة المستحقة: 86.400000 EN96";
    miningProgressBox.style.width = "100%";
  } else {
    miningStateBox.textContent = "حالة التعدين: متوقف";
    miningTimerBox.textContent = "24:00:00";
    miningRewardBox.textContent = "المكافأة عند إكمال 24 ساعة: 86.400000 EN96";
    miningProgressBox.style.width = "0%";
  }
}

async function refreshMiningStatus() {
  try {
    miningState = await api("/api/mining/status");
    renderMiningStatus();
    if (timerInterval) clearInterval(timerInterval);
    if (miningState.status === "active") {
      timerInterval = setInterval(() => {
        miningState.remaining_seconds = Math.max(0, (miningState.remaining_seconds || 0) - 1);
        miningState.elapsed_seconds = Math.min(86400, (miningState.elapsed_seconds || 0) + 1);
        if (miningState.remaining_seconds <= 0) {
          miningState.status = "ready_to_claim";
          clearInterval(timerInterval);
          timerInterval = null;
        }
        renderMiningStatus();
      }, 1000);
    }
  } catch (error) {
    showMessage(error.message);
  }
}

async function startMining() {
  startMiningButton.disabled = true;
  try {
    showMessage("جارٍ بدء جلسة التعدين...");
    const data = await api("/api/mining/start", {});
    if (data.status === "started" || data.status === "active" || data.status === "ready_to_claim") {
      showMessage(data.message || "تم تحديث حالة التعدين.");
    } else {
      showMessage(data.message || "تعذر بدء التعدين: " + (data.status || "خطأ غير معروف"));
    }
    await refreshMiningStatus();
  } catch (error) {
    showMessage(error.message);
  } finally {
    startMiningButton.disabled = false;
  }
}

async function claimMining() {
  claimMiningButton.disabled = true;
  try {
    showMessage("جارٍ التحقق من انتهاء جلسة التعدين...");
    const data = await api("/api/mining/claim", {});
    if (data.status === "claimed") {
      showMessage("🎉 تمت إضافة " + Number(data.reward).toFixed(6) + " EN96 إلى رصيدك.");
      await loadBalance();
    } else if (data.status === "not_ready") {
      showMessage("لم تنتهِ الجلسة بعد. الوقت المتبقي: " + formatTime(data.remaining_seconds));
    } else {
      showMessage(data.message || "تعذر استلام المكافأة: " + (data.status || "خطأ غير معروف"));
    }
    await refreshMiningStatus();
  } catch (error) {
    showMessage(error.message);
  } finally {
    claimMiningButton.disabled = false;
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


@app.get("/api/mining/status")
def api_mining_status():
    user, error = telegram_user()
    if error:
        return jsonify({"error": error}), 401
    try:
        profile_result = (
            en96_bot.db.table("profiles")
            .select("id")
            .eq("telegram_id", str(user["id"]))
            .limit(1).execute()
        )
        profiles = profile_result.data or []
        if not profiles:
            return jsonify({"error": "لم يتم العثور على حسابك في profiles."}), 404
        user_id = profiles[0]["id"]
        session_result = (
            en96_bot.db.table("mining_sessions")
            .select("id,started_at,ended_at,status")
            .eq("user_id", user_id)
            .order("started_at", desc=True)
            .limit(1).execute()
        )
        sessions = session_result.data or []
        if not sessions:
            return jsonify({"status": "idle", "remaining_seconds": 86400, "elapsed_seconds": 0})
        session = sessions[0]
        started_raw = session.get("started_at")
        if session.get("status") == "active" and started_raw:
            started = datetime.fromisoformat(started_raw.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            elapsed = max(0, int((now - started).total_seconds()))
            remaining = max(0, 86400 - elapsed)
            if remaining == 0:
                return jsonify({"status": "ready_to_claim", "remaining_seconds": 0, "elapsed_seconds": 86400})
            return jsonify({"status": "active", "remaining_seconds": remaining, "elapsed_seconds": elapsed})
        return jsonify({"status": "idle", "remaining_seconds": 86400, "elapsed_seconds": 0})
    except Exception:
        logger.exception("Could not load mining status")
        return jsonify({"error": "تعذر تحميل حالة التعدين."}), 500


@app.post("/api/mining/start")
def api_mining_start():
    user, error = telegram_user()
    if error:
        return jsonify({"error": error}), 401
    try:
        result = en96_bot.db.rpc("en96_start_mining", {"p_telegram_id": user["id"]}).execute()
        data = result.data
        if isinstance(data, list) and data:
            data = data[0]
        if isinstance(data, str):
            try: data = json.loads(data)
            except (ValueError, TypeError): data = {}
        if not isinstance(data, dict): data = {}
        status = data.get("status", "unknown")
        messages = {
            "started": "⛏️ بدأ التعدين الافتراضي لمدة 24 ساعة.",
            "active": "⛏️ التعدين جارٍ بالفعل؛ تم تحميل الوقت المتبقي.",
            "ready_to_claim": "🎉 انتهت الجلسة. اضغط استلام المكافأة.",
            "profile_missing": "حسابك غير موجود في profiles.",
            "balance_missing": "سجل رصيدك غير موجود في balances."
        }
        logger.info("Mining start checked for Telegram user %s: %s", user["id"], status)
        return jsonify({**data, "message": messages.get(status, "حالة التعدين: " + status)}), 200
    except Exception:
        logger.exception("Mining start RPC failed")
        return jsonify({"error": "تعذر بدء التعدين. حاول لاحقًا."}), 500


@app.post("/api/mining/claim")
def api_mining_claim():
    user, error = telegram_user()
    if error:
        return jsonify({"error": error}), 401
    try:
        result = en96_bot.db.rpc("en96_claim_mining", {"p_telegram_id": user["id"]}).execute()
        data = result.data
        if isinstance(data, list) and data:
            data = data[0]
        if isinstance(data, str):
            try: data = json.loads(data)
            except (ValueError, TypeError): data = {}
        if not isinstance(data, dict): data = {}
        status = data.get("status", "unknown")
        if status == "claimed":
            data["message"] = "تم استلام المكافأة وحفظها في رصيدك. ابدأ جلسة جديدة عندما تكون مستعدًا."
        elif status == "not_ready":
            data["message"] = "لم تنتهِ جلسة التعدين بعد."
        elif status == "no_active_session":
            data["message"] = "لا توجد جلسة نشطة لاستلام مكافأتها."
        logger.info("Mining claim checked for Telegram user %s: %s", user["id"], status)
        return jsonify(data), 200
    except Exception:
        logger.exception("Mining claim RPC failed")
        return jsonify({"error": "تعذر استلام المكافأة. حاول لاحقًا."}), 500


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
