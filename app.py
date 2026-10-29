import hashlib
import hmac
import json
import logging
import os
import re
import threading
import time

from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl
from uuid import UUID

from flask import (
    Flask,
    Response,
    abort,
    jsonify,
    request,
    send_from_directory,
)

import bot as en96_bot
from en96_accounts import (
    RegistrationError,
    ensure_profile,
)


# =====================================
# EN96 ICE BEAR KINGDOM
# =====================================

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("EN96")

app = Flask(__name__)
BASE = Path(__file__).resolve().parent

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

DURATION = 24 * 60 * 60
RATE = 0.001

TAP_LIMIT = 3650
TAP_DAILY_REWARD = 15


# =====================================
# IMAGES
# =====================================

IMAGE_ALIASES = {
    "en96-welcome.jpg": [
        "en96-welcome.jpg",
        "en96-welcome .jpg",
        "en96-welcome (1).jpg",
        "en96-welcome (2).jpg",
    ],
    "en96-bear-face.webp": [
        "en96-bear-face.webp",
        "en96-bear-face .webp",
        "en96-bear-face (1).webp",
        "en96-bear-face (2).webp",
    ],
    "en96-coin.webp": [
        "en96-coin.webp",
        "en96-coin .webp",
        "en96-coin (1).webp",
        "en96-coin (2).webp",
    ],
}

RAW_IMAGE_BASE = (
    "https://raw.githubusercontent.com/"
    "Fouad1299/en96/main/"
)


# =====================================
# SECURITY HEADERS
# =====================================

@app.after_request
def no_cache(response):
    if (
        request.path == "/"
        or request.path.startswith("/api/")
    ):
        response.headers["Cache-Control"] = (
            "no-store, max-age=0"
        )

    response.headers[
        "X-Content-Type-Options"
    ] = "nosniff"

    return response


@app.errorhandler(404)
def not_found(error):
    if request.path.startswith("/api/"):
        return jsonify(
            error=(
                "مسار API غير موجود. "
                "تحقق من نشر app.py الجديد."
            )
        ), 404

    return error


@app.errorhandler(405)
def wrong_method(error):
    if request.path.startswith("/api/"):
        return jsonify(
            error="طريقة الطلب غير صحيحة."
        ), 405

    return error


# =====================================
# TELEGRAM AUTHENTICATION
# =====================================

def telegram_user():
    init_data = request.headers.get(
        "X-Telegram-Init-Data", ""
    )

    if not BOT_TOKEN:
        return None, (
            "BOT_TOKEN غير موجود في Render."
        )

    if not init_data or len(init_data) > 10000:
        return None, (
            "افتح التطبيق من داخل بوت EN96."
        )

    try:
        fields = dict(
            parse_qsl(
                init_data,
                keep_blank_values=True
            )
        )

        received_hash = fields.pop(
            "hash", ""
        )

        if not re.fullmatch(
            r"[0-9a-fA-F]{64}",
            received_hash
        ):
            return None, (
                "توقيع تيليغرام غير صالح."
            )

        check_string = "\n".join(
            f"{key}={value}"
            for key, value in sorted(
                fields.items()
            )
        )

        secret_key = hmac.new(
            b"WebAppData",
            BOT_TOKEN.encode(),
            hashlib.sha256
        ).digest()

        expected_hash = hmac.new(
            secret_key,
            check_string.encode(),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(
            expected_hash,
            received_hash.lower()
        ):
            return None, (
                "فشل التحقق من هوية تيليغرام."
            )

        now = int(time.time())

        auth_date = int(
            fields.get("auth_date", "0")
        )

        if (
            auth_date < now - 86400
            or auth_date > now + 60
        ):
            return None, (
                "انتهت صلاحية الجلسة. "
                "افتح التطبيق من البوت مجددًا."
            )

        user = json.loads(
            fields.get("user", "{}")
        )

        telegram_id = str(
            user.get("id", "")
        )

        if not telegram_id.isdigit():
            return None, (
                "معرّف تيليغرام غير صالح."
            )

        return {
            "id": telegram_id,
            "first_name": str(
                user.get("first_name", "")
            )[:80],
        }, None

    except (
        TypeError,
        ValueError,
        json.JSONDecodeError
    ):
        return None, (
            "بيانات تسجيل الدخول غير صالحة."
        )


def current_account():
    user, error = telegram_user()

    if error:
        return None, None, (
            jsonify(error=error), 401
        )

    try:
        profile = ensure_profile(
            en96_bot.db,
            user["id"]
        )

        return user, profile, None

    except RegistrationError as exc:
        return None, None, (
            jsonify(error=str(exc)), 409
        )

    except Exception:
        log.exception(
            "EN96 profile lookup failed"
        )

        return None, None, (
            jsonify(
                error="تعذّر تحميل حساب EN96."
            ), 500
        )


# =====================================
# WALLET DATABASE HELPERS
# =====================================

def wallet_for(profile):
    rows = (
        en96_bot.db
        .table("balances")
        .select("available,reserved")
        .eq("user_id", profile["id"])
        .limit(1)
        .execute()
        .data or []
    )

    if not rows:
        raise RuntimeError(
            "Missing balance row"
        )

    return rows[0]


def rpc_value(response):
    data = response.data

    if isinstance(data, list):
        data = (
            data[0]
            if data
            else {}
        )

    if isinstance(data, str):
        try:
            data = json.loads(data)
        except ValueError:
            data = {
                "message": data
            }

    return (
        data
        if isinstance(data, dict)
        else {}
    )


# =====================================
# MINING SYSTEM
# =====================================

def mining_state(profile):
    rows = (
        en96_bot.db
        .table("mining_sessions")
        .select("started_at")
        .eq("user_id", profile["id"])
        .order("started_at", desc=True)
        .limit(1)
        .execute()
        .data or []
    )

    now = time.time()

    if not rows:
        return {
            "status": "not_started",
            "elapsed_seconds": 0,
            "remaining_seconds": DURATION,
            "duration": DURATION,
            "rate": RATE,
            "server_time": now,
        }

    started_str = rows[0]["started_at"]

    started = datetime.fromisoformat(
        started_str.replace(
            "Z", "+00:00"
        )
    )

    if started.tzinfo is None:
        started = started.replace(
            tzinfo=timezone.utc
        )

    elapsed = min(
        DURATION,
        max(
            0,
            now - started.timestamp()
        )
    )

    return {
        "status": (
            "ready"
            if elapsed >= DURATION
            else "active"
        ),
        "started_at": started_str,
        "elapsed_seconds": int(elapsed),
        "remaining_seconds": max(
            0,
            int(DURATION - elapsed)
        ),
        "duration": DURATION,
        "rate": RATE,
        "server_time": now,
    }


# =====================================
# IMAGES AND WEBSITE
# =====================================

def find_image(filename):
    if filename not in IMAGE_ALIASES:
        return None

    for folder in (
        BASE / "assets",
        BASE
    ):
        for candidate in IMAGE_ALIASES[
            filename
        ]:
            if (
                folder / candidate
            ).is_file():
                return folder, candidate

    return None


@app.get("/")
def homepage():
    try:
        html = (
            BASE / "index.html"
        ).read_text(
            encoding="utf-8"
        )

    except OSError:
        return (
            "Missing index.html", 500
        )

    for name in IMAGE_ALIASES:
        html = html.replace(
            RAW_IMAGE_BASE + name,
            "/assets/" + name
        )

    return Response(
        html,
        mimetype="text/html"
    )


@app.get("/assets/<path:filename>")
def asset(filename):
    found = find_image(filename)

    if not found:
        abort(404)

    folder, name = found

    return send_from_directory(
        str(folder),
        name
    )


@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "app": "EN96 Ice Bear",
        "images": {
            name: bool(
                find_image(name)
            )
            for name in IMAGE_ALIASES
        },
    })


# =====================================
# USER ACCOUNT AND BALANCE
# =====================================

@app.get("/api/me")
def me():
    user, profile, failure = (
        current_account()
    )

    if failure:
        return failure

    try:
        wallet = wallet_for(profile)

        return jsonify({
            "telegram_id": user["id"],
            "first_name": user[
                "first_name"
            ],
            "stellar_public_address": (
                profile.get(
                    "stellar_public_address"
                ) or ""
            ),
            "available": str(
                wallet.get("available") or 0
            ),
            "reserved": str(
                wallet.get("reserved") or 0
            ),
        })

    except Exception:
        log.exception(
            "EN96 wallet load failed"
        )

        return jsonify(
            error=(
                "تعذّر تحميل رصيد المحفظة."
            )
        ), 500


# =====================================
# MINING API
# =====================================

@app.get("/api/mining/status")
def mining_status():
    user, profile, failure = (
        current_account()
    )

    if failure:
        return failure

    try:
        return jsonify(
            mining_state(profile)
        )

    except Exception:
        log.exception(
            "EN96 mining status failed"
        )

        return jsonify(
            error=(
                "تعذّر قراءة حالة التعدين."
            )
        ), 500


@app.post("/api/mining")
def mining_action():
    user, profile, failure = (
        current_account()
    )

    if failure:
        return failure

    try:
        result = rpc_value(
            en96_bot.db.rpc(
                "en96_mining_action",
                {
                    "p_telegram_id": user[
                        "id"
                    ]
                }
            ).execute()
        )

        if result.get(
            "status"
        ) not in (
            "started",
            "active",
            "rewarded_and_started"
        ):
            return jsonify(
                error=(
                    "لم تؤكد Supabase "
                    "عملية التعدين."
                ),
                result=result
            ), 409

        return jsonify(
            success=True,
            result=result,
            mining=mining_state(
                profile
            )
        )

    except Exception:
        log.exception(
            "EN96 mining action failed"
        )

        return jsonify(
            error=(
                "تعذّر تنفيذ التعدين."
            )
        ), 500


# =====================================
# VIDEO GIFTS
# =====================================

@app.get("/api/videos")
def videos():
    user, profile, failure = (
        current_account()
    )

    if failure:
        return failure

    try:
        rows = (
            en96_bot.db
            .table("video_gift_codes")
            .select(
                "video_url,description,reward"
            )
            .eq("active", True)
            .order(
                "created_at",
                desc=True
            )
            .limit(10)
            .execute()
            .data or []
        )

        return jsonify(
            videos=rows
        )

    except Exception:
        log.exception(
            "EN96 videos lookup failed"
        )

        return jsonify(
            error=(
                "تعذّر تحميل الفيديوهات."
            )
        ), 500


@app.post("/api/redeem-gift")
def redeem_gift():
    user, profile, failure = (
        current_account()
    )

    if failure:
        return failure

    payload = request.get_json(
        silent=True
    )

    if (
        not isinstance(payload, dict)
        or not isinstance(
            payload.get("code"),
            str
        )
    ):
        return jsonify(
            error="أدخل كود الهدية."
        ), 400

    code = payload[
        "code"
    ].strip()

    if not 1 <= len(code) <= 100:
        return jsonify(
            error="كود الهدية غير صالح."
        ), 400

    try:
        result = rpc_value(
            en96_bot.db.rpc(
                "redeem_en96_video_gift",
                {
                    "p_telegram_id": int(
                        user["id"]
                    ),
                    "p_code": code,
                }
            ).execute()
        )

        if result.get("ok") is True:
            return jsonify(
                success=True,
                reward=result.get(
                    "reward", 1
                )
            )

        reasons = {
            "invalid_input":
                "كود غير صالح.",

            "profile_not_found":
                "الحساب غير موجود.",

            "invalid_or_inactive_code":
                "الكود غير صالح أو غير مفعّل.",

            "already_claimed":
                "استُخدم هذا الكود سابقًا.",

            "cooldown_2_hours":
                "يمكنك استلام هدية بعد مرور ساعتين.",

            "balance_not_found":
                "رصيد حسابك غير موجود.",
        }

        reason = str(
            result.get("reason")
            or result.get("status")
            or "unknown"
        )

        return jsonify(
            success=False,
            error=reasons.get(
                reason,
                "لم تُقبل الهدية: " + reason
            )
        ), 400

    except Exception:
        log.exception(
            "EN96 gift claim failed"
        )

        return jsonify(
            error=(
                "تعذّر استلام الهدية."
            )
        ), 500


# =====================================
# STELLAR PUBLIC WALLET ADDRESS
# =====================================

@app.post("/api/profile/stellar")
def save_stellar_address():
    user, profile, failure = (
        current_account()
    )

    if failure:
        return failure

    payload = request.get_json(
        silent=True
    )

    if (
        not isinstance(payload, dict)
        or not isinstance(
            payload.get("address"),
            str
        )
    ):
        return jsonify(
            error=(
                "أدخل عنوان Stellar العام."
            )
        ), 400

    address = (
        payload["address"]
        .strip()
        .upper()
    )

    if not re.fullmatch(
        r"G[A-Z2-7]{55}",
        address
    ):
        return jsonify(
            error=(
                "عنوان Stellar العام "
                "يجب أن يبدأ بـ G "
                "ويتكوّن من 56 حرفًا."
            )
        ), 400

    try:
        en96_bot.db.table(
            "profiles"
        ).update({
            "stellar_public_address": (
                address
            )
        }).eq(
            "id",
            profile["id"]
        ).execute()

        rows = (
            en96_bot.db
            .table("profiles")
            .select(
                "stellar_public_address"
            )
            .eq(
                "id",
                profile["id"]
            )
            .limit(1)
            .execute()
            .data or []
        )

        if (
            not rows
            or rows[0].get(
                "stellar_public_address"
            ) != address
        ):
            return jsonify(
                error=(
                    "لم يؤكّد الخادم "
                    "حفظ العنوان في Supabase."
                )
            ), 500

        return jsonify(
            success=True,
            stellar_public_address=address
        )

    except Exception:
        log.exception(
            "EN96 Stellar save failed"
        )

        return jsonify(
            error=(
                "تعذّر حفظ عنوان Stellar "
                "في Supabase."
            )
        ), 500


# =====================================
# TAP TO EARN STATUS
# =====================================

@app.get("/api/tap/status")
def tap_status():
    user, profile, failure = (
        current_account()
    )

    if failure:
        return failure

    try:
        rows = (
            en96_bot.db
            .table("en96_tap_cycles")
            .select(
                "period_start,taps,earned"
            )
            .eq(
                "user_id",
                profile["id"]
            )
            .limit(1)
            .execute()
            .data or []
        )

        taps = 0
        earned = "0"
        reset_at = None

        if rows:
            started = (
                datetime.fromisoformat(
                    rows[0]["period_start"]
                    .replace(
                        "Z", "+00:00"
                    )
                )
            )

            if started.tzinfo is None:
                started = started.replace(
                    tzinfo=timezone.utc
                )

            end_time = (
                started.timestamp()
                + DURATION
            )

            if time.time() < end_time:
                taps = int(
                    rows[0].get("taps") or 0
                )

                earned = str(
                    rows[0].get("earned") or 0
                )

                reset_at = (
                    datetime.fromtimestamp(
                        end_time,
                        tz=timezone.utc
                    ).isoformat()
                )

        wallet = wallet_for(profile)

        return jsonify({
            "status": (
                "limit_reached"
                if taps >= TAP_LIMIT
                else "ready"
            ),
            "taps": taps,
            "remaining": max(
                0,
                TAP_LIMIT - taps
            ),
            "daily_taps": TAP_LIMIT,
            "earned": earned,
            "daily_reward": str(
                TAP_DAILY_REWARD
            ),
            "reset_at": reset_at,
            "available": str(
                wallet.get("available") or 0
            ),
        })

    except Exception:
        log.exception(
            "EN96 tap status failed"
        )

        return jsonify(
            error=(
                "تعذّر تحميل عداد النقر."
            )
        ), 500


# =====================================
# TAP TO EARN ACTION
# =====================================

@app.post("/api/tap")
def tap_action():
    user, profile, failure = (
        current_account()
    )

    if failure:
        return failure

    payload = request.get_json(
        silent=True
    )

    if not isinstance(payload, dict):
        return jsonify(
            error=(
                "بيانات النقرة غير صالحة."
            )
        ), 400

    raw_id = payload.get(
        "request_id"
    )

    if not isinstance(
        raw_id,
        str
    ):
        return jsonify(
            error=(
                "معرّف النقرة غير صالح."
            )
        ), 400

    try:
        request_id = str(
            UUID(raw_id)
        )

    except (
        ValueError,
        AttributeError
    ):
        return jsonify(
            error=(
                "معرّف النقرة غير صالح."
            )
        ), 400

    try:
        result = rpc_value(
            en96_bot.db.rpc(
                "en96_tap_action",
                {
                    "p_telegram_id":
                        user["id"],

                    "p_request_id":
                        request_id,
                }
            ).execute()
        )

        state = result.get(
            "status"
        )

        if state in (
            "ok",
            "duplicate"
        ):
            try:
                wallet = wallet_for(
                    profile
                )

                result["available"] = str(
                    wallet.get(
                        "available"
                    ) or 0
                )

            except Exception:
                log.warning(
                    "Tap accepted but wallet "
                    "refresh failed"
                )

            return jsonify(result)

        if state == "too_fast":
            return jsonify(
                **result,
                error=(
                    "النقر سريع جدًا. "
                    "حاول مجددًا."
                )
            ), 429

        if state == "limit_reached":
            return jsonify(
                **result,
                error=(
                    "اكتملت 3650 نقرة "
                    "لهذه الدورة."
                )
            ), 429

        return jsonify(
            status=state,
            error=(
                "لم تؤكد قاعدة البيانات النقرة."
            )
        ), 409

    except Exception:
        log.exception(
            "EN96 tap action failed"
        )

        return jsonify(
            error=(
                "تعذّر تسجيل النقرة الآن."
            )
        ), 500


# =====================================
# OFFICIAL EN96 STELLAR TOML
# =====================================

@app.get("/.well-known/stellar.toml")
def stellar_toml():
    toml_path = (
        BASE
        / ".well-known"
        / "stellar.toml"
    )

    if not toml_path.is_file():
        return Response(
            "stellar.toml not found",
            status=404,
            content_type=(
                "text/plain; charset=utf-8"
            )
        )

    response = Response(
        toml_path.read_text(
            encoding="utf-8"
        ),
        content_type=(
            "text/plain; charset=utf-8"
        )
    )

    response.headers[
        "Access-Control-Allow-Origin"
    ] = "*"

    response.headers[
        "Cache-Control"
    ] = "public, max-age=300"

    return response


# =====================================
# TELEGRAM BOT
# =====================================

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
        log.exception(
            "EN96 Telegram polling failed"
        )


# =====================================
# START SERVER
# =====================================

if __name__ == "__main__":
    threading.Thread(
        target=run_bot,
        daemon=True
    ).start()

    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                "10000"
            )
        )
    )

