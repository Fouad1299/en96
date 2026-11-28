
"""
EN96 Ice Bear Kingdom
Classic Stellar -> BNB Smart Chain
Validator preparation - SAFE MODE
"""

import json
import re
import time
from decimal import Decimal, InvalidOperation

from en96_stellar_verifier import verify_deposit

CHAIN_ID = 56
DOMAIN_NAME = "EN96BridgeV3"
DOMAIN_VERSION = "1"

BRIDGE_ADDRESS = (
    "0x376edf142106274fe7db370475aa761f1ec0bc21"
)

DECIMALS = 7

MAX_SUPPLY_UNITS = 90_000_000_000 * 10**DECIMALS
MAX_DEPOSIT_UNITS = 1_000_000 * 10**DECIMALS

SIGNATURE_VALIDITY_SECONDS = 300

SIGNING_ENABLED = False
MINTING_ENABLED = False

EVM_ADDRESS = re.compile(
    r"^0x[0-9a-fA-F]{40}$"
)

STELLAR_TX_HASH = re.compile(
    r"^0x[0-9a-fA-F]{64}$"
)


# ==========================================
# ADDRESS VALIDATION
# ==========================================

def validate_address(value):

    if not isinstance(value, str):
        raise ValueError("Invalid EVM address")

    if not EVM_ADDRESS.fullmatch(value):
        raise ValueError("Invalid EVM address")

    if int(value, 16) == 0:
        raise ValueError("Zero address forbidden")

    return value.lower()


def validate_transaction_hash(value):

    if not isinstance(value, str):
        raise ValueError(
            "Invalid Stellar transaction hash"
        )

    value = value.strip().lower()

    if not value.startswith("0x"):
        value = "0x" + value

    if not STELLAR_TX_HASH.fullmatch(value):
        raise ValueError(
            "Invalid Stellar transaction hash"
        )

    if int(value, 16) == 0:
        raise ValueError(
            "Zero transaction hash forbidden"
        )

    return value


def require_integer(
    value,
    name,
    minimum,
    maximum,
):

    if type(value) is not int:
        raise ValueError(
            f"{name} must be an integer"
        )

    if not minimum <= value <= maximum:
        raise ValueError(
            f"{name} out of range"
        )

    return value


# ==========================================
# EN96 AMOUNT VALIDATION
# ==========================================

def en96_to_units(amount):

    try:
        value = Decimal(str(amount))

    except (
        InvalidOperation,
        ValueError,
        TypeError,
    ) as exc:

        raise ValueError(
            "Invalid EN96 amount"
        ) from exc

    if not value.is_finite():
        raise ValueError("Invalid EN96 amount")

    if not Decimal("0") < value <= Decimal("1000000"):
        raise ValueError(
            "Deposit amount out of range"
        )

    units = value * (10**DECIMALS)

    if units != units.to_integral_value():
        raise ValueError(
            "EN96 supports 7 decimals"
        )

    units = int(units)

    if not 1 <= units <= MAX_DEPOSIT_UNITS:
        raise ValueError(
            "Deposit amount out of range"
        )

    return units


# ==========================================
# EIP-712 DATA CONSTRUCTION
# ==========================================

def prepare_deposit_typed_data(
    bridge_address,
    stellar_tx_hash,
    operation_index,
    recipient,
    amount_en96,
    deadline,
    validator_epoch,
):

    """
    Low-level EIP-712 preparation.

    This function does not authorize signing.
    Use prepare_verified_deposit for Stellar
    verification before preparing a request.
    """

    bridge = validate_address(
        bridge_address
    )

    if bridge != BRIDGE_ADDRESS:
        raise ValueError(
            "Unexpected EN96 bridge address"
        )

    tx_hash = validate_transaction_hash(
        stellar_tx_hash
    )

    recipient = validate_address(
        recipient
    )

    if recipient == BRIDGE_ADDRESS:
        raise ValueError(
            "Bridge cannot be recipient"
        )

    operation_index = require_integer(
        operation_index,
        "operation_index",
        0,
        2**32 - 1,
    )

    deadline = require_integer(
        deadline,
        "deadline",
        1,
        2**256 - 1,
    )

    validator_epoch = require_integer(
        validator_epoch,
        "validator_epoch",
        1,
        2**256 - 1,
    )

    amount_units = en96_to_units(
        amount_en96
    )

    return {
        "types": {
            "EIP712Domain": [
                {
                    "name": "name",
                    "type": "string",
                },
                {
                    "name": "version",
                    "type": "string",
                },
                {
                    "name": "chainId",
                    "type": "uint256",
                },
                {
                    "name": "verifyingContract",
                    "type": "address",
                },
            ],
            "Deposit": [
                {
                    "name": "stellarTxHash",
                    "type": "bytes32",
                },
                {
                    "name": "operationIndex",
                    "type": "uint32",
                },
                {
                    "name": "recipient",
                    "type": "address",
                },
                {
                    "name": "amount",
                    "type": "uint256",
                },
                {
                    "name": "deadline",
                    "type": "uint256",
                },
                {
                    "name": "epoch",
                    "type": "uint256",
                },
            ],
        },
        "primaryType": "Deposit",
        "domain": {
            "name": DOMAIN_NAME,
            "version": DOMAIN_VERSION,
            "chainId": CHAIN_ID,
            "verifyingContract": bridge,
        },
        "message": {
            "stellarTxHash": tx_hash,
            "operationIndex": operation_index,
            "recipient": recipient,
            "amount": amount_units,
            "deadline": deadline,
            "epoch": validator_epoch,
        },
    }


# ==========================================
# VERIFIED STELLAR DEPOSIT PREPARATION
# ==========================================

def prepare_verified_deposit(
    stellar_tx_hash,
    operation_index,
    validator_epoch,
):

    """
    Verify a classic Stellar deposit using Horizon.

    Recipient and amount are obtained exclusively
    from the verified Stellar transaction.

    No private keys, signing or minting.
    """

    tx_hash = validate_transaction_hash(
        stellar_tx_hash
    )

    operation_index = require_integer(
        operation_index,
        "operation_index",
        0,
        0,
    )

    validator_epoch = require_integer(
        validator_epoch,
        "validator_epoch",
        1,
        2**256 - 1,
    )

    deposit = verify_deposit(
        tx_hash[2:],
        operation_index,
    )

    if deposit.get("verified") is not True:
        raise ValueError(
            "Stellar deposit verification failed"
        )

    if deposit.get("custody_type") != (
        "classic_stellar_account"
    ):
        raise ValueError(
            "Invalid Stellar custody type"
        )

    if deposit.get("soroban_enabled") is not False:
        raise ValueError(
            "Soroban deposits are not supported"
        )

    if deposit.get("asset_code") != "EN96":
        raise ValueError(
            "Unexpected asset"
        )

    if deposit.get("bnb_chain_id") != CHAIN_ID:
        raise ValueError(
            "Unexpected BNB chain ID"
        )

    if deposit.get("bnb_bridge_address") != BRIDGE_ADDRESS:
        raise ValueError(
            "Unexpected BNB bridge"
        )

    if deposit.get("decimals") != DECIMALS:
        raise ValueError(
            "Invalid EN96 decimals"
        )

    if validate_transaction_hash(
        deposit["stellar_tx_hash"]
    ) != tx_hash:

        raise ValueError(
            "Verified transaction hash mismatch"
        )

    if deposit.get("operation_index") != operation_index:
        raise ValueError(
            "Operation index mismatch"
        )

    recipient = validate_address(
        deposit["bnb_recipient"]
    )

    amount_units = en96_to_units(
        deposit["amount"]
    )

    if type(deposit.get("amount_units")) is not int:
        raise ValueError(
            "Invalid verified amount units"
        )

    if amount_units != deposit["amount_units"]:
        raise ValueError(
            "Verified amount mismatch"
        )

    deadline = (
        int(time.time())
        + SIGNATURE_VALIDITY_SECONDS
    )

    typed_data = prepare_deposit_typed_data(
        bridge_address=BRIDGE_ADDRESS,
        stellar_tx_hash=tx_hash,
        operation_index=operation_index,
        recipient=recipient,
        amount_en96=deposit["amount"],
        deadline=deadline,
        validator_epoch=validator_epoch,
    )

    return {
        "project": "EN96 Ice Bear Kingdom",
        "verified": True,
        "stellar_tx_hash": tx_hash,
        "operation_index": operation_index,
        "stellar_sender": deposit["stellar_sender"],
        "stellar_reserve": deposit["stellar_vault"],
        "bnb_recipient": recipient,
        "amount_en96": deposit["amount"],
        "amount_units": amount_units,
        "deposit_key": deposit["deposit_key"],
        "chain_id": CHAIN_ID,
        "bridge_address": BRIDGE_ADDRESS,
        "validator_epoch": validator_epoch,
        "validator_epoch_onchain_verified": False,
        "deadline": deadline,
        "typed_data": typed_data,
        "custody_lock_proven": False,
        "replay_check_completed": False,
        "reserve_coverage_verified": False,
        "signing_enabled": False,
        "minting_enabled": False,
        "mint_authorized": False,
    }


# ==========================================
# SECURITY STATUS
# ==========================================

def security_status():

    return {
        "project": "EN96 Ice Bear Kingdom",
        "network": "BNB Smart Chain",
        "chain_id": CHAIN_ID,
        "contract": DOMAIN_NAME,
        "bridge_address": BRIDGE_ADDRESS,
        "decimals": DECIMALS,
        "max_supply_en96": "90000000000",
        "max_deposit_en96": "1000000",
        "validator_threshold_target": "2 of 3",
        "custody_type": "classic_stellar_account",
        "soroban_enabled": False,
        "stellar_verification": "CONNECTED",
        "recipient_source": "STELLAR_MEMO_HASH",
        "signature_validity_seconds": (
            SIGNATURE_VALIDITY_SECONDS
        ),
        "signing_enabled": SIGNING_ENABLED,
        "minting_enabled": MINTING_ENABLED,
        "private_keys": "NOT USED",
        "mode": "SAFE PREPARATION ONLY",
    }


if __name__ == "__main__":

    print(
        json.dumps(
            security_status(),
            indent=2,
        )
    )
