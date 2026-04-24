import { BigInt, Bytes } from "@graphprotocol/graph-ts";
import { Transfer as TransferEvent } from "../generated/RizeGovernanceNFT/RizeGovernanceNFT";
import { NftTransferEvent, BondOwner } from "../generated/schema";

let ZERO_ADDRESS = "0x0000000000000000000000000000000000000000";

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

export function handleTransfer(event: TransferEvent): void {
  let tokenId = event.params.tokenId;
  let from    = event.params.from;
  let to      = event.params.to;
  let dateStr = tsToDateStr(event.block.timestamp.toI64());
  let isMint  = from.toHexString() == ZERO_ADDRESS;

  // Immutable transfer event
  let ev        = new NftTransferEvent(event.transaction.hash.toHex() + "-" + event.logIndex.toString());
  ev.tokenId    = tokenId;
  ev.from       = from;
  ev.to         = to;
  ev.isMint     = isMint;
  ev.date       = dateStr;
  ev.blockNumber   = event.block.number;
  ev.timestamp     = event.block.timestamp;
  ev.txHash        = event.transaction.hash;
  ev.save();

  // Upsert BondOwner
  let id    = tokenId.toString();
  let owner = BondOwner.load(id);
  if (owner == null) {
    owner = new BondOwner(id);
    owner.tokenId          = tokenId;
    owner.mintDate         = dateStr;
    owner.mintTimestamp    = event.block.timestamp;
    owner.transferCount    = 0;
  }
  owner.owner                  = to;
  owner.lastTransferDate       = dateStr;
  owner.lastTransferTimestamp  = event.block.timestamp;
  owner.transferCount          = owner.transferCount + 1;
  owner.save();
}
