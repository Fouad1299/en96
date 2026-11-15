
import unittest
from decimal import Decimal

from en96_validator_signer import (
    CHAIN_ID,
    SIGNING_ENABLED,
    MINTING_ENABLED,
    en96_to_units,
    prepare_deposit_typed_data,
    validate_address,
    validate_transaction_hash,
    security_status,
)


BRIDGE = "0x" + "11" * 20
RECIPIENT = "0x" + "22" * 20
TX_HASH = "0x" + "ab" * 32


class TestEN96ValidatorSigner(unittest.TestCase):

    def test_safe_mode(self):
        self.assertEqual(CHAIN_ID, 56)
        self.assertFalse(SIGNING_ENABLED)
        self.assertFalse(MINTING_ENABLED)

        status = security_status()
        self.assertEqual(
            status["mode"],
            "SAFE PREPARATION ONLY",
        )

    def test_en96_decimals(self):
        self.assertEqual(en96_to_units("1"), 10**7)
        self.assertEqual(en96_to_units("0.0000001"), 1)
        self.assertEqual(
            en96_to_units("1000000"),
            10**13,
        )

    def test_invalid_amounts(self):
        for amount in (
            "0",
            "-1",
            "1000001",
            "0.00000001",
            "NaN",
            "Infinity",
        ):
            with self.subTest(amount=amount):
                with self.assertRaises(ValueError):
                    en96_to_units(amount)

    def test_valid_addresses(self):
        self.assertEqual(
            validate_address(BRIDGE),
            BRIDGE,
        )
        self.assertEqual(
            validate_transaction_hash(TX_HASH),
            TX_HASH,
        )

    def test_zero_address_rejected(self):
        with self.assertRaises(ValueError):
            validate_address("0x" + "00" * 20)

    def test_zero_transaction_hash_rejected(self):
        with self.assertRaises(ValueError):
            validate_transaction_hash("0x" + "00" * 32)

    def test_eip712_structure(self):
        data = prepare_deposit_typed_data(
            bridge_address=BRIDGE,
            stellar_tx_hash=TX_HASH,
            operation_index=0,
            recipient=RECIPIENT,
            amount_en96=Decimal("1"),
            deadline=2000000000,
            validator_epoch=1,
        )

        self.assertEqual(
            data["domain"]["name"],
            "EN96BridgeV3",
        )
        self.assertEqual(
            data["domain"]["version"],
            "1",
        )
        self.assertEqual(
            data["domain"]["chainId"],
            56,
        )
        self.assertEqual(
            data["domain"]["verifyingContract"],
            BRIDGE,
        )
        self.assertEqual(
            data["primaryType"],
            "Deposit",
        )
        self.assertEqual(
            data["message"]["amount"],
            10**7,
        )
        self.assertEqual(
            data["message"]["epoch"],
            1,
        )

    def test_invalid_operation_index(self):
        with self.assertRaises(ValueError):
            prepare_deposit_typed_data(
                BRIDGE,
                TX_HASH,
                2**32,
                RECIPIENT,
                "1",
                2000000000,
                1,
            )

    def test_invalid_epoch(self):
        with self.assertRaises(ValueError):
            prepare_deposit_typed_data(
                BRIDGE,
                TX_HASH,
                0,
                RECIPIENT,
                "1",
                2000000000,
                0,
            )


if __name__ == "__main__":
    unittest.main()
