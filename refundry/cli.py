"""The demo CLI.

    python -m refundry.cli demo            file the case, pause at the approval
    python -m refundry.cli demo --yes      approve without prompting
    python -m refundry.cli trail RFD-48213 replay what crossed the wire
    python -m refundry.cli cards           every Agent Card, as discovery returns it
    python -m refundry.cli doctor          check all fifteen services separately
    python -m refundry.cli jev             what the System One layer decided
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

import httpx

from refundry.config import base_url

GW = base_url("gateway") + "/api/v1"

CASE = {
    "order_ref": "NW-7731094",
    "buyer_ref": "BUY-90211",
    "narrative": ("It arrived with the boiler casing cracked. The seller is "
                  "telling me to pay return shipping on a machine that showed "
                  "up broken."),
    "evidence_refs": [
        "case://RFD-48213/evidence/photo-1.jpg",
        "case://RFD-48213/evidence/photo-2.jpg",
        "case://RFD-48213/evidence/photo-3.jpg",
        "case://RFD-48213/evidence/packing-slip.pdf",
    ],
}

RULE = "─" * 78


def hr(title: str = "") -> None:
    print(f"\n{RULE}")
    if title:
        print(f"  {title}")


def show_timeline(rows: list[dict]) -> None:
    for e in rows:
        actor = e.get("actor", "")
        event = e.get("event", "")
        detail = (e.get("detail") or "").strip()
        if len(detail) > 500:
            detail = detail[:500] + " ..."
        print(f"  · {actor:<13} {event:<18} {detail}")


async def demo(auto_yes: bool) -> int:
    async with httpx.AsyncClient(timeout=180) as http:
        hr("Filing the claim")
        print(f"  order   {CASE['order_ref']}")
        print(f"  buyer   \"{CASE['narrative']}\"")
        r = await http.post(f"{GW}/refunds", json=CASE)
        r.raise_for_status()
        out = r.json()

        hr("The network at work")
        show_timeline(out["timeline"])

        routing = out.get("routing") or {}
        if routing:
            hr("What System One decided")
            for where, summary in routing.items():
                if isinstance(summary, dict) and "backend" in summary:
                    print(f"  · {where:<18} {json.dumps(summary)}")
                else:
                    print(f"  · {where:<18} {summary}")

        if not out["awaiting_approval"]:
            hr(f"{out['case_id']}  {str(out.get('status','')).upper()}")
            print(f"  {out['message']}")
            return 0

        req = out["approval_request"] or {}
        hr("Approval required")
        print(f"  {req.get('question','')}")
        print(f"  amount      ${req.get('amount', 0):,.2f} to {req.get('tender','')}")
        for c in req.get("citations", [])[:1]:
            print(f"  basis       {c['clause_id']} {c['title']}")
        print(f"  risk        {req.get('abuse','')[:150]}")
        conf = req.get("confidence") or {}
        if conf:
            print(f"  confidence  {conf.get('why','')}")

        if auto_yes:
            answer = "y"
            print("\n  Approve this spend? [y/N] y   (--yes)")
        else:
            answer = input("\n  Approve this spend? [y/N] ").strip().lower()

        approver = "elena.marchetti@northwind"
        r = await http.post(
            f"{GW}/refunds/{out['case_id']}/approve",
            json={"approved": answer == "y", "approver": approver if answer == "y" else "",
                  "note": "" if answer == "y" else "declined at the console"})
        if r.status_code == 422:
            print("  declined; no money moved.")
            return 0
        r.raise_for_status()
        done = r.json()

        hr("Resumed")
        show_timeline(done["timeline"][len(out["timeline"]):])

        hr(f"{done['case_id']}  {str(done.get('status','')).upper()}")
        result = done.get("result") or {}
        if result:
            print(f"  {result.get('message','')}")
            print(f"  approver   {result.get('approver','')}")
        print(f"  {done['message']}")
        return 0


async def trail(case_id: str) -> int:
    async with httpx.AsyncClient(timeout=30) as http:
        r = await http.get(f"{GW}/trail/{case_id}")
        r.raise_for_status()
        rows = r.json()["trail"]
    hr(f"Protocol traffic for {case_id}   ({len(rows)} exchanges, one contextId)")
    import time as _t
    for e in rows:
        when = _t.strftime("%H:%M:%S", _t.localtime(e["at"]))
        detail = (e.get("detail") or "")[:78]
        print(f"  {when}  {e['actor']:<12} {e['kind']:<18} "
              f"{e.get('target',''):<14} {detail}")
    return 0


async def cards() -> int:
    async with httpx.AsyncClient(timeout=30) as http:
        r = await http.get(f"{GW}/agents")
        agents = r.json()["agents"]
        r = await http.get(f"{GW}/servers")
        servers = r.json()["servers"]
    hr("Agent Cards, as A2A discovery returns them")
    for a in agents:
        if not a.get("reachable"):
            print(f"  {a['key']:<14} UNREACHABLE  {a.get('error','')}")
            continue
        print(f"  {a['name']:<14} v{a['version']:<8} {a['organization']:<38} "
              f"{','.join(a['skills'])}")
    hr("MCP servers")
    for s in servers:
        if not s.get("reachable"):
            print(f"  {s['key']:<14} UNREACHABLE  {s.get('error','')}")
            continue
        print(f"  {s['name']:<14} scope={s.get('scope',''):<22} "
              f"risk={s.get('riskTier',''):<8} stateless={s.get('stateless')}")
    return 0


async def doctor() -> int:
    async with httpx.AsyncClient(timeout=30) as http:
        try:
            r = await http.get(f"{GW}/doctor")
        except Exception as exc:
            print(f"  gateway unreachable on {base_url('gateway')}: {exc}")
            print("  start the network with:  make run")
            return 1
        d = r.json()
    hr("Doctor")
    print(f"  jev backend  {d['jev_backend']}")
    for c in d["checks"]:
        mark = "ok " if c["ok"] else "DOWN"
        print(f"  {mark}  {c['kind']:<7} {c['key']:<14} "
              f"{'' if c['ok'] else c.get('error','')}")
    print(f"\n  {'all fifteen services are up' if d['ok'] else 'something is down'}")
    return 0 if d["ok"] else 1


async def jev_report(case_id: str) -> int:
    async with httpx.AsyncClient(timeout=30) as http:
        r = await http.get(f"{GW}/refunds/{case_id}")
        if r.status_code == 404:
            print(f"  no case {case_id}; run the demo first")
            return 1
        record = r.json()["record"]
    hr(f"System One decisions for {case_id}")
    for where, summary in (record.get("routing") or {}).items():
        print(f"  {where}")
        print(f"    {json.dumps(summary, indent=6)[6:]}" if isinstance(summary, dict)
              else f"    {summary}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="refundry")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("demo", help="file the sample claim end to end")
    d.add_argument("--yes", action="store_true", help="approve without prompting")

    t = sub.add_parser("trail", help="replay the protocol traffic for a case")
    t.add_argument("case_id", nargs="?", default="RFD-48213")

    sub.add_parser("cards", help="every Agent Card and MCP server")
    sub.add_parser("doctor", help="check all fifteen services")

    j = sub.add_parser("jev", help="what the System One layer decided")
    j.add_argument("case_id", nargs="?", default="RFD-48213")

    args = p.parse_args(argv)
    if args.cmd == "demo":
        return asyncio.run(demo(args.yes))
    if args.cmd == "trail":
        return asyncio.run(trail(args.case_id))
    if args.cmd == "cards":
        return asyncio.run(cards())
    if args.cmd == "doctor":
        return asyncio.run(doctor())
    if args.cmd == "jev":
        return asyncio.run(jev_report(args.case_id))
    return 1


if __name__ == "__main__":
    sys.exit(main())
