
# EN96 Ice Bear Kingdom
# BNB Smart Chain wallet signature security
# Chain ID: 56
# This module does not mint or transfer tokens.

import re

from eth_account import Account
from eth_account.messages import encode_defunct


BNB_CHAIN_ID = 56

ADDRESS_PATTERN = re.compile(
    r"^0x[0-9a-fA-F]{40}$"
)


def normalize_bnb_address(address):
    """
    Validate an EVM address and return lowercase form.
    """
    if not isinstance(address, str):
        raise ValueError("Invalid BNB wallet address")

    address = address.strip()

    if not ADDRESS_PATTERN.fullmatch(address):
        raise ValueError("Invalid BNB wallet address")

    return address.lower()


def build_wallet_message(
    telegram_id,
    bnb_address,
    nonce,
    issued_at,
    expires_at,
):
    """
    Build a message binding a BNB wallet to an
    authenticated EN96 Telegram account.

    The nonce must be generated securely by the server.
    """

    address = normalize_bnb_address(bnb_address)

    telegram_id = str(telegram_id)

    if not telegram_id.isdigit():
        raise ValueError("Invalid Telegram ID")

    if not isinstance(nonce, str):
        raise ValueError("Invalid nonce")

    if not re.fullmatch(
        r"[0-9a-f]{64}", nonce
    ):
        raise ValueError("Invalid nonce")

    return (
        "EN96 Ice Bear Kingdom\n"
        "BNB Wallet Verification\n"
        "\n"
        "Action: Link BNB wallet\n"
        f"Telegram ID: {telegram_id}\n"
        f"BNB Address: {address}\n"
        f"Chain ID: {BNB_CHAIN_ID}\n"
        f"Nonce: {nonce}\n"
        f"Issued At: {issued_at}\n"
        f"Expires At: {expires_at}\n"
        "\n"
        "Signing proves wallet ownership only.\n"
        "This message does not authorize a "
        "transaction, token transfer, or spending."
    )


def verify_wallet_signature(
    message,
    signature,
    expected_address,
):
    """
    Verify an Ethereum personal_sign / EIP-191
    signature and recover the signing address.
    """

    expected = normalize_bnb_address(
        expected_address
    )

    if not isinstance(message, str):
        return False

    if not isinstance(signature, str):
        return False

    if not re.fullmatch(
        r"0x[0-9a-fA-F]{130}", signature
    ):
        return False

    try:
        encoded = encode_defunct(text=message)

        recovered = Account.recover_message(
            encoded,
            signature=signature,
        )

        return recovered.lower() == expected

    except Exception:
        return False
