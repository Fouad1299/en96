
 // SPDX-License-Identifier: MIT
 pragma solidity ^0.8.20;

 import "@openzeppelin/contracts@5.0.2/token/ERC20/ERC20.sol";
 import "@openzeppelin/contracts@5.0.2/token/ERC20/extensions/ERC20Burnable.sol";
 import "@openzeppelin/contracts@5.0.2/token/ERC20/extensions/ERC20Capped.sol";
 import "@openzeppelin/contracts@5.0.2/access/Ownable.sol";
 import "@openzeppelin/contracts@5.0.2/access/Ownable2Step.sol";

 contract EN96V3Test is ERC20, ERC20Burnable, ERC20Capped, Ownable2Step {
     uint256 public constant MAX_SUPPLY = 90_000_000_000 * 10 ** 7;

     address public bridge;
     bool public bridgeConfigured;
     bool public mintPaused = true;

     event BridgeConfigured(address indexed bridgeAddress);
     event MintPaused(bool paused);

     constructor(address initialOwner)
         ERC20("EN96 Ice Bear Kingdom V3 Test", "EN96")
         ERC20Capped(MAX_SUPPLY)
         Ownable(initialOwner)
     {}

     function decimals() public pure override returns (uint8) {
         return 7;
     }

     function configureBridge(address bridgeAddress)
         external
         onlyOwner
     {
         require(!bridgeConfigured, "Bridge already configured");
         require(bridgeAddress != address(0), "Invalid bridge");
         require(bridgeAddress.code.length > 0, "Bridge must be contract");

         bridge = bridgeAddress;
         bridgeConfigured = true;

         emit BridgeConfigured(bridgeAddress);
     }

     function setMintPaused(bool paused) external onlyOwner {
         mintPaused = paused;
         emit MintPaused(paused);
     }

     function mintBacked(address to, uint256 amount) external {
         require(bridgeConfigured, "Bridge not configured");
         require(msg.sender == bridge, "Only bridge");
         require(!mintPaused, "Minting paused");
         require(to != address(0), "Invalid recipient");
         require(amount > 0, "Invalid amount");

         _mint(to, amount);
     }

     function _update(
         address from,
         address to,
         uint256 value
     ) internal override(ERC20, ERC20Capped) {
         super._update(from, to, value);
     }
 }
