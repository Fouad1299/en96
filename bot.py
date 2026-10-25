
MINING_RATE = 0.001
MINING_DURATION = 24 * 60 * 60
MINING_COUNTERS = {}
MINING_LOCK = threading.Lock()


def mining_counter(chat_id, telegram_id, started_at=None):
    """عداد مرئي فقط؛ لا يضيف أي رصيد إلى قاعدة البيانات."""
    key = (chat_id, str(telegram_id))

    with MINING_LOCK:
        old_event = MINING_COUNTERS.get(key)
        if old_event:
            old_event.set()

        stop_event = threading.Event()
        MINING_COUNTERS[key] = stop_event

    start_time = started_at if isinstance(started_at, (int, float)) else time.time()

    try:
        msg = bot.send_message(
            chat_id,
            "🐉 منجم التنين الجليدي\n"
            "⛏️ التعدين الافتراضي نشط\n"
            "💎 المكافأة المعروضة: 0.0000000 EN96\n"
            "⏱️ الوقت: 00:00:00 / 24:00:00\n\n"
            "المعدل: 0.001 EN96/ثانية\n"
            "هذا عداد تقديري للعرض، وليس تأكيدًا لرصيد مستحق."
        )
    except Exception:
        log.exception("Could not send mining counter")
        return

    def update_counter():
        try:
            while not stop_event.is_set():
                elapsed = min(max(0, int(time.time() - start_time)),
                              MINING_DURATION)
                reward = elapsed * MINING_RATE
                hours = elapsed // 3600
                minutes = (elapsed % 3600) // 60
                seconds = elapsed % 60

                text = (
                    "🐉 منجم التنين الجليدي\n"
                    "⛏️ التعدين الافتراضي نشط\n"
                    f"💎 المكافأة المعروضة: {reward:.7f} EN96\n"
                    f"⏱️ الوقت: {hours:02d}:{minutes:02d}:{seconds:02d} / 24:00:00\n\n"
                    "المعدل: 0.001 EN96/ثانية\n"
                    "⚠️ هذا عداد تقديري للعرض فقط؛ الرصيد الفعلي "
                    "تحدده قاعدة بيانات Supabase."
                )

                try:
                    bot.edit_message_text(
                        text,
                        chat_id=chat_id,
                        message_id=msg.message_id
                    )
                except Exception as exc:
                    # نتجاهل خطأ عدم وجود تغيير في النص
                    if "message is not modified" not in str(exc).lower():
                        log.warning("Mining counter update: %s", exc)

                if elapsed >= MINING_DURATION:
                    bot.send_message(
                        chat_id,
                        "⏰ انتهى وقت العرض البالغ 24 ساعة.\n"
                        "استخدم زر بدء التعدين لمعرفة حالة الجلسة "
                        "وتحديثها من قاعدة البيانات."
                    )
                    break

                if stop_event.wait(5):
                    break
        finally:
            with MINING_LOCK:
                if MINING_COUNTERS.get(key) is stop_event:
                    MINING_COUNTERS.pop(key, None)

    threading.Thread(target=update_counter, daemon=True).start()


def mining(chat_id, telegram_id):
    try:
        if not profile_for(telegram_id):
            bot.send_message(
                chat_id,
                "لم أجد ملفك. افتح تطبيق EN96 وسجّل الدخول أولًا."
            )
            return

        data = rpc_data(
            db.rpc(
                "en96_mining_action",
                {"p_telegram_id": str(telegram_id)}
            ).execute()
        )

        status = (
            data.get("status")
            or data.get("reason")
            or data.get("message")
        )

        if status in ("started", "rewarded_and_started"):
            mining_counter(chat_id, telegram_id)
            return

        if status == "active":
            # لا نعرف وقت بدء الجلسة من الرد الحالي؛ لذلك يبدأ
            # العداد المرئي من لحظة فتحه، ولا ندّعي أنه وقت الجلسة الأصلي.
            mining_counter(chat_id, telegram_id)
            return

        if status == "profile_missing":
            bot.send_message(chat_id, "لم أجد ملفك في قاعدة البيانات.")
        elif status == "balance_missing":
            bot.send_message(chat_id, "لم أجد سجل رصيدك.")
        elif data.get("ok") is True:
            bot.send_message(
                chat_id,
                "تم تنفيذ طلب التعدين:\n"
                + json.dumps(data, ensure_ascii=False)
            )
        else:
            log.warning("Unexpected mining response: %r", data)
            bot.send_message(
                chat_id,
                "لم أتمكن من تأكيد حالة التعدين. راجع سجلات Render."
            )

    except Exception:
        log.exception("mining error")
        bot.send_message(
            chat_id,
            "حدث خطأ في التعدين. حاول لاحقًا."
        )
