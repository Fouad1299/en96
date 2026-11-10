
import os
import re
import json
import logging
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

import psycopg


# ==============================================
# EN96 ICE BEAR KINGDOM
# Stellar Mainnet Watcher - Version 0.8
#
# Verified deposit detection / dry-run
# Persistent checkpoint
#
# NO deposit database recording
# NO Stellar transfers
# NO BNB minting
# ==============================================

VERSION = "0.8"

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
TX_PAGE_SIZE = 200
MAX_TX_PAGES = 20

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s"
)

log = logging.getLogger("EN96-WATCHER")


def require_disabled_features():
    if os.getenv("EN96_RECORD_DEPOSITS") == "1":
        raise RuntimeError(
            "Deposit recording is not supported"
        )

    if os.getenv("EN96_ENABLE_BNB_MINT") == "1":
        raise RuntimeError(
            "BNB minting is not supported"
        )


def valid_token(value):
    return (
        isinstance(value, str)
        and re.fullmatch(r"[0-9]+", value) is not None
    )


def valid_hash(value):
    return (
        isinstance(value, str)
        and re.fullmatch(
            r"[0-9a-fA-F]{64}",
            value
        ) is not None
    )


def valid_address(value):
    return (
        isinstance(value, str)
        and re.fullmatch(
            r"G[A-Z2-7]{55}",
            value
        ) is not None
    )


def parse_amount(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise RuntimeError("Invalid amount")

    if not amount.is_finite():
        raise RuntimeError("Non-finite amount")

    if amount < 0:
        raise RuntimeError("Negative amount")

    if amount.as_tuple().exponent < -7:
        raise RuntimeError(
            "Amount exceeds seven decimal places"
        )

    return amount


def parse_timestamp(value):
    if not isinstance(value, str):
        raise RuntimeError("Missing timestamp")

    try:
        result = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise RuntimeError(
            "Invalid timestamp"
        ) from exc

    if result.tzinfo is None:
        raise RuntimeError(
            "Timestamp has no timezone"
        )

    return result.astimezone(timezone.utc)


def get_json(path, params=None):
    url = HORIZON + path

    if params:
        url += "?" + urlencode(params)

    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "EN96-Watcher/0.8"
        }
    )

    try:
        with urlopen(
            request,
            timeout=30
        ) as response:
            data = json.load(response)

    except (
        HTTPError,
        URLError,
        TimeoutError,
        ValueError
    ) as exc:
        raise RuntimeError(
            "Horizon request failed: " + str(exc)
        ) from exc

    if not isinstance(data, dict):
        raise RuntimeError(
            "Invalid Horizon response"
        )

    return data


def get_records(data):
    embedded = data.get("_embedded")

    if not isinstance(embedded, dict):
        raise RuntimeError(
            "Missing Horizon embedded data"
        )

    records = embedded.get("records")

    if not isinstance(records, list):
        raise RuntimeError(
            "Missing Horizon records"
        )

    return records


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
        record
        for record in records
        if (
            record.get("asset_code") == ASSET_CODE
            and record.get("asset_issuer")
            == ASSET_ISSUER
        )
    ]

    if not matching:
        raise RuntimeError(
            "EN96 asset not found"
        )

    balances = matching[0].get("balances")

    if not isinstance(balances, dict):
        raise RuntimeError(
            "Invalid asset balances"
        )

    total = Decimal("0")

    for value in balances.values():
        if value is not None:
            total += parse_amount(value)

    if total > MAX_SUPPLY:
        raise RuntimeError(
            "Stellar reported total exceeds cap"
        )

    print("PASS: EN96 asset found")
    print("Stellar reported total:", total)
    print(
        "NOTICE: Unified cross-chain supply "
        "is not verified"
    )


def check_escrow():
    if not valid_address(ESCROW_ACCOUNT):
        raise RuntimeError(
            "Invalid escrow address"
        )

    account = get_json(
        "/accounts/" + ESCROW_ACCOUNT
    )

    balances = account.get("balances")

    if not isinstance(balances, list):
        raise RuntimeError(
            "Invalid account balances"
        )

    for balance in balances:
        if (
            balance.get("asset_code") == ASSET_CODE
            and balance.get("asset_issuer")
            == ASSET_ISSUER
        ):
            amount = parse_amount(
                balance.get("balance")
            )

            print("PASS: Escrow trustline exists")
            print("Escrow EN96 balance:", amount)
            return

    raise RuntimeError(
        "Escrow trustline not found"
    )


def database_connection():
    password = (
        os.getenv("PGPASSWORD")
        or os.getenv("EN96_BRIDGE_DB_PASSWORD")
    )

    certificate = (
        os.getenv("PGSSLROOTCERT")
        or os.getenv("EN96_CA_CERT_PATH")
    )

    if not password:
        raise RuntimeError(
            "Database password missing"
        )

    if not certificate:
        raise RuntimeError(
            "Database CA path missing"
        )

    if not os.path.isfile(certificate):
        raise RuntimeError(
            "Database CA file missing"
        )

    return psycopg.connect(
        host=os.getenv(
            "PGHOST",
            "aws-0-eu-west-1.pooler.supabase.com"
        ),
        port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv(
            "PGDATABASE",
            "postgres"
        ),
        user=os.getenv(
            "PGUSER",
            "en96_bridge_writer.zfoanswefwufsifncrhl"
        ),
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
            "Starting from earliest available history."
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
            "Invalid checkpoint token"
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


def get_transaction(tx_hash):
    if not valid_hash(tx_hash):
        raise RuntimeError(
            "Invalid transaction hash"
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
            "Transaction was not successful"
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

    created_at = parse_timestamp(
        transaction.get("created_at")
    )

    return transaction, ledger, created_at


def get_transaction_operations(tx_hash):
    all_operations = []
    cursor = "0"
    complete = False

    for _ in range(MAX_TX_PAGES):
        data = get_json(
            "/transactions/"
            + tx_hash
            + "/operations",
            {
                "cursor": cursor,
                "order": "asc",
                "limit": TX_PAGE_SIZE,
                "include_failed": "false"
            }
        )

        records = get_records(data)

        if not records:
            complete = True
            break

        previous = cursor

        for record in records:
            token = record.get("paging_token")

            if not valid_token(token):
                raise RuntimeError(
                    "Invalid transaction operation token"
                )

            if int(token) <= int(previous):
                raise RuntimeError(
                    "Non-increasing transaction cursor"
                )

            previous = token

            if (
                record.get("transaction_hash", "").lower()
                != tx_hash.lower()
            ):
                raise RuntimeError(
                    "Transaction operation mismatch"
                )

            all_operations.append(record)

        cursor = previous

        if len(records) < TX_PAGE_SIZE:
            complete = True
            break

    if not complete:
        raise RuntimeError(
            "Transaction operation history incomplete"
        )

    if not all_operations:
        raise RuntimeError(
            "Transaction has no operations"
        )

    return all_operations


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
            "EN96 deposit must be positive"
        )

    return True


def verify_deposit(operation):
    tx_hash = operation.get("transaction_hash")
    operation_id = operation.get("id")
    source = operation.get("from")

    if not valid_hash(tx_hash):
        raise RuntimeError(
            "Invalid deposit transaction hash"
        )

    if not valid_token(operation_id):
        raise RuntimeError(
            "Invalid deposit operation ID"
        )

    if not valid_address(source):
        raise RuntimeError(
            "Invalid deposit source"
        )

    if source == ESCROW_ACCOUNT:
        raise RuntimeError(
            "Self-transfer cannot be bridged"
        )

    amount = parse_amount(
        operation.get("amount")
    )

    if amount <= 0:
        raise RuntimeError(
            "Invalid deposit amount"
        )

    transaction, ledger, tx_time = (
        get_transaction(tx_hash)
    )

    operations = get_transaction_operations(
        tx_hash
    )

    operation_index = None

    for index, candidate in enumerate(operations):
        if candidate.get("id") == operation_id:
            operation_index = index

            if not is_en96_deposit(candidate):
                raise RuntimeError(
                    "Operation is not an EN96 deposit"
                )

            if candidate.get("from") != source:
                raise RuntimeError(
                    "Source account mismatch"
                )

            if (
                parse_amount(candidate.get("amount"))
                != amount
            ):
                raise RuntimeError(
                    "Deposit amount mismatch"
                )

            if (
                candidate.get("paging_token")
                != operation.get("paging_token")
            ):
                raise RuntimeError(
                    "Paging token mismatch"
                )

            op_time = parse_timestamp(
                candidate.get("created_at")
            )

            if op_time != tx_time:
                raise RuntimeError(
                    "Operation timestamp mismatch"
                )

            break

    if operation_index is None:
        raise RuntimeError(
            "Deposit operation not found in transaction"
        )

    result = {
        "stellar_tx_hash": tx_hash.lower(),
        "operation_index": operation_index,
        "stellar_operation_id": operation_id,
        "source_account": source,
        "escrow_account": ESCROW_ACCOUNT,
        "asset_code": ASSET_CODE,
        "asset_issuer": ASSET_ISSUER,
        "amount": str(amount),
        "stellar_ledger": ledger,
        "stellar_created_at": tx_time.isoformat(),
        "status": "observed"
    }

    print("PASS: EN96 deposit verified")
    print("Transaction:", result["stellar_tx_hash"])
    print("Operation index:", operation_index)
    print("Operation ID:", operation_id)
    print("Amount:", amount)
    print("Ledger:", ledger)
    print(
        "NOTICE: Deposit is NOT recorded "
        "or minted"
    )

    return result


def scan_escrow(conn):
    cursor = read_checkpoint(conn)

    scanned = 0
    pages = 0
    reached_end = False

    while pages < MAX_PAGES:
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

        previous = cursor
        deposits = []

        for operation in records:
            token = operation.get("paging_token")

            if not valid_token(token):
                raise RuntimeError(
                    "Invalid operation paging token"
                )

            if int(token) <= int(previous):
                raise RuntimeError(
                    "Non-increasing escrow cursor"
                )

            previous = token
            scanned += 1

            if is_en96_deposit(operation):
                deposit = verify_deposit(operation)
                deposits.append(deposit)

        # Never advance beyond a page containing
        # EN96 deposits while recording is disabled.
        if deposits:
            print(
                "NOTICE: Verified deposits found:",
                len(deposits)
            )
            print(
                "Checkpoint NOT advanced "
                "past these deposits"
            )
            raise RuntimeError(
                "Manual deposit review required. "
                "Bridge remains disabled."
            )

        save_checkpoint(conn, previous)

        cursor = previous
        pages += 1

        if len(records) < PAGE_SIZE:
            reached_end = True
            break

    print("Operations scanned:", scanned)
    print("Pages scanned:", pages)
    print(
        "Reached available history end:",
        reached_end
    )

    if not reached_end:
        print(
            "NOTICE: Page limit reached; "
            "next run resumes from checkpoint"
        )

    return scanned, reached_end


def main():
    print("=" * 48)
    print(
        "EN96 STELLAR MAINNET WATCHER "
        "- VERSION " + VERSION
    )
    print("=" * 48)

    require_disabled_features()

    check_asset()
    check_escrow()

    with database_connection() as conn:
        scanned, completed = scan_escrow(conn)

    print("=" * 48)
    print("RESULT: SAFE SCAN COMPLETED")
    print("Operations scanned:", scanned)
    print("History end reached:", completed)
    print("Persistent checkpoint enabled")
    print("Deposit recording disabled")
    print("No Stellar transfers performed")
    print("No BNB minting performed")
    print("Bridge remains disabled")
    print("=" * 48)


if __name__ == "__main__":
    main()
