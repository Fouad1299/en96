
# EN96 Ice Bear Kingdom
# Stellar Mainnet Bridge Watcher
# Version 0.5 - Observed Deposit Recorder
#
# Checks Stellar asset, escrow and successful payments.
# Records observed deposits in Supabase PostgreSQL.
# No private keys, no transfers, no BNB minting.
# Never automatically marks a deposit as verified.

import json
import os
import sys
from datetime import datetime
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
MAX_PAGES = 5
PAGE_SIZE = 100

DB_HOST = "aws-0-eu-west-1.pooler.supabase.com"
DB_PORT = 5432
DB_NAME = "postgres"
DB_USER = (
    "en96_bridge_writer.zfoanswefwufsifncrhl"
)


def get_json(path, params=None):
    url = HORIZON.rstrip("/") + path

    if params:
        url += "?" + urlencode(params)

    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "EN96-Bridge-Watcher/0.5"
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

    records = response.get(
        "_embedded", {}
    ).get("records", [])

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
        print("FAIL: Invalid asset balances")
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

            source = operation.get("from")
            operation_id = operation.get("id")

            if not source or not operation_id:
                raise RuntimeError(
                    "Payment source or operation ID missing"
                )

            amount = amount_decimal(
                operation["amount"]
            )

            ledger = transaction.get("ledger")
            created_at = operation.get("created_at")

            deposit = {
                "deposit_id": deposit_id,
                "stellar_tx_hash": tx_hash,
                "operation_index": operation_index,
                "stellar_operation_id": str(operation_id),
                "source_account": source,
                "escrow_account": ESCROW,
                "asset_code": ASSET_CODE,
                "asset_issuer": ISSUER,
                "amount": amount,
                "stellar_ledger": ledger,
                "stellar_created_at": created_at,
                "status": "observed"
            }

            deposits.append(deposit)

            print(
                "OBSERVED:",
                deposit_id,
                "amount:",
                amount
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

    return deposits


def parse_timestamp(value):
    if value is None:
        return None

    return datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )


def same_deposit(existing, deposit):
    (
        operation_id,
        source,
        escrow,
        asset_code,
        issuer,
        amount,
        ledger,
        created_at
    ) = existing

    expected_created_at = parse_timestamp(
        deposit["stellar_created_at"]
    )

    return (
        operation_id == deposit["stellar_operation_id"]
        and source == deposit["source_account"]
        and escrow == deposit["escrow_account"]
        and asset_code == deposit["asset_code"]
        and issuer == deposit["asset_issuer"]
        and amount == deposit["amount"]
        and ledger == deposit["stellar_ledger"]
        and created_at == expected_created_at
    )


def record_deposits(deposits):
    if not deposits:
        print("No deposits to record")
        return

    password = os.getenv("EN96_BRIDGE_DB_PASSWORD")
    ca_file = os.getenv("EN96_SUPABASE_CA_FILE")

    if not password:
        raise RuntimeError(
            "Missing EN96_BRIDGE_DB_PASSWORD"
        )

    if not ca_file or not os.path.isfile(ca_file):
        raise RuntimeError(
            "Missing trusted Supabase CA file"
        )

    try:
        import psycopg
    except ImportError as error:
        raise RuntimeError(
            "Install psycopg[binary] first"
        ) from error

    print("\nConnecting to Supabase...")

    inserted = 0
    already_present = 0

    with psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=password,
        sslmode="verify-full",
        sslrootcert=ca_file,
        connect_timeout=10
    ) as connection:

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT current_user"
            )

            current_user = cursor.fetchone()[0]

            if current_user != "en96_bridge_writer":
                raise RuntimeError(
                    "Unexpected database role"
                )

            for deposit in deposits:
                # First inspect any existing record.
                # Do not change status or overwrite data.
                cursor.execute(
                    """
                    SELECT
                        stellar_operation_id,
                        source_account,
                        escrow_account,
                        asset_code,
                        asset_issuer,
                        amount,
                        stellar_ledger,
                        stellar_created_at
                    FROM public.en96_bridge_deposits
                    WHERE stellar_tx_hash = %s
                      AND operation_index = %s
                    """,
                    (
                        deposit["stellar_tx_hash"],
                        deposit["operation_index"]
                    )
                )

                existing = cursor.fetchone()

                if existing is not None:
                    if not same_deposit(existing, deposit):
                        raise RuntimeError(
                            "Conflicting deposit data: "
                            + deposit["deposit_id"]
                        )

                    already_present += 1
                    continue

                # Only an observed record is inserted.
                # No minting authorization is created.
                cursor.execute(
                    """
                    INSERT INTO public.en96_bridge_deposits (
                        stellar_tx_hash,
                        operation_index,
                        stellar_operation_id,
                        source_account,
                        escrow_account,
                        asset_code,
                        asset_issuer,
                        amount,
                        stellar_ledger,
                        stellar_created_at,
                        status
                    )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        'observed'
                    )
                    ON CONFLICT (
                        stellar_tx_hash,
                        operation_index
                    )
                    DO NOTHING
                    RETURNING id
                    """,
                    (
                        deposit["stellar_tx_hash"],
                        deposit["operation_index"],
                        deposit["stellar_operation_id"],
                        deposit["source_account"],
                        deposit["escrow_account"],
                        deposit["asset_code"],
                        deposit["asset_issuer"],
                        deposit["amount"],
                        deposit["stellar_ledger"],
                        parse_timestamp(
                            deposit["stellar_created_at"]
                        )
                    )
                )

                result = cursor.fetchone()

                if result is not None:
                    inserted += 1
                    print(
                        "RECORDED:",
                        deposit["deposit_id"]
                    )
                else:
                    # Another writer may have inserted the
                    # same transaction concurrently.
                    cursor.execute(
                        """
                        SELECT
                            stellar_operation_id,
                            source_account,
                            escrow_account,
                            asset_code,
                            asset_issuer,
                            amount,
                            stellar_ledger,
                            stellar_created_at
                        FROM public.en96_bridge_deposits
                        WHERE stellar_tx_hash = %s
                          AND operation_index = %s
                        """,
                        (
                            deposit["stellar_tx_hash"],
                            deposit["operation_index"]
                        )
                    )

                    existing = cursor.fetchone()

                    if (
                        existing is None
                        or not same_deposit(existing, deposit)
                    ):
                        raise RuntimeError(
                            "Conflicting concurrent deposit: "
                            + deposit["deposit_id"]
                        )

                    already_present += 1

    print("New records:", inserted)
    print("Existing matching records:", already_present)
    print("All new records remain observed")


def main():
    print("=" * 55)
    print("EN96 ICE BEAR KINGDOM")
    print("STELLAR MAINNET WATCHER - VERSION 0.5")
    print("=" * 55)

    if not check_asset():
        print("RESULT: ASSET VERIFICATION FAILED")
        return 1

    if not check_escrow():
        print("RESULT: ESCROW VERIFICATION FAILED")
        return 1

    deposits = scan_escrow()

    # Database writes must be explicitly enabled.
    if os.getenv("EN96_RECORD_DEPOSITS") == "1":
        record_deposits(deposits)
        print("\nRESULT: OBSERVATION RECORDING COMPLETED")
    else:
        print("\nRESULT: READ-ONLY SCAN COMPLETED")
        print("Database recording disabled")

    print("Observed deposits:", len(deposits))
    print("No transfers or BNB minting performed")
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
