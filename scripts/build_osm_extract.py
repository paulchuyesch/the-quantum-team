"""Extraer vías del bbox del escenario desde un PBF de Perú ya descargado.

Uso: python scripts/build_osm_extract.py /ruta/peru-latest.osm.pbf
Dependencia opcional: pip install osmium
"""
from pathlib import Path
import argparse
import hashlib
import gzip
import json
import sys
import xml.etree.ElementTree as ET

import osmium
import pandas as pd
from shapely.geometry import LineString, box

ROOT = Path(__file__).resolve().parents[1]
DRIVE_HIGHWAYS = {
    "motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link",
    "secondary", "secondary_link", "tertiary", "tertiary_link", "unclassified",
    "residential", "living_street", "service", "road",
}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pbf", type=Path)
    parser.add_argument("--config", default="config/phase2.json")
    parser.add_argument("--output", default="data/raw/osm_vias_demo.osm")
    parser.add_argument("--metadata", default="data/raw/osm_extract_metadata.json")
    args = parser.parse_args()
    config = json.loads((ROOT / args.config).read_text())
    points = pd.read_csv(ROOT / config["puntos"])
    margin = config["margen_grados"]
    bbox = [float(points.LONGITUD.min() - margin), float(points.LATITUD.min() - margin),
            float(points.LONGITUD.max() + margin), float(points.LATITUD.max() + margin)]
    polygon = box(*bbox)

    class Roads(osmium.SimpleHandler):
        def __init__(self):
            super().__init__()
            self.nodes = {}
            self.ways = []

        def way(self, way):
            tags = dict(way.tags)
            if tags.get("highway") not in DRIVE_HIGHWAYS or tags.get("area") == "yes":
                return
            access = next((tags[k] for k in ["motorcar", "motor_vehicle", "vehicle", "access"] if tags.get(k)), "yes")
            if access in {"no", "private", "agricultural", "forestry"}:
                return
            if not all(n.location.valid() for n in way.nodes) or len(way.nodes) < 2:
                return
            coords = [(n.lon, n.lat) for n in way.nodes]
            if not LineString(coords).intersects(polygon):
                return
            refs = []
            for n in way.nodes:
                self.nodes[n.ref] = (n.lon, n.lat)
                refs.append(n.ref)
            self.ways.append((way.id, refs, tags))

    handler = Roads()
    handler.apply_file(str(args.pbf), locations=True, idx="flex_mem")
    if not handler.ways:
        raise RuntimeError("No se encontraron vías para el área configurada.")
    tree = ET.Element("osm", version="0.6", generator="QFire-Cusco bbox extract from Geofabrik")
    for node_id, (lon, lat) in sorted(handler.nodes.items()):
        ET.SubElement(tree, "node", id=str(node_id), lon=str(lon), lat=str(lat), version="1")
    for way_id, refs, tags in handler.ways:
        element = ET.SubElement(tree, "way", id=str(way_id), version="1")
        for ref in refs:
            ET.SubElement(element, "nd", ref=str(ref))
        for key, value in tags.items():
            ET.SubElement(element, "tag", k=key, v=value)
    target = ROOT / args.output
    payload = ET.tostring(tree, encoding="utf-8", xml_declaration=True)
    target.write_bytes(gzip.compress(payload, mtime=0) if target.name.endswith(".gz") else payload)
    source_meta = args.pbf.parent / "download_metadata.json"
    provenance = json.loads(source_meta.read_text()) if source_meta.exists() else {"url": "https://download.geofabrik.de/south-america/peru-latest.osm.pbf"}
    provenance.update({"bbox_lon_lat": bbox, "nodes": len(handler.nodes), "ways": len(handler.ways),
                       "xml_sha256": sha256(target), "pbf_sha256": sha256(args.pbf),
                       "subset": "Vías seleccionadas por highway y acceso, con geometría que intersecta el bbox. Se conservan sus nodos completos.",
                       "turn_restrictions": "Las relaciones de restricciones de giro no se incluyen en este prototipo.",
                       "attribution": "© OpenStreetMap contributors; extracto Geofabrik; ODbL 1.0"})
    provenance["compression"] = "gzip" if target.name.endswith(".gz") else "none"
    (ROOT / args.metadata).write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"nodes": len(handler.nodes), "ways": len(handler.ways), "xml_bytes": target.stat().st_size, "bbox": bbox}))


if __name__ == "__main__":
    main()
