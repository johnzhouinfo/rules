#!/usr/bin/env python3
import json
import ipaddress
import sys
import urllib.request
from pathlib import Path
from typing import Iterable, List

RIPESTAT = "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS{}"

SECTION_ASNS = {
    "Freedom Mobile": [20365, 36273],
    "Bell Mobility (AS36522)": [36522],
    "Rogers Communications (Rogers/Fido) (AS812)": [812],
    "TELUS Mobility (AS14663)": [14663],
}

FILE_PATH = Path("surge/CAN-wifi-calling.list")


def fetch_prefixes(asn: int) -> List[str]:
    url = RIPESTAT.format(asn)
    with urllib.request.urlopen(url, timeout=30) as resp:
        data = json.load(resp)
    prefixes = [p.get("prefix") for p in data.get("data", {}).get("prefixes", [])]
    return [p for p in prefixes if p]


def dedupe_subnets(nets: Iterable[ipaddress._BaseNetwork]) -> List[ipaddress._BaseNetwork]:
    # Keep supernets, drop subnets fully covered by a kept network.
    nets_sorted = sorted(nets, key=lambda n: (n.version, n.prefixlen, int(n.network_address)))
    kept: List[ipaddress._BaseNetwork] = []
    for net in nets_sorted:
        covered = False
        for k in kept:
            if net.version == k.version and net.subnet_of(k):
                covered = True
                break
        if not covered:
            kept.append(net)
    # Stable, readable ordering
    return sorted(kept, key=lambda n: (n.version, int(n.network_address), n.prefixlen))


def build_lines(prefixes: Iterable[str]) -> List[str]:
    nets = [ipaddress.ip_network(p, strict=False) for p in prefixes]
    deduped = dedupe_subnets(nets)
    lines: List[str] = []
    for net in deduped:
        if net.version == 4:
            lines.append(f"IP-CIDR,{net},no-resolve")
        else:
            lines.append(f"IP-CIDR6,{net},no-resolve")
    return lines


def replace_section(lines: List[str], header: str, new_block: List[str]) -> List[str]:
    header_line = f"# {header}"
    try:
        start_idx = lines.index(header_line)
    except ValueError:
        raise SystemExit(f"Missing section header: {header_line}")

    end_idx = start_idx + 1
    while end_idx < len(lines) and not lines[end_idx].startswith("# "):
        end_idx += 1

    # Ensure a blank line separation before next header.
    block = new_block + [""]
    return lines[: start_idx + 1] + block + lines[end_idx:]


def main() -> None:
    if not FILE_PATH.exists():
        raise SystemExit(f"Missing file: {FILE_PATH}")

    lines = FILE_PATH.read_text(encoding="utf-8").splitlines()

    for header, asns in SECTION_ASNS.items():
        prefixes: List[str] = []
        for asn in asns:
            prefixes.extend(fetch_prefixes(asn))
        new_block = build_lines(prefixes)
        lines = replace_section(lines, header, new_block)

    FILE_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"update_can_ips.py failed: {exc}", file=sys.stderr)
        raise
