import { BigDecimal, BigInt, Bytes, log } from "@graphprotocol/graph-ts";
import {
  BondCreated as BondCreatedEvent,
  BondBroken as BondBrokenEvent,
  TokensReleased as TokensReleasedEvent,
  BondMigrated as BondMigratedEvent,
  PoolUpdated as PoolUpdatedEvent,
  VestedTokenClawed as VestedTokenClawedEvent,
  GovernanceBonding,
  GovernanceBonding__getBondResult,
} from "../generated/GovernanceBonding/GovernanceBonding";
import {
  Bond,
  Pool,
  BondCreatedEvent as BondCreatedEntity,
  IncreaseBondEvent,
  BondBrokenEvent as BondBrokenEntity,
  TokensReleasedEvent as TokensReleasedEntity,
  BondMigratedEvent as BondMigratedEntity,
  PoolUpdatedEvent as PoolUpdatedEntity,
  VestedTokenClawedEvent as VestedTokenClawedEntity,
  DailySnapshot,
  GlobalStats,
} from "../generated/schema";
import { increaseBond as IncreaseBondCall } from "../generated/GovernanceBonding/GovernanceBonding";

// ── Constants ─────────────────────────────────────────────────────────────────
let DECIMALS = BigDecimal.fromString("1000000000000000000"); // 1e18
let ZERO_BD  = BigDecimal.fromString("0");
let ZERO_BI  = BigInt.fromI32(0);
let ONE_I    = 1;

// ── Date helper (identical to existing subgraph) ──────────────────────────────
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
  let months: i32[] = [31, isLeapYear(y as i32) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  let m = 0;
  while (m < 12 && remaining >= months[m]) {
    remaining -= months[m];
    m++;
  }
  let month      = m + 1;
  let dayOfMonth = (remaining as i32) + 1;
  let mm = month      < 10 ? "0" + month.toString()      : month.toString();
  let dd = dayOfMonth < 10 ? "0" + dayOfMonth.toString() : dayOfMonth.toString();
  return y.toString() + "-" + mm + "-" + dd;
}

// ── GlobalStats helper ────────────────────────────────────────────────────────
function getOrCreateGlobalStats(block: BigInt, timestamp: BigInt): GlobalStats {
  let stats = GlobalStats.load("global");
  if (stats == null) {
    stats = new GlobalStats("global");
    stats.totalBonded       = ZERO_BD;
    stats.totalBondCount    = 0;
    stats.totalActiveBonds  = 0;
    stats.totalDeposited    = ZERO_BD;
    stats.totalBroken       = ZERO_BD;
    stats.totalReleased     = ZERO_BD;
    stats.uniqueBonders     = 0;
    stats.lastUpdatedBlock  = block;
    stats.lastUpdatedTimestamp = timestamp;
  }
  return stats as GlobalStats;
}

// ── DailySnapshot helper ──────────────────────────────────────────────────────
function getOrCreateDailySnapshot(dateStr: string, block: BigInt, timestamp: BigInt): DailySnapshot {
  let snap = DailySnapshot.load(dateStr);
  if (snap == null) {
    snap = new DailySnapshot(dateStr);
    snap.date            = dateStr;
    snap.totalBonded     = ZERO_BD;
    snap.totalBroken     = ZERO_BD;
    snap.totalReleased   = ZERO_BD;
    snap.activeBonds     = 0;
    snap.newBonds        = 0;
    snap.newBreaks       = 0;
    snap.newReleases     = 0;
    snap.volumeDeposited = ZERO_BD;
    snap.volumeBroken    = ZERO_BD;
  }
  return snap as DailySnapshot;
}

// ── Bond helper ───────────────────────────────────────────────────────────────
function getOrCreateBond(nftId: BigInt, block: BigInt, timestamp: BigInt): Bond {
  let id   = nftId.toString();
  let bond = Bond.load(id);
  if (bond == null) {
    bond = new Bond(id);
    bond.nftId               = nftId;
    bond.owner               = Bytes.fromHexString("0x0000000000000000000000000000000000000000");
    bond.poolId              = 0;
    bond.amount              = ZERO_BD;
    bond.timeMarker          = ZERO_BI;
    bond.createdAtBlock      = block;
    bond.createdAtTimestamp  = timestamp;
    bond.createdAtDate       = tsToDateStr(timestamp.toI64());
    bond.lastUpdatedBlock    = block;
    bond.lastUpdatedTimestamp= timestamp;
    bond.isActive            = true;
    bond.totalDeposited      = ZERO_BD;
    bond.totalBroken         = ZERO_BD;
    bond.totalReleased       = ZERO_BD;
    bond.increaseCount       = 0;
    bond.breakCount          = 0;
  }
  return bond as Bond;
}

// ── Event: BondCreated ────────────────────────────────────────────────────────
export function handleBondCreated(event: BondCreatedEvent): void {
  let amount  = event.params.amount.toBigDecimal().div(DECIMALS);
  let dateStr = tsToDateStr(event.block.timestamp.toI64());
  let nftId   = event.params.nftId;

  // Bond entity
  let bond            = getOrCreateBond(nftId, event.block.number, event.block.timestamp);
  bond.owner          = event.params.account;
  bond.poolId         = event.params.poolId as i32;
  bond.amount         = amount;
  bond.timeMarker     = event.block.timestamp; // initial timeMarker = creation timestamp
  bond.totalDeposited = amount;
  bond.isActive       = true;
  bond.lastUpdatedBlock     = event.block.number;
  bond.lastUpdatedTimestamp = event.block.timestamp;
  bond.save();

  // Immutable event
  let ev       = new BondCreatedEntity(event.transaction.hash.toHex() + "-" + event.logIndex.toString());
  ev.nftId     = nftId;
  ev.owner     = event.params.account;
  ev.poolId    = event.params.poolId as i32;
  ev.amount    = amount;
  ev.date      = dateStr;
  ev.blockNumber  = event.block.number;
  ev.timestamp    = event.block.timestamp;
  ev.txHash       = event.transaction.hash;
  ev.save();

  // Daily snapshot
  let snap = getOrCreateDailySnapshot(dateStr, event.block.number, event.block.timestamp);
  snap.newBonds        = snap.newBonds + ONE_I;
  snap.volumeDeposited = snap.volumeDeposited.plus(amount);
  snap.activeBonds     = snap.activeBonds + ONE_I;
  snap.totalBonded     = snap.totalBonded.plus(amount);
  snap.save();

  // Global stats
  let stats = getOrCreateGlobalStats(event.block.number, event.block.timestamp);
  stats.totalBondCount   = stats.totalBondCount + ONE_I;
  stats.totalActiveBonds = stats.totalActiveBonds + ONE_I;
  stats.totalBonded      = stats.totalBonded.plus(amount);
  stats.totalDeposited   = stats.totalDeposited.plus(amount);
  stats.lastUpdatedBlock      = event.block.number;
  stats.lastUpdatedTimestamp  = event.block.timestamp;
  stats.save();
}

// ── Call: increaseBond ────────────────────────────────────────────────────────
export function handleIncreaseBond(call: IncreaseBondCall): void {
  let nftId   = call.inputs.tokenId;
  let amount  = call.inputs.amount.toBigDecimal().div(DECIMALS);
  let dateStr = tsToDateStr(call.block.timestamp.toI64());

  // Update bond
  let bond = Bond.load(nftId.toString());
  if (bond == null) return;
  let prevAmount   = bond.amount;
  bond.amount      = bond.amount.plus(amount);
  bond.totalDeposited = bond.totalDeposited.plus(amount);
  bond.increaseCount  = bond.increaseCount + ONE_I;
  bond.lastUpdatedBlock     = call.block.number;
  bond.lastUpdatedTimestamp = call.block.timestamp;
  // Note: timeMarker is recalculated by the contract — we don't update it here
  // (it will be read via RPC when needed for accurate maturity)
  bond.save();

  // Immutable event
  let id = call.transaction.hash.toHex() + "-inc";
  let ev       = new IncreaseBondEvent(id);
  ev.nftId     = nftId;
  ev.amount    = amount;
  ev.newTotal  = bond.amount;
  ev.date      = dateStr;
  ev.blockNumber  = call.block.number;
  ev.timestamp    = call.block.timestamp;
  ev.txHash       = call.transaction.hash;
  ev.save();

  // Daily snapshot
  let snap = getOrCreateDailySnapshot(dateStr, call.block.number, call.block.timestamp);
  snap.volumeDeposited = snap.volumeDeposited.plus(amount);
  snap.totalBonded     = snap.totalBonded.plus(amount);
  snap.save();

  // Global stats
  let stats = getOrCreateGlobalStats(call.block.number, call.block.timestamp);
  stats.totalBonded    = stats.totalBonded.plus(amount);
  stats.totalDeposited = stats.totalDeposited.plus(amount);
  stats.lastUpdatedBlock     = call.block.number;
  stats.lastUpdatedTimestamp = call.block.timestamp;
  stats.save();
}

// ── Event: BondBroken ─────────────────────────────────────────────────────────
export function handleBondBroken(event: BondBrokenEvent): void {
  let amount  = event.params.amount.toBigDecimal().div(DECIMALS);
  let dateStr = tsToDateStr(event.block.timestamp.toI64());
  let nftId   = event.params.nftId;

  // Update bond
  let bond = Bond.load(nftId.toString());
  if (bond != null) {
    bond.amount       = bond.amount.minus(amount); // amount already deducted by contract
    bond.totalBroken  = bond.totalBroken.plus(amount);
    bond.breakCount   = bond.breakCount + ONE_I;
    if (bond.amount.le(ZERO_BD)) {
      bond.amount   = ZERO_BD;
      bond.isActive = false;
    }
    bond.lastUpdatedBlock     = event.block.number;
    bond.lastUpdatedTimestamp = event.block.timestamp;
    bond.save();
  }

  // Immutable event
  let ev        = new BondBrokenEntity(event.transaction.hash.toHex() + "-" + event.logIndex.toString());
  ev.nftId      = nftId;
  ev.amount     = amount;
  ev.date       = dateStr;
  ev.blockNumber   = event.block.number;
  ev.timestamp     = event.block.timestamp;
  ev.txHash        = event.transaction.hash;
  ev.save();

  // Daily snapshot
  let snap = getOrCreateDailySnapshot(dateStr, event.block.number, event.block.timestamp);
  snap.newBreaks    = snap.newBreaks + ONE_I;
  snap.volumeBroken = snap.volumeBroken.plus(amount);
  snap.totalBroken  = snap.totalBroken.plus(amount);
  snap.save();

  // Global stats
  let stats = getOrCreateGlobalStats(event.block.number, event.block.timestamp);
  stats.totalBroken = stats.totalBroken.plus(amount);
  stats.totalBonded = stats.totalBonded.minus(amount);
  if (stats.totalBonded.lt(ZERO_BD)) stats.totalBonded = ZERO_BD;
  stats.lastUpdatedBlock     = event.block.number;
  stats.lastUpdatedTimestamp = event.block.timestamp;
  stats.save();
}

// ── Event: TokensReleased ─────────────────────────────────────────────────────
export function handleTokensReleased(event: TokensReleasedEvent): void {
  let amount  = event.params.amount.toBigDecimal().div(DECIMALS);
  let dateStr = tsToDateStr(event.block.timestamp.toI64());
  let nftId   = event.params.nftId;

  // Update bond
  let bond = Bond.load(nftId.toString());
  if (bond != null) {
    bond.totalReleased = bond.totalReleased.plus(amount);
    bond.lastUpdatedBlock     = event.block.number;
    bond.lastUpdatedTimestamp = event.block.timestamp;
    bond.save();
  }

  // Immutable event
  let ev      = new TokensReleasedEntity(event.transaction.hash.toHex() + "-" + event.logIndex.toString());
  ev.nftId    = nftId;
  ev.to       = event.params.to;
  ev.amount   = amount;
  ev.date     = dateStr;
  ev.blockNumber  = event.block.number;
  ev.timestamp    = event.block.timestamp;
  ev.txHash       = event.transaction.hash;
  ev.save();

  // Daily snapshot
  let snap = getOrCreateDailySnapshot(dateStr, event.block.number, event.block.timestamp);
  snap.newReleases   = snap.newReleases + ONE_I;
  snap.totalReleased = snap.totalReleased.plus(amount);
  snap.save();

  // Global stats
  let stats = getOrCreateGlobalStats(event.block.number, event.block.timestamp);
  stats.totalReleased = stats.totalReleased.plus(amount);
  stats.lastUpdatedBlock     = event.block.number;
  stats.lastUpdatedTimestamp = event.block.timestamp;
  stats.save();
}

// ── Event: BondMigrated ───────────────────────────────────────────────────────
export function handleBondMigrated(event: BondMigratedEvent): void {
  let dateStr = tsToDateStr(event.block.timestamp.toI64());
  let nftId   = event.params.nftId;

  // Update bond pool
  let bond = Bond.load(nftId.toString());
  let fromPool = 0;
  if (bond != null) {
    fromPool     = bond.poolId;
    bond.poolId  = event.params.toPool as i32;
    bond.lastUpdatedBlock     = event.block.number;
    bond.lastUpdatedTimestamp = event.block.timestamp;
    bond.save();
  }

  // Immutable event
  let ev        = new BondMigratedEntity(event.transaction.hash.toHex() + "-" + event.logIndex.toString());
  ev.nftId      = nftId;
  ev.fromPool   = fromPool;
  ev.toPool     = event.params.toPool as i32;
  ev.migrator   = event.params.migrator;
  ev.date       = dateStr;
  ev.blockNumber   = event.block.number;
  ev.timestamp     = event.block.timestamp;
  ev.txHash        = event.transaction.hash;
  ev.save();
}

// ── Event: PoolUpdated ────────────────────────────────────────────────────────
export function handlePoolUpdated(event: PoolUpdatedEvent): void {
  let dateStr = tsToDateStr(event.block.timestamp.toI64());
  let poolId  = event.params.poolId as i32;
  let id      = poolId.toString();

  // Pool entity (upsert)
  let pool = Pool.load(id);
  if (pool == null) {
    pool = new Pool(id);
    pool.poolId = poolId;
  }
  pool.baseWeight         = BigInt.fromI32(event.params.baseWeight as i32);
  pool.maturedWeightBonus = BigInt.fromI32(event.params.maturedWeightBonus as i32);
  pool.fullMaturity       = event.params.fullMaturity;
  pool.updatedAtBlock     = event.block.number;
  pool.updatedAtTimestamp = event.block.timestamp;
  pool.updatedAtDate      = dateStr;
  pool.save();

  // Immutable event
  let ev                  = new PoolUpdatedEntity(event.transaction.hash.toHex() + "-" + event.logIndex.toString());
  ev.poolId               = poolId;
  ev.baseWeight           = BigInt.fromI32(event.params.baseWeight as i32);
  ev.maturedWeightBonus   = BigInt.fromI32(event.params.maturedWeightBonus as i32);
  ev.fullMaturity         = event.params.fullMaturity;
  ev.date                 = dateStr;
  ev.blockNumber          = event.block.number;
  ev.timestamp            = event.block.timestamp;
  ev.txHash               = event.transaction.hash;
  ev.save();
}

// ── Event: VestedTokenClawed ──────────────────────────────────────────────────
export function handleVestedTokenClawed(event: VestedTokenClawedEvent): void {
  let amount  = event.params.amount.toBigDecimal().div(DECIMALS);
  let dateStr = tsToDateStr(event.block.timestamp.toI64());
  let nftId   = event.params.nftId;

  let ev      = new VestedTokenClawedEntity(event.transaction.hash.toHex() + "-" + event.logIndex.toString());
  ev.nftId    = nftId;
  ev.amount   = amount;
  ev.to       = event.params.to;
  ev.date     = dateStr;
  ev.blockNumber  = event.block.number;
  ev.timestamp    = event.block.timestamp;
  ev.txHash       = event.transaction.hash;
  ev.save();
}
