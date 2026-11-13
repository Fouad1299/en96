
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


# ==========================================
# EN96 ICE BEAR KINGDOM
# Stellar Mainnet Deposit Watcher
# Version 0.9 - Safe deposit recording
#
# No BNB minting
# No transaction signing
# No Stellar payouts
# ==========================================

VERSION = "0.9"

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
MAX_DEPOSIT = Decimal("1000000")

PAGE_SIZE = 100
MAX_PAGES = 5
TX_PAGE_SIZE = 200
MAX_TX_PAGES = 20

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s"
)

log = logging.getLogger("EN96-WATCHER")


def check_features():
    if os.getenv("EN96_ENABLE_BNB_MINT") == "1":
        raise RuntimeError(
            "BNB minting is disabled"
        )

    if os.getenv("EN96_ENABLE_SIGNING") == "1":
        raise RuntimeError(
            "Signing is disabled"
        )

    if os.getenv("EN96_ENABLE_STELLAR_PAYOUT") == "1":
        raise RuntimeError(
            "Stellar payouts are disabled"
        )

    recording = os.getenv(
        "EN96_RECORD_DEPOSITS", "0"
    )

    if recording not in ("0", "1"):
        raise RuntimeError(
            "Invalid EN96_RECORD_DEPOSITS setting"
        )

    return recording == "1"


def valid_token(value):
    return (
        isinstance(value, str)
        and re.fullmatch(r"[0-9]+", value)
        is not None
    )


def valid_hash(value):
    return (
        isinstance(value, str)
        and re.fullmatch(
            r"[0-9a-fA-F]{64}", value
        ) is not None
    )


def valid_address(value):
    return (
        isinstance(value, str)
        and re.fullmatch(
            r"G[A-Z2-7]{55}", value
        ) is not None
    )


def parse_amount(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise RuntimeError("Invalid amount")

    if not amount.is_finite():
        raise RuntimeError("Non-finite amount")

    if amount <= 0:
        raise RuntimeError(
            "Amount must be positive"
        )

    if amount.as_tuple().exponent < -7:
        raise RuntimeError(
            "Too many decimal places"
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
            "Timestamp missing timezone"
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
            "User-Agent": "EN96-Watcher/0.9"
        }
    )

    try:
        with urlopen(
            request, timeout=30
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
            "Missing embedded data"
        )

    records = embedded.get("records")

    if not isinstance(records, list):
        raise RuntimeError(
            "Missing records"
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
        r for r in records
        if r.get("asset_code") == ASSET_CODE
        and r.get("asset_issuer") == ASSET_ISSUER
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

    # FIX:
    # Zero balances are valid for asset statistics.
    # Deposit amounts must still be positive.
    for value in balances.values():
        if value is not None:
            try:
                balance = Decimal(str(value))
            except (
                InvalidOperation,
                ValueError,
                TypeError
            ) as exc:
                raise RuntimeError(
                    "Invalid asset balance"
                ) from exc

            if not balance.is_finite() or balance < 0:
                raise RuntimeError(
                    "Invalid asset balance"
                )

            total += balance

    if total > MAX_SUPPLY:
        raise RuntimeError(
            "Stellar supply exceeds cap"
        )

    print("PASS: EN96 asset verified")
    print("Stellar reported total:", total)
    print(
        "NOTICE: Unified cross-chain supply "
        "not verified"
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
            amount = Decimal(
                str(balance.get("balance"))
            )

            if not amount.is_finite() or amount < 0:
                raise RuntimeError(
                    "Invalid escrow balance"
                )

            print(
                "PASS: Escrow trustline verified"
            )
            print(
                "Escrow EN96 balance:", amount
            )
            return

    raise RuntimeError(
        "Escrow trustline not found"
    )


def database_connection():
    password = (
        os.getenv("PGPASSWORD")
        or os.getenv(
            "EN96_BRIDGE_DB_PASSWORD"
        )
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
            "PGDATABASE", "postgres"
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
            "NOTICE: No checkpoint found"
        )
        return "0"

    token = row[0]

    if not valid_token(token):
        raise RuntimeError(
            "Invalid stored checkpoint"
        )

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

    # Deposit records and checkpoint must
    # commit in the same transaction.


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
            "Transaction not successful"
        )

    ledger = transaction.get("ledger")

    if (
        not isinstance(ledger, int)
        or isinstance(ledger, bool)
        or ledger <= 0
    ):
        raise RuntimeError(
            "Invalid ledger"
        )

    created_at = parse_timestamp(
        transaction.get("created_at")
    )

    return transaction, ledger, created_at


def get_transaction_operations(tx_hash):
    operations = []
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
                    "Invalid operation token"
                )

            if int(token) <= int(previous):
                raise RuntimeError(
                    "Non-increasing operation cursor"
                )

            if (
                str(
                    record.get(
                        "transaction_hash", ""
                    )
                ).lower() != tx_hash.lower()
            ):
                raise RuntimeError(
                    "Operation transaction mismatch"
                )

            previous = token
            operations.append(record)

        cursor = previous

        if len(records) < TX_PAGE_SIZE:
            complete = True
            break

    if not complete or not operations:
        raise RuntimeError(
            "Incomplete transaction operations"
        )

    return operations


def is_en96_deposit(operation):
    if operation.get("type") != "payment":
        return False

    if operation.get("to") != ESCROW_ACCOUNT:
        return False

    if (
        operation.get("asset_type")
        != "credit_alphanum4"
    ):
        return False

    if operation.get("asset_code") != ASSET_CODE:
        return False

    if (
        operation.get("asset_issuer")
        != ASSET_ISSUER
    ):
        return False

    amount = parse_amount(
        operation.get("amount")
    )

    return amount > 0


def verify_deposit(operation):
    tx_hash = operation.get("transaction_hash")
    operation_id = operation.get("id")
    source = operation.get("from")

    if not valid_hash(tx_hash):
        raise RuntimeError(
            "Invalid deposit hash"
        )

    if not valid_token(operation_id):
        raise RuntimeError(
            "Invalid operation ID"
        )

    if not valid_address(source):
        raise RuntimeError(
            "Invalid source address"
        )

    if source == ESCROW_ACCOUNT:
        raise RuntimeError(
            "Self-transfer rejected"
        )

    amount = parse_amount(
        operation.get("amount")
    )

    if amount > MAX_DEPOSIT:
        raise RuntimeError(
            "Deposit exceeds bridge limit"
        )

    transaction, ledger, tx_time = (
        get_transaction(tx_hash)
    )

    operations = get_transaction_operations(
        tx_hash
    )

    operation_index = None

    for index, candidate in enumerate(
        operations
    ):
        if candidate.get("id") != operation_id:
            continue

        operation_index = index

        if not is_en96_deposit(candidate):
            raise RuntimeError(
                "Not an EN96 deposit"
            )

        if candidate.get("from") != source:
            raise RuntimeError(
                "Source mismatch"
            )

        if (
            parse_amount(candidate.get("amount"))
            != amount
        ):
            raise RuntimeError(
                "Amount mismatch"
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
                "Timestamp mismatch"
            )

        break

    if operation_index is None:
        raise RuntimeError(
            "Operation not found"
        )

    return {
        "stellar_tx_hash": tx_hash.lower(),
        "operation_index": operation_index,
        "stellar_operation_id": operation_id,
        "source_account": source,
        "escrow_account": ESCROW_ACCOUNT,
        "asset_code": ASSET_CODE,
        "asset_issuer": ASSET_ISSUER,
        "amount": amount,
        "stellar_ledger": ledger,
        "stellar_created_at": tx_time,
        "status": "observed"
    }


def record_deposit(conn, deposit):
    """
    Store only observed deposits.

    No BNB recipient is assigned.
    No minting approval is given.
    """

    with conn.cursor() as cur:
        cur.execute(
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
                status,
                bnb_recipient_address,
                bnb_recipient_verified
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                'observed', NULL, false
            )
            ON CONFLICT DO NOTHING
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
                deposit["stellar_created_at"]
            )
        )

        inserted = cur.fetchone()

        if inserted is not None:
            print(
                "PASS: Deposit recorded:",
                inserted[0]
            )
            return True

        # A conflict is acceptable only when
        # the existing record matches this
        # exact verified Stellar operation.
        cur.execute(
            """
            SELECT
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
            FROM public.en96_bridge_deposits
            WHERE stellar_tx_hash = %s
              AND operation_index = %s
              AND stellar_operation_id = %s
            """,
            (
                deposit["stellar_tx_hash"],
                deposit["operation_index"],
                deposit["stellar_operation_id"]
            )
        )

        existing = cur.fetchone()

        if existing is None:
            raise RuntimeError(
                "Deposit conflict: existing "
                "record not accessible or mismatched"
            )

        expected = (
            deposit["stellar_tx_hash"],
            deposit["operation_index"],
            deposit["stellar_operation_id"],
            deposit["source_account"],
            deposit["escrow_account"],
            deposit["asset_code"],
            deposit["asset_issuer"],
            deposit["amount"],
            deposit["stellar_ledger"],
            deposit["stellar_created_at"]
        )

        if tuple(existing[:10]) != expected:
            raise RuntimeError(
                "Deposit conflict: data mismatch"
            )

        if existing[10] not in (
            "observed", "verified"
        ):
            raise RuntimeError(
                "Deposit conflict: unexpected status"
            )

        print(
            "PASS: Previously recorded deposit"
        )

        return False


def scan_escrow(conn, recording_enabled):
    cursor = read_checkpoint(conn)

    scanned = 0
    recorded = 0
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
                    "Invalid escrow cursor"
                )

            if int(token) <= int(previous):
                raise RuntimeError(
                    "Non-increasing escrow cursor"
                )

            previous = token
            scanned += 1

            if is_en96_deposit(operation):
                deposit = verify_deposit(
                    operation
                )
                deposits.append(deposit)

        if not recording_enabled:
            if deposits:
                print(
                    "NOTICE: Deposits detected:",
                    len(deposits)
                )
                print(
                    "Checkpoint not advanced"
                )
                raise RuntimeError(
                    "Recording disabled. "
                    "Manual review required."
                )

            # Keep existing safe dry-run
            # behavior for non-deposit pages.
            try:
                save_checkpoint(conn, previous)
                conn.commit()
            except Exception:
                conn.rollback()
                raise

        else:
            # Atomic transaction:
            # either every deposit in the page
            # and its checkpoint are saved,
            # or none of them are committed.
            try:
                page_recorded = 0

                for deposit in deposits:
                    if record_deposit(
                        conn, deposit
                    ):
                        page_recorded += 1

                save_checkpoint(conn, previous)

                conn.commit()

                recorded += page_recorded

                print(
                    "PASS: Page committed safely"
                )

            except Exception:
                conn.rollback()
                print(
                    "ERROR: Page rolled back. "
                    "Checkpoint unchanged."
                )
                raise

        cursor = previous
        pages += 1

        if len(records) < PAGE_SIZE:
            reached_end = True
            break

    print("Operations scanned:", scanned)
    print("New deposits recorded:", recorded)
    print("Pages scanned:", pages)
    print(
        "History end reached:", reached_end
    )

    return scanned, recorded, reached_end


def main():
    print("=" * 48)
    print(
        "EN96 STELLAR MAINNET WATCHER "
        "VERSION " + VERSION
    )
    print("=" * 48)

    recording_enabled = check_features()

    print(
        "Deposit recording:",
        "ENABLED" if recording_enabled
        else "DISABLED"
    )

    check_asset()
    check_escrow()

    with database_connection() as conn:
        scanned, recorded, completed = (
            scan_escrow(
                conn, recording_enabled
            )
        )

    print("=" * 48)
    print("RESULT: WATCHER COMPLETED")
    print("Operations scanned:", scanned)
    print("Deposits recorded:", recorded)
    print("History end reached:", completed)
    print("BNB minting: DISABLED")
    print("Validator signing: DISABLED")
    print("Stellar payouts: DISABLED")
    print("=" * 48)


if __name__ == "__main__":
    main()
