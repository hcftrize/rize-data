import { BigDecimal, BigInt } from "@graphprotocol/graph-ts";
import { ethereum } from "@graphprotocol/graph-ts";
import { BondCreated } from "../generated/GovernanceBonding/GovernanceBonding";
import { Bond, BondCreatedEvent, IncreaseBondEvent } from "../generated/schema";

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

export function handleBondCreated(event: BondCreated): void {
  let nftId  = event.params.bondId;
  let amount = event.params.amount.toBigDecimal().div(DECIMALS);
  let date   = tsToDateStr(event.block.timestamp.toI64());

  let ev        = new BondCreatedEvent(event.transaction.hash.toHex() + "-" + event.logIndex.toString());
  ev.nftId      = nftId;
  ev.owner      = event.params.owner;
  ev.poolId     = event.params.poolId as i32;
  ev.amount     = amount;
  ev.date       = date;
  ev.blockNumber = event.block.number;
  ev.timestamp  = event.block.timestamp;
  ev.txHash     = event.transaction.hash;
  ev.save();

  let bond = Bond.load(nftId.toString());
  if (bond == null) {
    bond = new Bond(nftId.toString());
    bond.nftId               = nftId;
    bond.owner               = event.params.owner;
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

  let ev        = new IncreaseBondEvent(call.transaction.hash.toHex() + "-" + call.block.number.toString());
  ev.nftId      = nftId;
  ev.amount     = amountAdded;
  ev.date       = date;
  ev.blockNumber = call.block.number;
  ev.timestamp  = call.block.timestamp;
  ev.txHash     = call.transaction.hash;
  ev.save();

  let bond = Bond.load(nftId.toString());
  if (bond == null) return;
  bond.totalDeposited        = bond.totalDeposited.plus(amountAdded);
  bond.increaseCount         = bond.increaseCount + 1;
  bond.lastDepositDate       = date;
  bond.lastDepositTimestamp  = call.block.timestamp;
  bond.save();
}
