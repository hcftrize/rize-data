import { BigDecimal, BigInt } from "@graphprotocol/graph-ts";
import { ethereum } from "@graphprotocol/graph-ts";
import { GovernanceBonding } from "../generated/GovernanceBonding/GovernanceBonding";
import { BondTimeMarkerSnapshot } from "../generated/schema";

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

export function handleIncreaseBond(call: ethereum.Call): void {
  let nftId       = call.inputValues[0].value.toBigInt();
  let amountAdded = call.inputValues[1].value.toBigInt().toBigDecimal().div(DECIMALS);

  let contract   = GovernanceBonding.bind(call.to);
  let bondResult = contract.try_getBond(nftId);
  if (bondResult.reverted) return;

  let timeMarker = bondResult.value.getTimeMarker();
  let amount     = bondResult.value.getAmount().toBigDecimal().div(DECIMALS);
  let poolId     = bondResult.value.getPoolId() as i32;

  let ev         = new BondTimeMarkerSnapshot(call.transaction.hash.toHex() + "-" + call.block.number.toString());
  ev.nftId       = nftId;
  ev.timeMarker  = timeMarker;
  ev.amount      = amount;
  ev.poolId      = poolId;
  ev.amountAdded = amountAdded;
  ev.date        = tsToDateStr(call.block.timestamp.toI64());
  ev.blockNumber = call.block.number;
  ev.timestamp   = call.block.timestamp;
  ev.txHash      = call.transaction.hash;
  ev.save();
}
