
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Capped.sol";
import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Burnable.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract EN96Test is ERC20, ERC20Capped, ERC20Burnable, Ownable {
    constructor()
        ERC20("EN96 Ice Bear Kingdom Test", "EN96T")
        ERC20Capped(90_000_000_000 * 10 ** 7)
        Ownable(msg.sender)
    {}

    function decimals() public pure override returns (uint8) {
        return 7;
    }

    function mintTest(address to, uint256 amount)
        external
        onlyOwner
    {
        _mint(to, amount);
    }

    function _update(address from, address to, uint256 value)
        internal
        override(ERC20, ERC20Capped)
    {
        super._update(from, to, value);
    }
}
