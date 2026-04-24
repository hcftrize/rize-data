import { BigDecimal, BigInt } from "@graphprotocol/graph-ts";
import {
  PoolUpdated as PoolUpdatedEvent,
  ReleaseWarmupUpdated as ReleaseWarmupUpdatedEvent,
  MigratorAdded as MigratorAddedEvent,
  MigratorRemoved as MigratorRemovedEvent,
} from "../generated/GovernanceBonding/GovernanceBonding";
import {
  Pool,
  PoolUpdatedEvent as PoolUpdatedEntity,
  ReleaseWarmupUpdatedEvent as ReleaseWarmupUpdatedEntity,
  MigratorAddedEvent as MigratorAddedEntity,
  MigratorRemovedEvent as MigratorRemovedEntity,
} from "../generated/schema";

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
  while (m < 12 && remaining >= months[m]) { remaining -= months[m]; m++; }
  let month = m + 1;
  let day   = (remaining as i32) + 1;
  let mm = month < 10 ? "0" + month.toString() : month.toString();
  let dd = day   < 10 ? "0" + day.toString()   : day.toString();
  return y.toString() + "-" + mm + "-" + dd;
}

export function handlePoolUpdated(event: PoolUpdatedEvent): void {
  let dateStr = tsToDateStr(event.block.timestamp.toI64());
  let poolId  = event.params.poolId as i32;

  // Upsert Pool entity
  let pool = Pool.load(poolId.toString());
  if (pool == null) { pool = new Pool(poolId.toString()); pool.poolId = poolId; }
  pool.baseWeight         = BigInt.fromString(event.params.baseWeight.toString());
  pool.maturedWeightBonus = BigInt.fromString(event.params.maturedWeightBonus.toString());
  pool.fullMaturity       = event.params.fullMaturity;
  pool.updatedAtDate      = dateStr;
  pool.updatedAtTimestamp = event.block.timestamp;
  pool.save();

  // Immutable event
  let ev                  = new PoolUpdatedEntity(event.transaction.hash.toHex() + "-" + event.logIndex.toString());
  ev.poolId               = poolId;
  ev.baseWeight           = BigInt.fromString(event.params.baseWeight.toString());
  ev.maturedWeightBonus   = BigInt.fromString(event.params.maturedWeightBonus.toString());
  ev.fullMaturity         = event.params.fullMaturity;
  ev.date                 = dateStr;
  ev.blockNumber          = event.block.number;
  ev.timestamp            = event.block.timestamp;
  ev.txHash               = event.transaction.hash;
  ev.save();
}

export function handleReleaseWarmupUpdated(event: ReleaseWarmupUpdatedEvent): void {
  let ev      = new ReleaseWarmupUpdatedEntity(event.transaction.hash.toHex() + "-" + event.logIndex.toString());
  ev.value    = event.params.value;
  ev.date     = tsToDateStr(event.block.timestamp.toI64());
  ev.blockNumber = event.block.number;
  ev.timestamp   = event.block.timestamp;
  ev.txHash      = event.transaction.hash;
  ev.save();
}

export function handleMigratorAdded(event: MigratorAddedEvent): void {
  let ev        = new MigratorAddedEntity(event.transaction.hash.toHex() + "-" + event.logIndex.toString());
  ev.migrator   = event.params.migrator;
  ev.date       = tsToDateStr(event.block.timestamp.toI64());
  ev.blockNumber   = event.block.number;
  ev.timestamp     = event.block.timestamp;
  ev.txHash        = event.transaction.hash;
  ev.save();
}

export function handleMigratorRemoved(event: MigratorRemovedEvent): void {
  let ev        = new MigratorRemovedEntity(event.transaction.hash.toHex() + "-" + event.logIndex.toString());
  ev.migrator   = event.params.migrator;
  ev.date       = tsToDateStr(event.block.timestamp.toI64());
  ev.blockNumber   = event.block.number;
  ev.timestamp     = event.block.timestamp;
  ev.txHash        = event.transaction.hash;
  ev.save();
}
