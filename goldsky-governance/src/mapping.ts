import { BigDecimal, BigInt } from "@graphprotocol/graph-ts";
import { ethereum } from "@graphprotocol/graph-ts";
import { BondCreated as BondCreatedEvent } from "../generated/GovernanceBonding/GovernanceBonding";
import { Bond, BondCreatedEvent as BondCreatedEntity, IncreaseBondEvent } from "../generated/schema";

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

export function handleBondCreated(event: BondCreatedEvent): void {
  let amount  = event.params.amount.toBigDecimal().div(DECIMALS);
  let dateStr = tsToDateStr(event.block.timestamp.toI64());
  let nftId   = event.params.nftId;
  let id      = nftId.toString();

  let bond = new Bond(id);
  bond.nftId                = nftId;
  bond.owner                = event.params.account;
  bond.poolId               = event.params.poolId as i32;
  bond.createdAtDate        = dateStr;
  bond.createdAtTimestamp   = event.block.timestamp;
  bond.createdAtBlock       = event.block.number;
  bond.totalDeposited       = amount;
  bond.increaseCount        = 0;
  bond.lastDepositDate      = dateStr;
  bond.lastDepositTimestamp = event.block.timestamp;
  bond.save();

  let ev         = new BondCreatedEntity(event.transaction.hash.toHex() + "-" + event.logIndex.toString());
  ev.nftId       = nftId;
  ev.owner       = event.params.account;
  ev.poolId      = event.params.poolId as i32;
  ev.amount      = amount;
  ev.date        = dateStr;
  ev.blockNumber = event.block.number;
  ev.timestamp   = event.block.timestamp;
  ev.txHash      = event.transaction.hash;
  ev.save();
}

export function handleIncreaseBond(call: ethereum.Call): void {
  let nftId       = call.inputValues[0].value.toBigInt();
  let amountAdded = call.inputValues[1].value.toBigInt().toBigDecimal().div(DECIMALS);
  let dateStr     = tsToDateStr(call.block.timestamp.toI64());
  let id          = nftId.toString();

  let bond = Bond.load(id);
  if (bond != null) {
    bond.totalDeposited        = bond.totalDeposited.plus(amountAdded);
    bond.increaseCount         = bond.increaseCount + 1;
    bond.lastDepositDate       = dateStr;
    bond.lastDepositTimestamp  = call.block.timestamp;
    bond.save();
  }

  let ev         = new IncreaseBondEvent(call.transaction.hash.toHex() + "-inc-" + call.block.number.toString());
  ev.nftId       = nftId;
  ev.amount      = amountAdded;
  ev.date        = dateStr;
  ev.blockNumber = call.block.number;
  ev.timestamp   = call.block.timestamp;
  ev.txHash      = call.transaction.hash;
  ev.save();
}
