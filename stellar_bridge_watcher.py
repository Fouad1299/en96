
import os
import re
import json
import logging
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

import psycopg


# ============================================
# EN96 ICE BEAR KINGDOM
# Stellar Mainnet Watcher - Version 0.7
#
# READ-ONLY STELLAR SCAN
# PERSISTENT DATABASE CHECKPOINT
#
# Deposit recording: DISABLED
# BNB minting: DISABLED
# Stellar transfers: DISABLED
# ============================================

VERSION = "0.7"

HORIZON = "https://horizon.stellar.org"

ASSET_CODE = "EN96"

ASSET_ISSUER = (
    "GCUGIICUGBFC3KBPIFYAMPNA7OVJHGY277TNYTZUSG7EVVUCVACH3OGB"
)

ESCROW_ACCOUNT = (
    "GCLZAUUMJHXSEGO5KQEIX5IMEVW3766CRG5TFR4PPUKTR5JUYXJDFM4O"
)

WATCHER_NAME = "stellar_escrow_v1"

MAX_SUPPLY = Decimal("90000000000")

PAGE_SIZE = 100
MAX_PAGES = 5

RECORDING_SUPPORTED = False
BNB_MINTING_SUPPORTED = False

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s"
)

log = logging.getLogger("EN96-WATCHER")


def get_json(path, params=None):
    url = HORIZON + path

    if params:
        url += "?" + urlencode(params)

    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "EN96-Stellar-Watcher/0.7"
        }
    )

    try:
        with urlopen(request, timeout=30) as response:
            data = json.load(response)

    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(
            "Horizon request failed: " + str(exc)
        ) from exc

    if not isinstance(data, dict):
        raise RuntimeError("Invalid Horizon response")

    return data


def get_records(data):
    embedded = data.get("_embedded")

    if not isinstance(embedded, dict):
        raise RuntimeError("Missing embedded data")

    records = embedded.get("records")

    if not isinstance(records, list):
        raise RuntimeError("Missing records list")

    return records


def parse_amount(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise RuntimeError("Invalid amount")

    if not amount.is_finite():
        raise RuntimeError("Non-finite amount")

    if amount < 0:
        raise RuntimeError("Negative amount")

    if amount.as_tuple().exponent < -7:
        raise RuntimeError("Too many decimal places")

    return amount


def valid_address(value):
    return (
        isinstance(value, str)
        and re.fullmatch(
            r"G[A-Z2-7]{55}",
            value
        ) is not None
    )


def valid_hash(value):
    return (
        isinstance(value, str)
        and re.fullmatch(
            r"[0-9a-fA-F]{64}",
            value
        ) is not None
    )


def valid_token(value):
    return (
        isinstance(value, str)
        and re.fullmatch(
            r"[0-9]+",
            value
        ) is not None
    )


def check_asset():
    data = get_json(
        "/assets",
        {
            "asset_code": ASSET_CODE,
            "asset_issuer": ASSET_ISSUER,
            "limit": 1
        }
    )

    records = get_records(data)

    matching = [
        item for item in records
        if item.get("asset_code") == ASSET_CODE
        and item.get("asset_issuer") == ASSET_ISSUER
    ]

    if not matching:
        raise RuntimeError(
            "EN96 asset not found on Stellar Mainnet"
        )

    asset = matching[0]

    balances = asset.get("balances", {})

    if not isinstance(balances, dict):
        raise RuntimeError("Invalid asset balances")

    total = Decimal("0")

    for value in balances.values():
        if value is not None:
            total += parse_amount(value)

    if total > MAX_SUPPLY:
        raise RuntimeError(
            "Reported Stellar amount exceeds planned cap"
        )

    print("PASS: EN96 asset found")
    print("Stellar reported total:", total)
    print(
        "NOTICE: Unified cross-chain supply "
        "is not verified"
    )


def check_escrow():
    if not valid_address(ESCROW_ACCOUNT):
        raise RuntimeError("Invalid escrow address")

    data = get_json(
        "/accounts/" + ESCROW_ACCOUNT
    )

    balances = data.get("balances")

    if not isinstance(balances, list):
        raise RuntimeError("Invalid escrow balances")

    for balance in balances:
        if (
            balance.get("asset_code") == ASSET_CODE
            and balance.get("asset_issuer") == ASSET_ISSUER
        ):
            amount = parse_amount(
                balance.get("balance")
            )

            print("PASS: Escrow trustline exists")
            print("Escrow EN96 balance:", amount)

            return

    raise RuntimeError(
        "Escrow EN96 trustline missing"
    )


def database_connection():
    password = (
        os.getenv("PGPASSWORD")
        or os.getenv("EN96_BRIDGE_DB_PASSWORD")
    )

    host = os.getenv(
        "PGHOST",
        "aws-0-eu-west-1.pooler.supabase.com"
    )

    port = os.getenv("PGPORT", "5432")

    database = os.getenv(
        "PGDATABASE",
        "postgres"
    )

    user = os.getenv(
        "PGUSER",
        "en96_bridge_writer.zfoanswefwufsifncrhl"
    )

    certificate = (
        os.getenv("PGSSLROOTCERT")
        or os.getenv("EN96_CA_CERT_PATH")
    )

    if not password:
        raise RuntimeError(
            "Database password environment "
            "variable is missing"
        )

    if not certificate:
        raise RuntimeError(
            "Database CA certificate path is missing"
        )

    if not os.path.isfile(certificate):
        raise RuntimeError(
            "Database CA certificate file not found"
        )

    return psycopg.connect(
        host=host,
        port=port,
        dbname=database,
        user=user,
        password=password,
        sslmode="verify-full",
        sslrootcert=certificate,
        connect_timeout=15,
        autocommit=False
    )


def read_checkpoint(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT paging_token
            FROM public.en96_bridge_checkpoints
            WHERE watcher_name = %s
            ORDER BY
                length(paging_token) DESC,
                paging_token DESC
            LIMIT 1
            """,
            (WATCHER_NAME,)
        )

        row = cur.fetchone()

    conn.commit()

    if row is None:
        print(
            "NOTICE: No checkpoint found. "
            "Starting from earliest history."
        )
        return "0"

    token = row[0]

    if not valid_token(token):
        raise RuntimeError(
            "Invalid stored checkpoint"
        )

    print("PASS: Stored checkpoint loaded")
    print("Checkpoint:", token)

    return token


def save_checkpoint(conn, token):
    if not valid_token(token):
        raise RuntimeError(
            "Refusing invalid checkpoint"
        )

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO public.en96_bridge_checkpoints
                (watcher_name, paging_token)
            VALUES (%s, %s)
            ON CONFLICT
                (watcher_name, paging_token)
            DO NOTHING
            """,
            (WATCHER_NAME, token)
        )

    conn.commit()

    print("PASS: Checkpoint saved:", token)


def is_en96_deposit(operation):
    if operation.get("type") != "payment":
        return False

    if operation.get("to") != ESCROW_ACCOUNT:
        return False

    if operation.get("asset_type") != "credit_alphanum4":
        return False

    if operation.get("asset_code") != ASSET_CODE:
        return False

    if operation.get("asset_issuer") != ASSET_ISSUER:
        return False

    amount = parse_amount(
        operation.get("amount")
    )

    if amount <= 0:
        raise RuntimeError(
            "Invalid EN96 deposit amount"
        )

    return True


def verify_deposit(operation):
    tx_hash = operation.get("transaction_hash")

    operation_id = operation.get("id")

    source = operation.get("from")

    if not valid_hash(tx_hash):
        raise RuntimeError(
            "Invalid transaction hash"
        )

    if not valid_token(operation_id):
        raise RuntimeError(
            "Invalid operation ID"
        )

    if not valid_address(source):
        raise RuntimeError(
            "Invalid deposit source address"
        )

    transaction = get_json(
        "/transactions/" + tx_hash
    )

    if (
        str(transaction.get("hash", "")).lower()
        != tx_hash.lower()
    ):
        raise RuntimeError(
            "Transaction hash mismatch"
        )

    if transaction.get("successful") is not True:
        raise RuntimeError(
            "Deposit transaction not successful"
        )

    ledger = transaction.get("ledger")

    if (
        not isinstance(ledger, int)
        or isinstance(ledger, bool)
        or ledger <= 0
    ):
        raise RuntimeError(
            "Invalid transaction ledger"
        )

    print(
        "EN96 deposit detected:",
        "operation =", operation_id,
        "amount =", operation.get("amount"),
        "ledger =", ledger
    )


def scan_escrow(conn):
    cursor = read_checkpoint(conn)

    total_scanned = 0
    pages_scanned = 0
    reached_end = False

    while pages_scanned < MAX_PAGES:
        data = get_json(
            "/accounts/"
            + ESCROW_ACCOUNT
            + "/operations",
            {
                "cursor": cursor,
                "order": "asc",
                "limit": PAGE_SIZE,
                "include_failed": "false"
            }
        )

        records = get_records(data)

        if not records:
            reached_end = True
            break

        previous_token = cursor
        deposits_in_page = 0

        for operation in records:
            token = operation.get("paging_token")

            if not valid_token(token):
                raise RuntimeError(
                    "Operation has invalid paging token"
                )

            if int(token) <= int(previous_token):
                raise RuntimeError(
                    "Non-increasing operation cursor"
                )

            previous_token = token

            total_scanned += 1

            if is_en96_deposit(operation):
                deposits_in_page += 1
                verify_deposit(operation)

        if deposits_in_page:
            raise RuntimeError(
                "EN96 deposit found. "
                "Checkpoint NOT advanced. "
                "Deposit recording remains disabled. "
                "Manual review required."
            )

        # Save only after every operation in the
        # page was checked successfully.
        #
        # Pages containing EN96 deposits are
        # deliberately NOT checkpointed.
        save_checkpoint(conn, previous_token)

        cursor = previous_token
        pages_scanned += 1

        if len(records) < PAGE_SIZE:
            reached_end = True
            break

    print("Operations scanned:", total_scanned)
    print("Pages scanned:", pages_scanned)
    print("Reached available history end:", reached_end)

    if not reached_end:
        print(
            "NOTICE: Page limit reached. "
            "Next run will resume from checkpoint."
        )

    return total_scanned, reached_end


def main():
    print("=" * 48)
    print(
        "EN96 STELLAR MAINNET WATCHER "
        "- VERSION " + VERSION
    )
    print("=" * 48)

    if os.getenv("EN96_RECORD_DEPOSITS") == "1":
        raise RuntimeError(
            "Deposit recording is disabled"
        )

    if os.getenv("EN96_ENABLE_BNB_MINT") == "1":
        raise RuntimeError(
            "BNB minting is disabled"
        )

    check_asset()
    check_escrow()

    with database_connection() as conn:
        scanned, completed = scan_escrow(conn)

    print("=" * 48)
    print("RESULT: CHECKPOINT SCAN COMPLETED")
    print("Operations scanned:", scanned)
    print("History end reached:", completed)
    print("Database checkpoint enabled")
    print("Deposit recording disabled")
    print("No Stellar transfers performed")
    print("No BNB minting performed")
    print("Bridge remains disabled")
    print("=" * 48)


if __name__ == "__main__":
    main()
