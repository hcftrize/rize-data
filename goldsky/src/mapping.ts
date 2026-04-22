import { BigDecimal, BigInt } from "@graphprotocol/graph-ts";
import { BondBroken as BondBrokenEvent } from "../generated/Governance/Governance";
import { BondBroken } from "../generated/schema";

export function handleBondBroken(event: BondBrokenEvent): void {
  let entity = new BondBroken(event.transaction.hash.toHex());

  entity.nftId       = event.params.nftId;
  entity.amount      = event.params.amount.toBigDecimal().div(
                         BigDecimal.fromString("1000000000000000000")
                       );
  entity.blockNumber = event.block.number;
  entity.timestamp   = event.block.timestamp;

  // ISO date string from unix timestamp
  let ts      = event.block.timestamp.toI64();
  let day     = ts / 86400;
  let year    = 1970;
  let month   = 1;
  let dayOfMonth = 1;

  // Simple date calculation from unix days
  let remaining = day;
  let y = 1970;
  while (true) {
    let daysInYear = isLeapYear(y) ? 366 : 365;
    if (remaining < daysInYear) break;
    remaining -= daysInYear;
    y++;
  }
  year = y;
  let months = [31, isLeapYear(year) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  let m = 0;
  while (m < 12 && remaining >= months[m]) {
    remaining -= months[m];
    m++;
  }
  month      = m + 1;
  dayOfMonth = remaining as i32 + 1;

  let mm = month < 10   ? "0" + month.toString()      : month.toString();
  let dd = dayOfMonth < 10 ? "0" + dayOfMonth.toString() : dayOfMonth.toString();
  entity.date = year.toString() + "-" + mm + "-" + dd;

  entity.save();
}

function isLeapYear(year: i32): bool {
  return (year % 4 == 0 && year % 100 != 0) || (year % 400 == 0);
}
