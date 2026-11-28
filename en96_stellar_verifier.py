
import base64
import binascii
import json
import os
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


# ==========================================
# EN96 ICE BEAR KINGDOM
# Stellar Mainnet -> BNB Smart Chain
# Classic Stellar Reserve Account
# NO SOROBAN
# ==========================================

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

EXPECTED_ISSUER = (
    "GBWLEH67H6HCH264IWJFL66CJYF34B7WEC4GSZQJZPDM23WVC6UKB7SJ"
)

BNB_CHAIN_ID = 56

BNB_BRIDGE_ADDRESS = (
    "0x376edf142106274fe7db370475aa761f1ec0bc21"
)

STELLAR_ADDRESS = re.compile(
    r"^G[A-Z2-7]{55}$"
)

TX_HASH = re.compile(
    r"^[0-9a-fA-F]{64}$"
)

BNB_ADDRESS = re.compile(
    r"^0x[0-9a-fA-F]{40}$"
)

MAX_SUPPLY = Decimal("90000000000")
MAX_AMOUNT = Decimal("1000000")
QUANTUM = Decimal("0.0000001")

DECIMALS = 7
UNIT_MULTIPLIER = 10 ** DECIMALS

MEMO_PREFIX = b"EN96-BNB-V01"

MAX_OPERATIONS = 1000

# Verification only.
# Signing and minting are not enabled here.

SIGNING_ENABLED = False
MINTING_ENABLED = False

# Historical treasury funding.
# Never accept this transaction as a deposit.

BLOCKED_TREASURY_TX = (
    "d2afa7fe4f8fc21c5208828e046091f915c536959108d18d329f345ae13a0e91"
)


class StellarVerificationError(Exception):
    pass


# ==========================================
# HORIZON CONNECTION
# ==========================================

def horizon_get(path):

    request = Request(
        HORIZON + path,
        headers={
            "Accept": "application/json",
            "User-Agent": "EN96-Stellar-Verifier/2.0",
        },
    )

    try:
        with urlopen(request, timeout=15) as response:
            result = json.load(response)

        if not isinstance(result, dict):
            raise ValueError("Invalid Horizon response")

        return result

    except (
        HTTPError,
        URLError,
        TimeoutError,
        ValueError,
    ) as exc:

        raise StellarVerificationError(
            "Unable to verify transaction with Stellar Horizon"
        ) from exc


# ==========================================
# STELLAR ADDRESS VALIDATION
# ==========================================

def valid_stellar_address(address):

    if not isinstance(address, str):
        return False

    if not STELLAR_ADDRESS.fullmatch(address):
        return False

    try:
        decoded = base64.b32decode(address)

        if len(decoded) != 35:
            return False

        if decoded[0] != 48:
            return False

        payload = decoded[:-2]

        expected_checksum = binascii.crc_hqx(
            payload, 0
        ).to_bytes(2, "little")

        return decoded[-2:] == expected_checksum

    except (
        ValueError,
        TypeError,
        binascii.Error,
    ):
        return False


# ==========================================
# CONFIGURATION VALIDATION
# ==========================================

def verify_config():

    if ASSET_CODE != "EN96":
        raise StellarVerificationError(
            "Invalid EN96 asset code"
        )

    if not valid_stellar_address(ISSUER):
        raise StellarVerificationError(
            "Invalid issuer address"
        )

    if ISSUER != EXPECTED_ISSUER:
        raise StellarVerificationError(
            "Unexpected EN96 issuer"
        )

    if not valid_stellar_address(VAULT):
        raise StellarVerificationError(
            "Invalid classic Stellar reserve address"
        )

    if ISSUER == VAULT:
        raise StellarVerificationError(
            "Issuer and reserve must be different"
        )

    configured_bridge = os.getenv(
        "EN96_BNB_BRIDGE_ADDRESS", ""
    ).strip().lower()

    if configured_bridge != BNB_BRIDGE_ADDRESS:
        raise StellarVerificationError(
            "Invalid BNB bridge configuration"
        )


# ==========================================
# BNB RECIPIENT VALIDATION
# ==========================================

def normalize_bnb_address(address):

    if not isinstance(address, str):
        raise StellarVerificationError(
            "Invalid BNB recipient"
        )

    address = address.strip()

    if not BNB_ADDRESS.fullmatch(address):
        raise StellarVerificationError(
            "Invalid BNB recipient"
        )

    address = address.lower()

    if address == "0x" + "0" * 40:
        raise StellarVerificationError(
            "Zero BNB recipient"
        )

    if address == BNB_BRIDGE_ADDRESS:
        raise StellarVerificationError(
            "Bridge cannot be the recipient"
        )

    return address


# ==========================================
# BUILD STELLAR BRIDGE MEMO
# ==========================================

def build_bridge_memo(bnb_recipient):

    recipient = normalize_bnb_address(
        bnb_recipient
    )

    recipient_bytes = bytes.fromhex(
        recipient[2:]
    )

    memo = MEMO_PREFIX + recipient_bytes

    if len(memo) != 32:
        raise StellarVerificationError(
            "Invalid bridge memo length"
        )

    return {
        "memo_type": "hash",
        "memo_hex": memo.hex(),
        "memo_base64": base64.b64encode(
            memo
        ).decode("ascii"),
        "bnb_recipient": recipient,
        "bnb_chain_id": BNB_CHAIN_ID,
    }


# ==========================================
# VERIFY SIGNED BNB RECIPIENT
# ==========================================

def verify_bnb_recipient(tx, sender):

    if tx.get("source_account") != sender:
        raise StellarVerificationError(
            "Transaction source must match payment sender"
        )

    if tx.get("source_account_muxed"):
        raise StellarVerificationError(
            "Muxed transaction sources are not supported"
        )

    if tx.get("memo_type") != "hash":
        raise StellarVerificationError(
            "EN96 bridge requires Memo Hash"
        )

    encoded_memo = tx.get("memo", "")

    if not isinstance(encoded_memo, str):
        raise StellarVerificationError(
            "Invalid bridge memo"
        )

    try:
        memo = base64.b64decode(
            encoded_memo,
            validate=True,
        )

    except (
        ValueError,
        TypeError,
        binascii.Error,
    ) as exc:

        raise StellarVerificationError(
            "Invalid bridge memo encoding"
        ) from exc

    if len(memo) != 32:
        raise StellarVerificationError(
            "Invalid bridge memo length"
        )

    if memo[:12] != MEMO_PREFIX:
        raise StellarVerificationError(
            "Invalid EN96 bridge identifier"
        )

    recipient_bytes = memo[12:]

    recipient = normalize_bnb_address(
        "0x" + recipient_bytes.hex()
    )

    return recipient


# ==========================================
# GET STELLAR TRANSACTION OPERATIONS
# ==========================================

def get_transaction_operations(
    tx_hash,
    operation_index,
):

    operations = []
    cursor = None

    while True:

        path = (
            "/transactions/"
            + quote(tx_hash, safe="")
            + "/operations?limit=200&order=asc"
        )

        if cursor is not None:

            path += (
                "&cursor="
                + quote(cursor, safe="")
            )

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

        next_cursor = records[-1].get(
            "paging_token"
        )

        if (
            not next_cursor
            or next_cursor == cursor
        ):
            raise StellarVerificationError(
                "Invalid operations pagination"
            )

        cursor = next_cursor

    if operation_index >= len(operations):
        raise StellarVerificationError(
            "Operation index does not exist"
        )

    return operations[operation_index]


# ==========================================
# VERIFY EN96 AMOUNT
# ==========================================

def verify_amount(raw_amount):

    try:

        amount = Decimal(
            str(raw_amount)
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

        units = int(
            amount * UNIT_MULTIPLIER
        )

        if units <= 0:
            raise StellarVerificationError(
                "Invalid EN96 units"
            )

        return amount, units

    except (
        InvalidOperation,
        ValueError,
        TypeError,
        OverflowError,
    ) as exc:

        raise StellarVerificationError(
            "Invalid payment amount"
        ) from exc


# ==========================================
# VERIFY STELLAR BRIDGE DEPOSIT
# ==========================================

def verify_deposit(
    stellar_tx_hash,
    operation_index,
):

    """
    Read-only EN96 deposit verification.

    Verifies:
    - Stellar Mainnet transaction.
    - Correct EN96 asset and issuer.
    - Classic Stellar reserve account.
    - Successful payment operation.
    - Signed BNB recipient memo.
    - Sender and transaction source.
    - Amount and decimal precision.

    Does not:
    - Use Soroban.
    - Transfer Stellar assets.
    - Write to Supabase.
    - Sign validator messages.
    - Mint BNB tokens.
    """

    verify_config()

    if not isinstance(stellar_tx_hash, str):
        raise StellarVerificationError(
            "Invalid transaction hash"
        )

    tx_hash = (
        stellar_tx_hash.strip().lower()
    )

    if not TX_HASH.fullmatch(tx_hash):
        raise StellarVerificationError(
            "Invalid transaction hash"
        )

    if (
        type(operation_index) is not int
        or operation_index < 0
        or operation_index >= MAX_OPERATIONS
    ):
        raise StellarVerificationError(
            "Invalid operation index"
        )

    # Reject historical treasury funding.

    if tx_hash == BLOCKED_TREASURY_TX:
        raise StellarVerificationError(
            "Historical treasury funding is not a bridge deposit"
        )

    # Read transaction from Stellar Mainnet.

    tx = horizon_get(
        "/transactions/"
        + quote(tx_hash, safe="")
    )

    if tx.get("successful") is not True:
        raise StellarVerificationError(
            "Stellar transaction was not successful"
        )

    if str(tx.get("hash", "")).lower() != tx_hash:
        raise StellarVerificationError(
            "Transaction hash mismatch"
        )

    # Restrict this bridge version to one payment
    # per transaction.

    if tx.get("operation_count") != 1:
        raise StellarVerificationError(
            "Bridge requires a single-operation transaction"
        )

    if operation_index != 0:
        raise StellarVerificationError(
            "Bridge payment operation index must be zero"
        )

    # Reject fee-bump transactions in this version.

    if tx.get("fee_bump_transaction"):
        raise StellarVerificationError(
            "Fee-bump transactions are not supported"
        )

    # Read payment operation.

    op = get_transaction_operations(
        tx_hash,
        operation_index,
    )

    if str(
        op.get("transaction_hash", "")
    ).lower() != tx_hash:

        raise StellarVerificationError(
            "Operation transaction mismatch"
        )

    if op.get(
        "transaction_successful"
    ) is not True:

        raise StellarVerificationError(
            "Operation was not successful"
        )

    if op.get("type") != "payment":
        raise StellarVerificationError(
            "Operation is not a payment"
        )

    if op.get(
        "asset_type"
    ) != "credit_alphanum4":

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
            "Payment was not sent to the reserve"
        )

    if (
        op.get("from_muxed")
        or op.get("to_muxed")
        or op.get("source_account_muxed")
    ):
        raise StellarVerificationError(
            "Muxed accounts are not supported"
        )

    # Verify payment sender.

    sender = op.get("from", "")

    if not valid_stellar_address(sender):
        raise StellarVerificationError(
            "Invalid sender address"
        )

    if op.get("source_account") != sender:
        raise StellarVerificationError(
            "Operation source mismatch"
        )

    if sender == ISSUER:
        raise StellarVerificationError(
            "Issuer funding is not a bridge deposit"
        )

    if sender == VAULT:
        raise StellarVerificationError(
            "Reserve self-payment is not a bridge deposit"
        )

    # Extract BNB recipient from signed transaction.

    bnb_recipient = verify_bnb_recipient(
        tx,
        sender,
    )

    # Verify payment amount.

    amount, amount_units = verify_amount(
        op.get("amount")
    )

    operation_id = str(
        op.get("id", "")
    )

    if not operation_id.isdigit():
        raise StellarVerificationError(
            "Invalid Stellar operation ID"
        )

    # Return verified deposit data.
    # Verification alone does not authorize minting.

    return {
        "verified": True,
        "stellar_tx_hash": tx_hash,
        "operation_index": operation_index,
        "stellar_operation_id": operation_id,
        "stellar_sender": sender,
        "stellar_vault": VAULT,
        "asset_code": ASSET_CODE,
        "asset_issuer": ISSUER,
        "amount": format(amount, ".7f"),
        "amount_units": amount_units,
        "decimals": DECIMALS,
        "bnb_recipient": bnb_recipient,
        "bnb_chain_id": BNB_CHAIN_ID,
        "bnb_bridge_address": BNB_BRIDGE_ADDRESS,
        "stellar_ledger": tx.get("ledger"),
        "created_at": tx.get("created_at"),
        "deposit_key": (
            tx_hash + ":" + str(operation_index)
        ),
        "custody_type": "classic_stellar_account",
        "soroban_enabled": False,
        "signing_enabled": SIGNING_ENABLED,
        "minting_enabled": MINTING_ENABLED,
        "mint_authorized": False,
    }
