
import logging
import threading
import uuid

log = logging.getLogger("EN96.accounts")
lock = threading.RLock()


class RegistrationError(Exception):
    pass


def ensure_profile(db, telegram_id):
    tid = str(telegram_id)

    if not tid.isdigit():
        raise RegistrationError(
            "معرّف تيليغرام غير صالح."
        )

    with lock:
        try:
            existing = (
                db.table("profiles")
                .select(
                    "id,telegram_id,stellar_public_address"
                )
                .eq("telegram_id", tid)
                .limit(1)
                .execute().data or []
            )

            if existing:
                profile = existing[0]

            else:
                new_id = str(uuid.uuid4())

                try:
                    inserted = (
                        db.table("profiles")
                        .insert({
                            "id": new_id,
                            "telegram_id": tid
                        })
                        .execute().data or []
                    )

                    profile = (
                        inserted[0]
                        if inserted
                        else {
                            "id": new_id,
                            "telegram_id": tid,
                            "stellar_public_address": None
                        }
                    )

                except Exception:
                    retry = (
                        db.table("profiles")
                        .select(
                            "id,telegram_id,stellar_public_address"
                        )
                        .eq("telegram_id", tid)
                        .limit(1)
                        .execute().data or []
                    )

                    if not retry:
                        raise RegistrationError(
                            "تعذّر إنشاء حساب EN96."
                        )

                    profile = retry[0]

            balances = (
                db.table("balances")
                .select("user_id")
                .eq("user_id", profile["id"])
                .limit(1)
                .execute().data or []
            )

            if not balances:
                try:
                    db.table("balances").insert({
                        "user_id": profile["id"],
                        "available": 0,
                        "reserved": 0
                    }).execute()

                except Exception:
                    retry = (
                        db.table("balances")
                        .select("user_id")
                        .eq("user_id", profile["id"])
                        .limit(1)
                        .execute().data or []
                    )

                    if not retry:
                        raise RegistrationError(
                            "تعذّر إنشاء سجل الرصيد."
                        )

            return profile

        except RegistrationError:
            raise

        except Exception as exc:
            log.exception(
                "EN96 account registration failed"
            )

            raise RegistrationError(
                "تعذّر الاتصال بقاعدة البيانات."
            ) from exc
