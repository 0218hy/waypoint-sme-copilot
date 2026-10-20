"""Hash-chained, append-only audit log (SPEC §8.2, §8.5).

Each record carries the SHA-256 of the previous record, so editing, deleting or reordering any
record breaks the chain. A record's hash is the hash of its link (seq, prev, a digest of its content and
a tag of its owner), so an owner's proof can carry every link of the chain without anyone else's
content, and a checker re-derives each link from genesis to the head. Cutting records off the end
leaves a shorter chain that still verifies on its own: that is caught only against a head someone
pinned earlier (`verify <path> --head <seq:hash>`, the `pin` of `/api/audit/proof`).
Arguments are stored redacted. `python -m agent.audit verify <path>` exits 1 on tamper.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import rfc8785

GENESIS = "0" * 64
VERSION = 2  # records without "v" use the first format: the hash of the whole record
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# A phone number stands on its own: digits inside a longer token (a hex hash, an id like "u_0da5..." or
# "doc-1234...") are not one, and neither is an ISO date. Only ASCII bounds it, so "电话13800138000" matches.
_PHONE = re.compile(r"(?<![0-9A-Za-z_-])(?!\d{4}-\d{2}-\d{2}(?!\d))(?:\+?\d[\d -]{7,}\d)(?![0-9A-Za-z_-])")
_SECRET_KEYS = {"token", "password", "api_key", "authorization", "cookie", "secret", "email"}


def redact(value: Any) -> Any:
    """Redact personal data and secrets before anything is logged."""
    if isinstance(value, dict):
        return {k: ("[redacted]" if k.lower() in _SECRET_KEYS else redact(v)) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return _PHONE.sub("[phone]", _EMAIL.sub("[email]", value))
    return value


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def record_hash(body: dict[str, Any]) -> str:
    return hashlib.sha256(rfc8785.dumps(_jsonable(body))).hexdigest()


def owner_tag(owner_id: str | None) -> str | None:
    """Stands for the owner in a link, so a proof shows which links are an owner's without naming others."""
    return None if owner_id is None else hashlib.sha256(f"waypoint-owner:{owner_id}".encode()).hexdigest()


def link(rec: dict[str, Any]) -> dict[str, Any]:
    """What a record's hash covers: its place in the chain, its owner's tag and a digest of its content."""
    content = {k: v for k, v in rec.items() if k not in ("seq", "prev", "hash")}
    return {
        "seq": rec.get("seq"),
        "prev": rec.get("prev"),
        "owner_tag": owner_tag(rec.get("owner")),
        "digest": record_hash(content),
    }


def chained_hash(rec: dict[str, Any]) -> str:
    if rec.get("v") == VERSION:
        return record_hash(link(rec))
    return record_hash({k: v for k, v in rec.items() if k != "hash"})


class AuditLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._seq, self._prev = self._tail()

    def _tail(self) -> tuple[int, str]:
        if not self.path.exists():
            return 0, GENESIS
        last: dict[str, Any] | None = None
        with self.path.open() as fh:
            for line in fh:
                if line.strip():
                    last = json.loads(line)
        if last is None:
            return 0, GENESIS
        return int(last["seq"]), str(last["hash"])

    def append(self, kind: str, owner_id: str | None, **fields: Any) -> dict[str, Any]:
        with self._lock:
            body: dict[str, Any] = {
                "seq": self._seq + 1,
                "ts": datetime.now(UTC).isoformat(),
                "kind": kind,
                "owner": owner_id,
                **redact(_jsonable(fields)),
                "prev": self._prev,
                "v": VERSION,
            }
            body["hash"] = chained_hash(body)
            with self.path.open("a") as fh:
                fh.write(json.dumps(body, ensure_ascii=False, sort_keys=True) + "\n")
            self._seq, self._prev = body["seq"], body["hash"]
            return body


def parse_head(text: str) -> tuple[int, str]:
    """A pinned head written as "<seq>:<hash>" (the `head` of a proof)."""
    seq, _, h = text.strip().partition(":")
    if not seq.isdigit() or not re.fullmatch(r"[0-9a-f]{64}", h):
        raise ValueError("a head is <seq>:<64 hex characters>")
    return int(seq), h


def verify(path: Path, head: tuple[int, str] | None = None) -> tuple[bool, int | None, str]:
    """Return (ok, first bad seq, message). With a pinned `head` (seq, hash), the chain must still hold
    that record: a log cut back below it, or rewritten up to it, fails."""
    prev = GENESIS
    expected_seq = 1
    seen_head: str | None = None
    with path.open() as fh:
        for lineno, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                rec = None
            if not isinstance(rec, dict):
                return False, expected_seq, f"malformed record on line {lineno}: not a JSON object"
            claimed = rec.pop("hash", None)
            if rec.get("seq") != expected_seq:
                return False, rec.get("seq"), f"sequence break: expected {expected_seq}"
            if rec.get("prev") != prev:
                return False, rec["seq"], "previous-hash mismatch"
            if chained_hash(rec) != claimed:
                return False, rec["seq"], "record hash mismatch"
            if head is not None and rec["seq"] == head[0]:
                seen_head = claimed
            prev = claimed
            expected_seq += 1
    n = expected_seq - 1
    if head is not None:
        if n < head[0]:
            return False, n + 1, f"truncated: the chain ends at seq {n}, the pinned head is seq {head[0]}"
        if seen_head != head[1]:
            return False, head[0], "pinned head mismatch: the record at that seq has a different hash"
        return True, None, f"{n} records verified; pinned head seq {head[0]} present"
    return True, None, f"{n} records verified"


def proof(path: Path, owner_id: str) -> dict[str, Any]:
    """What an owner can hand to WeBank or a regulator: whether the whole chain verifies now, its head
    (the latest seq and hash, to compare with the copy the operator or the bank keeps), every record about
    this owner, and every link of the chain (seq, prev, owner tag, content digest, hash) with no one
    else's content. `check_proof` re-derives the links from genesis to the head offline."""
    ok, seq, msg = verify(path) if path.exists() else (True, None, "0 records verified")
    mine: list[dict[str, Any]] = []
    chain: list[dict[str, Any]] = []
    head = {"seq": 0, "hash": GENESIS}
    if path.exists():
        with path.open() as fh:
            for line in fh:
                if not line.strip():
                    continue
                rec = json.loads(line)
                head = {"seq": rec["seq"], "hash": rec["hash"]}
                chain.append(
                    {**link(rec), "hash": rec["hash"]}
                    if rec.get("v") == VERSION
                    else {"seq": rec["seq"], "prev": rec.get("prev"), "hash": rec["hash"], "v": 1}
                )
                if rec.get("owner") == owner_id:
                    mine.append(rec)
    return {
        "chain_intact": ok,
        "message": msg if ok else f"tamper at seq {seq}: {msg}",
        "owner": owner_id,
        "head": head,
        "records": mine,
        "chain": chain,
        "pin": f"{head['seq']}:{head['hash']}",
        "how_to_check": "python -m agent.audit check-proof <this file> [--head <pin kept earlier>]: "
        "re-derives every link of 'chain' from genesis to 'head' (each hash is SHA-256 of RFC 8785 JSON of "
        "seq, prev, owner_tag and digest), re-hashes each of the owner's records against its link, and "
        "fails if a link of this owner has no record here. Keep 'pin' (the chain head now): later, "
        "python -m agent.audit verify <log> --head <pin>, or check-proof of a newer proof with --head <pin>, "
        "fails if the chain was cut back or rewritten below it. Without a pinned head kept outside the "
        "server, an operator who rebuilds the whole chain goes unnoticed.",
    }


def check_proof(data: dict[str, Any], head: tuple[int, str] | None = None) -> tuple[bool, str]:
    """Offline check of a proof. The links must chain from genesis to the stated head, each link's hash
    must follow from its fields, each of the owner's records must re-hash to its link, and every link
    tagged with the owner must have its record here. With a pinned `head`, the chain must still hold it."""
    owner = data.get("owner")
    records = data.get("records") or []
    chain = data.get("chain")
    stated = data.get("head") or {}
    if not isinstance(owner, str) or not isinstance(chain, list):
        return False, "the proof has no owner or no chain links"
    prev, by_seq = GENESIS, {}
    for i, ln in enumerate(chain, start=1):
        if not isinstance(ln, dict) or ln.get("seq") != i:
            return False, f"chain link {i} is missing or out of order"
        if ln.get("prev") != prev:
            return False, f"chain link seq {i} does not point to the link before it"
        if ln.get("v") == 1 or "digest" not in ln:
            return False, f"chain link seq {i} is in the first log format, which a proof can't bind"
        fields = {k: ln.get(k) for k in ("seq", "prev", "owner_tag", "digest")}
        if record_hash(fields) != ln.get("hash"):
            return False, f"chain link seq {i} does not match its hash"
        prev, by_seq[i] = ln["hash"], ln
    n = len(chain)
    if stated.get("seq") != n or stated.get("hash") != prev:
        return False, f"the stated head is not where the chain ends (seq {n})"
    if data.get("pin") is not None and data.get("pin") != f"{n}:{prev}":
        return False, "the pin is not the chain head"
    tag, seen = owner_tag(owner), set()
    for rec in records:
        seq = rec.get("seq")
        ln = by_seq.get(seq) if isinstance(seq, int) else None
        if rec.get("owner") != owner:
            return False, f"record seq {seq} belongs to someone else"
        if ln is None or seq in seen:
            return False, f"record seq {seq} has no link in the chain, or is repeated"
        if rec.get("v") != VERSION or {**link(rec), "hash": rec.get("hash")} != ln:
            return False, f"record seq {seq} does not match its link"
        if chained_hash(rec) != rec.get("hash"):
            return False, f"record seq {seq} does not match its hash"
        seen.add(seq)
    missing = [s for s, ln in by_seq.items() if ln.get("owner_tag") == tag and s not in seen]
    if missing:
        return False, f"the chain has records of this owner that the proof leaves out: seq {missing}"
    if head is not None:
        if n < head[0]:
            return False, f"truncated: the chain ends at seq {n}, the pinned head is seq {head[0]}"
        if head[0] > 0 and by_seq[head[0]]["hash"] != head[1]:
            return False, f"pinned head mismatch at seq {head[0]}"
    pinned = f"; pinned head seq {head[0]} present" if head is not None else ""
    return True, (
        f"{len(records)} records of this owner match their links; {n} links chain from genesis to "
        f"head seq {n}{pinned}"
    )


def main(argv: list[str]) -> int:
    usage = (
        "usage: python -m agent.audit verify <path> [--head <seq:hash>]"
        " | check-proof <proof.json> [--head <seq:hash>]"
    )
    if (
        len(argv) not in (3, 5)
        or argv[1] not in ("verify", "check-proof")
        or (len(argv) == 5 and argv[3] != "--head")
    ):
        print(usage)
        return 2
    try:
        head = parse_head(argv[4]) if len(argv) == 5 else None
    except ValueError as exc:
        print(f"{usage}\n{exc}")
        return 2
    if argv[1] == "check-proof":
        try:
            data = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"MISMATCH: the proof is not valid JSON ({exc})")
            return 1
        ok, msg = (
            check_proof(data, head) if isinstance(data, dict) else (False, "the proof is not a JSON object")
        )
        print(("OK: " if ok else "MISMATCH: ") + msg)
        return 0 if ok else 1
    ok, seq, msg = verify(Path(argv[2]), head)
    print(("OK: " if ok else f"TAMPER at seq {seq}: ") + msg)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
