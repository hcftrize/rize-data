import { BigDecimal, BigInt } from "@graphprotocol/graph-ts";
import { BondBroken as BondBrokenEvent } from "../generated/Governance/Governance";
import { BondBroken, DailyUnbondingQueue } from "../generated/schema";

// ── Date helpers ──────────────────────────────────────────────────────────────

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

function dayStartTs(ts: i64): i64 {
  return (ts / 86400) * 86400;
}

// ── Handler ───────────────────────────────────────────────────────────────────

export function handleBondBroken(event: BondBrokenEvent): void {
  let DECIMALS = BigDecimal.fromString("1000000000000000000");
  let amount   = event.params.amount.toBigDecimal().div(DECIMALS);
  let ts       = event.block.timestamp.toI64();
  let dateStr  = tsToDateStr(ts);

  // ── BondBroken entity (immutable, one per event) ──────────────────────────
  let entity      = new BondBroken(event.transaction.hash.toHex());
  entity.nftId    = event.params.nftId;
  entity.amount   = amount;
  entity.date     = dateStr;
  entity.blockNumber = event.block.number;
  entity.timestamp   = event.block.timestamp;
  entity.save();

  // ── DailyUnbondingQueue — rolling 7-day sum ───────────────────────────────
  // We store one entry per day and accumulate all BondBroken that fire that day.
  // The JS side will do the 7-day rolling window across these daily totals.
  let dayId  = dateStr;
  let dayRec = DailyUnbondingQueue.load(dayId);
  if (dayRec == null) {
    dayRec             = new DailyUnbondingQueue(dayId);
    dayRec.date        = dateStr;
    dayRec.timestamp   = BigInt.fromI64(dayStartTs(ts));
    dayRec.totalAmount = BigDecimal.fromString("0");
    dayRec.eventCount  = 0;
  }
  dayRec.totalAmount = dayRec.totalAmount.plus(amount);
  dayRec.eventCount  = dayRec.eventCount + 1;
  dayRec.save();
}
