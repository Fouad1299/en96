
import os
import re
import json
import time
import logging
import threading
from decimal import Decimal, InvalidOperation
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

import telebot
from telebot.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
)
from supabase import create_client
from en96_accounts import ensure_profile


# ======================================
# EN96 ICE BEAR KINGDOM
# TELEGRAM BOT - WITHDRAWAL EDITION
# ======================================

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("EN96")

BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = (
    os.getenv("SUPABASE_SECRET_KEY")
    or os.getenv("SUPABASE_KEY")
)

ADMIN_ID = str(
    os.getenv("ADMIN_TELEGRAM_ID", "8721009110")
)

APP_URL = os.getenv(
    "APP_URL",
    "https://en96.onrender.com"
)

ROYAL_APP_URL = (
    "https://fouad1299.github.io/"
    "en96/en96-royal.html"
)

BOT_USERNAME = "EN96_IceDragon_2026_Bot"

YOUTUBE_URL = (
    "https://www.youtube.com/"
    "@EN96_Gold_Miner_bo"
)

TIKTOK_URL = (
    "https://www.tiktok.com/@en96mining"
)

LOBSTR_URL = "https://lobstr.co/"

HORIZON_URL = "https://horizon.stellar.org"

EN96_ISSUER = (
    "GCUGIICUGBFC3KBPIFYAMPNA7OVJHGY"
    "277TNYTZUSG7EVVUCVACH3OGB"
)

MINING_RATE = Decimal("0.001")
MINING_DURATION = 86400
MIN_WITHDRAWAL = Decimal("500")

# Keep this False until the withdrawal
# workflow has been safely tested.
WITHDRAWALS_ENABLED = (
    os.getenv("EN96_WITHDRAWALS_ENABLED", "false")
    .lower() == "true"
)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN missing")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Supabase configuration missing")

bot = telebot.TeleBot(
    BOT_TOKEN,
    threaded=True,
    num_threads=4
)

db = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)

MINING_COUNTERS = {}
MINING_LOCK = threading.Lock()

USER_STATES = {}
STATE_LOCK = threading.RLock()

WITHDRAW_LOCKS = {}
WITHDRAW_LOCKS_GUARD = threading.Lock()


# ======================================
# GENERAL HELPERS
# ======================================

def is_admin(user_id):
    return str(user_id) == ADMIN_ID


def is_private(message):
    return (
        message.chat.type == "private"
        and str(message.chat.id)
        == str(message.from_user.id)
    )


def rpc_data(result):
    data = result.data

    if isinstance(data, list):
        data = data[0] if data else {}

    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            data = {"message": data}

    return data or {}


def en96_number(value):
    try:
        number = Decimal(str(value or "0"))
        return f"{number:,.7f}"
    except (ValueError, TypeError, InvalidOperation):
        return "0.0000000"


def valid_address(address):
    return bool(
        isinstance(address, str)
        and re.fullmatch(
            r"G[A-Z2-7]{55}",
            address.strip().upper()
        )
    )


def valid_amount(value):
    try:
        amount = Decimal(str(value))

        if not amount.is_finite():
            return None

        if amount < MIN_WITHDRAWAL:
            return None

        if amount > Decimal("1000000000000"):
            return None

        if amount != amount.quantize(
            Decimal("0.0000001")
        ):
            return None

        return amount

    except (InvalidOperation, ValueError):
        return None


def set_state(uid, action, **kwargs):
    with STATE_LOCK:
        USER_STATES[str(uid)] = {
            "action": action,
            **kwargs
        }


def get_state(uid):
    with STATE_LOCK:
        return dict(
            USER_STATES.get(str(uid), {})
        )


def clear_state(uid):
    with STATE_LOCK:
        USER_STATES.pop(str(uid), None)


def user_withdraw_lock(uid):
    with WITHDRAW_LOCKS_GUARD:
        key = str(uid)

        if key not in WITHDRAW_LOCKS:
            WITHDRAW_LOCKS[key] = threading.Lock()

        return WITHDRAW_LOCKS[key]


def profile_for(uid):
    rows = (
        db.table("profiles")
        .select(
            "id,telegram_id,stellar_public_address"
        )
        .eq("telegram_id", str(uid))
        .limit(1)
        .execute()
        .data or []
    )

    return rows[0] if rows else None


def balance_for(uid):
    profile = profile_for(uid)

    if not profile:
        return None

    rows = (
        db.table("balances")
        .select("available,reserved")
        .eq("user_id", profile["id"])
        .limit(1)
        .execute()
        .data or []
    )

    return rows[0] if rows else None


def register_member(uid):
    try:
        ensure_profile(db, uid)
        return True
    except Exception:
        log.exception("Member registration error")
        return False


def stellar_account(address):
    url = (
        HORIZON_URL
        + "/accounts/"
        + address
    )

    request = Request(
        url,
        headers={"Accept": "application/json"}
    )

    try:
        with urlopen(request, timeout=12) as response:
            return json.loads(
                response.read().decode("utf-8")
            )
    except HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def stellar_trustline(address):
    if not valid_address(address):
        return False, "invalid_address", None

    account = stellar_account(address)

    if not account:
        return False, "account_not_found", None

    for item in account.get("balances", []):
        if (
            item.get("asset_code") == "EN96"
            and item.get("asset_issuer")
            == EN96_ISSUER
        ):
            return True, "ok", item

    return False, "trustline_missing", None


# ======================================
# MAIN MENU
# ======================================

def menu(uid=None):
    kb = ReplyKeyboardMarkup(
        resize_keyboard=True
    )

    kb.row(
        KeyboardButton("⛏️ بدء التعدين"),
        KeyboardButton("💰 محفظتي")
    )

    kb.row(
        KeyboardButton("💸 سحب EN96"),
        KeyboardButton("🔗 محفظة Stellar")
    )

    kb.row(
        KeyboardButton("⚡ ترقية المنجم"),
        KeyboardButton("🏆 المكافآت")
    )

    kb.row(
        KeyboardButton("📺 مشاهدة الفيديوهات"),
        KeyboardButton("🎁 استلام الهدية")
    )

    kb.row(
        KeyboardButton("🐻 أعضاء القبيلة"),
        KeyboardButton("ℹ️ معلومات EN96")
    )

    kb.row(
        KeyboardButton("🎵 TikTok EN96"),
        KeyboardButton("▶️ YouTube EN96")
    )

    kb.row(
        KeyboardButton("🌐 فتح تطبيق EN96")
    )

    if uid is not None and is_admin(uid):
        kb.row(
            KeyboardButton("🛠️ إدارة الهدايا"),
            KeyboardButton("⭐ رصيد Stars للإدارة")
        )

        kb.row(
            KeyboardButton("👑 إدارة السحوبات")
        )

    return kb


def admin_menu():
    kb = ReplyKeyboardMarkup(
        resize_keyboard=True
    )

    kb.row(
        KeyboardButton("➕ إنشاء كود هدية"),
        KeyboardButton("📋 أكواد الهدايا")
    )

    kb.row(
        KeyboardButton("⛔ تعطيل كود"),
        KeyboardButton("✅ تفعيل كود")
    )

    kb.add(
        KeyboardButton("🔙 القائمة الرئيسية")
    )

    return kb


def send_menu(chat_id, uid=None):
    bot.send_message(
        chat_id,
        "🐻‍❄️👑 مرحبًا بك في مملكة EN96!",
        reply_markup=menu(uid)
    )


# ======================================
# WEB APP
# ======================================

def app_button(chat_id):
    kb = InlineKeyboardMarkup()

    kb.add(
        InlineKeyboardButton(
            "👑 افتح مملكة EN96",
            web_app=WebAppInfo(
                url=ROYAL_APP_URL
            )
        )
    )

    bot.send_message(
        chat_id,
        "🐻‍❄️ EN96 Ice Bear Kingdom\n\n"
        "⛏️ التعدين الافتراضي\n"
        "💰 المحفظة\n"
        "🎁 الهدايا والقبيلة\n"
        "👑 الواجهة الملكية\n\n"
        "اضغط لفتح التطبيق.\n\n"
        "⚠️ النقر التجريبي في الواجهة "
        "لا يضيف رصيدًا.",
        reply_markup=kb
    )


# ======================================
# EN96 WALLET
# ======================================

def wallet(chat_id, uid):
    try:
        profile = profile_for(uid)
        balance = balance_for(uid)

        if not profile or not balance:
            bot.send_message(
                chat_id,
                "⚠️ لم نجد حسابك أو رصيدك.\n"
                "أرسل /start أولًا."
            )
            return

        address = (
            profile.get("stellar_public_address")
            or "غير مربوط"
        )

        kb = InlineKeyboardMarkup()

        kb.row(
            InlineKeyboardButton(
                "💸 السحب",
                callback_data="withdraw_start"
            ),
            InlineKeyboardButton(
                "🔗 محفظة G",
                callback_data="stellar_menu"
            )
        )

        kb.add(
            InlineKeyboardButton(
                "🔄 تحديث المحفظة",
                callback_data="wallet_refresh"
            )
        )

        bot.send_message(
            chat_id,
            "🐻‍❄️👑 محفظة EN96\n"
            "━━━━━━━━━━━━━━\n\n"
            "💎 الرصيد المتاح:\n"
            f"{en96_number(balance.get('available'))}"
            " EN96\n\n"
            "🔒 الرصيد المحجوز:\n"
            f"{en96_number(balance.get('reserved'))}"
            " EN96\n\n"
            "🌐 عنوان Stellar:\n"
            f"{address}\n\n"
            "💸 الحد الأدنى للسحب: 500 EN96\n"
            "⏳ مراجعة السحوبات يدوية.\n\n"
            "⚠️ الرصيد داخل EN96 لا يعني "
            "أن العملات وصلت بالفعل إلى Stellar.",
            reply_markup=kb
        )

    except Exception:
        log.exception("Wallet loading error")
        bot.send_message(
            chat_id,
            "تعذر تحميل المحفظة."
        )


# ======================================
# STELLAR WALLET
# ======================================

def stellar_menu(chat_id, uid):
    try:
        profile = profile_for(uid)

        address = (
            profile.get("stellar_public_address")
            if profile else None
        )

        kb = InlineKeyboardMarkup()

        kb.add(
            InlineKeyboardButton(
                "🪙 إنشاء محفظة LOBSTR",
                url=LOBSTR_URL
            )
        )

        kb.add(
            InlineKeyboardButton(
                "🔗 إدخال عنوان G",
                callback_data="stellar_link"
            )
        )

        kb.add(
            InlineKeyboardButton(
                "🛡️ فحص خط الثقة EN96",
                callback_data="stellar_check"
            )
        )

        bot.send_message(
            chat_id,
            "👑 محفظة Stellar - EN96\n\n"
            "1️⃣ افتح LOBSTR أو أنشئ محفظة.\n"
            "2️⃣ انسخ عنوانك العام G.\n"
            "3️⃣ احفظ العنوان في بوت EN96.\n"
            "4️⃣ أضف EN96 إلى المحفظة "
            "عبر خط الثقة.\n"
            "5️⃣ افحص خط الثقة من البوت.\n\n"
            "💎 الأصل: EN96\n"
            "🌐 الشبكة: Stellar Mainnet\n\n"
            "🏦 المُصدر:\n"
            f"{EN96_ISSUER}\n\n"
            "📍 عنوانك المسجل:\n"
            f"{address or 'غير مسجل'}\n\n"
            "🔒 لا تشارك مفتاحك السري "
            "أو عبارة الاسترداد.\n"
            "⚠️ حفظ عنوان G وحده لا يثبت "
            "ملكية المحفظة.",
            reply_markup=kb
        )

    except Exception:
        log.exception("Stellar menu error")


def begin_stellar_link(chat_id, uid):
    set_state(uid, "stellar_address")

    bot.send_message(
        chat_id,
        "🔗 أرسل عنوان Stellar العام.\n\n"
        "يبدأ بحرف G ويتكون من 56 حرفًا.\n\n"
        "لا ترسل المفتاح السري.\n"
        "للإلغاء: /cancel"
    )


def save_stellar_address(message):
    uid = message.from_user.id
    address = (
        (message.text or "")
        .strip()
        .upper()
    )

    if not valid_address(address):
        bot.send_message(
            message.chat.id,
            "⚠️ عنوان G غير صالح.\n"
            "انسخه من LOBSTR وحاول مجددًا."
        )
        return

    try:
        profile = profile_for(uid)

        if not profile:
            clear_state(uid)
            bot.send_message(
                message.chat.id,
                "أرسل /start أولًا."
            )
            return

        db.table("profiles").update({
            "stellar_public_address": address
        }).eq("id", profile["id"]).execute()

        clear_state(uid)

        bot.send_message(
            message.chat.id,
            "✅ تم حفظ عنوان G في EN96.\n\n"
            f"{address}\n\n"
            "ℹ️ العنوان محفوظ، لكن ملكيته "
            "لم تُثبت بتوقيع المحفظة بعد."
        )

    except Exception:
        log.exception("Save stellar address error")
        bot.send_message(
            message.chat.id,
            "تعذر حفظ عنوان Stellar."
        )


def check_trustline(chat_id, uid):
    try:
        profile = profile_for(uid)

        address = (
            profile.get("stellar_public_address")
            if profile else None
        )

        if not valid_address(address):
            bot.send_message(
                chat_id,
                "⚠️ احفظ عنوان G أولًا."
            )
            return

        found, status, asset = stellar_trustline(address)

        if found:
            bot.send_message(
                chat_id,
                "✅ خط الثقة EN96 موجود!\n\n"
                "🌐 Stellar Mainnet\n"
                "💎 رصيد EN96 على الشبكة:\n"
                f"{asset.get('balance', '0')} EN96\n\n"
                "✅ المُصدر متطابق.\n"
                "⚠️ الفحص لا يثبت ملكية "
                "العضو لهذا العنوان."
            )

        elif status == "account_not_found":
            bot.send_message(
                chat_id,
                "⚠️ الحساب غير موجود أو "
                "غير مفعل على Stellar Mainnet."
            )

        else:
            bot.send_message(
                chat_id,
                "⚠️ خط الثقة EN96 غير موجود.\n\n"
                "افتح LOBSTR ثم Add Asset.\n"
                "ابحث عن EN96 باستخدام "
                "عنوان المُصدر:\n\n"
                f"{EN96_ISSUER}\n\n"
                "وافق على خط الثقة "
                "داخل المحفظة."
            )

    except (HTTPError, URLError, TimeoutError):
        bot.send_message(
            chat_id,
            "تعذر الاتصال بشبكة Stellar."
        )

    except Exception:
        log.exception("Trustline check error")
        bot.send_message(
            chat_id,
            "تعذر فحص خط الثقة."
        )


# ======================================
# WITHDRAWAL SYSTEM
# ======================================

def pending_withdrawals(uid):
    profile = profile_for(uid)

    if not profile:
        return []

    return (
        db.table("withdrawal_requests")
        .select("id,amount,status")
        .eq("user_id", profile["id"])
        .eq("status", "pending")
        .limit(10)
        .execute()
        .data or []
    )


def begin_withdrawal(chat_id, uid):
    if not WITHDRAWALS_ENABLED:
        bot.send_message(
            chat_id,
            "💸 نظام سحوبات EN96\n\n"
            "🔒 طلبات السحب الحقيقية "
            "موقوفة مؤقتًا للاختبار.\n\n"
            "يمكنك تسجيل عنوان G وفحص "
            "خط الثقة ومشاهدة الرصيدين."
        )
        return

    try:
        profile = profile_for(uid)
        balance = balance_for(uid)

        if not profile or not balance:
            bot.send_message(
                chat_id,
                "⚠️ حسابك أو رصيدك غير موجود."
            )
            return

        available = Decimal(
            str(balance.get("available") or "0")
        )

        if available < MIN_WITHDRAWAL:
            bot.send_message(
                chat_id,
                "⚠️ الرصيد غير كافٍ للسحب.\n\n"
                "الحد الأدنى: 500 EN96\n"
                f"المتاح: {en96_number(available)}"
            )
            return

        if pending_withdrawals(uid):
            bot.send_message(
                chat_id,
                "⏳ لديك طلب سحب قيد المراجعة.\n"
                "لا يمكنك إنشاء طلب آخر الآن."
            )
            return

        address = (
            profile.get("stellar_public_address")
            or ""
        )

        if not valid_address(address):
            stellar_menu(chat_id, uid)
            bot.send_message(
                chat_id,
                "⚠️ سجل عنوان G أولًا."
            )
            return

        found, status, asset = stellar_trustline(address)

        if not found:
            bot.send_message(
                chat_id,
                "⚠️ لا يمكن متابعة طلب السحب.\n"
                "يجب أن يكون حساب Stellar "
                "مفعلًا ولديه خط ثقة EN96.\n"
                f"نتيجة الفحص: {status}"
            )
            return

        set_state(
            uid,
            "withdraw_amount",
            address=address
        )

        bot.send_message(
            chat_id,
            "💸 طلب سحب EN96\n\n"
            f"💎 المتاح: {en96_number(available)}"
            " EN96\n\n"
            "أرسل مبلغ السحب.\n"
            "الحد الأدنى 500 EN96.\n\n"
            "سيُحجز المبلغ عند التأكيد.\n"
            "للإلغاء: /cancel"
        )

    except Exception:
        log.exception("Begin withdrawal error")
        bot.send_message(
            chat_id,
            "تعذر فحص طلب السحب."
        )


def withdrawal_amount_input(message):
    uid = message.from_user.id
    amount = valid_amount(
        (message.text or "").replace(",", ".")
    )

    if amount is None:
        bot.send_message(
            message.chat.id,
            "⚠️ المبلغ غير صالح.\n"
            "الحد الأدنى 500 EN96 "
            "وبحد أقصى 7 أرقام عشرية."
        )
        return

    try:
        balance = balance_for(uid)

        if not balance:
            clear_state(uid)
            bot.send_message(
                message.chat.id,
                "تعذر تحميل الرصيد."
            )
            return

        available = Decimal(
            str(balance.get("available") or "0")
        )

        if amount > available:
            bot.send_message(
                message.chat.id,
                "⚠️ رصيدك غير كافٍ.\n"
                f"المتاح: {en96_number(available)}"
            )
            return

        state = get_state(uid)
        address = state.get("address", "")

        if not valid_address(address):
            clear_state(uid)
            bot.send_message(
                message.chat.id,
                "عنوان المحفظة غير صالح."
            )
            return

        set_state(
            uid,
            "withdraw_confirm",
            amount=str(amount),
            address=address
        )

        kb = InlineKeyboardMarkup()

        kb.row(
            InlineKeyboardButton(
                "✅ تأكيد السحب",
                callback_data="withdraw_confirm"
            ),
            InlineKeyboardButton(
                "❌ تراجع",
                callback_data="withdraw_abort"
            )
        )

        bot.send_message(
            message.chat.id,
            "💸 مراجعة طلب EN96\n\n"
            f"💎 المبلغ: {en96_number(amount)}"
            " EN96\n\n"
            "🌐 عنوان الاستلام:\n"
            f"{address}\n\n"
            "🔒 سيتم حجز المبلغ "
            "من الرصيد المتاح.\n"
            "⏳ التحويل الفعلي يدوي "
            "بعد مراجعة الإدارة.",
            reply_markup=kb
        )

    except Exception:
        log.exception("Withdrawal amount error")
        bot.send_message(
            message.chat.id,
            "تعذر مراجعة المبلغ."
        )


def confirm_withdrawal(call):
    uid = call.from_user.id
    chat_id = call.message.chat.id

    if not WITHDRAWALS_ENABLED:
        bot.send_message(
            chat_id,
            "🔒 السحوبات الحقيقية "
            "غير مفعلة حاليًا."
        )
        return

    lock = user_withdraw_lock(uid)

    if not lock.acquire(blocking=False):
        bot.send_message(
            chat_id,
            "⏳ تتم معالجة طلبك بالفعل."
        )
        return

    try:
        with STATE_LOCK:
            state = dict(
                USER_STATES.get(str(uid), {})
            )

            if state.get("action") != "withdraw_confirm":
                bot.send_message(
                    chat_id,
                    "انتهت صلاحية تأكيد الطلب."
                )
                return

            USER_STATES[str(uid)]["action"] = (
                "withdraw_submitting"
            )

        amount = valid_amount(state.get("amount"))
        address = state.get("address", "")

        if amount is None or not valid_address(address):
            clear_state(uid)
            bot.send_message(
                chat_id,
                "بيانات السحب غير صالحة."
            )
            return

        profile = profile_for(uid)

        if not profile:
            clear_state(uid)
            bot.send_message(
                chat_id,
                "حساب العضو غير موجود."
            )
            return

        if (
            profile.get("stellar_public_address")
            != address
        ):
            clear_state(uid)
            bot.send_message(
                chat_id,
                "عنوان Stellar تغير.\n"
                "ابدأ الطلب من جديد."
            )
            return

        if pending_withdrawals(uid):
            clear_state(uid)
            bot.send_message(
                chat_id,
                "⚠️ لديك طلب سحب سابق "
                "قيد المراجعة."
            )
            return

        result = db.rpc(
            "en96_request_withdrawal",
            {
                "p_telegram_id": str(uid),
                "p_amount": str(amount),
                "p_stellar_address": address
            }
        ).execute()

        # Existing Supabase RPC returns UUID.
        request_id = str(result.data or "")

        if not request_id:
            raise RuntimeError("Missing withdrawal ID")

        clear_state(uid)

        bot.send_message(
            chat_id,
            "✅ تم تسجيل طلب السحب!\n\n"
            f"🆔 الطلب: {request_id}\n"
            f"💎 المبلغ: {en96_number(amount)}"
            " EN96\n\n"
            "🔒 المبلغ محجوز في Supabase.\n"
            "⏳ الحالة: pending\n\n"
            "لم تُرسل عملات Stellar بعد.\n"
            "افتح محفظتي لتحديث الرصيد."
        )

        try:
            bot.send_message(
                int(ADMIN_ID),
                "👑 طلب سحب جديد\n\n"
                f"👤 العضو: {uid}\n"
                f"🆔 الطلب: {request_id}\n"
                f"💎 المبلغ: {en96_number(amount)}"
                " EN96\n\n"
                f"🌐 المستلم:\n{address}\n\n"
                "⏳ قيد المراجعة."
            )
        except Exception:
            log.warning("Admin notification failed")

    except Exception:
        log.exception("Withdrawal confirmation error")

        clear_state(uid)

        bot.send_message(
            chat_id,
            "⚠️ تعذر تأكيد نتيجة الطلب.\n"
            "قد يكون قد سُجل بالفعل.\n"
            "لا تكرر السحب قبل مراجعة "
            "الطلبات مع الإدارة."
        )

    finally:
        lock.release()


# ======================================
# ADMIN WITHDRAWALS
# ======================================

def admin_withdrawals(chat_id, uid):
    if (
        not is_admin(uid)
        or str(chat_id) != str(uid)
    ):
        bot.send_message(
            chat_id,
            "🔒 هذا القسم خاص بالإدارة."
        )
        return

    try:
        rows = (
            db.table("withdrawal_requests")
            .select(
                "id,user_id,amount,status,"
                "stellar_public_address,"
                "transaction_hash,created_at"
            )
            .order("created_at", desc=True)
            .limit(15)
            .execute()
            .data or []
        )

        if not rows:
            bot.send_message(
                chat_id,
                "👑 لا توجد طلبات سحب حاليًا."
            )
            return

        bot.send_message(
            chat_id,
            "👑 لوحة سحوبات EN96\n\n"
            "📋 أحدث الطلبات:\n"
            "🔒 تأكيد الدفع معطل مؤقتًا "
            "إلى حين إكمال التحقق من Stellar."
        )

        for order in rows:
            status = order.get("status", "unknown")

            if status == "pending":
                symbol = "⏳"
            elif status == "paid":
                symbol = "✅"
            elif status == "cancelled":
                symbol = "❌"
            else:
                symbol = "📋"

            telegram_id = "غير معروف"

            try:
                profile_rows = (
                    db.table("profiles")
                    .select("telegram_id")
                    .eq("id", order["user_id"])
                    .limit(1)
                    .execute()
                    .data or []
                )

                if profile_rows:
                    telegram_id = profile_rows[0].get(
                        "telegram_id", "غير معروف"
                    )
            except Exception:
                log.warning("Profile read error")

            bot.send_message(
                chat_id,
                "━━━━━━━━━━━━━━\n"
                f"{symbol} {status}\n\n"
                f"🆔 الطلب: {order.get('id')}\n"
                f"👤 Telegram: {telegram_id}\n"
                f"💎 {en96_number(order.get('amount'))}"
                " EN96\n\n"
                "🌐 المستلم:\n"
                f"{order.get('stellar_public_address')}\n\n"
                "🔗 المعاملة:\n"
                f"{order.get('transaction_hash') or 'لا يوجد'}"
            )

    except Exception:
        log.exception("Admin withdrawals error")
        bot.send_message(
            chat_id,
            "تعذر عرض طلبات السحب."
        )


# ======================================
# MINING
# ======================================

def mining_keyboard():
    kb = InlineKeyboardMarkup()

    kb.add(
        InlineKeyboardButton(
            "🔄 تحديث التعدين",
            callback_data="mining_refresh"
        )
    )

    return kb


def mining_counter(chat_id, uid, elapsed_before=0):
    key = (chat_id, str(uid))

    with MINING_LOCK:
        previous = MINING_COUNTERS.get(key)

        if previous:
            previous.set()

        stop_event = threading.Event()
        MINING_COUNTERS[key] = stop_event

    elapsed_before = max(
        0,
        min(int(elapsed_before), MINING_DURATION)
    )

    started = time.time() - elapsed_before

    try:
        msg = bot.send_message(
            chat_id,
            "⛏️ التعدين الافتراضي نشط.\n"
            "⚡ 0.001 EN96/ثانية\n"
            "⏱️ الجلسة: 24 ساعة",
            reply_markup=mining_keyboard()
        )

    except Exception:
        log.exception("Mining message error")
        with MINING_LOCK:
            if MINING_COUNTERS.get(key) is stop_event:
                MINING_COUNTERS.pop(key, None)
        return

    def update():
        nonlocal started

        try:
            while not stop_event.is_set():
                elapsed = min(
                    max(0, int(time.time() - started)),
                    MINING_DURATION
                )

                estimate = (
                    Decimal(elapsed) * MINING_RATE
                )

                hours, remainder = divmod(elapsed, 3600)
                minutes, seconds = divmod(
                    remainder, 60
                )

                counter_text = (
                    "🐻‍❄️👑 منجم EN96\n\n"
                    "⛏️ التعدين الافتراضي نشط\n\n"
                    "💎 المكافأة التقديرية:\n"
                    f"{estimate:.7f} EN96\n\n"
                    "⏱️ الوقت:\n"
                    f"{hours:02d}:"
                    f"{minutes:02d}:"
                    f"{seconds:02d} / 24:00:00\n\n"
                    "⚡ 0.001 EN96/ثانية\n"
                    "⚠️ الرصيد الفعلي تحدده Supabase."
                )

                try:
                    bot.edit_message_text(
                        counter_text,
                        chat_id=chat_id,
                        message_id=msg.message_id,
                        reply_markup=mining_keyboard()
                    )
                except Exception as exc:
                    if (
                        "message is not modified"
                        not in str(exc).lower()
                    ):
                        log.warning(
                            "Mining counter: %s", exc
                        )

                if elapsed >= MINING_DURATION:
                    try:
                        data = rpc_data(
                            db.rpc(
                                "en96_mining_action",
                                {
                                    "p_telegram_id": str(uid)
                                }
                            ).execute()
                        )

                        status = data.get("status")

                        if status == "rewarded_and_started":
                            bot.send_message(
                                chat_id,
                                "✅ أكدت Supabase إضافة "
                                f"{data.get('reward', 86.4)}"
                                " EN96.\n"
                                "بدأت جلسة جديدة."
                            )
                            started = time.time()
                            continue

                        if status == "active":
                            remaining = max(
                                1,
                                int(data.get(
                                    "remaining_seconds", 1
                                ))
                            )

                            started = (
                                time.time()
                                - MINING_DURATION
                                + remaining
                            )
                            continue

                        bot.send_message(
                            chat_id,
                            "⚠️ لم يتم تأكيد مكافأة الجلسة."
                        )
                        break

                    except Exception:
                        log.exception("Mining settlement")
                        break

                if stop_event.wait(5):
                    break

        finally:
            with MINING_LOCK:
                if MINING_COUNTERS.get(key) is stop_event:
                    MINING_COUNTERS.pop(key, None)

    threading.Thread(
        target=update,
        daemon=True
    ).start()


def mining(chat_id, uid):
    try:
        if not profile_for(uid):
            bot.send_message(
                chat_id,
                "أرسل /start أولًا."
            )
            return

        data = rpc_data(
            db.rpc(
                "en96_mining_action",
                {"p_telegram_id": str(uid)}
            ).execute()
        )

        status = data.get("status")

        if status == "started":
            mining_counter(chat_id, uid)

        elif status == "rewarded_and_started":
            bot.send_message(
                chat_id,
                "✅ تمت إضافة "
                f"{data.get('reward', 86.4)} EN96 "
                "وبدأت جلسة جديدة."
            )
            mining_counter(chat_id, uid)

        elif status == "active":
            remaining = max(
                0,
                min(
                    int(data.get(
                        "remaining_seconds",
                        MINING_DURATION
                    )),
                    MINING_DURATION
                )
            )

            mining_counter(
                chat_id,
                uid,
                MINING_DURATION - remaining
            )

        elif status == "profile_missing":
            bot.send_message(
                chat_id,
                "حسابك غير موجود."
            )

        elif status == "balance_missing":
            bot.send_message(
                chat_id,
                "سجل الرصيد غير موجود."
            )

        else:
            bot.send_message(
                chat_id,
                "تعذر تأكيد حالة التعدين."
            )

    except Exception:
        log.exception("Mining error")
        bot.send_message(
            chat_id,
            "⚠️ حدث خطأ أثناء التعدين."
        )


# ======================================
# REFERRAL SYSTEM
# ======================================

def referral_link(uid):
    return (
        f"https://t.me/{BOT_USERNAME}"
        f"?start=ref_{uid}"
    )


def record_referral(message, payload):
    if not payload.startswith("ref_"):
        return

    referrer = payload[4:]
    new_user = str(message.from_user.id)

    if not referrer.isascii() or not referrer.isdigit():
        return

    if referrer == new_user:
        bot.send_message(
            message.chat.id,
            "لا يمكنك دعوة نفسك."
        )
        return

    try:
        result = db.rpc(
            "en96_record_referral",
            {
                "p_telegram_id": new_user,
                "p_referrer_telegram_id": referrer
            }
        ).execute()

        data = rpc_data(result)

        if data.get("status") == "registered":
            bot.send_message(
                message.chat.id,
                "🎉 تم تسجيل دعوتك في قبيلة EN96!"
            )

    except Exception:
        log.exception("Referral error")


def tribe(chat_id, uid):
    link = referral_link(uid)

    try:
        data = rpc_data(
            db.rpc(
                "en96_tribe_stats",
                {"p_telegram_id": str(uid)}
            ).execute()
        )

        if data.get("status") != "ok":
            raise ValueError("Tribe statistics error")

        bot.send_message(
            chat_id,
            "🐻‍❄️👑 قبيلة EN96\n"
            "━━━━━━━━━━━━━━\n\n"
            f"👥 عدد الأصدقاء: "
            f"{int(data.get('friends') or 0)}\n\n"
            "🎁 مكافآت الدعوات:\n"
            f"{en96_number(data.get('invitation_bonus'))}"
            " EN96\n\n"
            "⛏️ عمولة التعدين 5%:\n"
            f"{en96_number(data.get('mining_commission'))}"
            " EN96\n\n"
            "💎 مجموع مكافآت القبيلة:\n"
            f"{en96_number(data.get('total'))}"
            " EN96\n\n"
            "🔗 رابط دعوتك:\n"
            f"{link}\n\n"
            "🎁 50 EN96 عند اكتمال أول "
            "جلسة مؤهلة للصديق.\n"
            "⛏️ 5% من مكافآت تعدين "
            "الأصدقاء المباشرين المؤكدة.",
            disable_web_page_preview=True
        )

    except Exception:
        log.exception("Tribe error")

        bot.send_message(
            chat_id,
            "تعذر تحميل إحصائيات القبيلة.\n\n"
            f"رابطك:\n{link}",
            disable_web_page_preview=True
        )


# ======================================
# VIDEO GIFTS
# ======================================

def redeem_gift(message):
    uid = message.from_user.id
    code = (message.text or "").strip()

    clear_state(uid)

    try:
        data = rpc_data(
            db.rpc(
                "redeem_en96_video_gift",
                {
                    "p_telegram_id": int(uid),
                    "p_code": code
                }
            ).execute()
        )

        if data.get("ok") is True:
            bot.send_message(
                message.chat.id,
                "🎁 تم استلام "
                f"{data.get('reward', 1)}"
                " EN96 بنجاح!"
            )
            return

        reason = (
            data.get("reason")
            or data.get("status")
            or "unknown"
        )

        errors = {
            "invalid_input":
                "الكود غير صالح.",
            "profile_not_found":
                "أرسل /start أولًا.",
            "invalid_or_inactive_code":
                "الكود غير موجود أو غير مفعل.",
            "already_claimed":
                "استعملت الكود من قبل.",
            "cooldown_2_hours":
                "انتظر ساعتين قبل هدية أخرى.",
            "balance_not_found":
                "سجل الرصيد غير موجود."
        }

        bot.send_message(
            message.chat.id,
            errors.get(
                reason,
                f"تعذر استلام الهدية: {reason}"
            )
        )

    except Exception:
        log.exception("Redeem gift error")

        bot.send_message(
            message.chat.id,
            "تعذر التحقق من الهدية."
        )


def show_videos(chat_id):
    try:
        rows = (
            db.table("video_gift_codes")
            .select("video_url,reward,description")
            .eq("active", True)
            .order("created_at", desc=True)
            .limit(10)
            .execute()
            .data or []
        )

        if not rows:
            bot.send_message(
                chat_id,
                "لا توجد فيديوهات هدايا حاليًا."
            )
            return

        lines = []

        for row in rows:
            lines.append(
                f"📺 {row.get('description') or 'EN96'}\n"
                f"🎁 {row.get('reward')} EN96\n"
                f"{row.get('video_url')}"
            )

        bot.send_message(
            chat_id,
            "\n\n".join(lines),
            disable_web_page_preview=True
        )

    except Exception:
        log.exception("Videos error")

        bot.send_message(
            chat_id,
            "تعذر عرض الفيديوهات."
        )


def show_tiktok(chat_id):
    kb = InlineKeyboardMarkup()

    kb.add(
        InlineKeyboardButton(
            "🎵 TikTok EN96",
            url=TIKTOK_URL
        )
    )

    bot.send_message(
        chat_id,
        "🎵 TikTok الرسمي لمملكة EN96",
        reply_markup=kb
    )


def show_youtube(chat_id):
    kb = InlineKeyboardMarkup()

    kb.add(
        InlineKeyboardButton(
            "▶️ YouTube EN96",
            url=YOUTUBE_URL
        )
    )

    bot.send_message(
        chat_id,
        "▶️ قناة EN96 الرسمية",
        reply_markup=kb
    )


# ======================================
# ADMIN GIFTS
# ======================================

def admin_create_code(message):
    uid = message.from_user.id

    if not is_admin(uid):
        return

    code = (message.text or "").strip()

    if not code or len(code) > 120:
        bot.send_message(
            message.chat.id,
            "الكود غير صالح."
        )
        return

    set_state(
        uid,
        "admin_gift_video",
        code=code
    )

    bot.send_message(
        message.chat.id,
        "أرسل رابط فيديو الهدية."
    )


def admin_video(message):
    uid = message.from_user.id

    if not is_admin(uid):
        return

    url = (message.text or "").strip()

    if not url.startswith(("https://", "http://")):
        bot.send_message(
            message.chat.id,
            "رابط الفيديو غير صالح."
        )
        return

    state = get_state(uid)

    set_state(
        uid,
        "admin_gift_reward",
        code=state.get("code"),
        video_url=url
    )

    bot.send_message(
        message.chat.id,
        "أرسل مقدار المكافأة، مثل 1."
    )


def admin_reward(message):
    uid = message.from_user.id

    if not is_admin(uid):
        return

    try:
        reward = Decimal(
            (message.text or "")
            .strip()
            .replace(",", ".")
        )

        if (
            not reward.is_finite()
            or reward <= 0
            or reward > Decimal("1000000")
        ):
            raise ValueError

    except (InvalidOperation, ValueError):
        bot.send_message(
            message.chat.id,
            "أرسل مقدارًا موجبًا صالحًا."
        )
        return

    state = get_state(uid)

    if not state.get("code") or not state.get("video_url"):
        clear_state(uid)
        bot.send_message(
            message.chat.id,
            "بيانات الهدية ناقصة."
        )
        return

    try:
        db.table("video_gift_codes").insert({
            "code": state["code"],
            "video_url": state["video_url"],
            "reward": str(reward),
            "active": True,
            "description": "EN96 admin gift"
        }).execute()

        bot.send_message(
            message.chat.id,
            "✅ تم إنشاء الهدية.\n\n"
            f"الكود: {state['code']}\n"
            f"المكافأة: {reward} EN96"
        )

    except Exception:
        log.exception("Admin gift creation error")

        bot.send_message(
            message.chat.id,
            "تعذر إنشاء كود الهدية."
        )

    finally:
        clear_state(uid)


def list_gifts(chat_id):
    try:
        rows = (
            db.table("video_gift_codes")
            .select("id,code,reward,active")
            .order("created_at", desc=True)
            .limit(20)
            .execute()
            .data or []
        )

        if not rows:
            bot.send_message(
                chat_id,
                "لا توجد أكواد هدايا."
            )
            return

        lines = ["📋 أكواد هدايا EN96:"]

        for row in rows:
            status = (
                "مفعل"
                if row.get("active")
                else "معطل"
            )

            lines.append(
                f"{row.get('code')} | "
                f"{row.get('reward')} EN96 | "
                f"{status}"
            )

        bot.send_message(
            chat_id,
            "\n".join(lines)
        )

    except Exception:
        log.exception("Gift list error")
        bot.send_message(
            chat_id,
            "تعذر عرض الهدايا."
        )


def toggle_gift(message, active):
    if not is_admin(message.from_user.id):
        return

    code = (message.text or "").strip()

    try:
        result = (
            db.table("video_gift_codes")
            .update({"active": active})
            .eq("code", code)
            .execute()
        )

        if result.data:
            bot.send_message(
                message.chat.id,
                "✅ تم تغيير حالة الكود."
            )
        else:
            bot.send_message(
                message.chat.id,
                "الكود غير موجود."
            )

    except Exception:
        log.exception("Gift toggle error")
        bot.send_message(
            message.chat.id,
            "تعذر تغيير حالة الكود."
        )


# ======================================
# ADMIN TELEGRAM STARS
# ======================================

def admin_stars_balance(chat_id, uid):
    if (
        not is_admin(uid)
        or str(chat_id) != str(uid)
    ):
        bot.send_message(
            chat_id,
            "🔒 هذا القسم خاص بالإدارة."
        )
        return

    try:
        endpoint = (
            "https://api.telegram.org/bot"
            + BOT_TOKEN
            + "/getMyStarBalance"
        )

        request = Request(
            endpoint,
            data=b"{}",
            headers={
                "Content-Type": "application/json"
            },
            method="POST"
        )

        with urlopen(request, timeout=15) as response:
            payload = json.loads(
                response.read().decode("utf-8")
            )

        if not payload.get("ok"):
            raise RuntimeError("Stars request failed")

        result = payload.get("result") or {}

        amount = (
            int(result.get("amount", 0))
            + int(result.get("nanostar_amount", 0))
            / 1000000000
        )

        bot.send_message(
            chat_id,
            "👑 إدارة EN96\n\n"
            "⭐ رصيد نجوم البوت:\n"
            f"💎 {amount:,.9f} Stars\n\n"
            "هذا رصيد البوت وليس حسابك الشخصي.\n"
            "عمليات الدفع والسحب غير مفعلة."
        )

    except Exception:
        log.exception("Telegram Stars error")

        bot.send_message(
            chat_id,
            "تعذر الحصول على رصيد Stars."
        )


# ======================================
# START / COMMANDS
# ======================================

@bot.message_handler(commands=["start", "menu"])
def start(message):
    if not is_private(message):
        bot.reply_to(
            message,
            "افتح EN96 في محادثة خاصة."
        )
        return

    uid = message.from_user.id
    clear_state(uid)

    if not register_member(uid):
        bot.send_message(
            message.chat.id,
            "تعذر تأكيد حسابك.\n"
            "حاول مرة أخرى."
        )
        return

    parts = (
        (message.text or "")
        .strip()
        .split(maxsplit=1)
    )

    command = parts[0].split("@")[0] if parts else ""
    payload = parts[1].strip() if len(parts) > 1 else ""

    if command == "/start" and payload == "mining":
        mining(message.chat.id, uid)
        return

    if command == "/start" and payload.startswith("ref_"):
        record_referral(message, payload)

    send_menu(message.chat.id, uid)
    app_button(message.chat.id)


@bot.message_handler(commands=["cancel"])
def cancel_command(message):
    clear_state(message.from_user.id)

    bot.send_message(
        message.chat.id,
        "✅ تم إلغاء إدخال البيانات.\n"
        "لم نلغِ طلب سحب محفوظًا."
    )


@bot.message_handler(commands=["wallet"])
def wallet_command(message):
    if is_private(message):
        wallet(message.chat.id, message.from_user.id)


@bot.message_handler(commands=["mining"])
def mining_command(message):
    if is_private(message):
        mining(message.chat.id, message.from_user.id)


@bot.message_handler(commands=["withdraw"])
def withdraw_command(message):
    if is_private(message):
        begin_withdrawal(
            message.chat.id,
            message.from_user.id
        )


@bot.message_handler(commands=["tribe"])
def tribe_command(message):
    if is_private(message):
        tribe(message.chat.id, message.from_user.id)


@bot.message_handler(commands=["stars"])
def stars_command(message):
    if is_private(message):
        admin_stars_balance(
            message.chat.id,
            message.from_user.id
        )


@bot.message_handler(commands=["tiktok"])
def tiktok_command(message):
    show_tiktok(message.chat.id)


@bot.message_handler(commands=["youtube"])
def youtube_command(message):
    show_youtube(message.chat.id)


@bot.message_handler(commands=["admin"])
def admin_command(message):
    if (
        is_private(message)
        and is_admin(message.from_user.id)
    ):
        bot.send_message(
            message.chat.id,
            "🛠️ إدارة هدايا EN96",
            reply_markup=admin_menu()
        )
    else:
        bot.send_message(
            message.chat.id,
            "هذا القسم للمسؤول فقط."
        )


# ======================================
# INLINE CALLBACKS
# ======================================

@bot.callback_query_handler(
    func=lambda call: call.data in (
        "wallet_refresh",
        "withdraw_start",
        "withdraw_confirm",
        "withdraw_abort",
        "stellar_menu",
        "stellar_link",
        "stellar_check",
        "mining_refresh",
        "admin_withdrawals"
    )
)
def callback_handler(call):
    try:
        bot.answer_callback_query(call.id)

        uid = call.from_user.id
        chat_id = call.message.chat.id

        if (
            call.message.chat.type != "private"
            or str(chat_id) != str(uid)
        ):
            return

        action = call.data

        if action == "wallet_refresh":
            wallet(chat_id, uid)

        elif action == "withdraw_start":
            clear_state(uid)
            begin_withdrawal(chat_id, uid)

        elif action == "withdraw_confirm":
            confirm_withdrawal(call)

        elif action == "withdraw_abort":
            clear_state(uid)
            bot.send_message(
                chat_id,
                "✅ تراجعت عن إنشاء الطلب."
            )

        elif action == "stellar_menu":
            stellar_menu(chat_id, uid)

        elif action == "stellar_link":
            begin_stellar_link(chat_id, uid)

        elif action == "stellar_check":
            check_trustline(chat_id, uid)

        elif action == "mining_refresh":
            mining(chat_id, uid)

        elif action == "admin_withdrawals":
            admin_withdrawals(chat_id, uid)

    except Exception:
        log.exception("Callback handler error")


# ======================================
# MAIN TEXT HANDLER
# ======================================

@bot.message_handler(content_types=["text"])
def text_handler(message):
    if not is_private(message):
        return

    uid = message.from_user.id
    chat_id = message.chat.id
    text = (message.text or "").strip()

    # Navigation buttons
    if text == "🔙 القائمة الرئيسية":
        clear_state(uid)
        send_menu(chat_id, uid)
        return

    if text == "⛏️ بدء التعدين":
        clear_state(uid)
        mining(chat_id, uid)
        return

    if text == "💰 محفظتي":
        clear_state(uid)
        wallet(chat_id, uid)
        return

    if text == "💸 سحب EN96":
        clear_state(uid)
        begin_withdrawal(chat_id, uid)
        return

    if text == "🔗 محفظة Stellar":
        clear_state(uid)
        stellar_menu(chat_id, uid)
        return

    if text == "🌐 فتح تطبيق EN96":
        clear_state(uid)
        app_button(chat_id)
        return

    if text == "👑 إدارة السحوبات":
        clear_state(uid)
        admin_withdrawals(chat_id, uid)
        return

    if text == "⭐ رصيد Stars للإدارة":
        clear_state(uid)
        admin_stars_balance(chat_id, uid)
        return

    if text == "🎁 استلام الهدية":
        set_state(uid, "gift_code")
        bot.send_message(
            chat_id,
            "🎁 أرسل كود هدية الفيديو."
        )
        return

    if text == "📺 مشاهدة الفيديوهات":
        clear_state(uid)
        show_videos(chat_id)
        return

    if text in (
        "🐻 أعضاء القبيلة",
        "🐉 أعضاء القبيلة"
    ):
        clear_state(uid)
        tribe(chat_id, uid)
        return

    if text == "🎵 TikTok EN96":
        clear_state(uid)
        show_tiktok(chat_id)
        return

    if text == "▶️ YouTube EN96":
        clear_state(uid)
        show_youtube(chat_id)
        return

    if text == "⚡ ترقية المنجم":
        clear_state(uid)
        bot.send_message(
            chat_id,
            "⚡ ترقيات المنجم لم تفعل بعد."
        )
        return

    if text == "🏆 المكافآت":
        clear_state(uid)
        bot.send_message(
            chat_id,
            "🏆 مكافآت EN96\n\n"
            "🎁 هدايا الفيديو\n"
            "🐻 مكافآت القبيلة\n"
            "⛏️ التعدين الافتراضي"
        )
        return

    if text == "ℹ️ معلومات EN96":
        clear_state(uid)
        bot.send_message(
            chat_id,
            "🐻‍❄️ EN96 Ice Bear Kingdom\n\n"
            "🌐 Stellar Mainnet\n"
            "⛏️ تعدين افتراضي\n"
            "⚡ 0.001 EN96/ثانية\n"
            "⏱️ 24 ساعة للجلسة\n"
            "💎 86.4 EN96 للجلسة\n\n"
            "🎁 50 EN96 للدعوة المؤهلة\n"
            "👥 عمولة تعدين 5%\n"
            "💸 الحد الأدنى للسحب 500 EN96\n\n"
            "السحوبات تراجع يدويًا."
        )
        return

    # Administrator buttons
    if is_admin(uid):
        if text == "🛠️ إدارة الهدايا":
            clear_state(uid)
            bot.send_message(
                chat_id,
                "🛠️ إدارة الهدايا",
                reply_markup=admin_menu()
            )
            return

        if text == "➕ إنشاء كود هدية":
            set_state(uid, "admin_gift_code")
            bot.send_message(
                chat_id,
                "أرسل الكود الجديد."
            )
            return

        if text == "📋 أكواد الهدايا":
            clear_state(uid)
            list_gifts(chat_id)
            return

        if text == "⛔ تعطيل كود":
            set_state(
                uid,
                "admin_gift_toggle",
                active=False
            )
            bot.send_message(
                chat_id,
                "أرسل الكود المطلوب تعطيله."
            )
            return

        if text == "✅ تفعيل كود":
            set_state(
                uid,
                "admin_gift_toggle",
                active=True
            )
            bot.send_message(
                chat_id,
                "أرسل الكود المطلوب تفعيله."
            )
            return

    # Input states
    state = get_state(uid)
    action = state.get("action")

    if action == "stellar_address":
        save_stellar_address(message)
        return

    if action == "withdraw_amount":
        withdrawal_amount_input(message)
        return

    if action == "withdraw_confirm":
        bot.send_message(
            chat_id,
            "اضغط زر تأكيد السحب "
            "أو التراجع في الرسالة السابقة."
        )
        return

    if action == "withdraw_submitting":
        bot.send_message(
            chat_id,
            "⏳ تتم مراجعة طلبك.\n"
            "افتح المحفظة للتحقق من النتيجة."
        )
        return

    if action == "gift_code":
        redeem_gift(message)
        return

    if action == "admin_gift_code" and is_admin(uid):
        admin_create_code(message)
        return

    if action == "admin_gift_video" and is_admin(uid):
        admin_video(message)
        return

    if action == "admin_gift_reward" and is_admin(uid):
        admin_reward(message)
        return

    if action == "admin_gift_toggle" and is_admin(uid):
        active = bool(state.get("active"))
        clear_state(uid)
        toggle_gift(message, active)
        return

    send_menu(chat_id, uid)


# ======================================
# START BOT
# ======================================

if __name__ == "__main__":
    log.info("Starting EN96 Ice Bear Kingdom")

    bot.infinity_polling(
        skip_pending=True,
        timeout=30,
        long_polling_timeout=30
    )
