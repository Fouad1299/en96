
"""
EN96 Ice Bear Kingdom
Stellar Bridge Watcher - Safety Tests v0.9

Synthetic tests only:
- No real Horizon requests
- No real database connections
- No Stellar transfers
- No BNB minting
"""

import copy
import os
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

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


def make_deposit():
    return {
        "stellar_tx_hash": TX_HASH,
        "operation_index": 0,
        "stellar_operation_id": OPERATION_ID,
        "source_account": SOURCE,
        "escrow_account": ESCROW,
        "asset_code": "EN96",
        "asset_issuer": ISSUER,
        "amount": Decimal("5"),
        "stellar_ledger": 12345,
        "stellar_created_at": datetime(
            2026, 11, 10, 12, 0,
            tzinfo=timezone.utc
        ),
        "status": "observed",
    }


def make_existing_row(deposit):
    return (
        deposit["stellar_tx_hash"],
        deposit["operation_index"],
        deposit["stellar_operation_id"],
        deposit["source_account"],
        deposit["escrow_account"],
        deposit["asset_code"],
        deposit["asset_issuer"],
        deposit["amount"],
        deposit["stellar_ledger"],
        deposit["stellar_created_at"],
        deposit["status"],
    )


def fake_horizon(path, params=None):
    payment = make_payment()

    if path == "/transactions/" + TX_HASH:
        return make_transaction()

    if path == (
        "/transactions/"
        + TX_HASH
        + "/operations"
    ):
        return make_records([payment])

    if path == (
        "/accounts/"
        + ESCROW
        + "/operations"
    ):
        return make_records([payment])

    raise AssertionError(
        "Unexpected Horizon request: " + path
    )


class FakeConnection:
    """Tracks transactions without using a database."""

    def __init__(self):
        self.saved_tokens = []
        self.commits = 0
        self.rollbacks = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class TestEN96Watcher09(unittest.TestCase):

    def test_correct_en96_payment_detected(self):
        self.assertTrue(
            watcher.is_en96_deposit(make_payment())
        )

    def test_wrong_asset_rejected(self):
        self.assertFalse(
            watcher.is_en96_deposit(
                make_payment(asset_code="FAKE")
            )
        )

    def test_wrong_issuer_rejected(self):
        self.assertFalse(
            watcher.is_en96_deposit(
                make_payment(asset_issuer=SOURCE)
            )
        )

    def test_wrong_destination_rejected(self):
        self.assertFalse(
            watcher.is_en96_deposit(
                make_payment(destination=SOURCE)
            )
        )

    def test_zero_deposit_rejected(self):
        with self.assertRaises(RuntimeError):
            watcher.is_en96_deposit(
                make_payment(amount="0")
            )

    def test_negative_deposit_rejected(self):
        with self.assertRaises(RuntimeError):
            watcher.is_en96_deposit(
                make_payment(amount="-1")
            )

    def test_too_many_decimals_rejected(self):
        with self.assertRaises(RuntimeError):
            watcher.is_en96_deposit(
                make_payment(amount="1.12345678")
            )

    def test_deposit_limit_rejected(self):
        payment = make_payment(
            amount="1000000.0000001"
        )

        with self.assertRaises(RuntimeError):
            watcher.verify_deposit(payment)

    def test_successful_deposit_verification(self):
        payment = make_payment()

        with patch.object(
            watcher,
            "get_json",
            side_effect=fake_horizon,
        ):
            result = watcher.verify_deposit(payment)

        self.assertEqual(
            result["stellar_tx_hash"], TX_HASH
        )
        self.assertEqual(
            result["operation_index"], 0
        )
        self.assertEqual(
            result["stellar_operation_id"],
            OPERATION_ID
        )
        self.assertEqual(
            result["amount"], Decimal("5")
        )
        self.assertEqual(
            result["status"], "observed"
        )

    def test_failed_transaction_rejected(self):
        with patch.object(
            watcher,
            "get_json",
            return_value=make_transaction(
                successful=False
            ),
        ):
            with self.assertRaises(RuntimeError):
                watcher.verify_deposit(make_payment())

    def test_transaction_hash_mismatch_rejected(self):
        with patch.object(
            watcher,
            "get_json",
            return_value=make_transaction(
                transaction_hash=OTHER_HASH
            ),
        ):
            with self.assertRaises(RuntimeError):
                watcher.verify_deposit(make_payment())

    def test_operation_amount_mismatch_rejected(self):
        altered = make_payment()
        altered["amount"] = "999"

        def response(path, params=None):
            if path == "/transactions/" + TX_HASH:
                return make_transaction()
            return make_records([altered])

        with patch.object(
            watcher, "get_json",
            side_effect=response
        ):
            with self.assertRaises(RuntimeError):
                watcher.verify_deposit(make_payment())

    def test_operation_id_mismatch_rejected(self):
        altered = make_payment()
        altered["id"] = "987654321"

        def response(path, params=None):
            if path == "/transactions/" + TX_HASH:
                return make_transaction()
            return make_records([altered])

        with patch.object(
            watcher, "get_json",
            side_effect=response
        ):
            with self.assertRaises(RuntimeError):
                watcher.verify_deposit(make_payment())

    def test_recording_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(
                watcher.check_features()
            )

    def test_recording_flag_is_explicit(self):
        with patch.dict(
            os.environ,
            {"EN96_RECORD_DEPOSITS": "1"},
            clear=True,
        ):
            self.assertTrue(
                watcher.check_features()
            )

    def test_minting_cannot_be_enabled(self):
        with patch.dict(
            os.environ,
            {"EN96_ENABLE_BNB_MINT": "1"},
            clear=True,
        ):
            with self.assertRaises(RuntimeError):
                watcher.check_features()

    def test_signing_cannot_be_enabled(self):
        with patch.dict(
            os.environ,
            {"EN96_ENABLE_SIGNING": "1"},
            clear=True,
        ):
            with self.assertRaises(RuntimeError):
                watcher.check_features()

    def test_payout_cannot_be_enabled(self):
        with patch.dict(
            os.environ,
            {"EN96_ENABLE_STELLAR_PAYOUT": "1"},
            clear=True,
        ):
            with self.assertRaises(RuntimeError):
                watcher.check_features()

    def test_invalid_recording_flag_rejected(self):
        with patch.dict(
            os.environ,
            {"EN96_RECORD_DEPOSITS": "invalid"},
            clear=True,
        ):
            with self.assertRaises(RuntimeError):
                watcher.check_features()

    def test_record_deposit_insert_success(self):
        deposit = make_deposit()
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (42,)

        result = watcher.record_deposit(conn, deposit)

        self.assertTrue(result)
        self.assertEqual(cursor.execute.call_count, 1)

        sql = cursor.execute.call_args.args[0]

        self.assertIn(
            "INSERT INTO public.en96_bridge_deposits",
            sql
        )
        self.assertIn("'observed', NULL, false", sql)
        self.assertIn("ON CONFLICT DO NOTHING", sql)

        conn.commit.assert_not_called()

    def test_duplicate_deposit_is_idempotent(self):
        deposit = make_deposit()
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value

        cursor.fetchone.side_effect = [
            None,
            make_existing_row(deposit),
        ]

        result = watcher.record_deposit(conn, deposit)

        self.assertFalse(result)
        self.assertEqual(cursor.execute.call_count, 2)
        conn.commit.assert_not_called()

    def test_conflicting_deposit_rejected(self):
        deposit = make_deposit()
        existing = list(make_existing_row(deposit))
        existing[7] = Decimal("999")

        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value

        cursor.fetchone.side_effect = [
            None,
            tuple(existing),
        ]

        with self.assertRaises(RuntimeError):
            watcher.record_deposit(conn, deposit)

        conn.commit.assert_not_called()

    def test_inaccessible_conflict_rejected(self):
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value

        cursor.fetchone.side_effect = [
            None,
            None,
        ]

        with self.assertRaises(RuntimeError):
            watcher.record_deposit(
                conn, make_deposit()
            )

    def test_deposit_does_not_advance_when_disabled(self):
        conn = FakeConnection()

        with (
            patch.object(
                watcher,
                "read_checkpoint",
                return_value="0",
            ),
            patch.object(
                watcher,
                "get_json",
                side_effect=fake_horizon,
            ),
            patch.object(
                watcher,
                "save_checkpoint",
            ) as save,
            patch.object(
                watcher,
                "record_deposit",
            ) as record,
        ):
            with self.assertRaises(RuntimeError):
                watcher.scan_escrow(conn, False)

        save.assert_not_called()
        record.assert_not_called()
        self.assertEqual(conn.commits, 0)

    def test_empty_history(self):
        conn = FakeConnection()

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
            ) as save,
        ):
            scanned, recorded, ended = (
                watcher.scan_escrow(conn, False)
            )

        self.assertEqual(scanned, 0)
        self.assertEqual(recorded, 0)
        self.assertTrue(ended)
        save.assert_not_called()

    def test_recording_page_commits_once(self):
        conn = FakeConnection()

        with (
            patch.object(
                watcher,
                "read_checkpoint",
                return_value="0",
            ),
            patch.object(
                watcher,
                "get_json",
                side_effect=fake_horizon,
            ),
            patch.object(
                watcher,
                "record_deposit",
                return_value=True,
            ) as record,
            patch.object(
                watcher,
                "save_checkpoint",
            ) as save,
        ):
            scanned, recorded, ended = (
                watcher.scan_escrow(conn, True)
            )

        self.assertEqual(scanned, 1)
        self.assertEqual(recorded, 1)
        self.assertTrue(ended)

        record.assert_called_once()
        save.assert_called_once_with(
            conn, PAGING_TOKEN
        )

        self.assertEqual(conn.commits, 1)
        self.assertEqual(conn.rollbacks, 0)

    def test_recording_failure_rolls_back(self):
        conn = FakeConnection()

        with (
            patch.object(
                watcher,
                "read_checkpoint",
                return_value="0",
            ),
            patch.object(
                watcher,
                "get_json",
                side_effect=fake_horizon,
            ),
            patch.object(
                watcher,
                "record_deposit",
                side_effect=RuntimeError(
                    "Simulated database failure"
                ),
            ),
            patch.object(
                watcher,
                "save_checkpoint",
            ) as save,
        ):
            with self.assertRaises(RuntimeError):
                watcher.scan_escrow(conn, True)

        save.assert_not_called()
        self.assertEqual(conn.commits, 0)
        self.assertEqual(conn.rollbacks, 1)

    def test_checkpoint_failure_rolls_back(self):
        conn = FakeConnection()

        with (
            patch.object(
                watcher,
                "read_checkpoint",
                return_value="0",
            ),
            patch.object(
                watcher,
                "get_json",
                side_effect=fake_horizon,
            ),
            patch.object(
                watcher,
                "record_deposit",
                return_value=True,
            ),
            patch.object(
                watcher,
                "save_checkpoint",
                side_effect=RuntimeError(
                    "Simulated checkpoint failure"
                ),
            ),
        ):
            with self.assertRaises(RuntimeError):
                watcher.scan_escrow(conn, True)

        self.assertEqual(conn.commits, 0)
        self.assertEqual(conn.rollbacks, 1)

    def test_duplicate_page_commits_without_new_record(self):
        conn = FakeConnection()

        with (
            patch.object(
                watcher,
                "read_checkpoint",
                return_value="0",
            ),
            patch.object(
                watcher,
                "get_json",
                side_effect=fake_horizon,
            ),
            patch.object(
                watcher,
                "record_deposit",
                return_value=False,
            ),
            patch.object(
                watcher,
                "save_checkpoint",
            ) as save,
        ):
            scanned, recorded, ended = (
                watcher.scan_escrow(conn, True)
            )

        self.assertEqual(scanned, 1)
        self.assertEqual(recorded, 0)
        self.assertTrue(ended)
        self.assertEqual(conn.commits, 1)
        save.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
