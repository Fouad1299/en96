
# EN96 Ice Bear Kingdom
# Stellar Mainnet Asset Verification
# Version 0.3 - Read Only
# No private keys, no transfers, no minting

import json
import sys
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

HORIZON = "https://horizon.stellar.org"

ASSET_CODE = "EN96"

ISSUER = (
    "GCUGIICUGBFC3KBPIFYAMPNA7OVJHGY277TNYTZUSG7EVVUCVACH3OGB"
)

ESCROW = (
    "GCLZAUUMJHXSEGO5KQEIX5IMEVW3766CRG5TFR4PPUKTR5JUYXJDFM4O"
)

MAX_SUPPLY = Decimal("90000000000")


def get_json(path, params=None):
    url = HORIZON + path

    if params:
        url += "?" + urlencode(params)

    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "EN96-Stellar-Checker/0.3"
        }
    )

    try:
        with urlopen(request, timeout=25) as response:
            return json.load(response)

    except HTTPError as error:
        raise RuntimeError(
            f"Stellar HTTP error: {error.code}"
        ) from error

    except URLError as error:
        raise RuntimeError(
            f"Stellar connection error: {error.reason}"
        ) from error


def parse_amount(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Invalid Stellar amount")

    if not amount.is_finite() or amount < 0:
        raise ValueError("Invalid Stellar amount")

    return amount


def check_asset():
    print("\nChecking EN96 asset on Stellar Mainnet...")

    data = get_json(
        "/assets",
        {
            "asset_code": ASSET_CODE,
            "asset_issuer": ISSUER,
            "limit": 1
        }
    )

    records = data.get("_embedded", {}).get("records", [])

    if not records:
        print("FAIL: EN96 asset not found for issuer")
        return False

    asset = records[0]

    if (
        asset.get("asset_code") != ASSET_CODE
        or asset.get("asset_issuer") != ISSUER
    ):
        print("FAIL: Asset identity mismatch")
        return False

    balances = asset.get("balances")

    if not isinstance(balances, dict):
        print("FAIL: Missing Stellar balances data")
        return False

    total_supply = sum(
        (
            parse_amount(value)
            for value in balances.values()
        ),
        Decimal("0")
    )

    print("PASS: EN96 asset found")
    print("Issuer:", ISSUER)
    print("Stellar reported balances:", balances)
    print("Stellar reported total:", total_supply)
    print("Planned maximum:", MAX_SUPPLY)

    if total_supply > MAX_SUPPLY:
        print("FAIL: Stellar amount exceeds planned cap")
        return False

    print("PASS: Stellar amount within planned cap")
    return True


def check_escrow():
    print("\nChecking EN96 escrow account...")

    try:
        account = get_json("/accounts/" + ESCROW)
    except RuntimeError as error:
        print("FAIL:", error)
        return False

    print("PASS: Escrow account exists")
    print("Escrow:", ESCROW)

    for balance in account.get("balances", []):
        if (
            balance.get("asset_code") == ASSET_CODE
            and balance.get("asset_issuer") == ISSUER
        ):
            amount = parse_amount(
                balance.get("balance", "0")
            )

            print("PASS: EN96 trustline found")
            print("Escrow EN96 balance:", amount)
            return True

    print("FAIL: Matching EN96 trustline not found")
    return False


def main():
    print("=" * 55)
    print("EN96 ICE BEAR KINGDOM")
    print("STELLAR MAINNET VERIFICATION")
    print("READ ONLY - NO TRANSFERS")
    print("=" * 55)

    asset_ok = check_asset()
    escrow_ok = check_escrow()

    print("\n" + "=" * 55)

    if asset_ok and escrow_ok:
        print("RESULT: BASIC VERIFICATION PASSED")
        print("Asset identity and escrow trustline checked")
        print("Bridge is NOT authorized to mint")
        return 0

    print("RESULT: VERIFICATION INCOMPLETE")
    print("No bridge transactions performed")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, ValueError, KeyError) as error:
        print("VERIFICATION ERROR:", error)
        sys.exit(1)
