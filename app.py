
import os
import time
import hmac
import json
import uuid
import hashlib
import logging
import threading
from datetime import datetime, timezone
from urllib.parse import parse_qsl

from flask import Flask, jsonify, request, send_from_directory
import bot as en96_bot

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("EN96")

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

DURATION = 24 * 60 * 60
RATE = 0.001
REGISTER_LOCK = threading.RLock()


@app.after_request
def no_cache(response):
    if request.path.startswith("/api/") or request.path == "/":
        response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


# Telegram login verification
def telegram_user():
    raw = request.headers.get("X-Telegram-Init-Data", "")

    if not BOT_TOKEN or not raw or len(raw) > 10000:
        return None, "افتح تطبيق EN96 من داخل بوت تيليغرام."

    try:
        fields = dict(parse_qsl(raw, keep_blank_values=True))
        given_hash = fields.pop("hash", "")

        check_text = "\n".join(
            f"{k}={v}" for k, v in sorted(fields.items())
        )

        secret = hmac.new(
            b"WebAppData",
            BOT_TOKEN.encode(),
            hashlib.sha256
        ).digest()

        expected = hmac.new(
            secret,
            check_text.encode(),
            hashlib.sha256
        ).hexdigest()

        if len(given_hash) != 64 or not hmac.compare_digest(
            given_hash, expected
        ):
            return None, "تعذر التحقق من هوية تيليغرام."

        auth_date = int(fields.get("auth_date", "0"))
        now = int(time.time())

        if (
            auth_date <= 0
            or auth_date > now + 60
            or now - auth_date > 86400
        ):
            return None, "انتهت صلاحية تسجيل الدخول. افتح التطبيق مجددًا."

        user = json.loads(fields.get("user", "{}"))
        telegram_id = str(user.get("id", ""))

        if not telegram_id.isdigit():
            return None, "Telegram ID غير صالح."

        return {
            "id": telegram_id,
            "first_name": str(user.get("first_name", ""))[:80]
        }, None

    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None, "بيانات تسجيل الدخول غير صالحة."


# Telegram account registration
def ensure_profile(telegram_id):
    db = en96_bot.db

    with REGISTER_LOCK:
        rows = (
            db.table("profiles")
            .select("id,telegram_id")
            .eq("telegram_id", telegram_id)
            .limit(1)
            .execute()
            .data or []
        )

        if rows:
            profile = rows[0]
        else:
            new_id = str(uuid.uuid4())

            try:
                inserted = (
                    db.table("profiles")
                    .insert({
                        "id": new_id,
                        "telegram_id": telegram_id
                    })
                    .execute()
                    .data or []
                )

                profile = inserted[0] if inserted else {
                    "id": new_id
                }

            except Exception:
                rows = (
                    db.table("profiles")
                    .select("id,telegram_id")
                    .eq("telegram_id", telegram_id)
                    .limit(1)
                    .execute()
                    .data or []
                )

                if not rows:
                    raise

                profile = rows[0]

        balances = (
            db.table("balances")
            .select("user_id")
            .eq("user_id", profile["id"])
            .limit(1)
            .execute()
            .data or []
        )

        if not balances:
            try:
                db.table("balances").insert({
                    "user_id": profile["id"],
                    "available": 0,
                    "reserved": 0
                }).execute()

            except Exception:
                balances = (
                    db.table("balances")
                    .select("user_id")
                    .eq("user_id", profile["id"])
                    .limit(1)
                    .execute()
                    .data or []
                )

                if not balances:
                    raise

        return profile


def current_account():
    user, error = telegram_user()

    if error:
        return None, None, (jsonify({"error": error}), 401)

    try:
        profile = ensure_profile(user["id"])
        return user, profile, None

    except Exception:
        log.exception("Telegram user registration failed")
        return None, None, (
            jsonify({"error": "تعذر تجهيز حساب تيليغرام."}),
            500
        )


def rpc_json(result):
    data = result.data

    if isinstance(data, list):
        data = data[0] if data else {}

    if isinstance(data, str):
        data = json.loads(data)

    return data if isinstance(data, dict) else {}


# Mining session state from Supabase
def mining_state(profile):
    rows = (
        en96_bot.db.table("mining_sessions")
        .select("started_at")
        .eq("user_id", profile["id"])
        .order("started_at", desc=True)
        .limit(1)
        .execute()
        .data or []
    )

    if not rows:
        return {
            "status": "not_started",
            "elapsed_seconds": 0,
            "remaining_seconds": DURATION,
            "rate": RATE
        }

    value = rows[0]["started_at"]
    started = datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )

    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)

    elapsed = max(0, time.time() - started.timestamp())
    done = min(DURATION, int(elapsed))

    return {
        "status": "ready" if elapsed >= DURATION else "active",
        "started_at": value,
        "elapsed_seconds": done,
        "remaining_seconds": max(0, DURATION - done),
        "rate": RATE
    }


# EN96 website
@app.get("/")
def home():
    return send_from_directory(BASE_DIR, "index.html")


@app.get("/assets/<path:name>")
def assets(name):
    return send_from_directory(
        os.path.join(BASE_DIR, "assets"),
        name
    )


@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "app": "EN96 Ice Bear"
    })


# Wallet
@app.get("/api/me")
def me():
    user, profile, failure = current_account()

    if failure:
        return failure

    try:
        rows = (
            en96_bot.db.table("balances")
            .select("available,reserved")
            .eq("user_id", profile["id"])
            .limit(1)
            .execute()
            .data or []
        )

        if not rows:
            return jsonify({
                "error": "حساب الرصيد غير موجود."
            }), 500

        balance = rows[0]

        return jsonify({
            "telegram_id": user["id"],
            "first_name": user["first_name"],
            "available": str(balance.get("available") or 0),
            "reserved": str(balance.get("reserved") or 0)
        })

    except Exception:
        log.exception("Wallet load failed")
        return jsonify({
            "error": "تعذر تحميل الرصيد."
        }), 500


# Mining status
@app.get("/api/mining/status")
def status():
    user, profile, failure = current_account()

    if failure:
        return failure

    try:
        return jsonify(mining_state(profile))

    except Exception:
        log.exception("Mining status failed")
        return jsonify({
            "error": "تعذر جلب حالة التعدين."
        }), 500


# Mining: Supabase controls real credited rewards
@app.post("/api/mining")
def mine():
    user, profile, failure = current_account()

    if failure:
        return failure

    try:
        data = rpc_json(
            en96_bot.db.rpc(
                "en96_mining_action",
                {"p_telegram_id": user["id"]}
            ).execute()
        )

        if data.get("status") not in (
            "started",
            "active",
            "rewarded_and_started"
        ):
            return jsonify({
                "error": "تعذر اعتماد عملية التعدين.",
                "status": data.get("status")
            }), 409

        return jsonify({
            "success": True,
            "result": data,
            "mining": mining_state(profile)
        })

    except Exception:
        log.exception("Mining action failed")
        return jsonify({
            "error": "تعذر تنفيذ التعدين."
        }), 500


# Video gifts
@app.get("/api/videos")
def videos():
    user, profile, failure = current_account()

    if failure:
        return failure

    try:
        rows = (
            en96_bot.db.table("video_gift_codes")
            .select("description,video_url,reward")
            .eq("active", True)
            .order("created_at", desc=True)
            .limit(10)
            .execute()
            .data or []
        )

        return jsonify({"videos": rows})

    except Exception:
        log.exception("Videos failed")
        return jsonify({
            "error": "تعذر تحميل الفيديوهات."
        }), 500


# Redeem gift code
@app.post("/api/redeem-gift")
def redeem_gift():
    user, profile, failure = current_account()

    if failure:
        return failure

    payload = request.get_json(silent=True) or {}
    code = payload.get("code", "") if isinstance(payload, dict) else ""

    if not isinstance(code, str) or not (
        1 <= len(code.strip()) <= 100
    ):
        return jsonify({
            "error": "أدخل كود الهدية الصحيح."
        }), 400

    try:
        data = rpc_json(
            en96_bot.db.rpc(
                "redeem_en96_video_gift",
                {
                    "p_telegram_id": int(user["id"]),
                    "p_code": code.strip()
                }
            ).execute()
        )

        if data.get("ok") is True:
            return jsonify({
                "success": True,
                "reward": data.get("reward", 1)
            })

        messages = {
            "invalid_input": "الكود غير صحيح.",
            "profile_not_found": "حسابك غير موجود.",
            "invalid_or_inactive_code": "الكود غير موجود أو غير مفعل.",
            "already_claimed": "لقد استخدمت هذا الكود من قبل.",
            "cooldown_2_hours": "يمكن استلام هدية جديدة بعد ساعتين.",
            "balance_not_found": "رصيد حسابك غير موجود."
        }

        reason = (
            data.get("reason")
            or data.get("status")
            or "unknown"
        )

        return jsonify({
            "error": messages.get(
                reason,
                "لم تقبل الهدية."
            )
        }), 400

    except Exception:
        log.exception("Gift redemption failed")
        return jsonify({
            "error": "تعذر استلام الهدية الآن."
        }), 500


# Start Telegram bot
def run_bot():
    try:
        info = en96_bot.bot.get_me()
        log.info(
            "Telegram bot connected: @%s",
            info.username
        )

        en96_bot.bot.infinity_polling(
            skip_pending=True,
            timeout=30
        )

    except Exception:
        log.exception("Telegram polling stopped")


# Start Render server
if __name__ == "__main__":
    threading.Thread(
        target=run_bot,
        daemon=True
    ).start()

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "10000"))
    )
