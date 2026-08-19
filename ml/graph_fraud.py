"""Fraud-ring detection over the device / IP sharing graph.

The tabular model deliberately never sees `device_id` or `ip_hash` (it would
memorise the specific strings from training rings). This module consumes them
instead, structurally: applications are nodes, and an edge connects two
applications that shared a device fingerprint or a source IP. Connected
components of size >= 2 are candidate rings.

For scoring, `ring_lookup.json` stores the device->applications and
ip->applications indexes plus each historical application's confirmed-fraud
flag, so the backend can rebuild ring context for a new application with two
dictionary lookups - no graph library needed at serving time.

Run standalone for the ring-signal report:

    python ml/graph_fraud.py
"""

from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
RING_LOOKUP_PATH = ARTIFACTS_DIR / "ring_lookup.json"


def build_graph(df: pd.DataFrame) -> nx.Graph:
    """Nodes are application_ids; edges link applications sharing a device or IP.

    Within each shared-identifier group, members are chained (a-b, b-c, ...)
    rather than fully connected - connected components are identical either
    way, and a 3,000-member pathological group stays 2,999 edges, not 4.5M.
    """
    graph = nx.Graph()
    graph.add_nodes_from(df["application_id"])

    for key in ("device_id", "ip_hash"):
        for _, group in df.groupby(key)["application_id"]:
            members = group.tolist()
            for a, b in zip(members, members[1:]):
                graph.add_edge(a, b, shared=key)
    return graph


def ring_components(graph: nx.Graph) -> list[set[str]]:
    """Connected components of size >= 2 (singletons are not rings)."""
    return [c for c in nx.connected_components(graph) if len(c) >= 2]


def analyse_rings(df: pd.DataFrame, graph: nx.Graph) -> dict:
    """Per-ring stats and the aggregate ring-membership signal report.

    Ground-truth labels are used here for EVALUATION of the signal only; at
    serving time ring_risk_score uses previously confirmed cases, which is
    what the stored fraud flags represent.
    """
    fraud_map = dict(zip(df["application_id"], df["is_fraud"].astype(bool)))
    components = ring_components(graph)

    rings = []
    for members in components:
        member_list = sorted(members)
        n_fraud = sum(fraud_map[m] for m in member_list)
        rings.append(
            {
                "size": len(member_list),
                "n_fraud": int(n_fraud),
                "fraud_fraction": n_fraud / len(member_list),
                "members": member_list,
            }
        )

    in_big_rings = [m for r in rings if r["size"] >= 3 for m in r["members"]]
    big_ring_fraud = sum(fraud_map[m] for m in in_big_rings)
    baseline = float(df["is_fraud"].mean())

    return {
        "n_rings": len(rings),
        "n_rings_3plus": sum(1 for r in rings if r["size"] >= 3),
        "largest_ring": max((r["size"] for r in rings), default=0),
        "apps_in_rings_3plus": len(in_big_rings),
        "fraud_rate_in_rings_3plus": big_ring_fraud / len(in_big_rings) if in_big_rings else 0.0,
        "baseline_fraud_rate": baseline,
        "rings": rings,
    }


def get_ring_context(application_id: str, graph: nx.Graph, fraud_map: dict[str, bool]) -> dict:
    """Ring context for one application: who it connects to, and how bad they look.

    ring_risk_score is the fraction of OTHER ring members already confirmed as
    fraud - the application's own label (if any) never counts toward its own
    risk.
    """
    if application_id not in graph:
        return {"ring_size": 1, "ring_risk_score": 0.0, "connected_applications": []}

    members = nx.node_connected_component(graph, application_id)
    others = sorted(m for m in members if m != application_id)
    if not others:
        return {"ring_size": 1, "ring_risk_score": 0.0, "connected_applications": []}

    n_fraud_others = sum(bool(fraud_map.get(m, False)) for m in others)
    return {
        "ring_size": len(members),
        "ring_risk_score": n_fraud_others / len(others),
        "connected_applications": others,
    }


def save_ring_lookup(df: pd.DataFrame, path: Path = RING_LOOKUP_PATH) -> None:
    """Persist the indexes needed to rebuild ring context at scoring time."""
    device_index: dict[str, list[str]] = {}
    ip_index: dict[str, list[str]] = {}
    for _, row in df[["application_id", "device_id", "ip_hash"]].iterrows():
        device_index.setdefault(row["device_id"], []).append(row["application_id"])
        ip_index.setdefault(row["ip_hash"], []).append(row["application_id"])

    lookup = {
        "device_index": device_index,
        "ip_index": ip_index,
        "application_fraud_flags": {
            app_id: bool(flag)
            for app_id, flag in zip(df["application_id"], df["is_fraud"].astype(bool))
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(lookup), encoding="utf-8")


def format_ring_report(analysis: dict) -> str:
    lift = analysis["fraud_rate_in_rings_3plus"] / max(analysis["baseline_fraud_rate"], 1e-9)
    return "\n".join(
        [
            f"rings (components >= 2):        {analysis['n_rings']:,}",
            f"rings of size >= 3:             {analysis['n_rings_3plus']:,}",
            f"largest ring:                   {analysis['largest_ring']}",
            f"applications in rings >= 3:     {analysis['apps_in_rings_3plus']:,}",
            f"fraud rate inside rings >= 3:   {analysis['fraud_rate_in_rings_3plus']:.1%}",
            f"baseline fraud rate:            {analysis['baseline_fraud_rate']:.1%}",
            f"lift from ring membership:      {lift:.1f}x",
        ]
    )


if __name__ == "__main__":
    df = pd.read_csv(PROJECT_ROOT / "data" / "applications_train.csv")
    graph = build_graph(df)
    analysis = analyse_rings(df, graph)
    print(format_ring_report(analysis))
    save_ring_lookup(df)
    print(f"\nring lookup saved to {RING_LOOKUP_PATH.relative_to(PROJECT_ROOT)}")

    # Smoke-test the serving-time context call on a member of the largest ring.
    biggest = max(analysis["rings"], key=lambda r: r["size"])
    fraud_map = dict(zip(df["application_id"], df["is_fraud"].astype(bool)))
    ctx = get_ring_context(biggest["members"][0], graph, fraud_map)
    print(
        f"sample context: app in ring of {ctx['ring_size']}, "
        f"ring_risk_score={ctx['ring_risk_score']:.2f}"
    )
