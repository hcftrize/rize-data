import { BigDecimal } from "@graphprotocol/graph-ts";
import { BondBroken as BondBrokenEvent } from "../generated/GovernanceBonding/GovernanceBonding";
import { BondBrokenEvent as BondBrokenEntity } from "../generated/schema";

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

export function handleBondBroken(event: BondBrokenEvent): void {
  let ev         = new BondBrokenEntity(event.transaction.hash.toHex() + "-" + event.logIndex.toString());
  ev.nftId       = event.params.nftId;
  ev.amount      = event.params.amount.toBigDecimal().div(DECIMALS);
  ev.date        = tsToDateStr(event.block.timestamp.toI64());
  ev.blockNumber = event.block.number;
  ev.timestamp   = event.block.timestamp;
  ev.txHash      = event.transaction.hash;
  ev.save();
}
