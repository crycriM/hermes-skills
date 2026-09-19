# Strategy Contract ABI Surface (verified 2026-08-24)

Source: Blockscout verified-contract API (mainnet), no key needed:
`https://eth.blockscout.com/api?module=contract&action=getabi&address=0x5d5aa402fa16ff97b36193d3b66ce83c0484dc71`
Response `result` field is a JSON ABI string. Saved in project at
`~/projects/numerai-folders/numerai-crypto-bot/contracts/strategy_abi.json` (50 entries).
Sourcify 404s for these contracts; Etherscan requires an API key.

## Contract addresses
- Strategy (AllocationStrategy): `0x5d5aa402fa16ff97b36193d3b66ce83c0484dc71`
- v3 staking contract (from `v3StakeConfig(tournamentId:12)` AND `strategy.staking()`): `0xC1f46Adf341145369eeE9fBe0D84fA1cb0c24706`
- NMR token: `0x1776e1F26f98b1A5dF9cD347953a26dd3Cb46671`
- Strategy factory: `0x80c87c69fcfd53c937c3892f09550ff9a78924fc`
- Strategy owner(): `0xc728fd8e8c488828d959bb6b9d366df50b60f7a4` (= wallet in wallet_transactions)
- Strategy operator(): `0xb2c72a665c08c4a619d888ea3d5cfeb6601a9dc2` (Numerai's service account — runs the payout→strategy auto-sweep)
- v3 staking contract owner()/serviceWallet: `0x1105aFAF3002a48A305AFD631e3cb57277ceB0EA`

## Functions (20)
Reads (view):
- `modelConfig(uint256 tournamentId, bytes32 modelId) -> (uint128 perRoundStake, uint8 mode, bool enabled)` — per-model rules; unset = (0,0,False), no revert
- `availableBalance() -> (uint256)` — idle NMR in strategy
- `owner()`, `operator()`, `staking()`, `factory()`, `nmr()`, `pendingOwner()`

Mutations (APPLY path — never call in recon):
- `setModelConfig(uint256, bytes32, uint128, uint8, bool)` — set per-model per_round/mode/enabled
- `setModelConfigs(tuple[])` — batch version
- `deposit(uint256)`, `withdraw(uint256)` — move NMR idle ↔ wallet
- `claimToOwner(tuple[])` — collect claims to owner
- `updateSubmissionHashFor(uint256,uint256,bytes32,bytes32,uint256,uint256,bytes)` — per-round stake execution
- `invokeFor(uint256,bytes32,tuple[],tuple,uint256)` — generic exec
- `approveStaking()`, `acceptOwnership()`, `transferOwnership(address)`, `setOperator(address)`, `initialize(...)`

## Events
- `ModelConfigUpdated(uint256 indexed tournamentId, bytes32 indexed modelId, uint128 perRoundStake, uint8 mode, bool enabled)` — topic0 `0x481bad5c91011256e508ab43ccad86a505b44506b18d7f9dddd7a863bf711767`. **Count across full chain history for this strategy: 0** → proves setModelConfig was never called.
- Also: ClaimsCollected, Deposited, Initialized, Invoked, ModelConfigUpdated, OperatorUpdated, OwnershipTransferStarted, OwnershipTransferred, Withdrawn

## Live state snapshot (2026-08-24)
- `modelConfig(12, <model>)` = (0, 0, False) for m5_draft / m5_rc / m5_beta under all key encodings tried (ascii-dashless-uuid, hex-decoded left/right, keccak-of-name)
- `availableBalance()` = 44.72 NMR idle; wallet 0xc728fd8e... held 65.27 NMR (fresh deposit 08-24 14:15 UTC)
- Web-app stakes (`v3UserProfile.stakeValues`): m5_draft 20 → 15 → 0 (08-18), m5_rc 20 → 15 → 0 (08-18), m5_beta 4 → 0 (08-20) — all zero since the Aug 18–20 v3 migration
- Payout→strategy auto-sweep observed 08-14/18/20 (deposit wallet→sweep into strategy within ~25 s, exact amounts)
- Round 1339 (current): pool totalStaked 2,281.7 NMR; stake window closed; resolve pending
- Model ids: m5_draft 321d2449-61ff-40f7-97e6-67963e9240df, m5_rc 16d20604-33dd-40ef-b6c9-597f64d9d3ed, m5_beta 1b158a9a-9d76-4cf8-a45c-907bdcc6bef3

## Open item
Model key bytes32 encoding unresolved until the first real `setModelConfig`: read it back from the indexed `modelId` topic of the next `ModelConfigUpdated` log.