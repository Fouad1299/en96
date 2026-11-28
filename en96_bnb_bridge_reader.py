
"""
EN96 Ice Bear Kingdom
BNB Bridge Reader - READ ONLY
BNB Smart Chain Mainnet
Classic Stellar Reserve - NO SOROBAN
"""

import json
import os
from urllib.request import Request, urlopen
from eth_utils import keccak

CHAIN_ID = 56

BRIDGE_ADDRESS = (
    "0x376edf142106274fe7db370475aa761f1ec0bc21"
)

RPC_URL = os.getenv(
    "EN96_BNB_RPC_URL",
    "https://bsc-dataseed.bnbchain.org"
)

DECIMALS = 7
MAX_SUPPLY_UNITS = 90_000_000_000 * 10**7

EXPECTED_VALIDATORS = {
    "0xb80e51b464c8d2df43b353e0dc094c023d5e3c82",
    "0xcb48f41a5e3a93f704584e46cbfcadb7776d7332",
    "0xfc8bc13106c3c827427d40f64fc1926a35739d66",
}


class BridgeReaderError(Exception):
    pass


def rpc(method, params):

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    }

    request = Request(
        RPC_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json"
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=20) as response:
            result = json.load(response)

    except Exception as exc:
        raise BridgeReaderError(
            "BNB RPC connection failed"
        ) from exc

    if "error" in result:
        raise BridgeReaderError(
            str(result["error"])
        )

    if "result" not in result:
        raise BridgeReaderError(
            "Invalid RPC response"
        )

    return result["result"]


def verify_network():

    chain_id = int(
        rpc("eth_chainId", []),
        16,
    )

    if chain_id != CHAIN_ID:
        raise BridgeReaderError(
            "Wrong BNB network"
        )

    return chain_id


def read_contract(
    signature,
    arguments="",
    block="latest",
):

    selector = keccak(
        text=signature
    )[:4].hex()

    result = rpc(
        "eth_call",
        [
            {
                "to": BRIDGE_ADDRESS,
                "data": (
                    "0x"
                    + selector
                    + arguments
                ),
            },
            block,
        ],
    )

    if not isinstance(result, str):
        raise BridgeReaderError(
            "Invalid contract response"
        )

    if not result.startswith("0x"):
        raise BridgeReaderError(
            "Invalid contract encoding"
        )

    if len(result) != 66:
        raise BridgeReaderError(
            "Unexpected contract result length"
        )

    return int(result, 16)


def read_bool(signature, arguments="", block="latest"):

    value = read_contract(
        signature,
        arguments,
        block,
    )

    if value not in (0, 1):
        raise BridgeReaderError(
            "Invalid boolean result"
        )

    return bool(value)


def read_validator(index, block="latest"):

    if type(index) is not int or not 0 <= index <= 2:
        raise BridgeReaderError(
            "Invalid validator index"
        )

    arguments = format(index, "064x")

    value = read_contract(
        "validatorList(uint256)",
        arguments,
        block,
    )

    if not 0 < value < 2**160:
        raise BridgeReaderError(
            "Invalid validator address"
        )

    return "0x" + format(value, "040x")


def read_bridge_status():

    chain_id = verify_network()

    block = rpc(
        "eth_blockNumber",
        [],
    )

    code = rpc(
        "eth_getCode",
        [BRIDGE_ADDRESS, block],
    )

    if not code or code == "0x":
        raise BridgeReaderError(
            "Bridge contract not found"
        )

    paused = read_bool(
        "paused()",
        block=block,
    )

    epoch = read_contract(
        "validatorEpoch()",
        block=block,
    )

    outstanding = read_contract(
        "outstanding()",
        block=block,
    )

    return_nonce = read_contract(
        "returnNonce()",
        block=block,
    )

    validators = [
        read_validator(index, block)
        for index in range(3)
    ]

    validator_checks = []

    for address in validators:

        arguments = address[2:].rjust(
            64, "0"
        )

        active = read_bool(
            "validators(address)",
            arguments,
            block,
        )

        validator_checks.append({
            "address": address,
            "active": active,
        })

    validators_match = (
        len(set(validators)) == 3
        and set(validators) == EXPECTED_VALIDATORS
        and all(
            item["active"]
            for item in validator_checks
        )
    )

    issues = []

    if epoch < 1:
        issues.append(
            "Validator epoch not configured"
        )

    if not validators_match:
        issues.append(
            "Validator configuration mismatch"
        )

    if outstanding > MAX_SUPPLY_UNITS:
        issues.append(
            "Outstanding supply exceeds limit"
        )

    whole, fraction = divmod(
        outstanding,
        10**DECIMALS,
    )

    return {
        "project": "EN96 Ice Bear Kingdom",
        "network": "BNB Smart Chain Mainnet",
        "chain_id": chain_id,
        "block_number": int(block, 16),
        "bridge_address": BRIDGE_ADDRESS,
        "contract_exists": True,
        "bridge_paused": paused,
        "validator_epoch": epoch,
        "validators": validator_checks,
        "validators_match": validators_match,
        "outstanding_units": outstanding,
        "outstanding_en96": (
            f"{whole}.{fraction:07d}"
        ),
        "return_nonce": return_nonce,
        "issues": issues,
        "status": "OK" if not issues else "ERROR",
        "mode": "READ ONLY",
        "soroban_enabled": False,
        "signing_enabled": False,
        "minting_enabled": False,
        "mint_authorized": False,
    }


if __name__ == "__main__":

    try:
        print(
            json.dumps(
                read_bridge_status(),
                indent=2,
            )
        )

    except Exception as exc:

        print(
            json.dumps(
                {
                    "status": "ERROR",
                    "error": str(exc),
                    "mint_authorized": False,
                },
                indent=2,
            )
        )

        raise SystemExit(1)
