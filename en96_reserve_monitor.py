import json
import logging
import os
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# EN96 Ice Bear Kingdom
# Stellar reserve monitor - READ ONLY
# No private keys, signing, minting, or transactions.

HORIZON_URL = "https://horizon.stellar.org"

RESERVE_ACCOUNT = (
    "GCLZAUUMJHXSEGO5KQEIX5IMEVW3766CRG5TFR4PPUKTR5JUYXJDFM4O"
)
EN96_ISSUER = (
    "GCUGIICUGBFC3KBPIFYAMPNA7OVJHGY277TNYTZUSG7EVVUCVACH3OGB"
)
EN96_CODE = "EN96"
EXPECTED_RESERVE = Decimal("90000000000.0000000")

EXPECTED_THRESHOLDS = {
    "low_threshold": 20,
    "med_threshold": 20,
    "high_threshold": 20,
}

EXPECTED_SIGNERS = {
    RESERVE_ACCOUNT: 10,
    "GDWL3WLXNNMGXJKSVLFBRNAT344GFDL4TAWUSFEURZM3GVTOSLFOJPSM": 10,
    "GA2T6GR7VXXXBETTERSAFETHANSORRYXXXPROTECTEDBYLOBSTRVAULT": 1,
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("EN96_RESERVE_MONITOR")


def fetch_account():
    url = HORIZON_URL + "/accounts/" + RESERVE_ACCOUNT
    request = Request(
        url,
        headers={"Accept": "application/json"},
        method="GET",
    )
    with urlopen(request, timeout=20) as response:
        return json.load(response)


def check_reserve():
    timestamp = datetime.now(timezone.utc).isoformat()
    result = {
        "timestamp": timestamp,
        "account": RESERVE_ACCOUNT,
        "network": "Stellar Mainnet",
        "status": "ALERT",
        "issues": [],
    }

    try:
        account = fetch_account()

        balances = [
            balance
            for balance in account.get("balances", [])
            if balance.get("asset_code") == EN96_CODE
            and balance.get("asset_issuer") == EN96_ISSUER
        ]

        if len(balances) != 1:
            result["issues"].append("EN96 reserve asset not found")
        else:
            amount = Decimal(balances[0]["balance"])
            result["balance_en96"] = str(amount)

            if amount < EXPECTED_RESERVE:
                result["issues"].append(
                    "CRITICAL: reserve balance below 90 billion EN96"
                )
            elif amount > EXPECTED_RESERVE:
                result["issues"].append(
                    "Reserve balance differs from expected amount"
                )

            if balances[0].get("is_authorized") is False:
                result["issues"].append(
                    "EN96 trustline is not authorized"
                )

        thresholds = account.get("thresholds", {})
        for key, expected in EXPECTED_THRESHOLDS.items():
            if thresholds.get(key) != expected:
                result["issues"].append(
                    "Threshold changed: " + key
                )

        actual_signers = {
            signer["key"]: signer["weight"]
            for signer in account.get("signers", [])
        }

        if actual_signers != EXPECTED_SIGNERS:
            result["issues"].append(
                "CRITICAL: reserve account signers changed"
            )

        if not result["issues"]:
            result["status"] = "OK"

    except (
        HTTPError,
        URLError,
        TimeoutError,
        ValueError,
        KeyError,
        InvalidOperation,
        OSError,
    ) as exc:
        result["issues"].append(
            "Unable to verify Stellar reserve: "
            + type(exc).__name__
        )

    return result


def run_monitor():
    interval = max(
        60,
        int(os.getenv("EN96_MONITOR_INTERVAL", "300")),
    )

    log.info("EN96 read-only reserve monitor started")

    while True:
        result = check_reserve()
        message = json.dumps(result, ensure_ascii=False)

        if result["status"] == "OK":
            log.info(message)
        else:
            log.error(message)

        time.sleep(interval)


if __name__ == "__main__":
    run_monitor()
