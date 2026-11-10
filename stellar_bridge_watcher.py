
# EN96 Ice Bear Kingdom
# Stellar Mainnet Bridge Watcher
# Version 0.6 - Safer Observation and Validation
#
# READ-ONLY by default.
# No private keys, no Stellar transfers, no BNB minting.
# Never automatically verifies or authorizes a deposit.
#
# IMPORTANT:
# Recording remains blocked until a persistent cursor
# and complete historical synchronization are implemented.

import json
import os
import re
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


VERSION = "0.6"

HORIZON = "https://horizon.stellar.org"
ASSET_CODE = "EN96"

ISSUER = (
    "GCUGIICUGBFC3KBPIFYAMPNA7OVJHGY277TNYTZUSG7EVVUCVACH3OGB"
)

ESCROW = (
    "GCLZAUUMJHXSEGO5KQEIX5IMEVW3766CRG5TFR4PPUKTR5JUYXJDFM4O"
)

MAX_SUPPLY = Decimal("90000000000")

MAX_PAGES = 5
PAGE_SIZE = 100
MAX_TRANSACTION_PAGES = 20

DB_HOST = "aws-0-eu-west-1.pooler.supabase.com"
DB_PORT = 5432
DB_NAME = "postgres"

DB_USER = (
    "en96_bridge_writer.zfoanswefwufsifncrhl"
)

HASH_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
ADDRESS_PATTERN = re.compile(r"^G[A-Z2-7]{55}$")
OPERATION_ID_PATTERN = re.compile(r"^[0-9]+$")

# This version does not have a persistent checkpoint.
# Database recording must remain disabled.
RECORDING_SUPPORTED = False


def get_json(path, params=None):
    if not path.startswith("/"):
        raise ValueError("Invalid Horizon path")

    url = HORIZON.rstrip("/") + path

    if params:
        url += "?" + urlencode(params)

    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "EN96-Bridge-Watcher/0.6",
        },
    )

    try:
        with urlopen(request, timeout=25) as response:
            data = json.load(response)

    except HTTPError as error:
        raise RuntimeError(
            f"Horizon HTTP error {error.code}: {path}"
        ) from error

    except URLError as error:
        raise RuntimeError(
            f"Horizon connection error: {error.reason}"
        ) from error

    if not isinstance(data, dict):
        raise RuntimeError("Invalid Horizon response")

    return data


def get_records(response):
    embedded = response.get("_embedded")

    if not isinstance(embedded, dict):
        raise RuntimeError("Missing Horizon embedded data")

    records = embedded.get("records")

    if not isinstance(records, list):
        raise RuntimeError("Invalid Horizon records")

    return records


def amount_decimal(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Invalid EN96 amount")

    if not amount.is_finite():
        raise ValueError("Non-finite EN96 amount")

    if amount < 0:
        raise ValueError("Negative EN96 amount")

    # EN96 uses seven decimal places.
    if amount.as_tuple().exponent < -7:
        raise ValueError("Too many EN96 decimals")

    return amount


def valid_address(value):
    return (
        isinstance(value, str)
        and ADDRESS_PATTERN.fullmatch(value) is not None
    )


def valid_hash(value):
    return (
        isinstance(value, str)
        and HASH_PATTERN.fullmatch(value) is not None
    )


def parse_timestamp(value):
    if not isinstance(value, str):
        raise ValueError("Missing Stellar timestamp")

    try:
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError as error:
        raise ValueError(
            "Invalid Stellar timestamp"
        ) from error

    if parsed.tzinfo is None:
        raise ValueError("Timezone missing")

    return parsed.astimezone(timezone.utc)


def check_asset():
    print("\nChecking EN96 asset...")

    response = get_json(
        "/assets",
        {
            "asset_code": ASSET_CODE,
            "asset_issuer": ISSUER,
            "limit": 1,
        },
    )

    records = get_records(response)

    if not records:
        raise RuntimeError("EN96 asset not found")

    asset = records[0]

    if (
        asset.get("asset_code") != ASSET_CODE
        or asset.get("asset_issuer") != ISSUER
    ):
        raise RuntimeError("Asset identity mismatch")

    balances = asset.get("balances")

    if not isinstance(balances, dict):
        raise RuntimeError("Invalid asset balances")

    total = sum(
        (amount_decimal(v) for v in balances.values()),
        Decimal("0"),
    )

    if total > MAX_SUPPLY:
        raise RuntimeError(
            "Stellar reported amount exceeds planned cap"
        )

    print("PASS: EN96 asset found")
    print("Issuer:", ISSUER)
    print("Stellar reported total:", total)
    print("PASS: Stellar amount within planned cap")

    # This is not proof of the combined Stellar + BNB
    # circulating supply.
    print(
        "NOTICE: Unified cross-chain supply "
        "is not verified by this check"
    )

    return True


def check_escrow():
    print("\nChecking escrow account...")

    if not valid_address(ESCROW):
        raise RuntimeError("Invalid escrow address")

    account = get_json("/accounts/" + ESCROW)

    if account.get("account_id") != ESCROW:
        raise RuntimeError("Escrow identity mismatch")

    balances = account.get("balances")

    if not isinstance(balances, list):
        raise RuntimeError("Invalid escrow balances")

    for balance in balances:
        if (
            balance.get("asset_code") == ASSET_CODE
            and balance.get("asset_issuer") == ISSUER
        ):
            amount = amount_decimal(
                balance.get("balance")
            )

            print("PASS: Escrow trustline exists")
            print("Escrow EN96 balance:", amount)

            return True

    raise RuntimeError("Escrow EN96 trustline missing")


def get_transaction(tx_hash):
    if not valid_hash(tx_hash):
        raise ValueError("Invalid transaction hash")

    transaction = get_json(
        "/transactions/" + tx_hash
    )

    if transaction.get("hash", "").lower() != (
        tx_hash.lower()
    ):
        raise RuntimeError("Transaction hash mismatch")

    if transaction.get("successful") is not True:
        raise RuntimeError(
            "Transaction was not successful"
        )

    ledger = transaction.get("ledger")

    if (
        isinstance(ledger, bool)
        or not isinstance(ledger, int)
        or ledger <= 0
    ):
        raise RuntimeError("Invalid transaction ledger")

    return transaction


def get_transaction_operations(tx_hash):
    operations = []
    cursor = None
    previous_cursor = None
    complete = False

    for page in range(MAX_TRANSACTION_PAGES):
        params = {
            "limit": 200,
            "order": "asc",
        }

        if cursor is not None:
            params["cursor"] = cursor

        response = get_json(
            "/transactions/" + tx_hash + "/operations",
            params,
        )

        records = get_records(response)

        if not records:
            complete = True
            break

        for operation in records:
            if not operation.get("id"):
                raise RuntimeError(
                    "Transaction operation missing ID"
                )

        operations.extend(records)

        if len(records) < 200:
            complete = True
            break

        next_cursor = records[-1].get(
            "paging_token"
        )

        if (
            not next_cursor
            or next_cursor == cursor
            or next_cursor == previous_cursor
        ):
            raise RuntimeError(
                "Transaction pagination stalled"
            )

        previous_cursor = cursor
        cursor = next_cursor

    if not complete:
        raise RuntimeError(
            "Transaction operation scan incomplete"
        )

    if not operations:
        raise RuntimeError(
            "Transaction has no operations"
        )

    return operations


def is_en96_payment(operation):
    if operation.get("type") != "payment":
        return False

    if operation.get("to") != ESCROW:
        return False

    if operation.get("asset_code") != ASSET_CODE:
        return False

    if operation.get("asset_issuer") != ISSUER:
        return False

    if operation.get("asset_type") != (
        "credit_alphanum4"
    ):
        return False

    return amount_decimal(
        operation.get("amount")
    ) > 0


def validate_payment(operation, transaction):
    tx_hash = operation.get("transaction_hash")
    operation_id = str(operation.get("id", ""))
    source = operation.get("from")

    if not valid_hash(tx_hash):
        raise RuntimeError(
            "Invalid payment transaction hash"
        )

    if not OPERATION_ID_PATTERN.fullmatch(
        operation_id
    ):
        raise RuntimeError(
            "Invalid Stellar operation ID"
        )

    if not valid_address(source):
        raise RuntimeError(
            "Invalid payment source account"
        )

    if not valid_address(operation.get("to")):
        raise RuntimeError(
            "Invalid payment destination"
        )

    if not is_en96_payment(operation):
        raise RuntimeError(
            "Payment does not match EN96 escrow"
        )

    amount = amount_decimal(operation["amount"])

    if amount <= 0:
        raise RuntimeError(
            "Deposit amount must be positive"
        )

    created_at = operation.get("created_at")
    parsed_time = parse_timestamp(created_at)

    tx_time = transaction.get("created_at")

    if tx_time is not None:
        if parse_timestamp(tx_time) != parsed_time:
            raise RuntimeError(
                "Operation and transaction times differ"
            )

    return {
        "stellar_tx_hash": tx_hash,
        "stellar_operation_id": operation_id,
        "source_account": source,
        "escrow_account": ESCROW,
        "asset_code": ASSET_CODE,
        "asset_issuer": ISSUER,
        "amount": amount,
        "stellar_ledger": transaction["ledger"],
        "stellar_created_at": created_at,
        "status": "observed",
    }


def scan_escrow():
    print("\nScanning escrow operations...")

    cursor = None
    seen = set()

    transaction_cache = {}
    operation_cache = {}

    deposits = []
    scanned = 0
    complete = False

    for page in range(MAX_PAGES):
        params = {
            "limit": PAGE_SIZE,
            "order": "desc",
            "include_failed": "false",
        }

        if cursor:
            params["cursor"] = cursor

        response = get_json(
            "/accounts/" + ESCROW + "/operations",
            params,
        )

        records = get_records(response)

        if not records:
            complete = True
            break

        for operation in records:
            scanned += 1

            if not is_en96_payment(operation):
                continue

            tx_hash = operation.get(
                "transaction_hash"
            )

            if not valid_hash(tx_hash):
                raise RuntimeError(
                    "Payment transaction hash invalid"
                )

            if tx_hash not in transaction_cache:
                transaction_cache[tx_hash] = (
                    get_transaction(tx_hash)
                )

            transaction = transaction_cache[tx_hash]

            if tx_hash not in operation_cache:
                operation_cache[tx_hash] = (
                    get_transaction_operations(tx_hash)
                )

            tx_operations = operation_cache[tx_hash]

            operation_index = None

            for index, tx_operation in enumerate(
                tx_operations
            ):
                if (
                    str(tx_operation.get("id"))
                    == str(operation.get("id"))
                ):
                    operation_index = index
                    break

            if operation_index is None:
                raise RuntimeError(
                    "Operation index not found"
                )

            deposit = validate_payment(
                operation,
                transaction,
            )

            deposit["operation_index"] = (
                operation_index
            )

            deposit["deposit_id"] = (
                tx_hash + ":" + str(operation_index)
            )

            if deposit["deposit_id"] in seen:
                continue

            seen.add(deposit["deposit_id"])
            deposits.append(deposit)

            print(
                "OBSERVED:",
                deposit["deposit_id"],
                "amount:",
                deposit["amount"],
            )

        if len(records) < PAGE_SIZE:
            complete = True
            break

        next_cursor = records[-1].get(
            "paging_token"
        )

        if (
            not next_cursor
            or next_cursor == cursor
        ):
            raise RuntimeError(
                "Escrow pagination stalled"
            )

        cursor = next_cursor

    print("Operations scanned:", scanned)
    print("EN96 deposits observed:", len(deposits))

    if complete:
        print(
            "PASS: Reached end of available "
            "escrow operation history"
        )
    else:
        print(
            "WARNING: Scan stopped at configured "
            "page limit"
        )
        print(
            "WARNING: Older deposits may exist "
            "outside this scan"
        )

    return deposits, complete


def same_deposit(existing, deposit):
    (
        operation_id,
        source,
        escrow,
        asset_code,
        issuer,
        amount,
        ledger,
        created_at,
    ) = existing

    expected_time = parse_timestamp(
        deposit["stellar_created_at"]
    )

    return (
        operation_id
        == deposit["stellar_operation_id"]
        and source == deposit["source_account"]
        and escrow == deposit["escrow_account"]
        and asset_code == deposit["asset_code"]
        and issuer == deposit["asset_issuer"]
        and amount == deposit["amount"]
        and ledger == deposit["stellar_ledger"]
        and created_at == expected_time
    )


def record_deposits(deposits):
    # Safety gate for version 0.6.
    # A persistent checkpoint is required before
    # production recording can be enabled.

    if not RECORDING_SUPPORTED:
        raise RuntimeError(
            "Database recording blocked in v0.6: "
            "persistent cursor and historical "
            "synchronization are not implemented"
        )

    # The recording implementation is intentionally
    # unreachable until a later reviewed version
    # explicitly enables it.
    raise RuntimeError(
        "Recording implementation not enabled"
    )


def main():
    print("=" * 55)
    print("EN96 ICE BEAR KINGDOM")
    print(
        "STELLAR MAINNET WATCHER - VERSION",
        VERSION,
    )
    print("=" * 55)

    # Refuse any accidental attempt to activate writes.
    if os.getenv("EN96_RECORD_DEPOSITS") == "1":
        raise RuntimeError(
            "EN96_RECORD_DEPOSITS=1 is not allowed "
            "in watcher version 0.6"
        )

    check_asset()
    check_escrow()

    deposits, complete = scan_escrow()

    print("\nRESULT: READ-ONLY SCAN COMPLETED")
    print("Observed deposits:", len(deposits))
    print("History fully scanned:", complete)
    print("Database recording disabled")
    print("No Stellar transfers performed")
    print("No BNB minting performed")
    print("Bridge remains disabled")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())

    except Exception as error:
        print(
            "WATCHER ERROR:",
            type(error).__name__,
            str(error),
        )
        sys.exit(1)
