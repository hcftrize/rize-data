import { BigDecimal, BigInt, Address } from "@graphprotocol/graph-ts";
import { ethereum } from "@graphprotocol/graph-ts";

// GovernanceBonding events
import {
  BondCreated,
  BondBroken,
  TokensReleased,
  BondMigrated,
  VestingUpdated,
  VestedTokenClawed,
  PoolUpdated,
  ReleaseWarmupUpdated,
  MigratorAdded,
  MigratorRemoved,
} from "../generated/GovernanceBonding/GovernanceBonding";
import { GovernanceBonding } from "../generated/GovernanceBonding/GovernanceBonding";

// BondNFT events
import { Transfer } from "../generated/BondNFT/BondNFT";

// Schema entities
import {
  Bond,
  BondCreatedEvent,
  IncreaseBondEvent,
  BondTimeMarkerSnapshot,
  BondBrokenEvent,
  TokensReleasedEvent,
  BondMigratedEvent,
  VestingUpdatedEvent,
  VestedTokenClawedEvent,
  Pool,
  PoolUpdatedEvent,
  ReleaseWarmupUpdatedEvent,
  MigratorAddedEvent,
  MigratorRemovedEvent,
  NftTransferEvent,
  BondOwner,
} from "../generated/schema";

let DECIMALS = BigDecimal.fromString("1000000000000000000");
let ZERO_ADDRESS = "0x0000000000000000000000000000000000000000";

// ── Date helper ───────────────────────────────────────────────────────────────

function isLeapYear(year: i32): bool {
  return (year % 4 == 0 && year % 100 != 0) || (year % 400 == 0);
}

function tsToDateStr(ts: i64): string {
  let remaining = ts / 86400;
  let y = 1970;
  while (true) {
    let diy: i64 = isLeapYear(y as i32) ? 366 : 365;
    if (remaining < diy) break;
    remaining -= diy;
    y++;
  }
  let months: i32[] = [
    31, isLeapYear(y as i32) ? 29 : 28, 31, 30, 31, 30,
    31, 31, 30, 31, 30, 31,
  ];
  let m = 0;
  while (m < 12 && remaining >= months[m]) {
    remaining -= months[m];
    m++;
  }
  let month = m + 1;
  let day = (remaining as i32) + 1;
  let mm = month < 10 ? "0" + month.toString() : month.toString();
  let dd = day < 10 ? "0" + day.toString() : day.toString();
  return y.toString() + "-" + mm + "-" + dd;
}

// =============================================================================
// bond-created
// =============================================================================

export function handleBondCreated(event: BondCreated): void {
  let nftId  = event.params.nftId;
  let amount = event.params.amount.toBigDecimal().div(DECIMALS);
  let date   = tsToDateStr(event.block.timestamp.toI64());

  let ev         = new BondCreatedEvent(event.transaction.hash.toHex() + "-" + event.logIndex.toString());
  ev.nftId       = nftId;
  ev.owner       = event.params.account;
  ev.poolId      = event.params.poolId as i32;
  ev.amount      = amount;
  ev.date        = date;
  ev.blockNumber = event.block.number;
  ev.timestamp   = event.block.timestamp;
  ev.txHash      = event.transaction.hash;
  ev.save();

  let bond = Bond.load(nftId.toString());
  if (bond == null) {
    bond = new Bond(nftId.toString());
    bond.nftId               = nftId;
    bond.owner               = event.params.account;
    bond.poolId              = event.params.poolId as i32;
    bond.createdAtDate       = date;
    bond.createdAtTimestamp  = event.block.timestamp;
    bond.createdAtBlock      = event.block.number;
    bond.totalDeposited      = amount;
    bond.increaseCount       = 0;
    bond.lastDepositDate     = date;
    bond.lastDepositTimestamp = event.block.timestamp;
  }
  bond.save();
}

export function handleIncreaseBond(call: ethereum.Call): void {
  let nftId       = call.inputValues[0].value.toBigInt();
  let amountAdded = call.inputValues[1].value.toBigInt().toBigDecimal().div(DECIMALS);
  let date        = tsToDateStr(call.block.timestamp.toI64());

  // IncreaseBondEvent
  let ev         = new IncreaseBondEvent(call.transaction.hash.toHex() + "-" + call.block.number.toString());
  ev.nftId       = nftId;
  ev.amount      = amountAdded;
  ev.date        = date;
  ev.blockNumber = call.block.number;
  ev.timestamp   = call.block.timestamp;
  ev.txHash      = call.transaction.hash;
  ev.save();

  // BondTimeMarkerSnapshot — read onchain state post-call
  let contract = GovernanceBonding.bind(call.to);
  let bondData  = contract.try_getBond(nftId);
  if (!bondData.reverted) {
    let snapId   = call.transaction.hash.toHex() + "-" + call.block.number.toString() + "-tm";
    let snap     = new BondTimeMarkerSnapshot(snapId);
    snap.nftId       = nftId;
    snap.timeMarker  = bondData.value.timeMarker;
    snap.amount      = bondData.value.amount.toBigDecimal().div(DECIMALS);
    snap.poolId      = bondData.value.poolId as i32;
    snap.blockNumber = call.block.number;
    snap.timestamp   = call.block.timestamp;
    snap.save();
  }

  // Update Bond state entity
  let bond = Bond.load(nftId.toString());
  if (bond == null) return;
  bond.totalDeposited       = bond.totalDeposited.plus(amountAdded);
  bond.increaseCount        = bond.increaseCount + 1;
  bond.lastDepositDate      = date;
  bond.lastDepositTimestamp = call.block.timestamp;
  bond.save();
}

// =============================================================================
// bond-broken
// =============================================================================

export function handleBondBroken(event: BondBroken): void {
  let amount = event.params.amount.toBigDecimal().div(DECIMALS);
  let date   = tsToDateStr(event.block.timestamp.toI64());

  let ev         = new BondBrokenEvent(event.transaction.hash.toHex() + "-" + event.logIndex.toString());
  ev.nftId       = event.params.nftId;
  ev.amount      = amount;
  ev.date        = date;
  ev.blockNumber = event.block.number;
  ev.timestamp   = event.block.timestamp;
  ev.txHash      = event.transaction.hash;
  ev.save();
}

// =============================================================================
// bond-lifecycle
// =============================================================================

export function handleTokensReleased(event: TokensReleased): void {
  let amount = event.params.amount.toBigDecimal().div(DECIMALS);
  let date   = tsToDateStr(event.block.timestamp.toI64());

  let ev         = new TokensReleasedEvent(event.transaction.hash.toHex() + "-" + event.logIndex.toString());
  ev.nftId       = event.params.nftId;
  ev.to          = event.params.to;
  ev.amount      = amount;
  ev.date        = date;
  ev.blockNumber = event.block.number;
  ev.timestamp   = event.block.timestamp;
  ev.txHash      = event.transaction.hash;
  ev.save();
}

export function handleBondMigrated(event: BondMigrated): void {
  let date = tsToDateStr(event.block.timestamp.toI64());

  let ev         = new BondMigratedEvent(event.transaction.hash.toHex() + "-" + event.logIndex.toString());
  ev.nftId       = event.params.nftId;
  ev.toPool      = event.params.toPool as i32;
  ev.migrator    = event.params.migrator;
  ev.date        = date;
  ev.blockNumber = event.block.number;
  ev.timestamp   = event.block.timestamp;
  ev.txHash      = event.transaction.hash;
  ev.save();

  // Keep Bond state in sync
  let bond = Bond.load(event.params.nftId.toString());
  if (bond != null) {
    bond.poolId = event.params.toPool as i32;
    bond.save();
  }
}

export function handleVestingUpdated(event: VestingUpdated): void {
  let amount = event.params.amount.toBigDecimal().div(DECIMALS);
  let date   = tsToDateStr(event.block.timestamp.toI64());

  let ev         = new VestingUpdatedEvent(event.transaction.hash.toHex() + "-" + event.logIndex.toString());
  ev.nftId       = event.params.nftId;
  ev.amount      = amount;
  ev.cliff       = event.params.cliff;
  ev.vesting     = event.params.vesting;
  ev.start       = event.params.start;
  ev.date        = date;
  ev.blockNumber = event.block.number;
  ev.timestamp   = event.block.timestamp;
  ev.txHash      = event.transaction.hash;
  ev.save();
}

export function handleVestedTokenClawed(event: VestedTokenClawed): void {
  let amount = event.params.amount.toBigDecimal().div(DECIMALS);
  let date   = tsToDateStr(event.block.timestamp.toI64());

  let ev         = new VestedTokenClawedEvent(event.transaction.hash.toHex() + "-" + event.logIndex.toString());
  ev.nftId       = event.params.nftId;
  ev.amount      = amount;
  ev.to          = event.params.to;
  ev.date        = date;
  ev.blockNumber = event.block.number;
  ev.timestamp   = event.block.timestamp;
  ev.txHash      = event.transaction.hash;
  ev.save();
}

// =============================================================================
// pool-config
// =============================================================================

export function handlePoolUpdated(event: PoolUpdated): void {
  let date = tsToDateStr(event.block.timestamp.toI64());

  let ev                = new PoolUpdatedEvent(event.transaction.hash.toHex() + "-" + event.logIndex.toString());
  ev.poolId             = event.params.poolId as i32;
  ev.baseWeight         = BigInt.fromI32(event.params.baseWeight as i32);
  ev.maturedWeightBonus = BigInt.fromI32(event.params.maturedWeightBonus as i32);
  ev.fullMaturity       = event.params.fullMaturity;
  ev.date               = date;
  ev.blockNumber        = event.block.number;
  ev.timestamp          = event.block.timestamp;
  ev.txHash             = event.transaction.hash;
  ev.save();

  // Upsert Pool state entity
  let poolId = event.params.poolId.toString();
  let pool   = Pool.load(poolId);
  if (pool == null) {
    pool        = new Pool(poolId);
    pool.poolId = event.params.poolId as i32;
  }
  pool.baseWeight         = BigInt.fromI32(event.params.baseWeight as i32);
  pool.maturedWeightBonus = BigInt.fromI32(event.params.maturedWeightBonus as i32);
  pool.fullMaturity       = event.params.fullMaturity;
  pool.updatedAtDate      = date;
  pool.updatedAtTimestamp = event.block.timestamp;
  pool.save();
}

export function handleReleaseWarmupUpdated(event: ReleaseWarmupUpdated): void {
  let date = tsToDateStr(event.block.timestamp.toI64());

  let ev         = new ReleaseWarmupUpdatedEvent(event.transaction.hash.toHex() + "-" + event.logIndex.toString());
  ev.value       = event.params.value;
  ev.date        = date;
  ev.blockNumber = event.block.number;
  ev.timestamp   = event.block.timestamp;
  ev.txHash      = event.transaction.hash;
  ev.save();
}

export function handleMigratorAdded(event: MigratorAdded): void {
  let date = tsToDateStr(event.block.timestamp.toI64());

  let ev         = new MigratorAddedEvent(event.transaction.hash.toHex() + "-" + event.logIndex.toString());
  ev.migrator    = event.params.migrator;
  ev.date        = date;
  ev.blockNumber = event.block.number;
  ev.timestamp   = event.block.timestamp;
  ev.txHash      = event.transaction.hash;
  ev.save();
}

export function handleMigratorRemoved(event: MigratorRemoved): void {
  let date = tsToDateStr(event.block.timestamp.toI64());

  let ev         = new MigratorRemovedEvent(event.transaction.hash.toHex() + "-" + event.logIndex.toString());
  ev.migrator    = event.params.migrator;
  ev.date        = date;
  ev.blockNumber = event.block.number;
  ev.timestamp   = event.block.timestamp;
  ev.txHash      = event.transaction.hash;
  ev.save();
}

// =============================================================================
// nft-transfers
// =============================================================================

export function handleNftTransfer(event: Transfer): void {
  let date   = tsToDateStr(event.block.timestamp.toI64());
  let isMint = event.params.from.toHex() == ZERO_ADDRESS;

  // NftTransferEvent
  let ev         = new NftTransferEvent(event.transaction.hash.toHex() + "-" + event.logIndex.toString());
  ev.tokenId     = event.params.tokenId;
  ev.from        = event.params.from;
  ev.to          = event.params.to;
  ev.isMint      = isMint;
  ev.date        = date;
  ev.blockNumber = event.block.number;
  ev.timestamp   = event.block.timestamp;
  ev.txHash      = event.transaction.hash;
  ev.save();

  // Upsert BondOwner state entity
  let tokenId  = event.params.tokenId.toString();
  let owner    = BondOwner.load(tokenId);
  if (owner == null) {
    owner                    = new BondOwner(tokenId);
    owner.tokenId            = event.params.tokenId;
    owner.mintDate           = date;
    owner.mintTimestamp      = event.block.timestamp;
    owner.transferCount      = 0;
  }
  owner.owner                  = event.params.to;
  owner.lastTransferDate       = date;
  owner.lastTransferTimestamp  = event.block.timestamp;
  owner.transferCount          = owner.transferCount + 1;
  owner.save();
}
