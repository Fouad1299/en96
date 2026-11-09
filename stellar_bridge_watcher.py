
# EN96 Ice Bear Kingdom
# Stellar Mainnet - Read Only Verification
# No private keys, no transfers, no minting

import json
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from decimal import Decimal

HORIZON = "https://horizon.stellar.org"

ISSUER = (
    "GCUGIICUGBFC3KBPIFYAMPNA7OVJHGY277TNYTZUSG7EVVUCVACH3OGB"
)

ESCROW = (
    "GCLZAUUMJHXSEGO5KQEIX5IMEVW3766CRG5TFR4PPUKTR5JUYXJDFM4O"
)

ASSET_CODE = "EN96"
MAX_SUPPLY = Decimal("90000000000")


def get_json(path, params=None):
    url = HORIZON + path
    if params:
        url += "?" + urlencode(params)

    request = Request(
        url,
        headers={"Accept": "application/json"}
    )

    with urlopen(request, timeout=20) as response:
        return json.load(response)


def check_asset():
    data = get_json(
        "/assets",
        {
            "asset_code": ASSET_CODE,
            "asset_issuer": ISSUER,
            "limit": 1
        }
    )

    records = data.get("_embedded", {}).get(
        "records", []
    )

    if not records:
        print("EN96 asset not found for this issuer")
        return False

    asset = records[0]
    amount = Decimal(asset["amount"])

    print("EN96 asset found")
    print("Issuer:", ISSUER)
    print("Stellar supply:", amount)
    print("Maximum planned supply:", MAX_SUPPLY)

    if amount > MAX_SUPPLY:
        print("WARNING: Stellar supply exceeds cap")
        return False

    return True


def check_escrow():
    account = get_json("/accounts/" + ESCROW)

    print("Escrow account exists:", ESCROW)

    for balance in account.get("balances", []):
        if (
            balance.get("asset_code") == ASSET_CODE
            and balance.get("asset_issuer") == ISSUER
        ):
            print(
                "Escrow EN96 balance:",
                balance["balance"]
            )
            return True

    print("Escrow has no matching EN96 trustline")
    return False


def main():
    print("EN96 Stellar verification started")
    print("READ ONLY - NO TRANSFERS")

    asset_ok = check_asset()
    escrow_ok = check_escrow()

    if asset_ok and escrow_ok:
        print("Basic asset and escrow checks passed")
    else:
        print("Verification incomplete")

    print("No minting or bridge actions performed")


if __name__ == "__main__":
    main()
