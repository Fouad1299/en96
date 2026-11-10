
 // SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts@5.0.2/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts@5.0.2/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts@5.0.2/access/Ownable.sol";
import "@openzeppelin/contracts@5.0.2/access/Ownable2Step.sol";
import "@openzeppelin/contracts@5.0.2/utils/Pausable.sol";
import "@openzeppelin/contracts@5.0.2/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts@5.0.2/utils/cryptography/EIP712.sol";
import "@openzeppelin/contracts@5.0.2/utils/cryptography/ECDSA.sol";

interface IEN96BridgeToken is IERC20 {
    function mintBacked(address to, uint256 amount) external;
    function burn(uint256 amount) external;
}

contract EN96Bridge is
    Ownable2Step,
    Pausable,
    ReentrancyGuard,
    EIP712
{
    using SafeERC20 for IERC20;

    uint256 public constant MAX_SUPPLY =
        90_000_000_000 * 10 ** 7;

    uint256 public constant MIN_REFUND_DELAY = 7 days;

    IEN96BridgeToken public immutable en96;

    address[3] public validatorList;
    mapping(address => bool) public validators;

    uint256 public validatorEpoch;
    uint256 public outstanding;
    uint256 public returnNonce;

    mapping(bytes32 => bool) public usedDeposits;
    mapping(bytes32 => bool) public usedStellarReleases;

    enum ReturnStatus {
        None,
        Pending,
        Completed,
        Refunded
    }

    struct ReturnRequest {
        address sender;
        string stellarDestination;
        uint256 amount;
        ReturnStatus status;
        uint256 requestedAt;
    }

    mapping(uint256 => ReturnRequest) public returnRequests;

    bytes32 public constant DEPOSIT_TYPEHASH = keccak256(
        "Deposit(bytes32 stellarTxHash,uint32 operationIndex,address recipient,uint256 amount,uint256 deadline,uint256 epoch)"
    );

    bytes32 public constant COMPLETE_TYPEHASH = keccak256(
        "ReturnCompleted(uint256 requestId,bytes32 stellarTxHash,uint32 operationIndex,uint256 deadline,uint256 epoch)"
    );

    event ValidatorsChanged(uint256 epoch);

    event MintedFromStellar(
        bytes32 indexed depositId,
        bytes32 indexed stellarTxHash,
        uint32 operationIndex,
        address indexed recipient,
        uint256 amount
    );

    event ReturnRequested(
        uint256 indexed requestId,
        address indexed sender,
        string stellarDestination,
        uint256 amount
    );

    event ReturnCompleted(
        uint256 indexed requestId,
        bytes32 indexed stellarTxHash,
        uint32 operationIndex,
        uint256 amount
    );

    constructor(
        address tokenAddress,
        address[3] memory initialValidators
    )
        Ownable(msg.sender)
        EIP712("EN96Bridge", "4")
    {
        require(
            tokenAddress.code.length > 0,
            "Invalid token contract"
        );

        en96 = IEN96BridgeToken(tokenAddress);
        _setValidators(initialValidators);

        // Bridging disabled by default.
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
                "Unknown validator"
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

    function _operationId(
        bytes32 stellarTxHash,
        uint32 operationIndex
    ) internal pure returns (bytes32) {
        return keccak256(
            abi.encode(stellarTxHash, operationIndex)
        );
    }

    function mintFromStellar(
        bytes32 stellarTxHash,
        uint32 operationIndex,
        address recipient,
        uint256 amount,
        uint256 deadline,
        bytes[] calldata signatures
    )
        external
        nonReentrant
        whenNotPaused
    {
        require(
            stellarTxHash != bytes32(0),
            "Invalid Stellar transaction"
        );

        require(recipient != address(0), "Invalid recipient");
        require(amount > 0, "Zero amount");
        require(block.timestamp <= deadline, "Expired");

        bytes32 depositId = _operationId(
            stellarTxHash,
            operationIndex
        );

        require(
            !usedDeposits[depositId],
            "Deposit already processed"
        );

        require(
            amount <= MAX_SUPPLY - outstanding,
            "Outstanding cap exceeded"
        );

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

        _verifySignatures(
            _hashTypedDataV4(structHash),
            signatures
        );

        usedDeposits[depositId] = true;
        outstanding += amount;

        en96.mintBacked(recipient, amount);

        emit MintedFromStellar(
            depositId,
            stellarTxHash,
            operationIndex,
            recipient,
            amount
        );
    }

    // Stellar public G-address character validation.
    function _base32Value(
        uint8 c
    ) internal pure returns (uint8) {
        if (c >= 65 && c <= 90) {
            return c - 65;
        }
        if (c >= 50 && c <= 55) {
            return c - 50 + 26;
        }
        revert("Invalid Stellar character");
    }

    function _stellarChecksum(
        bytes memory data
    ) internal pure returns (uint16) {
        uint16 crc = 0;

        for (uint256 i = 0; i < data.length; i++) {
            crc ^= uint16(uint8(data[i])) << 8;

            for (uint256 j = 0; j < 8; j++) {
                if ((crc & 0x8000) != 0) {
                    crc = (crc << 1) ^ 0x1021;
                } else {
                    crc = crc << 1;
                }
            }
        }

        return crc;
    }

    function _validStellarAddress(
        string memory account
    ) internal pure returns (bool) {
        bytes memory encoded = bytes(account);

        if (encoded.length != 56) {
            return false;
        }

        bytes memory decoded = new bytes(35);

        uint256 buffer = 0;
        uint256 bits = 0;
        uint256 outputIndex = 0;

        for (uint256 i = 0; i < 56; i++) {
            uint8 c = uint8(encoded[i]);

            if (
                !((c >= 65 && c <= 90) ||
                  (c >= 50 && c <= 55))
            ) {
                return false;
            }

            uint8 value = _base32Value(c);

            buffer = (buffer << 5) | uint256(value);
            bits += 5;

            if (bits >= 8) {
                bits -= 8;

                if (outputIndex >= 35) {
                    return false;
                }

                decoded[outputIndex] = bytes1(
                    uint8(buffer >> bits)
                );

                outputIndex++;
                buffer &= (uint256(1) << bits) - 1;
            }
        }

        if (
            outputIndex != 35 ||
            bits != 0 ||
            decoded[0] != bytes1(uint8(0x30))
        ) {
            return false;
        }

        bytes memory payload = new bytes(33);

        for (uint256 i = 0; i < 33; i++) {
            payload[i] = decoded[i];
        }

        uint16 checksum = _stellarChecksum(payload);

        uint16 storedChecksum =
            uint16(uint8(decoded[33])) |
            (uint16(uint8(decoded[34])) << 8);

        return checksum == storedChecksum;
    }

    function returnToStellar(
        string calldata stellarDestination,
        uint256 amount
    )
        external
        nonReentrant
        whenNotPaused
    {
        require(
            _validStellarAddress(stellarDestination),
            "Invalid Stellar address"
        );

        require(amount > 0, "Zero amount");
        require(
            amount <= outstanding,
            "Exceeds outstanding"
        );

        IERC20(address(en96)).safeTransferFrom(
            msg.sender,
            address(this),
            amount
        );

        uint256 requestId = ++returnNonce;

        returnRequests[requestId] = ReturnRequest({
            sender: msg.sender,
            stellarDestination: stellarDestination,
            amount: amount,
            status: ReturnStatus.Pending,
            requestedAt: block.timestamp
        });

        emit ReturnRequested(
            requestId,
            msg.sender,
            stellarDestination,
            amount
        );
    }

    function completeReturn(
        uint256 requestId,
        bytes32 stellarTxHash,
        uint32 operationIndex,
        uint256 deadline,
        bytes[] calldata signatures
    )
        external
        nonReentrant
    {
        ReturnRequest storage request =
            returnRequests[requestId];

        require(
            request.status == ReturnStatus.Pending,
            "Return is not pending"
        );

        require(
            stellarTxHash != bytes32(0),
            "Invalid Stellar transaction"
        );

        require(
            block.timestamp <= deadline,
            "Expired signature"
        );

        bytes32 releaseId = _operationId(
            stellarTxHash,
            operationIndex
        );

        require(
            !usedStellarReleases[releaseId],
            "Stellar release already used"
        );

        bytes32 structHash = keccak256(
            abi.encode(
                COMPLETE_TYPEHASH,
                requestId,
                stellarTxHash,
                operationIndex,
                deadline,
                validatorEpoch
            )
        );

        _verifySignatures(
            _hashTypedDataV4(structHash),
            signatures
        );

        usedStellarReleases[releaseId] = true;
        request.status = ReturnStatus.Completed;
        outstanding -= request.amount;

        en96.burn(request.amount);

        emit ReturnCompleted(
            requestId,
            stellarTxHash,
            operationIndex,
            request.amount
        );
    }

    // Disabled until secure Stellar payment reconciliation exists.
    function refundReturn(
        uint256,
        uint256,
        bytes[] calldata
    ) external pure {
        revert("Refund disabled pending secure reconciliation");
    }

    function pause() external onlyOwner {
        _pause();
    }

    function unpause() external onlyOwner {
        _unpause();
    }
}
