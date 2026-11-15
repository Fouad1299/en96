
"""
EN96 Ice Bear Kingdom
Validator preparation - SAFE MODE
BNB Smart Chain Mainnet (Chain ID 56)

This module:
- Validates deposit-signing request fields.
- Prepares EIP-712 typed data for EN96BridgeV3.
- Does NOT sign, mint, transfer, or broadcast.
- Does NOT use private keys.

IMPORTANT:
A validated request is NOT proof of a Stellar deposit.
Independent Stellar verification is required before signing.
"""

import json
import re
from decimal import Decimal, InvalidOperation

CHAIN_ID = 56
DOMAIN_NAME = "EN96BridgeV3"
DOMAIN_VERSION = "1"

DECIMALS = 7
MAX_DEPOSIT_UNITS = 1_000_000 * 10**DECIMALS

SIGNING_ENABLED = False
MINTING_ENABLED = False

EVM_ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
STELLAR_TX_HASH = re.compile(r"^0x[0-9a-fA-F]{64}$")


def validate_address(value):
    if not isinstance(value, str):
        raise ValueError("Invalid EVM address")

    if not EVM_ADDRESS.fullmatch(value):
        raise ValueError("Invalid EVM address")

    if int(value, 16) == 0:
        raise ValueError("Zero address forbidden")

    return value


def validate_transaction_hash(value):
    if not isinstance(value, str):
        raise ValueError("Invalid Stellar transaction hash")

    if not STELLAR_TX_HASH.fullmatch(value):
        raise ValueError("Invalid Stellar transaction hash")

    if int(value, 16) == 0:
        raise ValueError("Zero transaction hash forbidden")

    return value


def require_integer(value, name, minimum, maximum):
    if type(value) is not int:
        raise ValueError(f"{name} must be an integer")

    if not minimum <= value <= maximum:
        raise ValueError(f"{name} out of range")

    return value


def en96_to_units(amount):
    try:
        value = Decimal(str(amount))
    except (InvalidOperation, ValueError):
        raise ValueError("Invalid EN96 amount")

    if not value.is_finite():
        raise ValueError("Invalid EN96 amount")

    units = value * (10**DECIMALS)

    if units != units.to_integral_value():
        raise ValueError("EN96 supports 7 decimals")

    units = int(units)

    if not 1 <= units <= MAX_DEPOSIT_UNITS:
        raise ValueError("Deposit amount out of range")

    return units


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
    Prepare typed data matching EN96BridgeV3.

    This function does NOT verify Stellar deposits.
    This function does NOT sign anything.
    """

    bridge = validate_address(bridge_address)
    tx_hash = validate_transaction_hash(stellar_tx_hash)
    recipient = validate_address(recipient)

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

    amount_units = en96_to_units(amount_en96)

    return {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            "Deposit": [
                {"name": "stellarTxHash", "type": "bytes32"},
                {"name": "operationIndex", "type": "uint32"},
                {"name": "recipient", "type": "address"},
                {"name": "amount", "type": "uint256"},
                {"name": "deadline", "type": "uint256"},
                {"name": "epoch", "type": "uint256"},
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


def security_status():
    return {
        "project": "EN96 Ice Bear Kingdom",
        "network": "BNB Smart Chain",
        "chain_id": CHAIN_ID,
        "contract": DOMAIN_NAME,
        "signing_enabled": SIGNING_ENABLED,
        "minting_enabled": MINTING_ENABLED,
        "stellar_verification": "REQUIRED",
        "private_keys": "NOT USED",
        "mode": "SAFE PREPARATION ONLY",
    }


if __name__ == "__main__":
    print(json.dumps(
        security_status(),
        indent=2,
    ))
