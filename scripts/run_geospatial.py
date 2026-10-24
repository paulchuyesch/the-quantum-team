"""Preparar el mapa y los costos viales del escenario de la fase 02."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from qfire_cusco.geospatial import (
    read_history, load_logistic_points, prepare_network, snap_points, build_costs, export_phase2,
)


def main():
    parser = argparse.ArgumentParser(description="Mapa y red vial de QFire Cusco.")
    parser.add_argument("--allow-download", action="store_true", help="Consultar Overpass si no existe cobertura vial local suficiente.")
    args = parser.parse_args()
    config = json.loads((ROOT / "config/phase2.json").read_text())
    history = read_history(ROOT)
    points = load_logistic_points(ROOT, history, config)
    graph, manifest, mode = prepare_network(ROOT, points, config, allow_download=args.allow_download)
    points = snap_points(graph, points, config["max_snap_m"])
    costs = build_costs(graph, points)
    _, summary, _ = export_phase2(ROOT, history, points, graph, manifest, costs)
    print(json.dumps({"modo_red": mode, **summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
