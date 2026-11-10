
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts@5.0.2/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts@5.0.2/token/ERC20/extensions/ERC20Burnable.sol";
import "@openzeppelin/contracts@5.0.2/token/ERC20/extensions/ERC20Capped.sol";
import "@openzeppelin/contracts@5.0.2/access/Ownable.sol";
import "@openzeppelin/contracts@5.0.2/access/Ownable2Step.sol";

contract EN96 is
    ERC20,
    ERC20Burnable,
    ERC20Capped,
    Ownable2Step
{
    uint256 public constant MAX_SUPPLY =
        90_000_000_000 * 10 ** 7;

    address public bridge;

    bool public bridgeConfigured;
    bool public mintPaused = true;

    event BridgeConfigured(address indexed bridge);
    event MintPaused(bool paused);

    constructor(address initialOwner)
        ERC20("EN96 Ice Bear Kingdom", "EN96")
        ERC20Capped(MAX_SUPPLY)
        Ownable(initialOwner)
    {}

    function decimals()
        public
        pure
        override
        returns (uint8)
    {
        return 7;
    }

    function setBridge(address newBridge)
        external
        onlyOwner
    {
        require(
            !bridgeConfigured,
            "Bridge already configured"
        );

        require(
            newBridge != address(0),
            "Invalid bridge"
        );

        require(
            newBridge.code.length > 0,
            "Bridge must be contract"
        );

        bridge = newBridge;
        bridgeConfigured = true;

        emit BridgeConfigured(newBridge);
    }

    function setMintPaused(bool paused)
        external
        onlyOwner
    {
        require(
            bridgeConfigured,
            "Bridge not configured"
        );

        mintPaused = paused;

        emit MintPaused(paused);
    }

    function mintBacked(
        address to,
        uint256 amount
    ) external {
        require(
            msg.sender == bridge,
            "Only bridge can mint"
        );

        require(
            !mintPaused,
            "Minting paused"
        );

        require(
            to != address(0),
            "Invalid recipient"
        );

        require(
            amount > 0,
            "Invalid amount"
        );

        _mint(to, amount);
    }

    function _update(
        address from,
        address to,
        uint256 value
    )
        internal
        override(ERC20, ERC20Capped)
    {
        super._update(from, to, value);
    }
}
