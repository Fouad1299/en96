
#!/usr/bin/env python3
# EN96 Ice Bear Kingdom
# Stellar Mainnet Reserve Evidence Provider
# Read-only: no signing, no transfers, no minting.

import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

HORIZON = "https://horizon.stellar.org"

ASSET_CODE = "EN96"

ISSUER = (
    "GCUGIICUGBFC3KBPIFYAMPNA7OVJHGY277TNYTZUSG7EVVUCVACH3OGB"
)

RESERVE_ACCOUNT = (
    "GCLZAUUMJHXSEGO5KQEIX5IMEVW3766CRG5TFR4PPUKTR5JUYXJDFM4O"
)

DECIMALS = 7
MAX_SUPPLY = Decimal("90000000000")
TIMEOUT_SECONDS = 20


def fetch_json(path):
    url = HORIZON + path
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "EN96-Reserve-Evidence/1.0",
        },
        method="GET",
    )

    with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        if response.status != 200:
            raise RuntimeError("Horizon returned an unexpected status")

        return json.load(response)


def find_en96_balance(account):
    matches = []

    for balance in account.get("balances", []):
        if (
            balance.get("asset_type") != "native"
            and balance.get("asset_code") == ASSET_CODE
            and balance.get("asset_issuer") == ISSUER
        ):
            matches.append(balance)

    if len(matches) != 1:
        raise RuntimeError(
            "Expected exactly one EN96 trustline for the issuer"
        )

    return matches[0]


def inspect_signers(account):
    signers = []

    for signer in account.get("signers", []):
        signers.append({
            "key": signer.get("key"),
            "type": signer.get("type"),
            "weight": int(signer.get("weight", 0)),
        })

    thresholds = account.get("thresholds", {})

    high = int(thresholds.get("high_threshold", 0))
    medium = int(thresholds.get("med_threshold", 0))
    low = int(thresholds.get("low_threshold", 0))

    positive_weights = sorted(
        [
            signer["weight"]
            for signer in signers
            if signer["weight"] > 0
        ],
        reverse=True,
    )

    return {
        "signers": signers,
        "thresholds": {
            "low": low,
            "medium": medium,
            "high": high,
        },
        "positive_signer_count": len(positive_weights),
        "top_two_weight": sum(positive_weights[:2]),
        "top_two_can_authorize_high": (
            len(positive_weights) >= 2
            and high > 0
            and sum(positive_weights[:2]) >= high
        ),
    }


def build_report():
    account = fetch_json(
        "/accounts/" + quote(RESERVE_ACCOUNT, safe="")
    )

    if account.get("account_id") != RESERVE_ACCOUNT:
        raise RuntimeError("Reserve account mismatch")

    asset = find_en96_balance(account)

    try:
        balance = Decimal(asset["balance"])
        buying_liabilities = Decimal(
            asset.get("buying_liabilities", "0")
        )
        selling_liabilities = Decimal(
            asset.get("selling_liabilities", "0")
        )
    except (InvalidOperation, KeyError, TypeError) as exc:
        raise RuntimeError("Invalid asset balance data") from exc

    if balance < 0:
        raise RuntimeError("Negative reserve balance")

    signer_report = inspect_signers(account)

    balance_matches_target = balance == MAX_SUPPLY

    # This is evidence of balance only.
    # Stellar account signers may still authorize transfers.
    custody_lock_proven = False

    # A live proof of backing requires independently
    # enforced custody and cross-chain supply accounting.
    mint_authorized = False

    return {
        "schema_version": "1.0",
        "project": "EN96 Ice Bear Kingdom",
        "network": "Stellar Mainnet",
        "checked_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "horizon": HORIZON,
        "reserve_account": RESERVE_ACCOUNT,
        "asset_code": ASSET_CODE,
        "asset_issuer": ISSUER,
        "decimals": DECIMALS,
        "target_supply_en96": str(MAX_SUPPLY),
        "reserve_balance_en96": str(balance),
        "balance_matches_target": balance_matches_target,
        "buying_liabilities_en96": str(buying_liabilities),
        "selling_liabilities_en96": str(selling_liabilities),
        "account_sequence": account.get("sequence"),
        "last_modified_ledger": account.get(
            "last_modified_ledger"
        ),
        "account_flags": account.get("flags", {}),
        "signer_analysis": signer_report,
        "custody_lock_proven": custody_lock_proven,
        "bnb_outstanding_verified": False,
        "mint_authorized": mint_authorized,
        "evidence_type": "READ_ONLY_BALANCE_SNAPSHOT",
        "status": (
            "BALANCE_OBSERVED_NOT_LOCK_PROVEN"
            if balance_matches_target
            else "BALANCE_DIFFERS_FROM_TARGET"
        ),
        "notes": [
            "Horizon balance is not a custody lock.",
            "This report does not prove BNB circulating supply.",
            "No validator signature is produced.",
            "No EVM transaction is submitted.",
            "This report must not be used alone to authorize minting.",
        ],
    }


def main():
    try:
        report = build_report()
        print(
            json.dumps(
                report,
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    except (HTTPError, URLError, TimeoutError) as exc:
        print(
            json.dumps({
                "status": "NETWORK_ERROR",
                "error": str(exc),
                "mint_authorized": False,
            }),
            file=sys.stderr,
        )
        return 1

    except Exception as exc:
        print(
            json.dumps({
                "status": "VERIFICATION_ERROR",
                "error": str(exc),
                "mint_authorized": False,
            }),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
