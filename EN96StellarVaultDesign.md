# EN96 Ice Bear Kingdom — Stellar Vault Security Design

Status: DESIGN ONLY — NOT DEPLOYED
Version: 0.1

## 1. Project Rules
- Maximum combined EN96 supply across Stellar and BNB: 90,000,000,000 EN96.
- Stellar EN96 issuer: GCUGIICUGBFC3KBPIFYAMPNA7OVJHGY277TNYTZUSG7EVVUCVACH3OGB
- Existing Stellar reserve account: GCLZAUUMJHXSEGO5KQEIX5IMEVW3766CRG5TFR4PPUKTR5JUYXJDFM4O
- The project has one owner.
- No additional native Stellar EN96 may be issued after bridge activation.

## 2. Current Reserve Status
- Observed Stellar EN96 reserve: 90,000,000,000 EN96.
- Existing reserve uses multisignature authorization.
- The owner controls both required signing keys.
- Current custody is NOT independently locked.
- A read-only Horizon balance report is available.
- A balance report alone does NOT authorize BNB minting.

## 3. Proposed Stellar Vault
Implementation target: Stellar Soroban smart contract written in Rust.

The vault must:
- Hold the Stellar EN96 reserve under enforceable contract rules.
- Reject arbitrary withdrawals by the project owner.
- Track deposits, releases, and outstanding bridge liabilities.
- Prevent replay of bridge operations.
- Require verified BNB burn evidence before releasing Stellar EN96.
- Apply amount limits and emergency pause controls.
- Avoid administrator bypasses that could withdraw backing.
- Publish auditable events and read-only reserve data.

## 4. Bridge Safety Invariants
- No unbacked BNB EN96 may be minted.
- Every BNB mint must correspond to verified Stellar EN96 locked for that mint.
- Every Stellar release must correspond to a verified, final BNB burn.
- Every bridge event must be processed at most once.
- The unified supply ceiling is 90,000,000,000 EN96.
- Validator signatures alone are not proof of an irreversible Stellar lock.
- Off-chain verification introduces trust assumptions and must be documented.

## 5. Required Engineering Before Mainnet
1. Specify the Stellar asset interface and vault custody model.
2. Specify independent verification of Stellar deposits and BNB burns.
3. Define replay protection, finality rules, and failure recovery.
4. Implement the Soroban contract in Rust.
5. Write automated tests, including unauthorized withdrawal tests.
6. Test on Stellar Testnet and BNB Testnet.
7. Perform independent security review before mainnet use.
8. Verify the deployed contracts and publish their addresses.
9. Move no reserve funds until the vault is verified.

## 6. Explicitly Not Authorized
- No private keys or recovery phrases in GitHub.
- No mainnet transfers.
- No Stellar issuer lock.
- No BNB minting.
- No claim that the current reserve is permanently locked.

This document is a preliminary security design, not an audited contract or proof of custody lock.
