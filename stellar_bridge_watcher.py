
import os
import json
import time
import logging
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# EN96 Ice Bear Kingdom
# Stellar Bridge Watcher - Read Only
# No private keys, no minting, no transfers

HORIZON_URL = "https://horizon.stellar.org"

ESCROW_ADDRESS = (
    "GCLZAUUMJHXSEGO5KQEIX5IMEVW3766CRG5TFR4PPUKTR5JUYXJDFM4O"
)

ASSET_CODE = "EN96"

# Set this to the verified EN96 Stellar issuer.
# Never use an unverified issuer.
ASSET_ISSUER = os.getenv(
    "EN96_STELLAR_ISSUER", ""
).strip()

STATE_FILE = Path("stellar_bridge_state.json")
POLL_SECONDS = 30

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

log = logging.getLogger("EN96BridgeWatcher")


def horizon_get(path, params=None):
    query = urlencode(params or {})
    url = HORIZON_URL + path

    if query:
        url += "?" + query

    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "EN96BridgeWatcher/0.1"
        }
    )

    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def load_state():
    if not STATE_FILE.exists():
        return {
            "cursor": None,
            "deposits": {}
        }

    with STATE_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_state(state):
    temp_file = STATE_FILE.with_suffix(".tmp")

    with temp_file.open("w", encoding="utf-8") as file:
        json.dump(
            state,
            file,
            indent=2,
            ensure_ascii=False
        )

    temp_file.replace(STATE_FILE)


def is_valid_deposit(operation):
    if operation.get("type") != "payment":
        return False

    if operation.get("to") != ESCROW_ADDRESS:
        return False

    if operation.get("asset_type") != "credit_alphanum4":
        return False

    if operation.get("asset_code") != ASSET_CODE:
        return False

    if operation.get("asset_issuer") != ASSET_ISSUER:
        return False

    try:
        amount = Decimal(operation.get("amount", "0"))
    except Exception:
        return False

    if not amount.is_finite() or amount <= 0:
        return False

    if amount.as_tuple().exponent < -7:
        return False

    return True


def record_deposit(operation, state):
    operation_id = str(operation["id"])

    if operation_id in state["deposits"]:
        return

    transaction_hash = operation.get("transaction_hash")

    if not transaction_hash:
        log.warning("Missing transaction hash: %s", operation_id)
        return

    deposit = {
        "operation_id": operation_id,
        "transaction_hash": transaction_hash,
        "source_account": operation.get("from"),
        "destination": operation.get("to"),
        "asset_code": ASSET_CODE,
        "asset_issuer": ASSET_ISSUER,
        "amount": operation.get("amount"),
        "created_at": operation.get("created_at"),
        "status": "observed_unverified"
    }

    state["deposits"][operation_id] = deposit

    log.info(
        "Observed EN96 payment: operation=%s amount=%s",
        operation_id,
        deposit["amount"]
    )


def poll_once(state):
    params = {
        "limit": 100,
        "order": "asc",
        "include_failed": "false"
    }

    if state["cursor"]:
        params["cursor"] = state["cursor"]
    else:
        # Start at the latest ledger, not historical deposits.
        params["cursor"] = "now"

    data = horizon_get(
        f"/accounts/{ESCROW_ADDRESS}/operations",
        params
    )

    records = data.get("_embedded", {}).get("records", [])

    for operation in records:
        if is_valid_deposit(operation):
            record_deposit(operation, state)

        state["cursor"] = operation["paging_token"]
        save_state(state)

    return len(records)


def main():
    if not ASSET_ISSUER:
        raise RuntimeError(
            "EN96_STELLAR_ISSUER is missing. "
            "Configure the verified Stellar issuer first."
        )

    state = load_state()

    log.info("EN96 Stellar watcher started")
    log.info("Escrow: %s", ESCROW_ADDRESS)
    log.info("Issuer: %s", ASSET_ISSUER)
    log.info("Read-only monitoring enabled")

    while True:
        try:
            count = poll_once(state)
            log.info("Checked %s operations", count)
        except Exception:
            log.exception("Watcher error")

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
