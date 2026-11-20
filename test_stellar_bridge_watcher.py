
import os
import unittest
from decimal import Decimal
from unittest.mock import patch

import stellar_bridge_watcher as watcher


# ==========================================
# EN96 ICE BEAR KINGDOM
# Stellar Bridge Watcher Tests
# Version 0.9.2
#
# All tests use synthetic data.
# No blockchain transactions.
# No database writes.
# No BNB minting.
# ==========================================


def make_operation(
    tx_hash=None,
    operation_id="281113898810253313",
    amount="1.0000000",
    source=None,
    destination=None,
    asset_code=None,
    asset_issuer=None,
    operation_type="payment",
    asset_type="credit_alphanum4",
):
    return {
        "id": operation_id,
        "paging_token": operation_id,
        "transaction_hash": (
            tx_hash
            or (
                "7a58fb081984b7dfdeda7ec1577ae55"
                "b126cb0c28e78dbd82662071ab5c94ecd"
            )
        ),
        "transaction_successful": True,
        "type": operation_type,
        "from": source or watcher.TREASURY_ACCOUNT,
        "to": destination or watcher.ESCROW_ACCOUNT,
        "source_account": source or watcher.TREASURY_ACCOUNT,
        "asset_type": asset_type,
        "asset_code": asset_code or watcher.ASSET_CODE,
        "asset_issuer": (
            asset_issuer or watcher.ASSET_ISSUER
        ),
        "amount": amount,
        "created_at": "2026-11-13T04:54:52Z",
    }


def make_treasury_operation():
    operation = make_operation(
        tx_hash=watcher.TREASURY_FUNDING_TX,
        operation_id=watcher.TREASURY_FUNDING_OPERATION_ID,
        amount=str(watcher.TREASURY_FUNDING_AMOUNT),
    )
    operation["created_at"] = "2026-11-16T02:16:57Z"
    return operation


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.result = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, query, params=None):
        self.connection.queries.append((query, params))

        normalized = " ".join(query.split()).lower()

        if "select paging_token" in normalized:
            self.result = (
                self.connection.checkpoint,
            )

        elif "returning id" in normalized:
            self.result = (1,)

        elif "select stellar_tx_hash" in normalized:
            self.result = None

        else:
            self.result = None

    def fetchone(self):
        return self.result


class FakeConnection:
    def __init__(self, checkpoint="280655600029863937"):
        self.checkpoint = checkpoint
        self.queries = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class TestEN96WatcherConfiguration(unittest.TestCase):

    def test_version(self):
        self.assertEqual(watcher.VERSION, "0.9.2")

    def test_supply_limit(self):
        self.assertEqual(
            watcher.MAX_SUPPLY,
            Decimal("90000000000"),
        )

    def test_deposit_limit(self):
        self.assertEqual(
            watcher.MAX_DEPOSIT,
            Decimal("1000000"),
        )

    def test_treasury_hash(self):
        self.assertEqual(
            watcher.TREASURY_FUNDING_TX,
            (
                "d2afa7fe4f8fc21c5208828e046091"
                "f915c536959108d18d329f345ae13a0e91"
            ),
        )

    def test_treasury_amount(self):
        self.assertEqual(
            watcher.TREASURY_FUNDING_AMOUNT,
            Decimal("89999999999.0000000"),
        )

    def test_recording_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(
                watcher.check_features()
            )

    def test_recording_enabled_explicitly(self):
        with patch.dict(
            os.environ,
            {"EN96_RECORD_DEPOSITS": "1"},
            clear=True,
        ):
            self.assertTrue(
                watcher.check_features()
            )

    def test_signing_must_remain_disabled(self):
        with patch.dict(
            os.environ,
            {"EN96_ENABLE_SIGNING": "1"},
            clear=True,
        ):
            with self.assertRaises(RuntimeError):
                watcher.check_features()

    def test_minting_must_remain_disabled(self):
        with patch.dict(
            os.environ,
            {"EN96_ENABLE_BNB_MINT": "1"},
            clear=True,
        ):
            with self.assertRaises(RuntimeError):
                watcher.check_features()

    def test_payouts_must_remain_disabled(self):
        with patch.dict(
            os.environ,
            {"EN96_ENABLE_STELLAR_PAYOUT": "1"},
            clear=True,
        ):
            with self.assertRaises(RuntimeError):
                watcher.check_features()


class TestEN96AmountValidation(unittest.TestCase):

    def test_one_en96(self):
        self.assertEqual(
            watcher.parse_amount("1.0000000"),
            Decimal("1.0000000"),
        )

    def test_smallest_unit(self):
        self.assertEqual(
            watcher.parse_amount("0.0000001"),
            Decimal("0.0000001"),
        )

    def test_zero_rejected(self):
        with self.assertRaises(RuntimeError):
            watcher.parse_amount("0")

    def test_negative_rejected(self):
        with self.assertRaises(RuntimeError):
            watcher.parse_amount("-1")

    def test_nan_rejected(self):
        with self.assertRaises(RuntimeError):
            watcher.parse_amount("NaN")

    def test_infinity_rejected(self):
        with self.assertRaises(RuntimeError):
            watcher.parse_amount("Infinity")

    def test_more_than_seven_decimals_rejected(self):
        with self.assertRaises(RuntimeError):
            watcher.parse_amount("0.00000001")


class TestEN96TreasuryProtection(unittest.TestCase):

    def test_known_treasury_funding_identified(self):
        operation = make_treasury_operation()

        self.assertTrue(
            watcher.is_treasury_funding(operation)
        )

    def test_treasury_not_user_deposit(self):
        operation = make_treasury_operation()

        self.assertFalse(
            watcher.is_en96_deposit(operation)
        )

    def test_treasury_cannot_be_verified_as_deposit(self):
        operation = make_treasury_operation()

        with self.assertRaisesRegex(
            RuntimeError,
            "Treasury funding is not",
        ):
            watcher.verify_deposit(operation)

    def test_treasury_amount_change_rejected(self):
        operation = make_treasury_operation()
        operation["amount"] = "89999999998.0000000"

        with self.assertRaisesRegex(
            RuntimeError,
            "unexpected fields",
        ):
            watcher.is_treasury_funding(operation)

    def test_treasury_destination_change_rejected(self):
        operation = make_treasury_operation()
        operation["to"] = watcher.TREASURY_ACCOUNT

        with self.assertRaisesRegex(
            RuntimeError,
            "unexpected fields",
        ):
            watcher.is_treasury_funding(operation)

    def test_treasury_operation_id_change_rejected(self):
        operation = make_treasury_operation()
        operation["id"] = "281328410951700482"

        with self.assertRaisesRegex(
            RuntimeError,
            "unexpected fields",
        ):
            watcher.is_treasury_funding(operation)

    def test_other_large_deposit_not_whitelisted(self):
        operation = make_operation(
            tx_hash="a" * 64,
            operation_id="281328410951700482",
            amount="89999999999.0000000",
        )

        self.assertFalse(
            watcher.is_treasury_funding(operation)
        )

        self.assertTrue(
            watcher.is_en96_deposit(operation)
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "Deposit exceeds bridge limit",
        ):
            watcher.verify_deposit(operation)

    def test_treasury_cannot_be_recorded(self):
        connection = FakeConnection()

        deposit = {
            "stellar_tx_hash": watcher.TREASURY_FUNDING_TX,
        }

        with self.assertRaisesRegex(
            RuntimeError,
            "Treasury funding cannot",
        ):
            watcher.record_deposit(
                connection,
                deposit,
            )

        self.assertEqual(
            len(connection.queries),
            0,
        )


class TestEN96UserDeposits(unittest.TestCase):

    def test_one_en96_is_user_deposit(self):
        operation = make_operation()

        self.assertTrue(
            watcher.is_en96_deposit(operation)
        )

    def test_one_en96_can_be_verified(self):
        operation = make_operation()

        transaction = {
            "hash": operation["transaction_hash"],
            "successful": True,
            "ledger": 65451930,
            "created_at": operation["created_at"],
        }

        with (
            patch.object(
                watcher,
                "get_transaction",
                return_value=(
                    transaction,
                    65451930,
                    watcher.parse_timestamp(
                        operation["created_at"]
                    ),
                ),
            ),
            patch.object(
                watcher,
                "get_transaction_operations",
                return_value=[operation],
            ),
        ):
            deposit = watcher.verify_deposit(
                operation
            )

        self.assertEqual(
            deposit["amount"],
            Decimal("1.0000000"),
        )

        self.assertEqual(
            deposit["operation_index"],
            0,
        )

        self.assertEqual(
            deposit["status"],
            "observed",
        )

    def test_exact_maximum_allowed(self):
        operation = make_operation(
            amount="1000000.0000000"
        )

        transaction = {
            "hash": operation["transaction_hash"],
            "successful": True,
            "ledger": 65451930,
            "created_at": operation["created_at"],
        }

        with (
            patch.object(
                watcher,
                "get_transaction",
                return_value=(
                    transaction,
                    65451930,
                    watcher.parse_timestamp(
                        operation["created_at"]
                    ),
                ),
            ),
            patch.object(
                watcher,
                "get_transaction_operations",
                return_value=[operation],
            ),
        ):
            deposit = watcher.verify_deposit(
                operation
            )

        self.assertEqual(
            deposit["amount"],
            Decimal("1000000.0000000"),
        )

    def test_over_maximum_rejected(self):
        operation = make_operation(
            amount="1000000.0000001"
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "Deposit exceeds bridge limit",
        ):
            watcher.verify_deposit(operation)

    def test_wrong_asset_not_deposit(self):
        operation = make_operation(
            asset_code="OTHER"
        )

        self.assertFalse(
            watcher.is_en96_deposit(operation)
        )

    def test_wrong_destination_not_deposit(self):
        operation = make_operation(
            destination=watcher.TREASURY_ACCOUNT
        )

        self.assertFalse(
            watcher.is_en96_deposit(operation)
        )

    def test_self_transfer_rejected(self):
        operation = make_operation(
            source=watcher.ESCROW_ACCOUNT
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "Self-transfer rejected",
        ):
            watcher.verify_deposit(operation)

    def test_issuer_origin_rejected(self):
        operation = make_operation(
            source=watcher.ASSET_ISSUER
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "Issuer-origin deposit rejected",
        ):
            watcher.verify_deposit(operation)


class TestEN96ReadOnlyScanning(unittest.TestCase):

    def test_treasury_only_no_checkpoint_write(self):
        connection = FakeConnection()

        operation = make_treasury_operation()

        with patch.object(
            watcher,
            "get_json",
            return_value={
                "_embedded": {
                    "records": [operation]
                }
            },
        ):
            scanned, recorded, completed = (
                watcher.scan_escrow(
                    connection,
                    recording_enabled=False,
                )
            )

        self.assertEqual(scanned, 1)
        self.assertEqual(recorded, 0)
        self.assertTrue(completed)

        self.assertEqual(
            connection.commits,
            1,
        )

        self.assertFalse(
            any(
                "insert into" in query.lower()
                for query, _ in connection.queries
            )
        )

    def test_one_deposit_requires_manual_review(self):
        connection = FakeConnection()

        operation = make_operation()

        with (
            patch.object(
                watcher,
                "get_json",
                return_value={
                    "_embedded": {
                        "records": [operation]
                    }
                },
            ),
            patch.object(
                watcher,
                "verify_deposit",
                return_value={
                    "amount": Decimal("1"),
                },
            ),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "Manual deposit review required",
            ):
                watcher.scan_escrow(
                    connection,
                    recording_enabled=False,
                )

        self.assertFalse(
            any(
                "insert into" in query.lower()
                for query, _ in connection.queries
            )
        )

    def test_non_deposit_page_does_not_write(self):
        connection = FakeConnection()

        operation = make_operation(
            operation_type="set_options",
            asset_type="native",
        )

        with patch.object(
            watcher,
            "get_json",
            return_value={
                "_embedded": {
                    "records": [operation]
                }
            },
        ):
            watcher.scan_escrow(
                connection,
                recording_enabled=False,
            )

        self.assertFalse(
            any(
                "insert into" in query.lower()
                or "update " in query.lower()
                or "delete " in query.lower()
                for query, _ in connection.queries
            )
        )

    def test_treasury_and_deposit_scanned_together(self):
        connection = FakeConnection()

        deposit = make_operation()
        treasury = make_treasury_operation()

        with (
            patch.object(
                watcher,
                "get_json",
                return_value={
                    "_embedded": {
                        "records": [
                            deposit,
                            treasury,
                        ]
                    }
                },
            ),
            patch.object(
                watcher,
                "verify_deposit",
                return_value={
                    "amount": Decimal("1"),
                },
            ),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "Manual deposit review required",
            ):
                watcher.scan_escrow(
                    connection,
                    recording_enabled=False,
                )

        self.assertFalse(
            any(
                "insert into" in query.lower()
                for query, _ in connection.queries
            )
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
