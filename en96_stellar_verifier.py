
import json
import os
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

HORIZON = "https://horizon.stellar.org"
ASSET_CODE = os.getenv("EN96_STELLAR_ASSET_CODE", "")
ISSUER = os.getenv("EN96_STELLAR_ISSUER_ADDRESS", "")
VAULT = os.getenv("EN96_STELLAR_VAULT_ADDRESS", "")

STELLAR_ADDRESS = re.compile(r"^G[A-Z2-7]{55}$")
TX_HASH = re.compile(r"^[0-9a-fA-F]{64}$")
MAX_AMOUNT = Decimal("1000000")
QUANTUM = Decimal("0.0000001")


class StellarVerificationError(Exception):
    pass


def horizon_get(path):
    request = Request(
        HORIZON + path,
        headers={"Accept": "application/json"}
    )

    try:
        with urlopen(request, timeout=15) as response:
            return json.load(response)
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise StellarVerificationError(
            "Unable to verify transaction with Stellar Horizon"
        ) from exc


def verify_config():
    if ASSET_CODE != "EN96":
        raise StellarVerificationError("Invalid EN96 asset code")

    if not STELLAR_ADDRESS.fullmatch(ISSUER):
        raise StellarVerificationError("Invalid issuer address")

    if not STELLAR_ADDRESS.fullmatch(VAULT):
        raise StellarVerificationError("Invalid vault address")

    if ISSUER == VAULT:
        raise StellarVerificationError(
            "Issuer and vault must be different"
        )


def verify_deposit(stellar_tx_hash, operation_index):
    """
    Read-only verification of an existing Stellar payment.

    Does not write to Supabase, sign messages,
    mint BNB tokens, or transfer Stellar assets.
    """
    verify_config()

    if not isinstance(stellar_tx_hash, str):
        raise StellarVerificationError("Invalid transaction hash")

    tx_hash = stellar_tx_hash.strip().lower()

    if not TX_HASH.fullmatch(tx_hash):
        raise StellarVerificationError("Invalid transaction hash")

    if type(operation_index) is not int or operation_index < 0:
        raise StellarVerificationError("Invalid operation index")

    tx = horizon_get(
        "/transactions/" + quote(tx_hash, safe="")
    )

    if tx.get("successful") is not True:
        raise StellarVerificationError(
            "Stellar transaction was not successful"
        )

    if tx.get("hash", "").lower() != tx_hash:
        raise StellarVerificationError(
            "Transaction hash mismatch"
        )

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
        records = page.get("_embedded", {}).get("records", [])

        if not isinstance(records, list):
            raise StellarVerificationError(
                "Invalid Horizon operations response"
            )

        operations.extend(records)

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

    op = operations[operation_index]

    if op.get("type") != "payment":
        raise StellarVerificationError(
            "Operation is not a payment"
        )

    if op.get("asset_type") == "native":
        raise StellarVerificationError(
            "Native XLM is not EN96"
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

    if not STELLAR_ADDRESS.fullmatch(sender):
        raise StellarVerificationError(
            "Invalid sender address"
        )

    try:
        amount = Decimal(str(op["amount"]))
    except (KeyError, InvalidOperation, ValueError, TypeError):
        raise StellarVerificationError(
            "Invalid payment amount"
        )

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
        "stellar_sender": sender,
        "stellar_vault": VAULT,
        "asset_code": ASSET_CODE,
        "asset_issuer": ISSUER,
        "amount": format(amount, ".7f"),
        "stellar_ledger": tx.get("ledger"),
        "created_at": tx.get("created_at"),
    }
