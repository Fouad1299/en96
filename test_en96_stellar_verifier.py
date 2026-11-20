
import unittest
from unittest.mock import patch
from decimal import Decimal

import en96_stellar_verifier as verifier


ISSUER = "G" + "A" * 55
VAULT = "G" + "B" * 55
SENDER = "G" + "C" * 55

TX_HASH = "ab" * 32


def make_transaction(successful=True):
    return {
        "successful": successful,
        "hash": TX_HASH,
        "ledger": 123456,
        "created_at": "2026-11-20T12:00:00Z",
    }


def make_operation(**changes):
    operation = {
        "id": "123456789",
        "paging_token": "123456789",
        "transaction_hash": TX_HASH,
        "transaction_successful": True,
        "type": "payment",
        "asset_type": "credit_alphanum4",
        "asset_code": "EN96",
        "asset_issuer": ISSUER,
        "from": SENDER,
        "to": VAULT,
        "amount": "100.0000000",
    }
    operation.update(changes)
    return operation


class TestEN96StellarVerifier(unittest.TestCase):

    def setUp(self):
        self.config_patches = [
            patch.object(verifier, "ASSET_CODE", "EN96"),
            patch.object(verifier, "ISSUER", ISSUER),
            patch.object(verifier, "VAULT", VAULT),
        ]

        for item in self.config_patches:
            item.start()
            self.addCleanup(item.stop)

        self.transaction = make_transaction()
        self.operation = make_operation()

        self.horizon_patch = patch.object(
            verifier,
            "horizon_get",
            side_effect=self.fake_horizon,
        )
        self.mock_horizon = self.horizon_patch.start()
        self.addCleanup(self.horizon_patch.stop)

    def fake_horizon(self, path):
        if path == "/transactions/" + TX_HASH:
            return self.transaction

        if path.startswith(
            "/transactions/" + TX_HASH + "/operations"
        ):
            return {
                "_embedded": {
                    "records": [self.operation]
                }
            }

        raise AssertionError(
            "Unexpected Horizon request: " + path
        )

    def assert_rejected(self):
        with self.assertRaises(
            verifier.StellarVerificationError
        ):
            verifier.verify_deposit(TX_HASH, 0)

    def test_valid_deposit(self):
        result = verifier.verify_deposit(TX_HASH, 0)

        self.assertTrue(result["verified"])
        self.assertEqual(
            result["stellar_tx_hash"],
            TX_HASH,
        )
        self.assertEqual(
            result["operation_index"],
            0,
        )
        self.assertEqual(
            result["asset_code"],
            "EN96",
        )
        self.assertEqual(
            result["asset_issuer"],
            ISSUER,
        )
        self.assertEqual(
            result["stellar_vault"],
            VAULT,
        )
        self.assertEqual(
            result["stellar_sender"],
            SENDER,
        )
        self.assertEqual(
            result["amount"],
            "100.0000000",
        )

    def test_failed_transaction(self):
        self.transaction["successful"] = False
        self.assert_rejected()

    def test_wrong_transaction_hash(self):
        self.transaction["hash"] = "cd" * 32
        self.assert_rejected()

    def test_failed_operation(self):
        self.operation["transaction_successful"] = False
        self.assert_rejected()

    def test_wrong_operation_transaction(self):
        self.operation["transaction_hash"] = "cd" * 32
        self.assert_rejected()

    def test_wrong_operation_type(self):
        self.operation["type"] = "create_account"
        self.assert_rejected()

    def test_wrong_asset_type(self):
        self.operation["asset_type"] = "native"
        self.assert_rejected()

    def test_wrong_asset_code(self):
        self.operation["asset_code"] = "FAKE"
        self.assert_rejected()

    def test_wrong_issuer(self):
        self.operation["asset_issuer"] = SENDER
        self.assert_rejected()

    def test_wrong_vault(self):
        self.operation["to"] = SENDER
        self.assert_rejected()

    def test_issuer_as_sender(self):
        self.operation["from"] = ISSUER
        self.assert_rejected()

    def test_vault_as_sender(self):
        self.operation["from"] = VAULT
        self.assert_rejected()

    def test_invalid_sender(self):
        self.operation["from"] = "INVALID"
        self.assert_rejected()

    def test_zero_amount(self):
        self.operation["amount"] = "0"
        self.assert_rejected()

    def test_negative_amount(self):
        self.operation["amount"] = "-1"
        self.assert_rejected()

    def test_amount_above_limit(self):
        self.operation["amount"] = "1000000.0000001"
        self.assert_rejected()

    def test_maximum_amount_allowed(self):
        self.operation["amount"] = "1000000.0000000"

        result = verifier.verify_deposit(TX_HASH, 0)

        self.assertEqual(
            result["amount"],
            "1000000.0000000",
        )

    def test_invalid_precision(self):
        self.operation["amount"] = "0.00000001"
        self.assert_rejected()

    def test_non_finite_amounts(self):
        for amount in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(amount=amount):
                self.operation["amount"] = amount
                self.assert_rejected()

    def test_missing_amount(self):
        del self.operation["amount"]
        self.assert_rejected()

    def test_invalid_hash_format(self):
        with self.assertRaises(
            verifier.StellarVerificationError
        ):
            verifier.verify_deposit("INVALID", 0)

    def test_invalid_operation_index(self):
        for index in (-1, "0", True):
            with self.subTest(index=index):
                with self.assertRaises(
                    verifier.StellarVerificationError
                ):
                    verifier.verify_deposit(TX_HASH, index)

    def test_missing_operation(self):
        self.operation = None

        def empty_operations(path):
            if path == "/transactions/" + TX_HASH:
                return self.transaction

            return {
                "_embedded": {
                    "records": []
                }
            }

        self.mock_horizon.side_effect = empty_operations
        self.assert_rejected()

    def test_historical_treasury_blocked(self):
        with self.assertRaisesRegex(
            verifier.StellarVerificationError,
            "Historical treasury funding",
        ):
            verifier.verify_deposit(
                verifier.BLOCKED_TREASURY_TX,
                0,
            )

        self.mock_horizon.assert_not_called()

    def test_missing_configuration(self):
        with patch.object(verifier, "ASSET_CODE", ""):
            self.assert_rejected()

    def test_invalid_issuer_configuration(self):
        with patch.object(verifier, "ISSUER", "INVALID"):
            self.assert_rejected()

    def test_invalid_vault_configuration(self):
        with patch.object(verifier, "VAULT", "INVALID"):
            self.assert_rejected()

    def test_same_issuer_and_vault(self):
        with patch.object(verifier, "VAULT", ISSUER):
            self.assert_rejected()

    def test_read_only_verification(self):
        result = verifier.verify_deposit(TX_HASH, 0)

        self.assertTrue(result["verified"])
        self.assertEqual(
            Decimal(result["amount"]),
            Decimal("100"),
        )


if __name__ == "__main__":
    unittest.main()
