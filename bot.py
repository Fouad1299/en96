@bot.message_handler(func=lambda m: m.text == "➕ إنشاء هدية")
def admin_create_button(message):
    if not is_admin(message):
        bot.reply_to(message, "⛔ غير مسموح.")
        return
    prompt = bot.send_message(message.chat.id, "أرسل كود الهدية الجديد:")
    bot.register_next_step_handler(prompt, admin_create_code_step)


@bot.message_handler(func=lambda m: m.text == "📋 قائمة الهدايا")
def admin_list_button(message):
    admin_list_gifts(message)


@bot.message_handler(func=lambda m: m.text == "⏸️ إيقاف هدية")
def admin_disable_button(message):
    if not is_admin(message):
        bot.reply_to(message, "⛔ غير مسموح.")
        return
    prompt = bot.send_message(message.chat.id, "أرسل الكود الذي تريد إيقافه:")
    bot.register_next_step_handler(prompt, admin_set_code_active, False)


@bot.message_handler(func=lambda m: m.text == "▶️ تفعيل هدية")
def admin_enable_button(message):
    if not is_admin(message):
        bot.reply_to(message, "⛔ غير مسموح.")
        return
    prompt = bot.send_message(message.chat.id, "أرسل الكود الذي تريد تفعيله:")
    bot.register_next_step_handler(prompt, admin_set_code_active, True)
