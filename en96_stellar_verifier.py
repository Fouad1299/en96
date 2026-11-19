import json
import os
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

HORIZON = "https://horizon.stellar.org"

ASSET_CODE = os.getenv(
    "EN96_STELLAR_ASSET_CODE", ""
).strip()

ISSUER = os.getenv(
    "EN96_STELLAR_ISSUER_ADDRESS", ""
).strip()

VAULT = os.getenv(
    "EN96_STELLAR_VAULT_ADDRESS", ""
).strip()

STELLAR_ADDRESS = re.compile(r"^G[A-Z2-7]{55}$")
TX_HASH = re.compile(r"^[0-9a-fA-F]{64}$")

MAX_AMOUNT = Decimal("1000000")
QUANTUM = Decimal("0.0000001")

# Historical treasury-funding transaction.
# NEVER accept it as a bridge deposit.
BLOCKED_TREASURY_TX = (
    "d2afa7fe4f8fc21c5208828e046091f915c536959108d18d329f345ae13a0e91"
)

MAX_OPERATIONS = 1000


class StellarVerificationError(Exception):
    pass


def horizon_get(path):
    request = Request(
        HORIZON + path,
        headers={
            "Accept": "application/json",
            "User-Agent": "EN96-Stellar-Verifier/1.1",
        },
    )

    try:
        with urlopen(request, timeout=15) as response:
            return json.load(response)

    except (
        HTTPError,
        URLError,
        TimeoutError,
        ValueError,
    ) as exc:
        raise StellarVerificationError(
            "Unable to verify transaction with Stellar Horizon"
        ) from exc


def verify_config():
    if ASSET_CODE != "EN96":
        raise StellarVerificationError(
            "Invalid EN96 asset code"
        )

    if not STELLAR_ADDRESS.fullmatch(ISSUER):
        raise StellarVerificationError(
            "Invalid issuer address"
        )

    if not STELLAR_ADDRESS.fullmatch(VAULT):
        raise StellarVerificationError(
            "Invalid vault address"
        )

    if ISSUER == VAULT:
        raise StellarVerificationError(
            "Issuer and vault must be different"
        )


def get_transaction_operations(tx_hash, operation_index):
    operations = []
    cursor = None

    while True:
        path = (
            "/transactions/"
            + quote(tx_hash, safe="")
            + "/operations?limit=200&order=asc"
        )

        if cursor is not None:
            path += "&cursor=" + quote(cursor, safe="")

        page = horizon_get(path)

        records = page.get(
            "_embedded", {}
        ).get("records", [])

        if not isinstance(records, list):
            raise StellarVerificationError(
                "Invalid Horizon operations response"
            )

        if not records:
            break

        operations.extend(records)

        if len(operations) > MAX_OPERATIONS:
            raise StellarVerificationError(
                "Too many operations"
            )

        if len(operations) > operation_index:
            break

        if len(records) < 200:
            break

        next_cursor = records[-1].get("paging_token")

        if not next_cursor or next_cursor == cursor:
            raise StellarVerificationError(
                "Invalid operations pagination"
            )

        cursor = next_cursor

    if operation_index >= len(operations):
        raise StellarVerificationError(
            "Operation index does not exist"
        )

    return operations[operation_index]


def verify_deposit(stellar_tx_hash, operation_index):
    """
    Read-only Stellar deposit verification.

    This function:
    - Verifies a real Stellar Mainnet transaction.
    - Verifies the EN96 asset and issuer.
    - Verifies the receiving vault.
    - Rejects historical treasury funding.
    - Enforces a 1,000,000 EN96 deposit limit.
    - Does NOT write to Supabase.
    - Does NOT mint tokens on BNB.
    - Does NOT transfer Stellar assets.
    """

    verify_config()

    if not isinstance(stellar_tx_hash, str):
        raise StellarVerificationError(
            "Invalid transaction hash"
        )

    tx_hash = stellar_tx_hash.strip().lower()

    if not TX_HASH.fullmatch(tx_hash):
        raise StellarVerificationError(
            "Invalid transaction hash"
        )

    if type(operation_index) is not int or operation_index < 0:
        raise StellarVerificationError(
            "Invalid operation index"
        )

    # Reject historical treasury funding before any processing.
    if tx_hash == BLOCKED_TREASURY_TX:
        raise StellarVerificationError(
            "Historical treasury funding is not a bridge deposit"
        )

    tx = horizon_get(
        "/transactions/" + quote(tx_hash, safe="")
    )

    if tx.get("successful") is not True:
        raise StellarVerificationError(
            "Stellar transaction was not successful"
        )

    if str(tx.get("hash", "")).lower() != tx_hash:
        raise StellarVerificationError(
            "Transaction hash mismatch"
        )

    op = get_transaction_operations(
        tx_hash,
        operation_index,
    )

    if op.get("transaction_hash", "").lower() != tx_hash:
        raise StellarVerificationError(
            "Operation transaction mismatch"
        )

    if op.get("transaction_successful") is not True:
        raise StellarVerificationError(
            "Operation was not successful"
        )

    if op.get("type") != "payment":
        raise StellarVerificationError(
            "Operation is not a payment"
        )

    if op.get("asset_type") != "credit_alphanum4":
        raise StellarVerificationError(
            "Wrong asset type"
        )

    if op.get("asset_code") != ASSET_CODE:
        raise StellarVerificationError(
            "Wrong asset code"
        )

    if op.get("asset_issuer") != ISSUER:
        raise StellarVerificationError(
            "Wrong EN96 issuer"
        )

    if op.get("to") != VAULT:
        raise StellarVerificationError(
            "Payment was not sent to the vault"
        )

    sender = op.get("from", "")

    if not isinstance(sender, str):
        raise StellarVerificationError(
            "Invalid sender address"
        )

    if not STELLAR_ADDRESS.fullmatch(sender):
        raise StellarVerificationError(
            "Invalid sender address"
        )

    if sender == ISSUER:
        raise StellarVerificationError(
            "Issuer funding is not a bridge deposit"
        )

    if sender == VAULT:
        raise StellarVerificationError(
            "Vault self-payment is not a bridge deposit"
        )

    try:
        amount = Decimal(str(op["amount"]))

    except (
        KeyError,
        InvalidOperation,
        ValueError,
        TypeError,
    ) as exc:
        raise StellarVerificationError(
            "Invalid payment amount"
        ) from exc

    if not amount.is_finite():
        raise StellarVerificationError(
            "Non-finite payment amount"
        )

    if amount <= 0 or amount > MAX_AMOUNT:
        raise StellarVerificationError(
            "Payment amount outside allowed limits"
        )

    if amount != amount.quantize(QUANTUM):
        raise StellarVerificationError(
            "Invalid EN96 decimal precision"
        )

    return {
        "verified": True,
        "stellar_tx_hash": tx_hash,
        "operation_index": operation_index,
        "stellar_operation_id": str(op.get("id", "")),
        "stellar_sender": sender,
        "stellar_vault": VAULT,
        "asset_code": ASSET_CODE,
        "asset_issuer": ISSUER,
        "amount": format(amount, ".7f"),
        "stellar_ledger": tx.get("ledger"),
        "created_at": tx.get("created_at"),
    }
