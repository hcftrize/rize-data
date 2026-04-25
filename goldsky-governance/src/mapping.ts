import { BigDecimal, BigInt } from "@graphprotocol/graph-ts";
import {
  TokensReleased as TokensReleasedEvent,
  BondMigrated as BondMigratedEvent,
  VestingUpdated as VestingUpdatedEvent,
  VestedTokenClawed as VestedTokenClawedEvent,
} from "../generated/GovernanceBonding/GovernanceBonding";
import {
  TokensReleasedEvent as TokensReleasedEntity,
  BondMigratedEvent as BondMigratedEntity,
  VestingUpdatedEvent as VestingUpdatedEntity,
  VestedTokenClawedEvent as VestedTokenClawedEntity,
} from "../generated/schema";

let DECIMALS = BigDecimal.fromString("1000000000000000000");

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

export function handleTokensReleased(event: TokensReleasedEvent): void {
  let ev      = new TokensReleasedEntity(event.transaction.hash.toHex() + "-" + event.logIndex.toString());
  ev.nftId    = event.params.nftId;
  ev.to       = event.params.to;
  ev.amount   = event.params.amount.toBigDecimal().div(DECIMALS);
  ev.date     = tsToDateStr(event.block.timestamp.toI64());
  ev.blockNumber = event.block.number;
  ev.timestamp   = event.block.timestamp;
  ev.txHash      = event.transaction.hash;
  ev.save();
}

export function handleBondMigrated(event: BondMigratedEvent): void {
  let ev        = new BondMigratedEntity(event.transaction.hash.toHex() + "-" + event.logIndex.toString());
  ev.nftId      = event.params.nftId;
  ev.toPool     = event.params.toPool as i32;
  ev.migrator   = event.params.migrator;
  ev.date       = tsToDateStr(event.block.timestamp.toI64());
  ev.blockNumber   = event.block.number;
  ev.timestamp     = event.block.timestamp;
  ev.txHash        = event.transaction.hash;
  ev.save();
}

export function handleVestingUpdated(event: VestingUpdatedEvent): void {
  let ev      = new VestingUpdatedEntity(event.transaction.hash.toHex() + "-" + event.logIndex.toString());
  ev.nftId    = event.params.nftId;
  ev.amount   = event.params.amount.toBigDecimal().div(DECIMALS);
  ev.cliff    = BigInt.fromI32(event.params.cliff as i32);
  ev.vesting  = BigInt.fromI32(event.params.vesting as i32);
  ev.start    = BigInt.fromI32(event.params.start as i32);
  ev.date     = tsToDateStr(event.block.timestamp.toI64());
  ev.blockNumber = event.block.number;
  ev.timestamp   = event.block.timestamp;
  ev.txHash      = event.transaction.hash;
  ev.save();
}

export function handleVestedTokenClawed(event: VestedTokenClawedEvent): void {
  let ev      = new VestedTokenClawedEntity(event.transaction.hash.toHex() + "-" + event.logIndex.toString());
  ev.nftId    = event.params.nftId;
  ev.amount   = event.params.amount.toBigDecimal().div(DECIMALS);
  ev.to       = event.params.to;
  ev.date     = tsToDateStr(event.block.timestamp.toI64());
  ev.blockNumber = event.block.number;
  ev.timestamp   = event.block.timestamp;
  ev.txHash      = event.transaction.hash;
  ev.save();
}
