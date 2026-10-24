"""Construir entradas de la fase 03 sobre la red incluida, sin consultas externas."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from qfire_cusco.geospatial import read_history, prepare_network, snap_points, build_costs
from qfire_cusco.logistics import (read_config, load_inputs, build_requests, build_donations,
    inventory_at, build_fleet, candidate_legs, export_phase3)


def main():
    config = read_config(ROOT)
    history = read_history(ROOT)
    points, centers, catalog, profiles = load_inputs(ROOT, history, config)
    requests = build_requests(profiles, catalog, config)
    donations = build_donations(requests, centers, catalog, config)
    inventory, ledger = inventory_at(donations, centers, catalog, config["reloj_escenario"])
    fleet = build_fleet(config)
    legs = candidate_legs(points, profiles, config)
    graph, manifest, mode = prepare_network(ROOT, points, config)
    points = snap_points(graph, points, config["max_snap_m"])
    costs = build_costs(graph, points)
    report, _, _ = export_phase3(ROOT, config, points, centers, catalog, profiles, requests, donations, inventory, ledger, fleet, legs, manifest, costs)
    print(json.dumps({"modo_red": mode, **report}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
