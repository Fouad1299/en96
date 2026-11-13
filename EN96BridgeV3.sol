
 // SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts@5.0.2/access/Ownable.sol";
import "@openzeppelin/contracts@5.0.2/access/Ownable2Step.sol";
import "@openzeppelin/contracts@5.0.2/utils/Pausable.sol";
import "@openzeppelin/contracts@5.0.2/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts@5.0.2/utils/cryptography/EIP712.sol";
import "@openzeppelin/contracts@5.0.2/utils/cryptography/ECDSA.sol";

interface IEN96V3Token {
    function mintBacked(address to, uint256 amount) external;
    function burnFrom(address account, uint256 amount) external;
    function bridge() external view returns (address);
    function bridgeConfigured() external view returns (bool);
    function mintPaused() external view returns (bool);
    function totalSupply() external view returns (uint256);
}

contract EN96BridgeV3 is
    Ownable2Step,
    Pausable,
    ReentrancyGuard,
    EIP712
{
    uint256 public constant MAX_SUPPLY =
        90_000_000_000 * 10 ** 7;

    uint256 public constant MAX_DEPOSIT =
        1_000_000 * 10 ** 7;

    uint256 public constant MAX_RETURN =
        1_000_000 * 10 ** 7;

    bytes32 public constant DEPOSIT_TYPEHASH = keccak256(
        "Deposit(bytes32 stellarTxHash,uint32 operationIndex,address recipient,uint256 amount,uint256 deadline,uint256 epoch)"
    );

    IEN96V3Token public immutable token;

    address[3] public validatorList;
    mapping(address => bool) public validators;
    mapping(bytes32 => bool) public usedDeposits;

    uint256 public validatorEpoch;
    uint256 public outstanding;
    uint256 public returnNonce;

    struct ReturnRequest {
        address sender;
        uint256 amount;
        string stellarAddress;
        uint256 timestamp;
    }

    mapping(uint256 => ReturnRequest) private returnRequests;

    event ValidatorsChanged(uint256 indexed epoch);

    event DepositMinted(
        bytes32 indexed depositId,
        bytes32 indexed stellarTxHash,
        uint32 operationIndex,
        address indexed recipient,
        uint256 amount
    );

    event ReturnRequested(
        uint256 indexed requestId,
        address indexed sender,
        string stellarAddress,
        uint256 amount
    );

    constructor(
        address tokenAddress,
        address[3] memory initialValidators
    )
        Ownable(msg.sender)
        EIP712("EN96BridgeV3", "1")
    {
        require(tokenAddress != address(0), "Invalid token");
        require(tokenAddress.code.length > 0, "Not a contract");

        token = IEN96V3Token(tokenAddress);

        _setValidators(initialValidators);
        _pause();
    }

    function _setValidators(
        address[3] memory newValidators
    ) internal {
        for (uint256 i = 0; i < 3; i++) {
            require(
                newValidators[i] != address(0),
                "Zero validator"
            );

            for (uint256 j = 0; j < i; j++) {
                require(
                    newValidators[i] != newValidators[j],
                    "Duplicate validator"
                );
            }
        }

        for (uint256 i = 0; i < 3; i++) {
            validators[validatorList[i]] = false;
        }

        for (uint256 i = 0; i < 3; i++) {
            validatorList[i] = newValidators[i];
            validators[newValidators[i]] = true;
        }

        validatorEpoch++;
        emit ValidatorsChanged(validatorEpoch);
    }

    function setValidators(
        address[3] calldata newValidators
    ) external onlyOwner whenPaused {
        _setValidators(newValidators);
    }

    function depositIdOf(
        bytes32 stellarTxHash,
        uint32 operationIndex
    ) public pure returns (bytes32) {
        return keccak256(
            abi.encode(stellarTxHash, operationIndex)
        );
    }

    function depositDigest(
        bytes32 stellarTxHash,
        uint32 operationIndex,
        address recipient,
        uint256 amount,
        uint256 deadline
    ) public view returns (bytes32) {
        bytes32 structHash = keccak256(
            abi.encode(
                DEPOSIT_TYPEHASH,
                stellarTxHash,
                operationIndex,
                recipient,
                amount,
                deadline,
                validatorEpoch
            )
        );

        return _hashTypedDataV4(structHash);
    }

    function _verifySignatures(
        bytes32 digest,
        bytes[] calldata signatures
    ) internal view {
        require(
            signatures.length >= 2 &&
            signatures.length <= 3,
            "Need 2 or 3 signatures"
        );

        address[3] memory seen;

        for (uint256 i = 0; i < signatures.length; i++) {
            address signer = ECDSA.recover(
                digest,
                signatures[i]
            );

            require(
                validators[signer],
                "Unauthorized validator"
            );

            for (uint256 j = 0; j < i; j++) {
                require(
                    seen[j] != signer,
                    "Duplicate signature"
                );
            }

            seen[i] = signer;
        }
    }

    function mintFromStellar(
        bytes32 stellarTxHash,
        uint32 operationIndex,
        address recipient,
        uint256 amount,
        uint256 deadline,
        bytes[] calldata signatures
    ) external whenNotPaused nonReentrant {
        require(token.bridgeConfigured(), "Bridge not configured");
        require(token.bridge() == address(this), "Wrong bridge");
        require(!token.mintPaused(), "Minting paused");

        require(stellarTxHash != bytes32(0), "Invalid hash");
        require(recipient != address(0), "Invalid recipient");
        require(amount > 0, "Invalid amount");
        require(amount <= MAX_DEPOSIT, "Deposit limit exceeded");
        require(block.timestamp <= deadline, "Expired");

        bytes32 depositId = depositIdOf(
            stellarTxHash,
            operationIndex
        );

        require(!usedDeposits[depositId], "Deposit already used");
        require(outstanding <= MAX_SUPPLY, "Invalid outstanding");
        require(
            amount <= MAX_SUPPLY - outstanding,
            "Outstanding cap exceeded"
        );

        uint256 supply = token.totalSupply();
        require(supply <= MAX_SUPPLY, "Invalid token supply");
        require(
            amount <= MAX_SUPPLY - supply,
            "Token cap exceeded"
        );

        bytes32 digest = depositDigest(
            stellarTxHash,
            operationIndex,
            recipient,
            amount,
            deadline
        );

        _verifySignatures(digest, signatures);

        usedDeposits[depositId] = true;
        outstanding += amount;

        token.mintBacked(recipient, amount);

        emit DepositMinted(
            depositId,
            stellarTxHash,
            operationIndex,
            recipient,
            amount
        );
    }

    function _validStellarAddress(
        string memory account
    ) internal pure returns (bool) {
        bytes memory a = bytes(account);

        if (a.length != 56 || a[0] != bytes1("G")) {
            return false;
        }

        for (uint256 i = 1; i < a.length; i++) {
            bytes1 c = a[i];

            bool letter = c >= bytes1("A") && c <= bytes1("Z");
            bool digit = c >= bytes1("2") && c <= bytes1("7");

            if (!letter && !digit) {
                return false;
            }
        }

        return true;
    }

    function returnToStellar(
        uint256 amount,
        string calldata stellarAddress
    ) external whenNotPaused nonReentrant returns (uint256) {
        require(token.bridgeConfigured(), "Bridge not configured");
        require(token.bridge() == address(this), "Wrong bridge");
        require(amount > 0, "Invalid amount");
        require(amount <= MAX_RETURN, "Return limit exceeded");
        require(
            _validStellarAddress(stellarAddress),
            "Invalid Stellar address format"
        );
        require(amount <= outstanding, "Exceeds outstanding");

        token.burnFrom(msg.sender, amount);

        outstanding -= amount;
        returnNonce++;

        uint256 requestId = returnNonce;

        returnRequests[requestId] = ReturnRequest({
            sender: msg.sender,
            amount: amount,
            stellarAddress: stellarAddress,
            timestamp: block.timestamp
        });

        emit ReturnRequested(
            requestId,
            msg.sender,
            stellarAddress,
            amount
        );

        return requestId;
    }

    function getReturnRequest(
        uint256 requestId
    )
        external
        view
        returns (
            address sender,
            uint256 amount,
            string memory stellarAddress,
            uint256 timestamp
        )
    {
        require(
            requestId > 0 && requestId <= returnNonce,
            "Unknown request"
        );

        ReturnRequest storage r = returnRequests[requestId];

        return (
            r.sender,
            r.amount,
            r.stellarAddress,
            r.timestamp
        );
    }

    function pause() external onlyOwner {
        _pause();
    }

    function unpause() external onlyOwner {
        require(token.bridgeConfigured(), "Bridge not configured");
        require(token.bridge() == address(this), "Wrong bridge");
        require(!token.mintPaused(), "Minting paused");

        _unpause();
    }
}
