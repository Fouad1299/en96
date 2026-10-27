
import hashlib
import hmac
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from urllib.parse import parse_qsl

from flask import Flask, jsonify, request, send_file, send_from_directory

import bot as en96_bot
from en96_accounts import RegistrationError, ensure_profile

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("EN96")

BASE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DURATION = 86400
RATE = 0.001


@app.after_request
def secure_responses(response):
    if request.path == "/" or request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def telegram_user():
    init_data = request.headers.get("X-Telegram-Init-Data", "")

    if not BOT_TOKEN:
        return None, "إعداد BOT_TOKEN غير موجود على Render."

    if not init_data or len(init_data) > 10000:
        return None, "افتح التطبيق من داخل بوت EN96 على تيليغرام."

    try:
        fields = dict(parse_qsl(init_data, keep_blank_values=True))
        received_hash = fields.pop("hash", None)

        if not received_hash or len(received_hash) != 64:
            return None, "تعذّر التحقق من هوية تيليغرام."

        signed_string = "\n".join(
            f"{k}={v}" for k, v in sorted(fields.items())
        )

        key = hmac.new(
            b"WebAppData",
            BOT_TOKEN.encode(),
            hashlib.sha256
        ).digest()

        expected = hmac.new(
            key,
            signed_string.encode(),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(expected, received_hash):
            return None, "فشل التحقق من بيانات تيليغرام."

        issued = int(fields.get("auth_date", "0"))
        now = int(time.time())

        if not issued or issued > now + 60 or now - issued > 86400:
            return None, "انتهت صلاحية تسجيل الدخول. أعد فتح التطبيق من البوت."

        member = json.loads(fields.get("user", "{}"))
        tid = str(member.get("id", ""))

        if not tid.isdigit():
            return None, "لم يتم العثور على Telegram ID صالح."

        return {
            "id": tid,
            "first_name": str(member.get("first_name", ""))[:80]
        }, None

    except (ValueError, TypeError, json.JSONDecodeError):
        return None, "بيانات دخول تيليغرام غير صالحة."


def current_account():
    user, err = telegram_user()

    if err:
        return None, None, (jsonify({"error": err}), 401)

    try:
        profile = ensure_profile(en96_bot.db, user["id"])
        return user, profile, None

    except RegistrationError as exc:
        return None, None, (
            jsonify({"error": str(exc)}),
            409
        )


def wallet_for(profile):
    rows = (
        en96_bot.db.table("balances")
        .select("available,reserved")
        .eq("user_id", profile["id"])
        .limit(1)
        .execute()
        .data or []
    )

    if not rows:
        raise RuntimeError("Missing wallet row")

    return rows[0]


def parse_rpc(result):
    data = result.data

    if isinstance(data, list):
        data = data[0] if data else {}

    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (TypeError, ValueError):
            return {
                "status": "unknown",
                "message": data
            }

    return data if isinstance(data, dict) else {
        "status": "unknown"
    }


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

    server_ts = time.time()

    if not rows:
        return {
            "status": "not_started",
            "duration": DURATION,
            "rate": RATE,
            "server_time": server_ts
        }

    raw = rows[0]["started_at"]
    started = datetime.fromisoformat(
        raw.replace("Z", "+00:00")
    )

    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)

    start_ts = started.timestamp()
    elapsed = max(0, server_ts - start_ts)

    status = "ready" if elapsed >= DURATION else "active"

    return {
        "status": status,
        "started_at": raw,
        "started_epoch": start_ts,
        "elapsed_seconds": min(DURATION, int(elapsed)),
        "remaining_seconds": max(
            0, int(DURATION - elapsed)
        ),
        "duration": DURATION,
        "rate": RATE,
        "server_time": server_ts
    }


@app.get("/")
def homepage():
    return send_file(
        os.path.join(BASE, "index.html")
    )


@app.get("/assets/<path:filename>")
def asset(filename):
    return send_from_directory(
        os.path.join(BASE, "assets"),
        filename
    )


@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "app": "EN96 Ice Bear"
    })


@app.get("/api/me")
def me():
    user, profile, failure = current_account()

    if failure:
        return failure

    try:
        w = wallet_for(profile)

        return jsonify({
            "telegram_id": user["id"],
            "first_name": user["first_name"],
            "stellar_public_address":
                profile.get("stellar_public_address") or "",
            "available": str(w.get("available") or 0),
            "reserved": str(w.get("reserved") or 0)
        })

    except Exception:
        log.exception("Could not load wallet")

        return jsonify({
            "error": "تعذّر تحميل المحفظة الآن."
        }), 500


@app.get("/api/mining/status")
def status():
    user, profile, failure = current_account()

    if failure:
        return failure

    try:
        return jsonify(mining_state(profile))

    except Exception:
        log.exception("Could not read mining status")

        return jsonify({
            "error": "تعذّر الحصول على حالة التعدين."
        }), 500


@app.post("/api/mining")
def mining_action():
    user, profile, failure = current_account()

    if failure:
        return failure

    try:
        response = en96_bot.db.rpc(
            "en96_mining_action",
            {"p_telegram_id": user["id"]}
        ).execute()

        result = parse_rpc(response)
        outcome = result.get("status")

        if outcome not in (
            "started",
            "active",
            "rewarded_and_started"
        ):
            log.warning(
                "Unexpected mining outcome: %s",
                outcome
            )

            return jsonify({
                "error": "لم تؤكد قاعدة البيانات عملية التعدين.",
                "status": outcome
            }), 409

        return jsonify({
            "success": True,
            "result": result,
            "mining": mining_state(profile)
        })

    except Exception:
        log.exception("Could not perform mining RPC")

        return jsonify({
            "error": "تعذّر تنفيذ طلب التعدين."
        }), 500


@app.get("/api/videos")
def videos():
    user, profile, failure = current_account()

    if failure:
        return failure

    try:
        rows = (
            en96_bot.db.table("video_gift_codes")
            .select("video_url,description,reward")
            .eq("active", True)
            .order("created_at", desc=True)
            .limit(10)
            .execute()
            .data or []
        )

        return jsonify({"videos": rows})

    except Exception:
        log.exception("Could not load EN96 videos")

        return jsonify({
            "error": "تعذّر تحميل الفيديوهات."
        }), 500


@app.post("/api/redeem-gift")
def redeem():
    user, profile, failure = current_account()

    if failure:
        return failure

    payload = request.get_json(silent=True) or {}
    code = payload.get("code", "")

    if not isinstance(code, str) or not 1 <= len(code.strip()) <= 100:
        return jsonify({
            "error": "أدخل كود هدية صالحًا."
        }), 400

    try:
        result = parse_rpc(
            en96_bot.db.rpc(
                "redeem_en96_video_gift",
                {
                    "p_telegram_id": int(user["id"]),
                    "p_code": code.strip()
                }
            ).execute()
        )

        if result.get("ok") is True:
            return jsonify({
                "success": True,
                "reward": result.get("reward", 1)
            })

        reason = str(
            result.get("reason")
            or result.get("status")
            or result.get("message")
            or "unknown"
        )

        explanations = {
            "invalid_input": "أدخل كود هدية صحيحًا.",
            "profile_not_found": "تعذّر العثور على حسابك في قاعدة البيانات.",
            "invalid_or_inactive_code": "كود الهدية غير صالح أو غير مفعّل.",
            "already_claimed": "لقد استعملت هذا الكود من قبل.",
            "cooldown_2_hours": "يمكنك استلام هدية جديدة بعد مرور ساعتين.",
            "balance_not_found": "تعذّر العثور على رصيدك في قاعدة البيانات."
        }

        return jsonify({
            "success": False,
            "error": explanations.get(
                reason,
                "لم تُقبل الهدية: " + reason
            )
        }), 400

    except Exception:
        log.exception("Gift redemption error")

        return jsonify({
            "error": "تعذّر استلام الهدية الآن."
        }), 500


@app.post("/api/profile/stellar")
def stellar_address():
    user, profile, failure = current_account()

    if failure:
        return failure

    data = request.get_json(silent=True) or {}
    address = data.get("address", "")

    if not isinstance(address, str):
        return jsonify({
            "error": "عنوان Stellar غير صالح."
        }), 400

    address = address.strip().upper()

    if address and (
        len(address) != 56
        or not address.startswith("G")
        or any(
            ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
            for ch in address
        )
    ):
        return jsonify({
            "error": "أدخل عنوان Stellar العام، الذي يبدأ بحرف G."
        }), 400

    try:
        (
            en96_bot.db.table("profiles")
            .update({
                "stellar_public_address": address or None
            })
            .eq("id", profile["id"])
            .execute()
        )

        return jsonify({"success": True})

    except Exception:
        log.exception("Could not save Stellar public address")

        return jsonify({
            "error": "تعذّر حفظ العنوان."
        }), 500


def run_bot():
    try:
        me = en96_bot.bot.get_me()

        log.info(
            "Telegram bot ready: @%s",
            me.username
        )

        en96_bot.bot.infinity_polling(
            skip_pending=True,
            timeout=30
        )

    except Exception:
        log.exception("Telegram polling failed")


if __name__ == "__main__":
    threading.Thread(
        target=run_bot,
        daemon=True
    ).start()

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "10000"))
    )
