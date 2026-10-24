@app.post("/api/redeem-gift")
def api_redeem_gift():
    user, error = telegram_user()
    if error:
        return jsonify({"error": error}), 401

    body = request.get_json(silent=True) or {}
    code = body.get("code", "")

    if not isinstance(code, str) or not code.strip() or len(code) > 100:
        return jsonify({
            "success": False,
            "error": "أدخل كود هدية صالحًا."
        }), 400

    try:
        result = en96_bot.db.rpc(
            "redeem_en96_video_gift",
            {
                "p_telegram_id": user["id"],
                "p_code": code.strip()
            }
        ).execute()

        data = result.data

        if isinstance(data, list) and data:
            data = data[0]

        if isinstance(data, str):
            try:
                data = json.loads(data)
            except (ValueError, TypeError):
                data = {"status": data}

        if not isinstance(data, dict):
            data = {}

        gift_status = str(data.get("status", "")).lower()

        # لا نعلن نجاح الهدية إلا إذا أكدت الدالة قبولها.
        if gift_status in ("claimed", "success", "redeemed"):
            return jsonify({
                "success": True,
                "status": gift_status,
                "message": "🎉 تم قبول الهدية."
            }), 200

        messages = {
            "invalid_code": "كود الهدية غير صحيح.",
            "not_found": "كود الهدية غير موجود.",
            "inactive": "كود الهدية متوقف.",
            "already_claimed": "لقد استخدمت هذا الكود سابقًا.",
            "already_redeemed": "لقد استخدمت هذا الكود سابقًا.",
            "expired": "انتهت صلاحية كود الهدية."
        }

        message = messages.get(
            gift_status,
            "لم تؤكد قاعدة البيانات قبول الهدية. تحقق من نتيجة الدالة."
        )

        return jsonify({
            "success": False,
            "status": gift_status or "unknown",
            "message": message
        }), 200

    except Exception:
        logger.exception("Gift redemption RPC failed")
        return jsonify({
            "success": False,
            "error": "تعذر التحقق من الكود. حاول لاحقًا."
        }), 500
