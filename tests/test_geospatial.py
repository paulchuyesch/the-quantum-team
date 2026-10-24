import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

import networkx as nx
import osmnx as ox
import pandas as pd
from shapely.geometry import LineString

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from qfire_cusco.geospatial import (
    annotate_graph, bbox_for_points, build_costs, graph_geojson, load_logistic_points,
    network_fingerprint, parsed_speed, prepare_network, route_coordinates, read_history,
)

CONFIG = {"velocidades_supuesto_kph": {"primary": 50, "residential": 20}, "velocidad_fallback_kph": 15}


def graph():
    g = nx.MultiDiGraph(crs="EPSG:4326")
    g.add_node(1, x=-72.0, y=-13.5)
    g.add_node(2, x=-71.999, y=-13.499)
    g.add_node(3, x=-71.998, y=-13.5)
    g.add_edge(1, 2, key=0, length=160.0, highway="primary", maxspeed="30",
               geometry=LineString([(-72, -13.5), (-72, -13.4995), (-71.999, -13.499)]))
    g.add_edge(2, 3, key=0, length=160.0, highway="primary")
    return annotate_graph(g, CONFIG)


def points():
    return pd.DataFrame([
        {"PUNTO_ID": "A", "NODO_VIAL": 1, "SNAP_OK": True, "LATITUD_NODO": -13.5, "LONGITUD_NODO": -72.0},
        {"PUNTO_ID": "B", "NODO_VIAL": 3, "SNAP_OK": True, "LATITUD_NODO": -13.5, "LONGITUD_NODO": -71.998},
    ])


class GeospatialTests(unittest.TestCase):
    def test_one_way_and_unreachable_pairs_are_preserved(self):
        distance, duration, reachable, pairs, routes = build_costs(graph(), points())
        self.assertTrue(reachable.loc["A", "B"])
        self.assertFalse(reachable.loc["B", "A"])
        self.assertTrue(math.isinf(distance.loc["B", "A"]))
        self.assertTrue(math.isinf(duration.loc["B", "A"]))
        self.assertEqual(len(routes["features"]), 1)

    def test_parallel_edges_use_the_same_fastest_path_for_time_and_distance(self):
        g = graph()
        g.add_edge(1, 3, key=0, length=500, highway="residential")
        g.add_edge(1, 3, key=1, length=400, highway="primary")
        g = annotate_graph(g, CONFIG)
        distance, duration, reachable, pairs, routes = build_costs(g, points())
        # El camino de 320 m tarda 30,72 s; el arco de 400 m tarda 28,8 s.
        self.assertAlmostEqual(distance.loc["A", "B"], 0.4)
        self.assertAlmostEqual(duration.loc["A", "B"], 0.48)
        self.assertEqual(routes["features"][0]["properties"]["TRAMO_IDS"], ["1_3_1"])

    def test_removing_a_real_arc_changes_connectivity_and_version(self):
        g = graph()
        old = network_fingerprint(g)
        g.remove_edge(2, 3, 0)
        self.assertNotEqual(network_fingerprint(g), old)
        distance, duration, reachable, pairs, routes = build_costs(g, points())
        self.assertFalse(reachable.loc["A", "B"])
        self.assertTrue(math.isinf(distance.loc["A", "B"]))

    def test_geometry_keeps_road_bends_and_correct_direction(self):
        g = graph()
        geometry = g[1][2][0]["geometry"]
        g[1][2][0]["geometry"] = LineString(list(geometry.coords)[::-1])
        coords = route_coordinates(g, [(1, 2, 0, g[1][2][0])])
        self.assertEqual(coords[0], (-72, -13.5))
        self.assertEqual(len(coords), 3)

    def test_speed_units_and_assumptions_are_explicit(self):
        self.assertAlmostEqual(parsed_speed("20 mph"), 32.18688)
        self.assertEqual(parsed_speed(["50", "30"]), 30)
        self.assertIsNone(parsed_speed("signals"))
        g = graph()
        self.assertEqual(g[1][2][0]["speed_kph"], 30)
        self.assertEqual(g[2][3][0]["speed_source"], "SUPUESTO_POR_CLASE")

    def test_invalid_snapping_blocks_cost_creation(self):
        p = points()
        p.loc[0, "SNAP_OK"] = False
        with self.assertRaises(ValueError):
            build_costs(graph(), p)

    def test_graphml_gzip_roundtrip_preserves_network_fingerprint(self):
        g = graph()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "red.graphml.gz"
            ox.io.save_graphml(g, path)
            loaded = ox.io.load_graphml(path)
            self.assertEqual(network_fingerprint(g), network_fingerprint(loaded))

    def test_geojson_exposes_directed_edge_ids_and_version(self):
        g = graph()
        features = graph_geojson(g)["features"]
        self.assertEqual({f["properties"]["TRAMO_ID"] for f in features}, {"1_2_0", "2_3_0"})
        self.assertTrue(all(f["properties"]["RED_VERSION"] == g.graph["red_version"] for f in features))

    def test_supplied_history_keeps_all_thirteen_provinces(self):
        history = read_history(ROOT)
        self.assertEqual(len(history), 3363)
        self.assertEqual(history.PROVINCIA.nunique(), 13)

    def test_history_accepts_2020_when_supplied_without_inventing_missing_years(self):
        original = read_history(ROOT)
        self.assertNotIn(2020, set(original.ANIO))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / 'data/processed'
            folder.mkdir(parents=True)
            row = original.iloc[[0]].copy()
            row['ANIO'] = 2020
            row['FECHA_INICIO'] = '2020-01-01'
            row.to_csv(folder / 'incendios_para_mapeo.csv', index=False)
            self.assertEqual(read_history(root).ANIO.tolist(), [2020])

    def test_demo_points_are_explicitly_simulated_not_incident_locations(self):
        config = json.loads((ROOT / "config/phase2.json").read_text())
        history = read_history(ROOT)
        p = load_logistic_points(ROOT, history, config)
        self.assertTrue(p.ORIGEN.eq("SIMULADO").all())
        self.assertFalse(p.VALIDADO_OPERATIVAMENTE.any())
        joined = p.loc[p.TIPO.eq("RECEPCION")].merge(history, on="INCENDIO_ID", suffixes=("_punto", "_incendio"))
        self.assertTrue(((joined.LATITUD_punto != joined.LATITUD_incendio) | (joined.LONGITUD_punto != joined.LONGITUD_incendio)).all())

    def test_bbox_uses_longitude_latitude_order_and_margin(self):
        p = pd.DataFrame({"LONGITUD": [-72.1, -71.9], "LATITUD": [-13.5, -13.3]})
        west, south, east, north = bbox_for_points(p, 0.1)
        self.assertAlmostEqual(west, -72.2)
        self.assertAlmostEqual(north, -13.2)

    def test_out_of_coverage_configuration_does_not_silently_reuse_the_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = {"margen_grados": 0.1, "network_type": "drive", **CONFIG}
            with self.assertRaises(FileNotFoundError):
                prepare_network(root, pd.DataFrame({"LONGITUD": [-72], "LATITUD": [-13.5]}), config, allow_download=False)


if __name__ == "__main__":
    unittest.main()
