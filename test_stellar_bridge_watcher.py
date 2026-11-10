
"""
EN96 Ice Bear Kingdom
Stellar Bridge Watcher - Safety Tests v0.9

Tests use synthetic Stellar Horizon responses.

NO real network requests
NO database connections
NO EN96 transfers
NO BNB minting
"""

import copy
import unittest
from decimal import Decimal
from unittest.mock import patch

import stellar_bridge_watcher as watcher


TX_HASH = "a" * 64
OTHER_HASH = "b" * 64

SOURCE = (
    "GAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
)

ESCROW = watcher.ESCROW_ACCOUNT
ISSUER = watcher.ASSET_ISSUER

TIMESTAMP = "2026-11-10T12:00:00Z"

OPERATION_ID = "123456789"
PAGING_TOKEN = "123456789"


def make_payment(
    amount="5.0000000",
    asset_code="EN96",
    asset_issuer=ISSUER,
    destination=ESCROW,
    source=SOURCE,
    transaction_hash=TX_HASH,
):
    return {
        "id": OPERATION_ID,
        "paging_token": PAGING_TOKEN,
        "type": "payment",
        "from": source,
        "to": destination,
        "asset_type": "credit_alphanum4",
        "asset_code": asset_code,
        "asset_issuer": asset_issuer,
        "amount": amount,
        "transaction_hash": transaction_hash,
        "created_at": TIMESTAMP,
    }


def make_transaction(
    transaction_hash=TX_HASH,
    successful=True,
):
    return {
        "hash": transaction_hash,
        "successful": successful,
        "ledger": 12345,
        "created_at": TIMESTAMP,
    }


def make_records(records):
    return {
        "_embedded": {
            "records": records
        }
    }


class FakeConnection:
    """No real database connection is created."""

    def __init__(self):
        self.saved_tokens = []


class TestEN96Watcher09(unittest.TestCase):

    def test_correct_en96_payment_detected(self):
        payment = make_payment()

        self.assertTrue(
            watcher.is_en96_deposit(payment)
        )

    def test_wrong_asset_rejected(self):
        payment = make_payment(
            asset_code="FAKE"
        )

        self.assertFalse(
            watcher.is_en96_deposit(payment)
        )

    def test_wrong_issuer_rejected(self):
        payment = make_payment(
            asset_issuer=SOURCE
        )

        self.assertFalse(
            watcher.is_en96_deposit(payment)
        )

    def test_wrong_destination_rejected(self):
        payment = make_payment(
            destination=SOURCE
        )

        self.assertFalse(
            watcher.is_en96_deposit(payment)
        )

    def test_zero_deposit_rejected(self):
        payment = make_payment(
            amount="0"
        )

        with self.assertRaises(RuntimeError):
            watcher.is_en96_deposit(payment)

    def test_negative_deposit_rejected(self):
        payment = make_payment(
            amount="-1"
        )

        with self.assertRaises(RuntimeError):
            watcher.is_en96_deposit(payment)

    def test_more_than_seven_decimals_rejected(self):
        payment = make_payment(
            amount="1.12345678"
        )

        with self.assertRaises(RuntimeError):
            watcher.is_en96_deposit(payment)

    def test_successful_deposit_verification(self):
        payment = make_payment()

        def fake_get_json(path, params=None):
            if path == "/transactions/" + TX_HASH:
                return make_transaction()

            if path == (
                "/transactions/"
                + TX_HASH
                + "/operations"
            ):
                return make_records([payment])

            raise AssertionError(
                "Unexpected Horizon request: " + path
            )

        with patch.object(
            watcher,
            "get_json",
            side_effect=fake_get_json,
        ):
            result = watcher.verify_deposit(payment)

        self.assertEqual(
            result["stellar_tx_hash"],
            TX_HASH
        )

        self.assertEqual(
            result["operation_index"],
            0
        )

        self.assertEqual(
            result["stellar_operation_id"],
            OPERATION_ID
        )

        self.assertEqual(
            Decimal(result["amount"]),
            Decimal("5")
        )

        self.assertEqual(
            result["status"],
            "observed"
        )

    def test_failed_transaction_rejected(self):
        payment = make_payment()

        with patch.object(
            watcher,
            "get_json",
            return_value=make_transaction(
                successful=False
            ),
        ):
            with self.assertRaises(RuntimeError):
                watcher.verify_deposit(payment)

    def test_transaction_hash_mismatch_rejected(self):
        payment = make_payment()

        with patch.object(
            watcher,
            "get_json",
            return_value=make_transaction(
                transaction_hash=OTHER_HASH
            ),
        ):
            with self.assertRaises(RuntimeError):
                watcher.verify_deposit(payment)

    def test_operation_amount_mismatch_rejected(self):
        payment = make_payment()
        altered = copy.deepcopy(payment)
        altered["amount"] = "999"

        def fake_get_json(path, params=None):
            if path == "/transactions/" + TX_HASH:
                return make_transaction()

            return make_records([altered])

        with patch.object(
            watcher,
            "get_json",
            side_effect=fake_get_json,
        ):
            with self.assertRaises(RuntimeError):
                watcher.verify_deposit(payment)

    def test_operation_id_mismatch_rejected(self):
        payment = make_payment()
        altered = copy.deepcopy(payment)
        altered["id"] = "987654321"

        def fake_get_json(path, params=None):
            if path == "/transactions/" + TX_HASH:
                return make_transaction()

            return make_records([altered])

        with patch.object(
            watcher,
            "get_json",
            side_effect=fake_get_json,
        ):
            with self.assertRaises(RuntimeError):
                watcher.verify_deposit(payment)

    def test_deposit_does_not_advance_checkpoint(self):
        payment = make_payment()
        connection = FakeConnection()

        def fake_get_json(path, params=None):
            if path.startswith(
                "/accounts/" + ESCROW + "/operations"
            ):
                return make_records([payment])

            if path == "/transactions/" + TX_HASH:
                return make_transaction()

            if path == (
                "/transactions/"
                + TX_HASH
                + "/operations"
            ):
                return make_records([payment])

            raise AssertionError(
                "Unexpected Horizon request: " + path
            )

        def fake_save_checkpoint(conn, token):
            conn.saved_tokens.append(token)

        with (
            patch.object(
                watcher,
                "read_checkpoint",
                return_value="0",
            ),
            patch.object(
                watcher,
                "save_checkpoint",
                side_effect=fake_save_checkpoint,
            ),
            patch.object(
                watcher,
                "get_json",
                side_effect=fake_get_json,
            ),
        ):
            with self.assertRaises(RuntimeError):
                watcher.scan_escrow(connection)

        self.assertEqual(
            connection.saved_tokens,
            []
        )

    def test_empty_history_does_not_save_checkpoint(self):
        connection = FakeConnection()

        with (
            patch.object(
                watcher,
                "read_checkpoint",
                return_value="123",
            ),
            patch.object(
                watcher,
                "get_json",
                return_value=make_records([]),
            ),
            patch.object(
                watcher,
                "save_checkpoint",
                side_effect=lambda conn, token:
                    conn.saved_tokens.append(token),
            ),
        ):
            scanned, reached_end = watcher.scan_escrow(
                connection
            )

        self.assertEqual(scanned, 0)
        self.assertTrue(reached_end)
        self.assertEqual(
            connection.saved_tokens,
            []
        )

    def test_bridge_flags_cannot_enable_minting(self):
        with patch.dict(
            "os.environ",
            {
                "EN96_ENABLE_BNB_MINT": "1",
                "EN96_RECORD_DEPOSITS": "0",
            },
        ):
            with self.assertRaises(RuntimeError):
                watcher.require_disabled_features()

    def test_bridge_flags_cannot_enable_recording(self):
        with patch.dict(
            "os.environ",
            {
                "EN96_ENABLE_BNB_MINT": "0",
                "EN96_RECORD_DEPOSITS": "1",
            },
        ):
            with self.assertRaises(RuntimeError):
                watcher.require_disabled_features()


if __name__ == "__main__":
    unittest.main(verbosity=2)
