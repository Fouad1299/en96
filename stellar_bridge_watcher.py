
# EN96 Ice Bear Kingdom
# Stellar Mainnet Bridge Watcher
# Version 0.4 - Read Only
#
# Checks:
# - EN96 asset and issuer
# - Escrow trustline
# - Successful incoming EN96 payments
# - Transaction hash and operation index
# - Duplicate detection within a scan
#
# No private keys, no transfers, no BNB minting.

import json
import os
import sys
import time
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

HORIZON = "https://horizon.stellar.org"

ASSET_CODE = "EN96"

ISSUER = (
    "GCUGIICUGBFC3KBPIFYAMPNA7OVJHGY277TNYTZUSG7EVVUCVACH3OGB"
)

ESCROW = (
    "GCLZAUUMJHXSEGO5KQEIX5IMEVW3766CRG5TFR4PPUKTR5JUYXJDFM4O"
)

MAX_SUPPLY = Decimal("90000000000")

# Scan the most recent escrow operations.
# This is a bounded audit, not a continuous watcher.
MAX_PAGES = 5
PAGE_SIZE = 100


def get_json(path, params=None):
    url = HORIZON.rstrip("/") + path

    if params:
        url += "?" + urlencode(params)

    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "EN96-Bridge-Watcher/0.4"
        }
    )

    try:
        with urlopen(request, timeout=25) as response:
            return json.load(response)
    except HTTPError as error:
        raise RuntimeError(
            f"Horizon HTTP error {error.code}: {path}"
        ) from error
    except URLError as error:
        raise RuntimeError(
            f"Horizon connection error: {error.reason}"
        ) from error


def amount_decimal(value):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"Invalid amount: {value}")

    if not result.is_finite() or result < 0:
        raise ValueError(f"Invalid amount: {value}")

    return result


def check_asset():
    print("\nChecking EN96 asset...")

    response = get_json(
        "/assets",
        {
            "asset_code": ASSET_CODE,
            "asset_issuer": ISSUER,
            "limit": 1
        }
    )

    records = response.get("_embedded", {}).get(
        "records", []
    )

    if not records:
        print("FAIL: EN96 asset not found")
        return False

    asset = records[0]

    if (
        asset.get("asset_code") != ASSET_CODE
        or asset.get("asset_issuer") != ISSUER
    ):
        print("FAIL: Asset identity mismatch")
        return False

    balances = asset.get("balances", {})

    if not isinstance(balances, dict):
        print("FAIL: Invalid balances response")
        return False

    total = sum(
        (amount_decimal(v) for v in balances.values()),
        Decimal("0")
    )

    print("PASS: EN96 asset found")
    print("Issuer:", ISSUER)
    print("Stellar reported total:", total)

    if total > MAX_SUPPLY:
        print("FAIL: Stellar amount exceeds planned cap")
        return False

    print("PASS: Stellar amount within planned cap")
    return True


def check_escrow():
    print("\nChecking escrow account...")

    account = get_json("/accounts/" + ESCROW)

    for balance in account.get("balances", []):
        if (
            balance.get("asset_code") == ASSET_CODE
            and balance.get("asset_issuer") == ISSUER
        ):
            amount = amount_decimal(
                balance.get("balance", "0")
            )

            print("PASS: Escrow trustline exists")
            print("Escrow EN96 balance:", amount)
            return True

    print("FAIL: EN96 escrow trustline missing")
    return False


def get_transaction(tx_hash):
    if not tx_hash:
        raise ValueError("Missing transaction hash")

    return get_json("/transactions/" + tx_hash)


def get_transaction_operations(tx_hash):
    operations = []
    cursor = None

    while True:
        params = {
            "limit": 200,
            "order": "asc"
        }

        if cursor:
            params["cursor"] = cursor

        response = get_json(
            "/transactions/" + tx_hash + "/operations",
            params
        )

        records = response.get(
            "_embedded", {}
        ).get("records", [])

        if not records:
            break

        operations.extend(records)

        if len(records) < 200:
            break

        next_cursor = records[-1].get("paging_token")

        if not next_cursor or next_cursor == cursor:
            raise RuntimeError(
                "Transaction operation pagination stalled"
            )

        cursor = next_cursor

    return operations


def is_en96_payment(operation):
    return (
        operation.get("type") == "payment"
        and operation.get("to") == ESCROW
        and operation.get("asset_code") == ASSET_CODE
        and operation.get("asset_issuer") == ISSUER
        and operation.get("asset_type") == "credit_alphanum4"
        and amount_decimal(
            operation.get("amount", "0")
        ) > 0
    )


def scan_escrow():
    print("\nScanning recent escrow operations...")

    cursor = None
    seen = set()
    transaction_cache = {}
    operation_cache = {}

    scanned = 0
    deposits = []

    for page in range(MAX_PAGES):
        params = {
            "limit": PAGE_SIZE,
            "order": "desc",
            "include_failed": "false"
        }

        if cursor:
            params["cursor"] = cursor

        response = get_json(
            "/accounts/" + ESCROW + "/operations",
            params
        )

        records = response.get(
            "_embedded", {}
        ).get("records", [])

        if not records:
            break

        for operation in records:
            scanned += 1

            if not is_en96_payment(operation):
                continue

            tx_hash = operation.get("transaction_hash")

            if not tx_hash:
                raise RuntimeError(
                    "Payment operation has no transaction hash"
                )

            if tx_hash not in transaction_cache:
                transaction_cache[tx_hash] = (
                    get_transaction(tx_hash)
                )

            transaction = transaction_cache[tx_hash]

            if transaction.get("successful") is not True:
                print("SKIP: Unsuccessful transaction")
                continue

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
                    "Could not determine operation index"
                )

            deposit_id = (
                tx_hash + ":" + str(operation_index)
            )

            if deposit_id in seen:
                continue

            seen.add(deposit_id)

            deposit = {
                "deposit_id": deposit_id,
                "transaction_hash": tx_hash,
                "operation_index": operation_index,
                "operation_id": str(operation["id"]),
                "source_account": operation.get("from"),
                "destination": ESCROW,
                "amount": str(
                    amount_decimal(operation["amount"])
                ),
                "asset_code": ASSET_CODE,
                "asset_issuer": ISSUER,
                "ledger": transaction.get("ledger"),
                "created_at": operation.get("created_at"),
                "status": "observed_unverified"
            }

            deposits.append(deposit)

            print(
                "OBSERVED:",
                deposit["deposit_id"],
                "amount:",
                deposit["amount"]
            )

        if len(records) < PAGE_SIZE:
            break

        next_cursor = records[-1].get("paging_token")

        if not next_cursor or next_cursor == cursor:
            raise RuntimeError(
                "Escrow pagination stalled"
            )

        cursor = next_cursor

    print("Operations scanned:", scanned)
    print("EN96 deposits observed:", len(deposits))

    # Print results only. Do not store permanent claims
    # or authorize minting.
    if deposits:
        print(
            "OBSERVED_DEPOSITS_JSON:",
            json.dumps(deposits, ensure_ascii=False)
        )

    return deposits


def main():
    print("=" * 55)
    print("EN96 ICE BEAR KINGDOM")
    print("STELLAR MAINNET - READ ONLY WATCHER")
    print("=" * 55)

    if not check_asset():
        print("RESULT: ASSET VERIFICATION FAILED")
        return 1

    if not check_escrow():
        print("RESULT: ESCROW VERIFICATION FAILED")
        return 1

    deposits = scan_escrow()

    print("\nRESULT: READ-ONLY SCAN COMPLETED")
    print("Observed deposits:", len(deposits))
    print("No transfers or minting performed")
    print("Bridge remains disabled")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(
            "WATCHER ERROR:",
            type(error).__name__,
            str(error)
        )
        sys.exit(1)
