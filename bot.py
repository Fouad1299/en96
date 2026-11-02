
import os
import json
import time
import logging
import threading
import re
from decimal import Decimal, InvalidOperation
from urllib.request import Request, urlopen
from urllib.error import HTTPError

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


# ==========================================
# EN96 ICE BEAR KINGDOM
# Telegram Mining and Withdrawal Bot
# Stellar Mainnet
# ==========================================

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

TIKTOK_URL = "https://www.tiktok.com/@en96mining"

YOUTUBE_URL = (
    "https://www.youtube.com/@EN96_Gold_Miner_bo"
)

LOBSTR_URL = "https://lobstr.co/"

HORIZON_URL = "https://horizon.stellar.org"

EN96_ISSUER = (
    "GCUGIICUGBFC3KBPIFYAMPNA7OVJHGY277TNYTZUSG7EVVUCVACH3OGB"
)

EN96_ASSET = "EN96"

MINING_RATE = 0.001
MINING_DURATION = 86400

MIN_WITHDRAWAL = Decimal("500")
MAX_WITHDRAWAL = Decimal("1000000000000")
EN96_STEP = Decimal("0.0000001")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN missing")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Supabase configuration missing")

bot = telebot.TeleBot(BOT_TOKEN)

db = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)

MINING_COUNTERS = {}
MINING_LOCK = threading.Lock()

WAITING_GIFT = set()
WAITING_ADMIN_CODE = set()
WAITING_ADMIN_VIDEO = set()
WAITING_ADMIN_REWARD = set()

ADMIN_ACTION = {}
PENDING = {}

# New withdrawal states
WITHDRAWAL_STATES = {}
WITHDRAWAL_LOCK = threading.RLock()

# Administrative cancellation confirmation
ADMIN_CANCEL_CONFIRM = {}


# ==========================================
# COMMON HELPERS
# ==========================================

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


def register_member(user_id):
    try:
        ensure_profile(db, user_id)
        return True
    except Exception:
        log.exception("Registration error")
        return False


def profile_for(user_id):
    result = (
        db.table("profiles")
        .select(
            "id,telegram_id,stellar_public_address"
        )
        .eq("telegram_id", str(user_id))
        .limit(1)
        .execute()
    )

    return result.data[0] if result.data else None


def balance_for(profile_id):
    result = (
        db.table("balances")
        .select("available,reserved")
        .eq("user_id", profile_id)
        .limit(1)
        .execute()
    )

    return result.data[0] if result.data else None


def en96_number(value):
    try:
        return f"{Decimal(str(value or 0)):,.7f}"
    except Exception:
        return "0.0000000"


def valid_stellar_address(value):
    if not isinstance(value, str):
        return False

    return bool(
        re.fullmatch(
            r"G[A-Z2-7]{55}",
            value.strip().upper()
        )
    )


def parse_amount(value):
    try:
        value = (
            str(value)
            .strip()
            .replace(",", ".")
        )

        amount = Decimal(value)

        if not amount.is_finite():
            return None

        if amount < MIN_WITHDRAWAL:
            return None

        if amount > MAX_WITHDRAWAL:
            return None

        if amount != amount.quantize(EN96_STEP):
            return None

        return amount

    except (
        InvalidOperation,
        ValueError,
        TypeError
    ):
        return None


def clear_withdrawal_state(user_id):
    with WITHDRAWAL_LOCK:
        WITHDRAWAL_STATES.pop(
            str(user_id),
            None
        )


def get_withdrawal_state(user_id):
    with WITHDRAWAL_LOCK:
        return WITHDRAWAL_STATES.get(
            str(user_id)
        )


def set_withdrawal_state(user_id, state):
    with WITHDRAWAL_LOCK:
        WITHDRAWAL_STATES[str(user_id)] = state


def wallet_support_keyboard():
    kb = InlineKeyboardMarkup()

    kb.add(
        InlineKeyboardButton(
            "🪙 إنشاء / فتح محفظة LOBSTR",
            url=LOBSTR_URL
        )
    )

    return kb


def app_button(chat_id):
    kb = InlineKeyboardMarkup()

    kb.add(
        InlineKeyboardButton(
            "👑 افتح مملكة EN96 الملكية 🐻",
            web_app=WebAppInfo(
                url=ROYAL_APP_URL
            )
        )
    )

    bot.send_message(
        chat_id,
        "👑🐻 مرحبًا بك في EN96!\n\n"
        "⛏️ التعدين الافتراضي\n"
        "💰 المحفظة\n"
        "💸 طلبات السحب\n"
        "🎁 الهدايا والقبيلة\n\n"
        "اضغط الزر للدخول.\n\n"
        "⚠️ النقر التجريبي على الدب "
        "لا يضيف رصيدًا حقيقيًا.",
        reply_markup=kb
    )


# ==========================================
# MAIN MENU
# ==========================================

def menu(user_id=None):
    kb = ReplyKeyboardMarkup(
        resize_keyboard=True
    )

    kb.row(
        KeyboardButton("⛏️ بدء التعدين"),
        KeyboardButton("💰 محفظتي")
    )

    kb.row(
        KeyboardButton("💸 سحب EN96"),
        KeyboardButton("📋 طلبات السحب")
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

    if user_id is not None and is_admin(user_id):
        kb.row(
            KeyboardButton("🛠️ إدارة الهدايا"),
            KeyboardButton("⭐ رصيد Stars للإدارة")
        )

        kb.row(
            KeyboardButton("👑 إدارة السحوبات")
        )

    return kb


def send_menu(
    chat_id,
    text="🐻 مرحبًا بك في EN96 Mining!",
    user_id=None
):
    bot.send_message(
        chat_id,
        text,
        reply_markup=menu(user_id)
    )

    if (
        user_id is not None
        and str(chat_id) == str(user_id)
    ):
        app_button(chat_id)


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

    kb.row(
        KeyboardButton("🔙 القائمة الرئيسية")
    )

    return kb


# ==========================================
# STELLAR ACCOUNT VERIFICATION
# ==========================================

def stellar_account_info(address):
    """
    Public account lookup only.
    Does not sign transactions.
    Does not prove wallet ownership.
    """

    if not valid_stellar_address(address):
        return {
            "ok": False,
            "reason": "invalid_address"
        }

    endpoint = (
        f"{HORIZON_URL}/accounts/"
        f"{address.upper()}"
    )

    request = Request(
        endpoint,
        headers={
            "Accept": "application/json",
            "User-Agent": "EN96Bot/1.0"
        }
    )

    try:
        with urlopen(
            request,
            timeout=12
        ) as response:
            account = json.loads(
                response.read().decode("utf-8")
            )

    except HTTPError as exc:
        if exc.code == 404:
            return {
                "ok": False,
                "reason": "account_not_found"
            }

        log.warning(
            "Stellar HTTP error: %s",
            exc.code
        )

        return {
            "ok": False,
            "reason": "network_error"
        }

    except Exception:
        log.exception("Stellar account lookup failed")

        return {
            "ok": False,
            "reason": "network_error"
        }

    asset = None

    for item in account.get("balances", []):
        if (
            item.get("asset_code") == EN96_ASSET
            and item.get("asset_issuer") == EN96_ISSUER
        ):
            asset = item
            break

    return {
        "ok": True,
        "trustline": asset is not None,
        "asset_balance": (
            asset.get("balance")
            if asset else None
        )
    }


def stellar_error_text(reason):
    errors = {
        "invalid_address":
            "عنوان Stellar غير صالح.",
        "account_not_found":
            "الحساب غير مفعّل على Stellar Mainnet.",
        "network_error":
            "تعذر الاتصال بشبكة Stellar الآن."
    }

    return errors.get(
        reason,
        "تعذر التحقق من المحفظة."
    )


# ==========================================
# EN96 WALLET
# ==========================================

def wallet(chat_id, user_id):
    try:
        profile = profile_for(user_id)

        if not profile:
            bot.send_message(
                chat_id,
                "لم أجد حسابك. أرسل /start أولًا."
            )
            return

        balance = balance_for(profile["id"])

        if not balance:
            bot.send_message(
                chat_id,
                "لم أجد سجل رصيدك."
            )
            return

        address = (
            profile.get("stellar_public_address")
            or ""
        )

        kb = InlineKeyboardMarkup()

        kb.row(
            InlineKeyboardButton(
                "💸 طلب سحب EN96",
                callback_data="withdraw_start"
            ),
            InlineKeyboardButton(
                "🔗 ربط عنوان G",
                callback_data="wallet_link"
            )
        )

        kb.row(
            InlineKeyboardButton(
                "🛡️ فحص خط الثقة",
                callback_data="wallet_trustline"
            )
        )

        kb.row(
            InlineKeyboardButton(
                "🪙 إنشاء محفظة LOBSTR",
                url=LOBSTR_URL
            )
        )

        bot.send_message(
            chat_id,
            "🐻‍❄️👑 محفظة EN96\n"
            "━━━━━━━━━━━━━━\n\n"
            "🟢 الرصيد المتاح:\n"
            f"{en96_number(balance.get('available'))} EN96\n\n"
            "🟡 الرصيد المحجوز:\n"
            f"{en96_number(balance.get('reserved'))} EN96\n\n"
            "💸 الحد الأدنى للسحب: 500 EN96\n\n"
            "🔗 عنوان Stellar:\n"
            f"{address if address else 'غير مربوط'}\n\n"
            "📌 السحب إلى شبكة Stellar Mainnet.\n"
            "📌 إرسال العملات يتم يدويًا بعد المراجعة.\n"
            "⚠️ الرصيد داخل البوت ليس رصيد Stellar.",
            reply_markup=kb
        )

    except Exception:
        log.exception("Wallet error")

        bot.send_message(
            chat_id,
            "تعذر عرض المحفظة الآن."
        )


def start_wallet_link(chat_id, user_id):
    set_withdrawal_state(
        user_id,
        {"step": "link_address"}
    )

    bot.send_message(
        chat_id,
        "🔗 ربط محفظة Stellar\n\n"
        "افتح LOBSTR واختر Receive، "
        "ثم انسخ عنوانك العام الذي يبدأ بحرف G.\n\n"
        "أرسله هنا لحفظ عنوان الاستلام.\n\n"
        "⚠️ لا ترسل المفتاح السري أو كلمات الاسترداد.\n"
        "⚠️ حفظ العنوان لا يثبت ملكيته.",
        reply_markup=wallet_support_keyboard()
    )


def save_wallet_address(chat_id, user_id, address):
    address = address.strip().upper()

    if not valid_stellar_address(address):
        bot.send_message(
            chat_id,
            "❌ عنوان G غير صالح.\n"
            "أرسل عنوان Stellar عامًا صحيحًا "
            "أو أرسل /cancel."
        )
        return

    try:
        profile = profile_for(user_id)

        if not profile:
            clear_withdrawal_state(user_id)
            bot.send_message(
                chat_id,
                "لم أجد حسابك. أرسل /start."
            )
            return

        # Do not change destination during a pending request.
        existing = (
            db.table("withdrawal_requests")
            .select("id")
            .eq("user_id", profile["id"])
            .eq("status", "pending")
            .limit(1)
            .execute()
            .data or []
        )

        if existing:
            clear_withdrawal_state(user_id)

            bot.send_message(
                chat_id,
                "⚠️ لديك طلب سحب معلق.\n"
                "لا يمكن تغيير عنوان الاستلام "
                "أثناء مراجعة الطلب."
            )
            return

        db.table("profiles").update(
            {
                "stellar_public_address": address
            }
        ).eq(
            "id", profile["id"]
        ).execute()

        clear_withdrawal_state(user_id)

        bot.send_message(
            chat_id,
            "✅ تم حفظ عنوان Stellar في حساب EN96.\n\n"
            f"{address}\n\n"
            "🛡️ افحص خط الثقة قبل طلب السحب.\n\n"
            "⚠️ حفظ عنوان G لا يعني إثبات "
            "ملكية المحفظة.",
            reply_markup=menu(user_id)
        )

    except Exception:
        log.exception("Save Stellar address error")

        bot.send_message(
            chat_id,
            "تعذر حفظ العنوان الآن."
        )


def check_wallet_trustline(chat_id, user_id):
    try:
        profile = profile_for(user_id)

        if not profile:
            bot.send_message(
                chat_id,
                "أرسل /start أولًا."
            )
            return

        address = (
            profile.get("stellar_public_address")
            or ""
        )

        if not valid_stellar_address(address):
            bot.send_message(
                chat_id,
                "⚠️ لم تربط عنوان G بعد.\n"
                "افتح المحفظة واضغط ربط عنوان G.",
                reply_markup=wallet_support_keyboard()
            )
            return

        result = stellar_account_info(address)

        if not result["ok"]:
            bot.send_message(
                chat_id,
                "⚠️ " + stellar_error_text(
                    result["reason"]
                ),
                reply_markup=wallet_support_keyboard()
            )
            return

        if result["trustline"]:
            bot.send_message(
                chat_id,
                "✅ تم العثور على خط ثقة EN96!\n\n"
                "🌐 Stellar Mainnet\n"
                f"🪙 الأصل: {EN96_ASSET}\n\n"
                "💎 رصيد المحفظة على Stellar:\n"
                f"{result['asset_balance']} EN96\n\n"
                "⚠️ هذا فحص عام، وليس إثبات ملكية."
            )
        else:
            bot.send_message(
                chat_id,
                "⚠️ حساب Stellar موجود، "
                "لكن خط ثقة EN96 غير موجود.\n\n"
                "افتح LOBSTR ثم Add Asset.\n"
                "ابحث عن EN96 بالمُصدر:\n\n"
                f"{EN96_ISSUER}\n\n"
                "وافق على إضافة الأصل من المحفظة.",
                reply_markup=wallet_support_keyboard()
            )

    except Exception:
        log.exception("Trustline check error")

        bot.send_message(
            chat_id,
            "تعذر فحص خط الثقة."
        )


# ==========================================
# WITHDRAWAL - MEMBER
# ==========================================

def start_withdrawal(chat_id, user_id):
    try:
        profile = profile_for(user_id)

        if not profile:
            bot.send_message(
                chat_id,
                "لم أجد حسابك.\nأرسل /start أولًا."
            )
            return

        balance = balance_for(profile["id"])

        if not balance:
            bot.send_message(
                chat_id,
                "تعذر العثور على رصيدك."
            )
            return

        available = Decimal(
            str(balance.get("available") or 0)
        )

        address = (
            profile.get("stellar_public_address")
            or ""
        )

        if available < MIN_WITHDRAWAL:
            bot.send_message(
                chat_id,
                "❌ الرصيد المتاح غير كافٍ.\n\n"
                f"رصيدك: {en96_number(available)} EN96\n"
                "الحد الأدنى: 500 EN96."
            )
            return

        existing = (
            db.table("withdrawal_requests")
            .select("id")
            .eq("user_id", profile["id"])
            .eq("status", "pending")
            .limit(1)
            .execute()
            .data or []
        )

        if existing:
            bot.send_message(
                chat_id,
                "⏳ لديك طلب سحب معلق بالفعل.\n"
                "افتح «📋 طلبات السحب» "
                "لمتابعة الطلب."
            )
            return

        if not valid_stellar_address(address):
            start_wallet_link(chat_id, user_id)
            return

        result = stellar_account_info(address)

        if not result["ok"]:
            bot.send_message(
                chat_id,
                "⚠️ لا يمكن بدء السحب.\n"
                + stellar_error_text(
                    result["reason"]
                )
            )
            return

        if not result["trustline"]:
            bot.send_message(
                chat_id,
                "⚠️ يجب إضافة خط ثقة EN96 "
                "إلى محفظتك أولًا.\n\n"
                f"المُصدر:\n{EN96_ISSUER}",
                reply_markup=wallet_support_keyboard()
            )
            return

        set_withdrawal_state(
            user_id,
            {
                "step": "amount",
                "address": address
            }
        )

        bot.send_message(
            chat_id,
            "💸 طلب سحب EN96\n"
            "━━━━━━━━━━━━━━\n\n"
            "🟢 الرصيد المتاح:\n"
            f"{en96_number(available)} EN96\n\n"
            "🟡 الحد الأدنى: 500 EN96\n\n"
            "🔗 عنوان الاستلام:\n"
            f"{address}\n\n"
            "✅ خط الثقة موجود.\n\n"
            "اكتب مبلغ السحب الآن.\n"
            "مثال: 500\n\n"
            "⚠️ تأكد أن هذا عنوان محفظتك."
        )

    except Exception:
        log.exception("Start withdrawal error")

        bot.send_message(
            chat_id,
            "تعذر بدء طلب السحب.\n"
            "لم يتم حجز رصيد جديد."
        )


def withdrawal_amount_input(
    chat_id,
    user_id,
    value
):
    amount = parse_amount(value)

    if amount is None:
        bot.send_message(
            chat_id,
            "❌ مبلغ غير صالح.\n\n"
            "الحد الأدنى: 500 EN96.\n"
            "أقصى دقة: 7 أرقام عشرية.\n\n"
            "أرسل المبلغ مجددًا أو /cancel."
        )
        return

    state = get_withdrawal_state(user_id)

    if not state or state.get("step") != "amount":
        return

    address = state.get("address", "")

    if not valid_stellar_address(address):
        clear_withdrawal_state(user_id)
        bot.send_message(
            chat_id,
            "عنوان Stellar غير صالح."
        )
        return

    set_withdrawal_state(
        user_id,
        {
            "step": "confirm",
            "amount": str(amount),
            "address": address
        }
    )

    kb = InlineKeyboardMarkup()

    kb.row(
        InlineKeyboardButton(
            "✅ تأكيد طلب السحب",
            callback_data="withdraw_confirm"
        ),
        InlineKeyboardButton(
            "❌ تراجع",
            callback_data="withdraw_abort"
        )
    )

    bot.send_message(
        chat_id,
        "👑 تأكيد سحب EN96\n"
        "━━━━━━━━━━━━━━\n\n"
        f"💎 المبلغ: {en96_number(amount)} EN96\n\n"
        f"🔗 المحفظة:\n{address}\n\n"
        "عند التأكيد سيُنقل المبلغ "
        "من المتاح إلى المحجوز.\n\n"
        "⚠️ لن تُرسل العملات فورًا.\n"
        "سيُراجع الطلب قبل الإرسال اليدوي.\n\n"
        "تأكد من صحة العنوان.",
        reply_markup=kb
    )


def confirm_withdrawal(chat_id, user_id):
    with WITHDRAWAL_LOCK:
        state = WITHDRAWAL_STATES.get(
            str(user_id)
        )

        if (
            not state
            or state.get("step") != "confirm"
        ):
            bot.send_message(
                chat_id,
                "لا يوجد طلب جاهز للتأكيد."
            )
            return

        # Prevent double-click duplicate requests.
        WITHDRAWAL_STATES[str(user_id)] = {
            **state,
            "step": "processing"
        }

    try:
        address = state["address"]
        amount = Decimal(state["amount"])

        # Check again before reserving.
        profile = profile_for(user_id)

        if not profile:
            raise ValueError("Account not found")

        if (
            profile.get("stellar_public_address")
            != address
        ):
            raise ValueError("Destination changed")

        check = stellar_account_info(address)

        if not check["ok"]:
            raise ValueError("Stellar verification unavailable")

        if not check["trustline"]:
            raise ValueError("EN96 trustline missing")

        # Existing Supabase function returns UUID.
        result = db.rpc(
            "en96_request_withdrawal",
            {
                "p_telegram_id": str(user_id),
                "p_amount": str(amount),
                "p_stellar_address": address
            }
        ).execute()

        request_id = result.data

        if isinstance(request_id, list):
            request_id = (
                request_id[0]
                if request_id else None
            )

        if not request_id:
            raise ValueError("Missing withdrawal request ID")

        clear_withdrawal_state(user_id)

        bot.send_message(
            chat_id,
            "✅ تم تسجيل طلب السحب!\n"
            "━━━━━━━━━━━━━━\n\n"
            f"💎 المبلغ: {en96_number(amount)} EN96\n\n"
            "🟡 الحالة: قيد المراجعة\n"
            "🔒 تم حجز المبلغ في Supabase.\n\n"
            f"🆔 رقم الطلب:\n{request_id}\n\n"
            "📌 العملات لم تُرسل بعد.\n"
            "سيتولى المسؤول مراجعة الطلب.",
            reply_markup=menu(user_id)
        )

        try:
            bot.send_message(
                int(ADMIN_ID),
                "👑 طلب سحب EN96 جديد\n\n"
                f"👤 Telegram ID: {user_id}\n"
                f"💎 المبلغ: {en96_number(amount)} EN96\n\n"
                f"🔗 عنوان الاستلام:\n{address}\n\n"
                f"🆔 الطلب:\n{request_id}\n\n"
                "⚠️ لا ترسل العملات مرتين.\n"
                "افتح لوحة إدارة السحوبات."
            )
        except Exception:
            log.exception("Admin notification error")

    except Exception as exc:
        clear_withdrawal_state(user_id)

        log.exception("Withdrawal request failed")

        bot.send_message(
            chat_id,
            "⚠️ لم يكتمل تأكيد طلب السحب.\n"
            "افتح «📋 طلبات السحب» "
            "وتحقق من وجود طلب معلق "
            "قبل المحاولة مجددًا.\n\n"
            "لم يتم إرسال أي عملات Stellar."
        )


def member_withdrawal_history(chat_id, user_id):
    try:
        profile = profile_for(user_id)

        if not profile:
            bot.send_message(
                chat_id,
                "أرسل /start أولًا."
            )
            return

        rows = (
            db.table("withdrawal_requests")
            .select(
                "id,amount,status,"
                "stellar_public_address"
            )
            .eq("user_id", profile["id"])
            .order("created_at", desc=True)
            .limit(10)
            .execute()
            .data or []
        )

        if not rows:
            bot.send_message(
                chat_id,
                "📋 لا توجد طلبات سحب حتى الآن."
            )
            return

        labels = {
            "pending": "⏳ قيد المراجعة",
            "paid": "✅ مدفوع",
            "cancelled": "❌ ملغى",
            "processing": "🔄 قيد المعالجة"
        }

        lines = [
            "🐻‍❄️ طلبات سحب EN96",
            "━━━━━━━━━━━━━━"
        ]

        for row in rows:
            status = row.get("status", "unknown")

            lines.append(
                "\n"
                f"🆔 {row.get('id')}\n"
                f"💎 {en96_number(row.get('amount'))} EN96\n"
                f"{labels.get(status, status)}"
            )

        bot.send_message(
            chat_id,
            "\n".join(lines)
        )

    except Exception:
        log.exception("Withdrawal history error")

        bot.send_message(
            chat_id,
            "تعذر تحميل طلبات السحب."
        )


# ==========================================
# ADMIN WITHDRAWALS
# ==========================================

def admin_withdrawals(chat_id, user_id):
    if (
        not is_admin(user_id)
        or str(chat_id) != str(user_id)
    ):
        bot.send_message(
            chat_id,
            "🔒 إدارة السحوبات خاصة بالمسؤول."
        )
        return

    try:
        rows = (
            db.table("withdrawal_requests")
            .select(
                "id,user_id,amount,status,"
                "stellar_public_address,created_at"
            )
            .eq("status", "pending")
            .order("created_at")
            .limit(20)
            .execute()
            .data or []
        )

        if not rows:
            bot.send_message(
                chat_id,
                "👑 إدارة السحوبات\n\n"
                "✅ لا توجد طلبات معلقة حاليًا.\n\n"
                "⚠️ التحقق من المدفوعات "
                "لم يُفعّل بعد."
            )
            return

        bot.send_message(
            chat_id,
            "👑 إدارة سحوبات EN96\n"
            "━━━━━━━━━━━━━━\n\n"
            f"📋 الطلبات المعلقة المعروضة: {len(rows)}\n\n"
            "راجع عنوان G والمبلغ.\n"
            "لا ترسل العملات دون سجل واضح.\n"
            "ولا تلغِ طلبًا بدأ تحويله."
        )

        for item in rows:
            request_id = str(item["id"])
            profile_id = item.get("user_id")

            telegram_id = "غير معروف"

            try:
                member = (
                    db.table("profiles")
                    .select("telegram_id")
                    .eq("id", profile_id)
                    .limit(1)
                    .execute()
                    .data or []
                )

                if member:
                    telegram_id = str(
                        member[0].get(
                            "telegram_id",
                            "غير معروف"
                        )
                    )
            except Exception:
                log.exception("Admin member lookup")

            kb = InlineKeyboardMarkup()

            kb.add(
                InlineKeyboardButton(
                    "🔍 فحص محفظة المستلم",
                    callback_data=(
                        "admin_check:" + request_id
                    )
                )
            )

            kb.add(
                InlineKeyboardButton(
                    "↩️ طلب إلغاء قبل الدفع",
                    callback_data=(
                        "admin_cancel:" + request_id
                    )
                )
            )

            bot.send_message(
                chat_id,
                "━━━━━━━━━━━━━━\n"
                "⏳ طلب سحب معلق\n\n"
                f"👤 Telegram: {telegram_id}\n\n"
                "💎 المبلغ:\n"
                f"{en96_number(item.get('amount'))} EN96\n\n"
                "🔗 المستلم:\n"
                f"{item.get('stellar_public_address')}\n\n"
                f"🆔 الطلب:\n{request_id}\n\n"
                "⚠️ لا يوجد تأكيد دفع آلي بعد.",
                reply_markup=kb
            )

    except Exception:
        log.exception("Admin withdrawals error")

        bot.send_message(
            chat_id,
            "تعذر تحميل لوحة السحوبات."
        )


def admin_check_withdrawal(
    chat_id,
    user_id,
    request_id
):
    if not is_admin(user_id):
        return

    try:
        rows = (
            db.table("withdrawal_requests")
            .select(
                "id,status,amount,"
                "stellar_public_address"
            )
            .eq("id", request_id)
            .limit(1)
            .execute()
            .data or []
        )

        if not rows:
            bot.send_message(
                chat_id,
                "الطلب غير موجود."
            )
            return

        item = rows[0]
        address = item["stellar_public_address"]

        result = stellar_account_info(address)

        if not result["ok"]:
            bot.send_message(
                chat_id,
                "⚠️ " + stellar_error_text(
                    result["reason"]
                )
            )
            return

        bot.send_message(
            chat_id,
            "🔍 فحص محفظة المستلم\n\n"
            f"🆔 الطلب: {request_id}\n"
            f"💎 المبلغ: {en96_number(item['amount'])}\n\n"
            "🛡️ خط الثقة:\n"
            + (
                "✅ موجود"
                if result["trustline"]
                else "❌ غير موجود"
            )
            + "\n\n"
            "⚠️ فحص خط الثقة لا يثبت ملكية "
            "المحفظة أو اكتمال الدفع."
        )

    except Exception:
        log.exception("Admin check withdrawal")

        bot.send_message(
            chat_id,
            "تعذر فحص المحفظة."
        )


def admin_cancel_prompt(
    chat_id,
    user_id,
    request_id
):
    if not is_admin(user_id):
        return

    try:
        rows = (
            db.table("withdrawal_requests")
            .select("id,status,amount")
            .eq("id", request_id)
            .limit(1)
            .execute()
            .data or []
        )

        if not rows or rows[0]["status"] != "pending":
            bot.send_message(
                chat_id,
                "لا يمكن إلغاء هذا الطلب."
            )
            return

        ADMIN_CANCEL_CONFIRM[str(user_id)] = request_id

        kb = InlineKeyboardMarkup()

        kb.row(
            InlineKeyboardButton(
                "✅ لم أرسل العملات، ألغِ الطلب",
                callback_data="admin_cancel_yes"
            ),
            InlineKeyboardButton(
                "❌ تراجع",
                callback_data="admin_cancel_no"
            )
        )

        bot.send_message(
            chat_id,
            "⚠️ تأكيد إلغاء سحب EN96\n\n"
            f"🆔 {request_id}\n"
            f"💎 {en96_number(rows[0]['amount'])} EN96\n\n"
            "لا توافق إلا إذا تأكدت أنك "
            "لم ترسل العملات ولم تبدأ "
            "عملية تحويل قد تكتمل لاحقًا.\n\n"
            "سيعود المبلغ إلى رصيد العضو المتاح.",
            reply_markup=kb
        )

    except Exception:
        log.exception("Admin cancel prompt error")

        bot.send_message(
            chat_id,
            "تعذر فتح تأكيد الإلغاء."
        )


def admin_cancel_execute(chat_id, user_id):
    if not is_admin(user_id):
        return

    request_id = ADMIN_CANCEL_CONFIRM.pop(
        str(user_id),
        None
    )

    if not request_id:
        bot.send_message(
            chat_id,
            "انتهى تأكيد الإلغاء."
        )
        return

    try:
        result = db.rpc(
            "en96_cancel_withdrawal",
            {
                "p_request_id": request_id
            }
        ).execute()

        if result.data != "cancelled":
            raise ValueError(
                "Unexpected cancellation response"
            )

        bot.send_message(
            chat_id,
            "✅ أُلغي طلب السحب.\n"
            "✅ أعادت Supabase المبلغ "
            "من المحجوز إلى المتاح.\n\n"
            f"🆔 {request_id}"
        )

    except Exception:
        log.exception("Cancel withdrawal failed")

        bot.send_message(
            chat_id,
            "⚠️ تعذر تأكيد الإلغاء.\n"
            "تحقق من حالة الطلب في Supabase."
        )


# ==========================================
# MINING
# ==========================================

def mining_keyboard():
    kb = InlineKeyboardMarkup()

    kb.add(
        InlineKeyboardButton(
            "🔄 تحديث التعدين",
            callback_data="mining_refresh"
        )
    )

    return kb


def mining_counter(
    chat_id,
    user_id,
    elapsed_before=0
):
    key = (chat_id, str(user_id))

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
            "🐻👑 منجم EN96\n\n"
            "⛏️ التعدين الافتراضي نشط.\n"
            "⚡ 0.001 EN96/ثانية\n"
            "⏱️ الجلسة: 24 ساعة\n\n"
            "العداد تقديري والرصيد تحدده Supabase.",
            reply_markup=mining_keyboard()
        )

    except Exception:
        log.exception("Counter send error")

        with MINING_LOCK:
            if MINING_COUNTERS.get(key) is stop_event:
                MINING_COUNTERS.pop(key, None)
        return

    def update():
        nonlocal started

        try:
            while not stop_event.is_set():
                elapsed = min(
                    max(
                        0,
                        int(time.time() - started)
                    ),
                    MINING_DURATION
                )

                estimate = elapsed * MINING_RATE

                hours, rest = divmod(elapsed, 3600)
                minutes, seconds = divmod(rest, 60)

                content = (
                    "🐻👑 منجم EN96\n\n"
                    "⛏️ التعدين الافتراضي نشط\n\n"
                    "💎 المكافأة التقديرية:\n"
                    f"{estimate:.7f} EN96\n\n"
                    "⏱️ الوقت:\n"
                    f"{hours:02d}:"
                    f"{minutes:02d}:"
                    f"{seconds:02d} / 24:00:00\n\n"
                    "⚡ 0.001 EN96/ثانية\n\n"
                    "⚠️ الرصيد الفعلي محفوظ في Supabase."
                )

                try:
                    bot.edit_message_text(
                        content,
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
                            "Mining counter update: %s",
                            exc
                        )

                if elapsed >= MINING_DURATION:
                    try:
                        data = rpc_data(
                            db.rpc(
                                "en96_mining_action",
                                {
                                    "p_telegram_id": str(user_id)
                                }
                            ).execute()
                        )

                        status = data.get("status")

                        if status == "rewarded_and_started":
                            bot.send_message(
                                chat_id,
                                "✅ أكدت Supabase إضافة "
                                f"{data.get('reward', 86.4)} "
                                "EN96.\nبدأت جلسة جديدة."
                            )

                            started = time.time()
                            continue

                        if status == "active":
                            remaining = max(
                                1,
                                int(
                                    data.get(
                                        "remaining_seconds", 1
                                    )
                                )
                            )

                            started = (
                                time.time()
                                - MINING_DURATION
                                + remaining
                            )
                            continue

                        bot.send_message(
                            chat_id,
                            "⚠️ لم يتم تأكيد المكافأة.\n"
                            "اضغط بدء التعدين للتحقق."
                        )
                        break

                    except Exception:
                        log.exception("Mining settlement error")
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


def mining(chat_id, user_id):
    try:
        if not profile_for(user_id):
            bot.send_message(
                chat_id,
                "لم أجد حسابك. أرسل /start أولًا."
            )
            return

        data = rpc_data(
            db.rpc(
                "en96_mining_action",
                {
                    "p_telegram_id": str(user_id)
                }
            ).execute()
        )

        status = data.get("status")

        if status == "started":
            mining_counter(chat_id, user_id)

        elif status == "rewarded_and_started":
            bot.send_message(
                chat_id,
                "✅ تمت إضافة "
                f"{data.get('reward', 86.4)} EN96 "
                "وبدأت جلسة تعدين جديدة."
            )

            mining_counter(chat_id, user_id)

        elif status == "active":
            remaining = max(
                0,
                min(
                    int(
                        data.get(
                            "remaining_seconds",
                            MINING_DURATION
                        )
                    ),
                    MINING_DURATION
                )
            )

            mining_counter(
                chat_id,
                user_id,
                MINING_DURATION - remaining
            )

        elif status == "profile_missing":
            bot.send_message(
                chat_id,
                "ملفك غير موجود في قاعدة البيانات."
            )

        elif status == "balance_missing":
            bot.send_message(
                chat_id,
                "سجل رصيدك غير موجود."
            )

        else:
            log.warning("Unexpected mining data: %s", data)

            bot.send_message(
                chat_id,
                "تعذر تأكيد حالة التعدين."
            )

    except Exception:
        log.exception("Mining error")

        bot.send_message(
            chat_id,
            "حدث خطأ في التعدين."
        )


# ==========================================
# REFERRALS AND TRIBE
# ==========================================

def referral_link(user_id):
    return (
        f"https://t.me/{BOT_USERNAME}"
        f"?start=ref_{user_id}"
    )


def record_referral(message):
    parts = (
        (message.text or "")
        .strip()
        .split(maxsplit=1)
    )

    if len(parts) != 2:
        return

    if parts[0].split("@")[0] != "/start":
        return

    payload = parts[1].strip()

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


def tribe(chat_id, user_id):
    link = referral_link(user_id)

    try:
        data = rpc_data(
            db.rpc(
                "en96_tribe_stats",
                {
                    "p_telegram_id": str(user_id)
                }
            ).execute()
        )

        if data.get("status") == "profile_missing":
            bot.send_message(
                chat_id,
                "لم أجد حسابك. أرسل /start أولًا."
            )
            return

        if data.get("status") != "ok":
            raise ValueError("Unexpected tribe response")

        friends = int(data.get("friends") or 0)

        invitation_bonus = en96_number(
            data.get("invitation_bonus")
        )

        commission = en96_number(
            data.get("mining_commission")
        )

        total = en96_number(
            data.get("total")
        )

        bot.send_message(
            chat_id,
            "🐻👑 قبيلة EN96\n"
            "━━━━━━━━━━━━━━\n\n"
            f"👥 عدد الأصدقاء: {friends}\n\n"
            "🎁 مكافآت الدعوات:\n"
            f"{invitation_bonus} EN96\n\n"
            "⛏️ عمولات تعدين الأصدقاء 5%:\n"
            f"{commission} EN96\n\n"
            "💎 مجموع مكافآت القبيلة:\n"
            f"{total} EN96\n\n"
            "🔗 رابط دعوتك:\n"
            f"{link}\n\n"
            "🎁 50 EN96 عند اكتمال "
            "أول جلسة مؤهلة للصديق.\n"
            "⛏️ 5% من مكافآت تعدين "
            "الأصدقاء المباشرين المؤكدة.\n\n"
            "⚠️ المكافآت حسب سجلات Supabase.",
            disable_web_page_preview=True
        )

    except Exception:
        log.exception("Tribe stats error")

        bot.send_message(
            chat_id,
            "🐻👑 قبيلة EN96\n\n"
            "تعذر تحميل الإحصائيات الآن.\n"
            f"رابط دعوتك:\n{link}",
            disable_web_page_preview=True
        )


# ==========================================
# VIDEO GIFTS
# ==========================================

def redeem_gift(message):
    uid = message.from_user.id
    code = (message.text or "").strip()

    WAITING_GIFT.discard(uid)

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
                f"{data.get('reward', 1)} "
                "EN96 بنجاح!"
            )
            return

        reason = (
            data.get("reason")
            or data.get("status")
            or "unknown"
        )

        errors = {
            "invalid_input": "الكود غير صالح.",
            "profile_not_found": "أرسل /start أولًا.",
            "invalid_or_inactive_code":
                "الكود غير موجود أو غير مفعل.",
            "already_claimed":
                "استعملت هذا الكود من قبل.",
            "cooldown_2_hours":
                "انتظر ساعتين قبل هدية أخرى.",
            "balance_not_found":
                "لم أجد سجل رصيدك."
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
            "تعذر التحقق من كود الهدية."
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
        log.exception("Show videos error")

        bot.send_message(
            chat_id,
            "تعذر تحميل الفيديوهات."
        )


# ==========================================
# ADMIN GIFTS
# ==========================================

def admin_create_code(message):
    uid = message.from_user.id

    if not is_admin(uid):
        return

    code = (message.text or "").strip()
    WAITING_ADMIN_CODE.discard(uid)

    if not code or len(code) > 120:
        bot.send_message(
            message.chat.id,
            "الكود غير صالح."
        )
        return

    PENDING[uid] = {"code": code}
    WAITING_ADMIN_VIDEO.add(uid)

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

    PENDING.setdefault(uid, {})[
        "video_url"
    ] = url

    WAITING_ADMIN_VIDEO.discard(uid)
    WAITING_ADMIN_REWARD.add(uid)

    bot.send_message(
        message.chat.id,
        "أرسل مقدار المكافأة، مثل 1."
    )


def admin_reward(message):
    uid = message.from_user.id

    if not is_admin(uid):
        return

    try:
        reward = float(
            (message.text or "")
            .strip()
            .replace(",", ".")
        )

        if reward <= 0:
            raise ValueError

    except ValueError:
        bot.send_message(
            message.chat.id,
            "أرسل رقمًا موجبًا."
        )
        return

    item = PENDING.get(uid, {})

    if (
        not item.get("code")
        or not item.get("video_url")
    ):
        WAITING_ADMIN_REWARD.discard(uid)
        bot.send_message(
            message.chat.id,
            "بيانات الهدية ناقصة."
        )
        return

    try:
        db.table("video_gift_codes").insert(
            {
                "code": item["code"],
                "video_url": item["video_url"],
                "reward": reward,
                "active": True,
                "description": "EN96 admin gift"
            }
        ).execute()

        bot.send_message(
            message.chat.id,
            "✅ تم إنشاء الكود "
            f"{item['code']} "
            f"بمكافأة {reward:g} EN96."
        )

    except Exception:
        log.exception("Create gift error")

        bot.send_message(
            message.chat.id,
            "تعذر إنشاء كود الهدية."
        )

    finally:
        WAITING_ADMIN_REWARD.discard(uid)
        PENDING.pop(uid, None)


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
        log.exception("List gifts error")

        bot.send_message(
            chat_id,
            "تعذر عرض الأكواد."
        )


def set_gift_active(message, active):
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
                "لم أجد هذا الكود."
            )

    except Exception:
        log.exception("Gift toggle error")

        bot.send_message(
            message.chat.id,
            "تعذر تغيير حالة الكود."
        )


# ==========================================
# SOCIAL LINKS
# ==========================================

def show_social(chat_id):
    kb = InlineKeyboardMarkup()

    kb.row(
        InlineKeyboardButton(
            "▶️ YouTube EN96",
            url=YOUTUBE_URL
        ),
        InlineKeyboardButton(
            "🎵 TikTok EN96",
            url=TIKTOK_URL
        )
    )

    bot.send_message(
        chat_id,
        "🐻👑 مجتمع EN96 الرسمي\n\n"
        "▶️ شاهد فيديوهات YouTube.\n"
        "🎵 تابع فيديوهات TikTok.\n"
        "🎁 ابحث عن أكواد الهدايا.\n\n"
        "يمكنك إدخال الأكواد الصحيحة "
        "داخل بوت EN96.",
        reply_markup=kb
    )


def show_tiktok(chat_id):
    kb = InlineKeyboardMarkup()

    kb.add(
        InlineKeyboardButton(
            "🎵 فتح TikTok الرسمي",
            url=TIKTOK_URL
        )
    )

    bot.send_message(
        chat_id,
        "🎵 TikTok الرسمي لمشروع EN96\n\n"
        "@en96mining",
        reply_markup=kb
    )


def show_youtube(chat_id):
    kb = InlineKeyboardMarkup()

    kb.add(
        InlineKeyboardButton(
            "▶️ فتح قناة YouTube",
            url=YOUTUBE_URL
        )
    )

    bot.send_message(
        chat_id,
        "▶️ قناة YouTube الرسمية لـ EN96\n\n"
        "@EN96_Gold_Miner_bo",
        reply_markup=kb
    )


# ==========================================
# TELEGRAM STARS - ADMIN ONLY
# ==========================================

def admin_stars_balance(
    chat_id,
    user_id,
    chat_type="private"
):
    if (
        not is_admin(user_id)
        or chat_type != "private"
        or str(chat_id) != str(user_id)
    ):
        bot.send_message(
            chat_id,
            "🔒 هذا القسم خاص بإدارة EN96."
        )
        return

    try:
        endpoint = (
            f"https://api.telegram.org/"
            f"bot{BOT_TOKEN}/getMyStarBalance"
        )

        request = Request(
            endpoint,
            data=b"{}",
            headers={
                "Content-Type": "application/json"
            },
            method="POST"
        )

        with urlopen(
            request,
            timeout=15
        ) as response:
            payload = json.loads(
                response.read().decode("utf-8")
            )

        if not payload.get("ok"):
            raise RuntimeError(
                "Telegram rejected getMyStarBalance"
            )

        result = payload.get("result") or {}

        whole = int(result.get("amount", 0))
        nano = int(
            result.get("nanostar_amount", 0)
        )

        amount = whole + nano / 1_000_000_000

        bot.send_message(
            chat_id,
            "👑 إدارة مملكة EN96\n"
            "━━━━━━━━━━━━━━\n\n"
            "⭐ رصيد نجوم البوت\n\n"
            f"💎 {amount:,.9f} Stars\n\n"
            "ℹ️ هذا رصيد Stars الخاص بالبوت، "
            "وليس رصيد حسابك الشخصي.\n\n"
            "⚠️ الرصيد لا يضمن أهلية السحب "
            "عبر Fragment."
        )

    except Exception:
        log.exception("Stars balance error")

        bot.send_message(
            chat_id,
            "⚠️ تعذر الحصول على رصيد Stars.\n"
            "تحقق من Render وحاول مجددًا."
        )


# ==========================================
# BOT COMMANDS
# ==========================================

@bot.message_handler(commands=["start", "menu"])
def start(message):
    if not is_private(message):
        bot.reply_to(
            message,
            "افتح EN96 في محادثة خاصة."
        )
        return

    uid = message.from_user.id
    chat_id = message.chat.id

    clear_withdrawal_state(uid)

    if not register_member(uid):
        bot.send_message(
            chat_id,
            "⚠️ تعذر تأكيد حسابك.\n"
            "حاول لاحقًا."
        )
        return

    parts = (
        (message.text or "")
        .strip()
        .split(maxsplit=1)
    )

    command = (
        parts[0].split("@")[0]
        if parts else ""
    )

    payload = (
        parts[1].strip()
        if len(parts) == 2
        else ""
    )

    if (
        command == "/start"
        and payload == "mining"
    ):
        mining(chat_id, uid)
        return

    if (
        command == "/start"
        and payload.startswith("ref_")
    ):
        record_referral(message)

    send_menu(
        chat_id,
        user_id=uid
    )


@bot.message_handler(commands=["cancel"])
def cancel_command(message):
    clear_withdrawal_state(message.from_user.id)

    WAITING_GIFT.discard(message.from_user.id)
    WAITING_ADMIN_CODE.discard(message.from_user.id)
    WAITING_ADMIN_VIDEO.discard(message.from_user.id)
    WAITING_ADMIN_REWARD.discard(message.from_user.id)

    ADMIN_ACTION.pop(message.from_user.id, None)
    PENDING.pop(message.from_user.id, None)

    bot.send_message(
        message.chat.id,
        "✅ تم إلغاء الإدخال الجاري.\n"
        "لم يتم إلغاء أي طلب سحب "
        "مسجل في Supabase.",
        reply_markup=menu(message.from_user.id)
    )


@bot.message_handler(commands=["wallet"])
def wallet_command(message):
    if is_private(message):
        wallet(
            message.chat.id,
            message.from_user.id
        )


@bot.message_handler(commands=["withdraw"])
def withdraw_command(message):
    if is_private(message):
        start_withdrawal(
            message.chat.id,
            message.from_user.id
        )


@bot.message_handler(commands=["withdrawals"])
def withdrawals_command(message):
    if is_private(message):
        member_withdrawal_history(
            message.chat.id,
            message.from_user.id
        )


@bot.message_handler(commands=["mining"])
def mining_command(message):
    if is_private(message):
        mining(
            message.chat.id,
            message.from_user.id
        )


@bot.message_handler(commands=["tribe"])
def tribe_command(message):
    if is_private(message):
        tribe(
            message.chat.id,
            message.from_user.id
        )


@bot.message_handler(commands=["stars"])
def stars_command(message):
    admin_stars_balance(
        message.chat.id,
        message.from_user.id,
        message.chat.type
    )


@bot.message_handler(commands=["tiktok"])
def tiktok_command(message):
    show_tiktok(message.chat.id)


@bot.message_handler(commands=["youtube"])
def youtube_command(message):
    show_youtube(message.chat.id)


@bot.message_handler(commands=["admin"])
def admin_command(message):
    if is_private(message) and is_admin(
        message.from_user.id
    ):
        admin_withdrawals(
            message.chat.id,
            message.from_user.id
        )
    else:
        bot.send_message(
            message.chat.id,
            "هذا الأمر مخصص للمسؤول."
        )


# ==========================================
# INLINE BUTTON HANDLER
# ==========================================

@bot.callback_query_handler(
    func=lambda call: True
)
def callback_handler(call):
    uid = call.from_user.id
    chat_id = call.message.chat.id
    data = call.data or ""

    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass

    if (
        call.message.chat.type != "private"
        or str(chat_id) != str(uid)
    ):
        return

    try:
        if data == "mining_refresh":
            mining(chat_id, uid)

        elif data == "withdraw_start":
            start_withdrawal(chat_id, uid)

        elif data == "wallet_link":
            start_wallet_link(chat_id, uid)

        elif data == "wallet_trustline":
            check_wallet_trustline(chat_id, uid)

        elif data == "withdraw_abort":
            clear_withdrawal_state(uid)

            bot.send_message(
                chat_id,
                "✅ تراجعت عن طلب السحب.\n"
                "لم يتم حجز مبلغ جديد."
            )

        elif data == "withdraw_confirm":
            confirm_withdrawal(chat_id, uid)

        elif (
            data.startswith("admin_check:")
            and is_admin(uid)
        ):
            request_id = data.split(":", 1)[1]

            admin_check_withdrawal(
                chat_id,
                uid,
                request_id
            )

        elif (
            data.startswith("admin_cancel:")
            and is_admin(uid)
        ):
            request_id = data.split(":", 1)[1]

            admin_cancel_prompt(
                chat_id,
                uid,
                request_id
            )

        elif (
            data == "admin_cancel_yes"
            and is_admin(uid)
        ):
            admin_cancel_execute(chat_id, uid)

        elif (
            data == "admin_cancel_no"
            and is_admin(uid)
        ):
            ADMIN_CANCEL_CONFIRM.pop(
                str(uid),
                None
            )

            bot.send_message(
                chat_id,
                "✅ لم يتم إلغاء الطلب."
            )

    except Exception:
        log.exception("Callback handler error")

        bot.send_message(
            chat_id,
            "⚠️ تعذر تنفيذ الأمر الآن."
        )


# ==========================================
# INPUT HANDLERS
# ==========================================

@bot.message_handler(
    func=lambda m: (
        is_private(m)
        and m.from_user.id in WAITING_GIFT
    ),
    content_types=["text"]
)
def gift_input(message):
    redeem_gift(message)


@bot.message_handler(
    func=lambda m: (
        is_private(m)
        and m.from_user.id in WAITING_ADMIN_CODE
        and ADMIN_ACTION.get(m.from_user.id)
        in ("enable", "disable")
    ),
    content_types=["text"]
)
def admin_toggle_input(message):
    uid = message.from_user.id

    if not is_admin(uid):
        return

    action = ADMIN_ACTION.pop(uid, None)
    WAITING_ADMIN_CODE.discard(uid)

    set_gift_active(
        message,
        active=(action == "enable")
    )


@bot.message_handler(
    func=lambda m: (
        is_private(m)
        and m.from_user.id in WAITING_ADMIN_CODE
    ),
    content_types=["text"]
)
def admin_code_input(message):
    if is_admin(message.from_user.id):
        admin_create_code(message)


@bot.message_handler(
    func=lambda m: (
        is_private(m)
        and m.from_user.id in WAITING_ADMIN_VIDEO
    ),
    content_types=["text"]
)
def admin_video_input(message):
    if is_admin(message.from_user.id):
        admin_video(message)


@bot.message_handler(
    func=lambda m: (
        is_private(m)
        and m.from_user.id in WAITING_ADMIN_REWARD
    ),
    content_types=["text"]
)
def admin_reward_input(message):
    if is_admin(message.from_user.id):
        admin_reward(message)


# Withdrawal text input

@bot.message_handler(
    func=lambda m: (
        is_private(m)
        and get_withdrawal_state(m.from_user.id)
        is not None
    ),
    content_types=["text"]
)
def withdrawal_input(message):
    uid = message.from_user.id
    chat_id = message.chat.id

    state = get_withdrawal_state(uid)

    if not state:
        return

    step = state.get("step")

    text_value = (
        message.text or ""
    ).strip()

    if step == "link_address":
        save_wallet_address(
            chat_id,
            uid,
            text_value
        )

    elif step == "amount":
        withdrawal_amount_input(
            chat_id,
            uid,
            text_value
        )

    elif step == "confirm":
        bot.send_message(
            chat_id,
            "اضغط زر تأكيد السحب "
            "أو تراجع من الرسالة السابقة."
        )

    elif step == "processing":
        bot.send_message(
            chat_id,
            "⏳ طلبك قيد المعالجة.\n"
            "تحقق من طلبات السحب."
        )


# ==========================================
# MAIN MENU HANDLER
# ==========================================

@bot.message_handler(content_types=["text"])
def menu_handler(message):
    if not is_private(message):
        return

    text_value = (
        message.text or ""
    ).strip()

    uid = message.from_user.id
    chat_id = message.chat.id

    if text_value == "⛏️ بدء التعدين":
        mining(chat_id, uid)

    elif text_value == "💰 محفظتي":
        wallet(chat_id, uid)

    elif text_value == "💸 سحب EN96":
        start_withdrawal(chat_id, uid)

    elif text_value == "📋 طلبات السحب":
        member_withdrawal_history(chat_id, uid)

    elif text_value == "👑 إدارة السحوبات":
        admin_withdrawals(chat_id, uid)

    elif text_value == "⭐ رصيد Stars للإدارة":
        admin_stars_balance(
            chat_id,
            uid,
            message.chat.type
        )

    elif text_value == "⚡ ترقية المنجم":
        bot.send_message(
            chat_id,
            "⚡ ترقيات المنجم لم تُفعّل بعد."
        )

    elif text_value == "🏆 المكافآت":
        bot.send_message(
            chat_id,
            "🏆 مكافآت EN96 الافتراضية.\n"
            "يمكنك جمع هدايا الفيديو "
            "ومكافآت القبيلة المؤهلة."
        )

    elif text_value == "🎵 TikTok EN96":
        show_tiktok(chat_id)

    elif text_value == "▶️ YouTube EN96":
        show_youtube(chat_id)

    elif text_value == "📺 مشاهدة الفيديوهات":
        show_videos(chat_id)

    elif text_value == "🎁 استلام الهدية":
        WAITING_GIFT.add(uid)

        bot.send_message(
            chat_id,
            "🎁 أرسل كود هدية الفيديو."
        )

    elif text_value in (
        "🐻 أعضاء القبيلة",
        "🐉 أعضاء القبيلة"
    ):
        tribe(chat_id, uid)

    elif text_value == "ℹ️ معلومات EN96":
        bot.send_message(
            chat_id,
            "🐻 EN96 Ice Bear Mining\n\n"
            "⛏️ التعدين افتراضي.\n"
            "⚡ 0.001 EN96 في الثانية.\n"
            "⏱️ الجلسة: 24 ساعة.\n"
            "💎 مكافأة الجلسة: 86.4 EN96.\n\n"
            "🎁 دعوة مؤهلة: 50 EN96.\n"
            "👥 عمولة تعدين الأصدقاء: 5%.\n\n"
            "💸 الحد الأدنى للسحب: 500 EN96.\n"
            "🌐 Stellar Mainnet.\n\n"
            "⚠️ ليس تعدين أجهزة حقيقيًا.\n"
            "السحب يحتاج مراجعة يدوية."
        )

    elif (
        text_value == "🛠️ إدارة الهدايا"
        and is_admin(uid)
    ):
        bot.send_message(
            chat_id,
            "🛠️ إدارة الهدايا",
            reply_markup=admin_menu()
        )

    elif (
        text_value == "➕ إنشاء كود هدية"
        and is_admin(uid)
    ):
        WAITING_ADMIN_CODE.add(uid)

        bot.send_message(
            chat_id,
            "أرسل كود الهدية الجديد."
        )

    elif (
        text_value == "📋 أكواد الهدايا"
        and is_admin(uid)
    ):
        list_gifts(chat_id)

    elif (
        text_value in (
            "⛔ تعطيل كود",
            "✅ تفعيل كود"
        )
        and is_admin(uid)
    ):
        ADMIN_ACTION[uid] = (
            "disable"
            if text_value == "⛔ تعطيل كود"
            else "enable"
        )

        WAITING_ADMIN_CODE.add(uid)

        bot.send_message(
            chat_id,
            "أرسل الكود المطلوب."
        )

    elif text_value == "🔙 القائمة الرئيسية":
        clear_withdrawal_state(uid)

        send_menu(
            chat_id,
            user_id=uid
        )

    elif text_value == "🌐 فتح تطبيق EN96":
        app_button(chat_id)

    else:
        send_menu(
            chat_id,
            "اختر زرًا من قائمة EN96.",
            user_id=uid
        )


# ==========================================
# START BOT
# ==========================================

if __name__ == "__main__":
    log.info("Starting EN96 Telegram bot")

    bot.infinity_polling(
        skip_pending=True,
        timeout=30,
        long_polling_timeout=30
    )
