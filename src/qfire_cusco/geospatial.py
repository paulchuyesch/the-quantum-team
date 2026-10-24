"""Historial geográfico, red vial versionada y costos de un escenario logístico.

No optimiza reparto, no infiere puntos seguros y no simula incendios activos.
"""
from __future__ import annotations

import hashlib
import html
import gzip
import json
import math
import re
import tempfile
import shutil
from pathlib import Path

import folium
from folium.plugins import MarkerCluster
import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd
from shapely.geometry import LineString, mapping

from .cleaning import sha256_file


def read_history(root: Path, year_start: int = 2020, year_end: int = 2026) -> pd.DataFrame:
    path = root / "data/processed/incendios_para_mapeo.csv"
    frame = pd.read_csv(path, dtype={"INCENDIO_ID": str}, keep_default_na=False, encoding="utf-8-sig")
    required = {"INCENDIO_ID", "DEPARTAMENTO", "PROVINCIA", "FECHA_INICIO", "ANIO", "LATITUD", "LONGITUD", "APTO_MAPEO"}
    if required - set(frame):
        raise ValueError(f"Faltan columnas: {sorted(required - set(frame))}")
    if not frame.INCENDIO_ID.is_unique or not frame.DEPARTAMENTO.eq("CUSCO").all():
        raise ValueError("La entrada debe contener IDs únicos y pertenecer al ámbito Cusco.")
    if year_start > year_end or not frame.ANIO.between(year_start, year_end).all():
        raise ValueError(f"La entrada contiene registros fuera de {year_start}–{year_end}.")
    if not frame.APTO_MAPEO.astype(str).str.lower().eq("true").all():
        raise ValueError("Use la salida incendios_para_mapeo.csv de la fase 01.")
    for column in ("LATITUD", "LONGITUD"):
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    if not frame.LATITUD.between(-18.6, 0.6).all() or not frame.LONGITUD.between(-82.1, -68).all():
        raise ValueError("Hay coordenadas no plausibles para Perú.")
    return frame


def load_logistic_points(root: Path, history: pd.DataFrame, config: dict) -> pd.DataFrame:
    points = pd.read_csv(root / config["puntos"], keep_default_na=False, encoding="utf-8-sig", dtype={"PUNTO_ID": str, "INCENDIO_ID": str})
    required = {"PUNTO_ID", "TIPO", "NOMBRE", "LATITUD", "LONGITUD", "INCENDIO_ID", "ESCENARIO_ID", "ORIGEN", "VALIDADO_OPERATIVAMENTE"}
    if required - set(points):
        raise ValueError(f"Faltan campos en puntos: {sorted(required - set(points))}")
    if not points.PUNTO_ID.is_unique or points.PUNTO_ID.eq("").any():
        raise ValueError("Cada punto logístico necesita un ID único no vacío.")
    if not points.TIPO.isin(["ACOPIO", "RECEPCION"]).all() or points.TIPO.eq("ACOPIO").sum() != 1:
        raise ValueError("Esta fase requiere un acopio y puntos de recepción.")
    if points.TIPO.eq("RECEPCION").sum() == 0:
        raise ValueError("Añada al menos un punto de recepción.")
    if not points.ESCENARIO_ID.eq(config["escenario_id"]).all():
        raise ValueError("Los puntos no pertenecen al escenario configurado.")
    incident_ids = set(history.INCENDIO_ID)
    receivers = points.loc[points.TIPO.eq("RECEPCION")]
    if not receivers.INCENDIO_ID.isin(incident_ids).all():
        raise ValueError("Cada receptor debe referenciar un registro utilizable del historial.")
    for column in ("LATITUD", "LONGITUD"):
        points[column] = pd.to_numeric(points[column], errors="raise")
    if not points.LATITUD.between(-18.6, 0.6).all() or not points.LONGITUD.between(-82.1, -68).all():
        raise ValueError("Coordenadas de puntos logísticos inválidas.")
    points["VALIDADO_OPERATIVAMENTE"] = points.VALIDADO_OPERATIVAMENTE.astype(str).str.lower().eq("true")
    return points


def bbox_for_points(points: pd.DataFrame, margin: float) -> tuple[float, float, float, float]:
    if margin <= 0:
        raise ValueError("El margen debe ser positivo para conservar conexiones alrededor de los destinos.")
    return (float(points.LONGITUD.min() - margin), float(points.LATITUD.min() - margin),
            float(points.LONGITUD.max() + margin), float(points.LATITUD.max() + margin))


def _contains(outer, inner) -> bool:
    return outer[0] <= inner[0] and outer[1] <= inner[1] and outer[2] >= inner[2] and outer[3] >= inner[3]


def parsed_speed(value) -> float | None:
    values = value if isinstance(value, list) else [value]
    valid = []
    for item in values:
        match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(mph|km/h|kph)?\s*", str(item), flags=re.I)
        if match:
            speed = float(match.group(1)) * (1.609344 if (match.group(2) or "").lower() == "mph" else 1)
            if speed > 0:
                valid.append(speed)
    return min(valid) if valid else None


def annotate_graph(graph: nx.MultiDiGraph, config: dict) -> nx.MultiDiGraph:
    policy = config["velocidades_supuesto_kph"]
    fallback = float(config["velocidad_fallback_kph"])
    if fallback <= 0 or any(float(v) <= 0 for v in policy.values()):
        raise ValueError("Las velocidades de estimación deben ser positivas.")
    for u, v, key, data in graph.edges(keys=True, data=True):
        length = float(data["length"])
        if not math.isfinite(length) or length < 0:
            raise ValueError("Arco sin longitud válida.")
        classes = data.get("highway", "road")
        classes = classes if isinstance(classes, list) else [classes]
        assumed = min(float(policy.get(c, fallback)) for c in classes)
        limit = parsed_speed(data.get("maxspeed", ""))
        speed = min(limit, assumed) if limit is not None else assumed
        data["speed_kph"] = speed
        data["speed_source"] = "ETIQUETA_OSM_CON_TOPE_SIMULADO" if limit is not None else "SUPUESTO_POR_CLASE"
        data["travel_time"] = length / (speed / 3.6)
        data["tramo_id"] = f"{u}_{v}_{key}"
        if "geometry" not in data:
            data["geometry"] = LineString([(graph.nodes[u]["x"], graph.nodes[u]["y"]), (graph.nodes[v]["x"], graph.nodes[v]["y"])])
    version = network_fingerprint(graph)
    graph.graph["red_version"] = version
    graph.graph["criterio_camino"] = "travel_time"
    return graph


def network_fingerprint(graph: nx.MultiDiGraph) -> str:
    digest = hashlib.sha256()
    for n, data in sorted(graph.nodes(data=True), key=lambda item: str(item[0])):
        digest.update(f"N:{n}:{float(data['x']):.10f}:{float(data['y']):.10f};".encode())
    for u, v, key, data in sorted(graph.edges(keys=True, data=True), key=lambda e: (str(e[0]), str(e[1]), str(e[2]))):
        geometry = data.get("geometry")
        value = [str(u), str(v), str(key), round(float(data["length"]), 6),
                 round(float(data["travel_time"]), 6), geometry.wkb_hex if geometry is not None else ""]
        digest.update(json.dumps(value, separators=(",", ":")).encode())
    return digest.hexdigest()[:20]


def prepare_network(root: Path, points: pd.DataFrame, config: dict, allow_download: bool = False):
    folder = root / config.get("storage_folder", "data/geo")
    folder.mkdir(parents=True, exist_ok=True)
    bbox = bbox_for_points(points, float(config["margen_grados"]))
    settings = {"bbox": bbox, "network_type": config["network_type"],
                "speeds": config["velocidades_supuesto_kph"], "fallback": config["velocidad_fallback_kph"]}
    query_key = hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()
    graph_path, manifest_path = folder / "red_vial_escenario.graphml.gz", folder / "network_manifest.json"
    xml_path = root / config.get("osm_xml", "data/raw/osm_vias_demo.osm")
    xml_metadata_path = root / config.get("osm_metadata", "data/raw/osm_extract_metadata.json")
    xml_meta = json.loads(xml_metadata_path.read_text()) if xml_metadata_path.exists() else None
    xml_hash = sha256_file(xml_path) if xml_path.exists() else None
    if graph_path.exists() and manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("query_key") == query_key and manifest.get("xml_sha256") == xml_hash:
            graph = ox.io.load_graphml(graph_path)
            if network_fingerprint(graph) != manifest["red_version"]:
                raise ValueError("La huella de la red guardada no coincide con su manifiesto.")
            return graph, manifest, "CACHE"
    if xml_meta is not None and xml_hash != xml_meta.get("xml_sha256"):
        raise ValueError("El extracto OSM cambió sin actualizar su procedencia.")
    if xml_path.exists() and xml_meta is not None and _contains(xml_meta["bbox_lon_lat"], bbox):
        if xml_path.name.endswith(".gz"):
            with tempfile.TemporaryDirectory() as directory:
                unpacked = Path(directory) / "roads.osm"
                with gzip.open(xml_path, "rb") as source, unpacked.open("wb") as target:
                    shutil.copyfileobj(source, target)
                graph = ox.graph.graph_from_xml(unpacked, simplify=True, retain_all=True)
        else:
            graph = ox.graph.graph_from_xml(xml_path, simplify=True, retain_all=True)
        source = "EXTRACTO_OSM_INCLUIDO"
        provenance = xml_meta
    else:
        if not allow_download:
            raise FileNotFoundError(
                "La configuración requiere otra cobertura vial. Genere un nuevo extracto con scripts/build_osm_extract.py "
                "o active ALLOW_DOWNLOAD para consultar Overpass. No se usarán carreteras incompletas silenciosamente."
            )
        ox.settings.use_cache = True
        ox.settings.cache_folder = str(root / "data/geo/osm_cache")
        ox.settings.requests_timeout = 90
        graph = ox.graph.graph_from_bbox(bbox, network_type=config["network_type"], simplify=True, retain_all=True, truncate_by_edge=True)
        source, provenance = "OSM_OVERPASS", {"url": ox.settings.overpass_url}
    graph = annotate_graph(graph, config)
    graph.graph["query_key"] = query_key
    graph.graph["source_kind"] = source
    graph.graph["bbox_lon_lat"] = json.dumps(bbox)
    ox.io.save_graphml(graph, graph_path)
    manifest = {"query_key": query_key, "red_version": graph.graph["red_version"], "source_kind": source,
                "xml_sha256": xml_hash, "bbox_lon_lat": list(bbox), "nodos": graph.number_of_nodes(),
                "arcos_dirigidos": graph.number_of_edges(), "componentes_debiles": nx.number_weakly_connected_components(graph),
                "scope": "Red del escenario logístico; el historial conserva todo Cusco.",
                "network_type": config["network_type"], "criterio_camino": "travel_time", "tiempos": "ESTIMADOS, sin tráfico en vivo",
                "supuestos_velocidades_kph": config["velocidades_supuesto_kph"], "fallback_kph": config["velocidad_fallback_kph"],
                "provenance": provenance, "attribution": "© OpenStreetMap contributors; ODbL 1.0",
                "limitations": ["No certifica transitabilidad ni aptitud de un vehículo concreto.",
                                "La red actual no reconstruye las carreteras de cada fecha histórica.",
                                "No se modelan restricciones de giro basadas en relaciones OSM en este prototipo."]}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return graph, manifest, source


def snap_points(graph: nx.MultiDiGraph, points: pd.DataFrame, max_distance_m: float) -> pd.DataFrame:
    projected = ox.projection.project_graph(graph)
    locations = gpd.GeoDataFrame(points.copy(), geometry=gpd.points_from_xy(points.LONGITUD, points.LATITUD), crs="EPSG:4326").to_crs(projected.graph["crs"])
    ids, distances = ox.distance.nearest_nodes(projected, X=locations.geometry.x.to_numpy(), Y=locations.geometry.y.to_numpy(), return_dist=True)
    result = points.copy()
    result["NODO_VIAL"] = [int(n) for n in ids]
    result["DISTANCIA_A_NODO_M"] = [float(d) for d in distances]
    result["SNAP_OK"] = result.DISTANCIA_A_NODO_M.le(max_distance_m)
    result["LATITUD_NODO"] = [float(graph.nodes[n]["y"]) for n in ids]
    result["LONGITUD_NODO"] = [float(graph.nodes[n]["x"]) for n in ids]
    result["RED_VERSION"] = graph.graph["red_version"]
    # Se mantienen las ubicaciones originales: no se simula el trayecto de acceso.
    result["ACCESO_ULTIMO_TRAMO_VALIDADO"] = False
    return result


def great_circle_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1, math.sqrt(a)))


def path_edges(graph, path):
    edges = []
    for u, v in zip(path, path[1:]):
        key = min(graph[u][v], key=lambda k: (float(graph[u][v][k]["travel_time"]), float(graph[u][v][k]["length"]), str(k)))
        edges.append((u, v, key, graph[u][v][key]))
    return edges


def route_coordinates(graph, edges):
    coords = []
    for u, v, key, data in edges:
        xy = list(data["geometry"].coords)
        origin = (graph.nodes[u]["x"], graph.nodes[u]["y"])
        squared = lambda p: (p[0] - origin[0]) ** 2 + (p[1] - origin[1]) ** 2
        if squared(xy[-1]) < squared(xy[0]):
            xy.reverse()
        if coords and coords[-1] == xy[0]:
            coords.extend(xy[1:])
        else:
            coords.extend(xy)
    return coords


def build_costs(graph: nx.MultiDiGraph, points: pd.DataFrame):
    if not points.SNAP_OK.all():
        raise ValueError("Hay puntos demasiado alejados del nodo vial. Revise la configuración antes de construir costos.")
    ids = points.PUNTO_ID.tolist()
    distances = pd.DataFrame(np.inf, index=ids, columns=ids)
    times = pd.DataFrame(np.inf, index=ids, columns=ids)
    reachable = pd.DataFrame(False, index=ids, columns=ids)
    pairs, features = [], []
    for _, origin in points.iterrows():
        _, paths = nx.single_source_dijkstra(graph, int(origin.NODO_VIAL), weight="travel_time")
        for _, destination in points.iterrows():
            a, b = origin.PUNTO_ID, destination.PUNTO_ID
            node = int(destination.NODO_VIAL)
            geodesic = great_circle_km(origin.LATITUD_NODO, origin.LONGITUD_NODO, destination.LATITUD_NODO, destination.LONGITUD_NODO)
            ok = node in paths
            if ok:
                edges = path_edges(graph, paths[node])
                km = sum(float(e[3]["length"]) for e in edges) / 1000
                minutes = sum(float(e[3]["travel_time"]) for e in edges) / 60
                distances.loc[a, b], times.loc[a, b], reachable.loc[a, b] = km, minutes, True
                if a != b:
                    coordinates = route_coordinates(graph, edges)
                    if len(coordinates) >= 2:
                        features.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": coordinates},
                                         "properties": {"ORIGEN": a, "DESTINO": b, "DISTANCIA_KM": km, "DURACION_MIN": minutes,
                                                        "RED_VERSION": graph.graph["red_version"], "TRAMO_IDS": [e[3]["tramo_id"] for e in edges]}})
            pairs.append({"ORIGEN": a, "DESTINO": b, "ALCANZABLE": ok, "DISTANCIA_KM": distances.loc[a, b],
                          "DURACION_MIN": times.loc[a, b], "GEODESICA_NODOS_KM": geodesic,
                          "CRITERIO_CAMINO": "travel_time", "RED_VERSION": graph.graph["red_version"]})
    for table in [distances, times, reachable]:
        table.index.name = "PUNTO_ID"
    return distances, times, reachable, pd.DataFrame(pairs), {"type": "FeatureCollection", "features": features}


def graph_geojson(graph):
    features = []
    for u, v, key, data in graph.edges(keys=True, data=True):
        highway = data.get("highway", "")
        name = data.get("name", "")
        features.append({"type": "Feature", "geometry": mapping(data["geometry"]), "properties": {
            "TRAMO_ID": data["tramo_id"], "U": str(u), "V": str(v), "KEY": str(key),
            "OSMID": str(data.get("osmid", "")), "NOMBRE": str(name), "HIGHWAY": str(highway),
            "LONGITUD_M": float(data["length"]), "TIEMPO_S": float(data["travel_time"]),
            "SPEED_KPH": float(data["speed_kph"]), "ORIGEN_VELOCIDAD": data["speed_source"],
            "RED_VERSION": graph.graph["red_version"]}})
    return {"type": "FeatureCollection", "features": features}


def create_map(history, points, edges_json, routes_json, bbox):
    location = [float(points.LATITUD.mean()), float(points.LONGITUD.mean())]
    m = folium.Map(location=location, zoom_start=10, tiles="OpenStreetMap", control_scale=True)
    palette = {2022: "#486f8c", 2023: "#448878", 2024: "#a4793b", 2025: "#855f95", 2026: "#ba5446"}
    for year, frame in history.groupby("ANIO"):
        layer = folium.FeatureGroup(name=f"Historial {year}: {len(frame)} registros", show=False)
        cluster = MarkerCluster(name=f"Registros {year}", control=False).add_to(layer)
        for row in frame.itertuples():
            text = f"{html.escape(row.INCENDIO_ID)}<br>{html.escape(row.PROVINCIA)} / {html.escape(row.DISTRITO)}<br>Fecha reportada: {html.escape(row.FECHA_INICIO)}<br>Registro histórico; no indica actividad actual."
            folium.CircleMarker([row.LATITUD, row.LONGITUD], radius=3, color=palette.get(int(year), "#6d7885"), fill=True, fill_opacity=0.65,
                                tooltip=f"Histórico {row.INCENDIO_ID}", popup=folium.Popup(text, max_width=320)).add_to(cluster)
        layer.add_to(m)
    main_roads = {"type": "FeatureCollection", "features": [f for f in edges_json["features"]
                  if any(c in f["properties"]["HIGHWAY"] for c in ["motorway", "trunk", "primary", "secondary", "tertiary"])]}
    folium.GeoJson(main_roads, name="Vías principales del escenario (OSM)", show=False,
                   style_function=lambda _: {"color": "#71818a", "weight": 1, "opacity": 0.6},
                   tooltip=folium.GeoJsonTooltip(fields=["TRAMO_ID", "HIGHWAY", "RED_VERSION"], aliases=["Tramo", "Clase", "Versión"])).add_to(m)
    source_id = points.loc[points.TIPO.eq("ACOPIO"), "PUNTO_ID"].iloc[0]
    colors = ["#2878a3", "#ad7430", "#6b5597"]
    receivers = points.loc[points.TIPO.eq("RECEPCION"), "PUNTO_ID"].tolist()
    route_layer = folium.FeatureGroup(name="Conexiones viales de referencia; no son plan de reparto", show=True)
    for feature in routes_json["features"]:
        p = feature["properties"]
        if p["ORIGEN"] != source_id:
            continue
        folium.GeoJson(feature, style_function=lambda _, color=colors[receivers.index(p["DESTINO"]) % len(colors)]: {"color": color, "weight": 4, "opacity": 0.85},
                       tooltip=f"{p['ORIGEN']} → {p['DESTINO']}: {p['DISTANCIA_KM']:.1f} km / {p['DURACION_MIN']:.0f} min estimados").add_to(route_layer)
    route_layer.add_to(m)
    point_layer = folium.FeatureGroup(name="Acopio y receptores simulados", show=True)
    for row in points.itertuples():
        popup = (f"<b>{html.escape(row.NOMBRE)}</b><br>ID: {html.escape(row.PUNTO_ID)}<br>Origen: {html.escape(row.ORIGEN)}"
                 f"<br>Validado operativamente: {row.VALIDADO_OPERATIVAMENTE}<br>Distancia al nodo: {row.DISTANCIA_A_NODO_M:.0f} m"
                 "<br>Ubicación de escenario, no punto seguro acreditado.")
        folium.Marker([row.LATITUD, row.LONGITUD], tooltip=row.NOMBRE, popup=folium.Popup(popup, max_width=340),
                      icon=folium.Icon(color="blue" if row.TIPO == "ACOPIO" else "orange", icon="home" if row.TIPO == "ACOPIO" else "flag")).add_to(point_layer)
        # Acceso aproximado visualmente diferenciado: no se cuenta como carretera.
        folium.PolyLine([[row.LATITUD, row.LONGITUD], [row.LATITUD_NODO, row.LONGITUD_NODO]], color="#555", dash_array="3 5", weight=1,
                        tooltip="Separación al nodo: acceso final sin validar").add_to(point_layer)
    point_layer.add_to(m)
    folium.Rectangle([[bbox[1], bbox[0]], [bbox[3], bbox[2]]], color="#596873", weight=1, fill=False,
                     tooltip="Área de extracción vial del escenario").add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    folium.LatLngPopup().add_to(m)
    m.fit_bounds([[bbox[1], bbox[0]], [bbox[3], bbox[2]]])
    legend = '<div style="position:fixed;bottom:25px;left:20px;z-index:9999;background:white;padding:10px;max-width:360px;border:1px solid #bbb;font-size:12px">'
    history_bounds = [[float(history.LATITUD.min()), float(history.LONGITUD.min())], [float(history.LATITUD.max()), float(history.LONGITUD.max())]]
    scenario_bounds = [[bbox[1], bbox[0]], [bbox[3], bbox[2]]]
    legend += '<b>QFire Cusco — Fase 02</b><br>Historial de todo Cusco: activar capas por año.<br>Acopio y receptores: simulados y editables.<br>Rutas por OSM; tiempos estimados, sin tráfico.<br>'
    legend += f'<button onclick=\'{m.get_name()}.fitBounds({json.dumps(history_bounds)})\'>Ver todo el historial</button> '
    legend += f'<button onclick=\'{m.get_name()}.fitBounds({json.dumps(scenario_bounds)})\'>Ver escenario</button>'
    legend += '<br>© OpenStreetMap contributors · ODbL 1.0</div>'
    m.get_root().html.add_child(folium.Element(legend))
    return m


def export_phase2(root: Path, history, points, graph, manifest, costs):
    geo, opt, reports, maps = root / "data/geo", root / "data/optimization", root / "outputs/reports", root / "outputs/maps"
    for folder in [geo, opt, reports, maps]:
        folder.mkdir(parents=True, exist_ok=True)
    distances, times, reachable, pairs, routes = costs
    edges = graph_geojson(graph)
    exports = {}
    tables = {
        geo / "puntos_logisticos.csv": points,
        geo / "snap_report.csv": points[["PUNTO_ID", "NODO_VIAL", "DISTANCIA_A_NODO_M", "SNAP_OK", "ACCESO_ULTIMO_TRAMO_VALIDADO", "RED_VERSION"]],
        geo / "resumen_provincia_anio.csv": history.groupby(["PROVINCIA", "ANIO"]).size().rename("REGISTROS").reset_index(),
        opt / "pares_viales.csv": pairs,
    }
    for path, table in tables.items():
        table.to_csv(path, index=False, encoding="utf-8-sig", lineterminator="\n")
        exports[path.name] = path
    for name, table in [("distance_matrix.csv", distances), ("duration_matrix.csv", times), ("reachability_matrix.csv", reachable)]:
        path = opt / name
        table.to_csv(path, encoding="utf-8-sig", lineterminator="\n")
        exports[name] = path
    for name, data in [("tramos_viales.geojson.gz", edges), ("rutas_pares.geojson", routes)]:
        path = geo / name
        payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if name.endswith(".gz"):
            path.write_bytes(gzip.compress(payload, mtime=0))
        else:
            path.write_bytes(payload)
        exports[name] = path
    incident_features = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [float(r.LONGITUD), float(r.LATITUD)]},
                          "properties": {"INCENDIO_ID": r.INCENDIO_ID, "PROVINCIA": r.PROVINCIA, "DISTRITO": r.DISTRITO,
                                         "FECHA_INICIO": r.FECHA_INICIO, "ANIO": int(r.ANIO), "ORIGEN": "HISTORICO_MINAM"}} for r in history.itertuples()]
    path = geo / "incendios_historicos.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": incident_features}, ensure_ascii=False, separators=(",", ":")))
    exports[path.name] = path
    map_object = create_map(history, points, edges, routes, manifest["bbox_lon_lat"])
    map_path = maps / "02_historial_y_logistica.html"
    map_object.save(map_path)
    exports[map_path.name] = map_path
    nonself = pairs.loc[pairs.ORIGEN.ne(pairs.DESTINO)]
    summary = {"registros_historicos_mapeables": len(history), "provincias_representadas": int(history.PROVINCIA.nunique()),
               "escenario_id": str(points.ESCENARIO_ID.iloc[0]), "puntos_logisticos_simulados": int(points.ORIGEN.eq("SIMULADO").sum()),
               "nodos_viales": graph.number_of_nodes(), "arcos_dirigidos": graph.number_of_edges(),
               "pares_dirigidos_no_diagonales": len(nonself), "pares_no_alcanzables": int((~nonself.ALCANZABLE).sum()),
               "puntos_fuera_de_umbral_snap": int((~points.SNAP_OK).sum()), "red_version": manifest["red_version"],
               "historial_sha256": sha256_file(root / "data/processed/incendios_para_mapeo.csv"),
               "points_config_sha256": sha256_file(root / "config/puntos_logisticos_demo.csv"),
               "interpretacion": "Matrices entre nodos viales asociados a puntos simulados. Accesos finales no validados. Sin reparto ni demanda todavía."}
    path = reports / "phase2_summary.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    exports[path.name] = path
    return exports, summary, map_object
