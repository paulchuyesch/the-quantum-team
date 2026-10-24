"""Entradas reproducibles de logística multirrecurso y centros de transferencia.

Fase 03: construye un escenario, no decide asignaciones ni ejecuta despachos.
Los perfiles, pedidos, donaciones, vehículos y sitios operativos son simulados.
"""
from __future__ import annotations

import gzip
import html
import json
import math
from pathlib import Path

import folium
import numpy as np
import pandas as pd

from .cleaning import sha256_file


def read_config(root: Path):
    return json.loads((root / "config/phase3.json").read_text())


def read_table(root, relative):
    return pd.read_csv(root / relative, keep_default_na=False, encoding="utf-8-sig")


def validate_centers(centers, points, root_id):
    if not centers.CENTRO_ID.is_unique or root_id not in set(centers.CENTRO_ID):
        raise ValueError("Centros duplicados o falta el COER central.")
    if set(centers.CENTRO_ID) != set(points.loc[points.TIPO.isin(["CENTRAL", "HUB"]), "PUNTO_ID"]):
        raise ValueError("Los centros necesitan una ubicación logística correspondiente.")
    parents = centers.set_index("CENTRO_ID").CENTRO_PADRE_ID.to_dict()
    if parents[root_id] != "" or not centers.CENTRO_COORDINADOR_ID.eq(root_id).all():
        raise ValueError("Todos los centros deben coordinarse desde el COER central.")
    for center in parents:
        seen, node = set(), center
        while node != root_id:
            if node in seen or node not in parents or not parents[node]:
                raise ValueError("Jerarquía cíclica o sin conexión con el COER.")
            seen.add(node)
            node = parents[node]


def load_inputs(root: Path, history, config):
    points = read_table(root, config["puntos"])
    centers = read_table(root, config["centros"])
    catalog = read_table(root, config["catalogo"])
    profiles = read_table(root, config["perfiles"])
    central = config["origen_central"]
    if not points.PUNTO_ID.is_unique or points.PUNTO_ID.eq("").any():
        raise ValueError("Puntos con identificadores inválidos.")
    if not points.TIPO.isin(["CENTRAL", "HUB", "RECEPCION"]).all():
        raise ValueError("Tipo de punto desconocido.")
    if points.TIPO.eq("CENTRAL").sum() != 1 or points.loc[points.TIPO.eq("CENTRAL"), "PUNTO_ID"].iloc[0] != central:
        raise ValueError("El único origen central debe ser COER_CUSCO.")
    if not points.ESCENARIO_ID.eq(config["escenario_id"]).all():
        raise ValueError("Mezcla de escenarios.")
    if not points.LATITUD.between(-18.6, .6).all() or not points.LONGITUD.between(-82.1, -68).all():
        raise ValueError("Coordenadas fuera de Perú.")
    points["VALIDADO_OPERATIVAMENTE"] = points.VALIDADO_OPERATIVAMENTE.astype(str).str.lower().eq("true")
    receivers = points.loc[points.TIPO.eq("RECEPCION")]
    if not receivers.INCENDIO_ID.isin(history.INCENDIO_ID).all():
        raise ValueError("Receptor sin referencia histórica válida.")
    if not profiles.PUNTO_ID.is_unique or set(profiles.PUNTO_ID) != set(receivers.PUNTO_ID):
        raise ValueError("Cada receptor necesita exactamente un perfil.")
    validate_centers(centers, points, central)
    if not profiles.CENTRO_PREFERENTE_ID.isin(centers.CENTRO_ID).all():
        raise ValueError("Centro preferente inexistente.")
    if not catalog.RECURSO_ID.is_unique or (catalog[["PESO_KG_UNIDAD", "VOLUMEN_M3_UNIDAD", "FACTOR_PRIORIDAD"]] <= 0).any().any():
        raise ValueError("Catálogo duplicado o unidades de carga inválidas.")
    if (profiles[["PERSONAL_DESPLEGADO", "FAUNA_REQUIERE_ATENCION", "MAGNITUD_RELATIVA"]] < 0).any().any():
        raise ValueError("Cantidades de perfil negativas.")
    for col in ["PERSONAL_DESPLEGADO", "FAUNA_REQUIERE_ATENCION"]:
        if not profiles[col].mod(1).eq(0).all():
            raise ValueError("Los recuentos de personal y fauna deben ser enteros.")
    if not profiles.FRACCION_TRABAJO_MANUAL.between(0, 1).all() or not profiles.URGENCIA_RELATIVA.between(0, 1).all() or (profiles.FACTOR_HUMO < 0).any():
        raise ValueError("Factores del perfil fuera de dominio.")
    profiles = profiles.merge(receivers[["PUNTO_ID", "INCENDIO_ID"]], on="PUNTO_ID", validate="one_to_one")
    # ENTIDAD_REPORTANTE es un dato original, nunca se sustituye por el centro coordinador.
    profiles = profiles.merge(history[["INCENDIO_ID", "PROVINCIA", "DISTRITO", "FECHA_INICIO", "ENTIDAD_REPORTANTE"]], on="INCENDIO_ID", validate="many_to_one")
    profiles["CENTRO_COORDINADOR_ID"] = central
    profiles["INCENDIO_ACTIVO_CONFIRMADO"] = False
    profiles["PERIODO_HORAS_SIMULADO"] = config["horizonte_horas"]
    weights = config["prioridad_pesos"]
    if set(weights) != {"magnitud", "personal", "fauna", "urgencia"} or any(v < 0 for v in weights.values()) or not math.isclose(sum(weights.values()), 1):
        raise ValueError("Pesos de prioridad inválidos: deben sumar uno.")
    score = np.zeros(len(profiles))
    for factor, column in [("magnitud", "MAGNITUD_RELATIVA"), ("personal", "PERSONAL_DESPLEGADO"), ("fauna", "FAUNA_REQUIERE_ATENCION"), ("urgencia", "URGENCIA_RELATIVA")]:
        maximum = profiles[column].max()
        score += weights[factor] * (profiles[column] / maximum if maximum > 0 else 0)
    profiles["PRIORIDAD_BASE"] = np.round(score * 100, 4)
    return points, centers, catalog, profiles


def demand_quantities(profile, coefficients):
    """Coeficientes demostrativos por horizonte; no son normas de consumo o atención."""
    c = coefficients
    if any(not math.isfinite(float(v)) or v <= 0 for v in c.values()):
        raise ValueError("Coeficientes de demanda deben ser finitos y positivos.")
    staff, fauna = float(profile["PERSONAL_DESPLEGADO"]), float(profile["FAUNA_REQUIERE_ATENCION"])
    manual = staff * float(profile["FRACCION_TRABAJO_MANUAL"])
    return {"AGUA": math.ceil(staff * c["agua_por_persona"]),
            "MASCARILLA": math.ceil(staff * c["mascarillas_por_persona"] * float(profile["FACTOR_HUMO"])),
            "PALA": math.ceil(manual / c["personas_manual_por_pala"]),
            "HACHA": math.ceil(manual / c["personas_manual_por_hacha"]),
            "PAQUETE_VETERINARIO": math.ceil(fauna / c["fauna_por_paquete"]),
            "BOTIQUIN_BRIGADA": math.ceil(staff / c["personas_por_botiquin"])}


def build_requests(profiles, catalog, config):
    rows = []
    clock = pd.Timestamp(config["reloj_escenario"])
    horizon = float(config["horizonte_horas"])
    if clock.tz is None or horizon <= 0:
        raise ValueError("Use un reloj con zona horaria y horizonte positivo.")
    resources = catalog.set_index("RECURSO_ID")
    for profile in profiles.to_dict("records"):
        for resource, qty in demand_quantities(profile, config["coeficientes_demanda"]).items():
            if resource not in resources.index:
                raise ValueError(f"Falta el recurso {resource} en el catálogo.")
            item = resources.loc[resource]
            # La ventana es un supuesto logístico de la demo; no establece plazos clínicos.
            deadline_h = min(horizon, 4 + 8 * (1 - profile["URGENCIA_RELATIVA"]))
            rows.append({"SOLICITUD_ID": f"SOL-{profile['PUNTO_ID']}-{resource}",
                         "ESCENARIO_ID": config["escenario_id"], "INCENDIO_ID": profile["INCENDIO_ID"],
                         "PUNTO_ID": profile["PUNTO_ID"], "CENTRO_COORDINADOR_ID": config["origen_central"],
                         "CENTRO_PREFERENTE_ID": profile["CENTRO_PREFERENTE_ID"],
                         "RECURSO_ID": resource, "UNIDAD": item.UNIDAD, "CANTIDAD_SOLICITADA": qty,
                         "CANTIDAD_ENTREGADA": 0, "CANTIDAD_PENDIENTE": qty,
                         "PESO_PENDIENTE_KG": round(qty * item.PESO_KG_UNIDAD, 6),
                         "VOLUMEN_PENDIENTE_M3": round(qty * item.VOLUMEN_M3_UNIDAD, 6),
                         "PRIORIDAD_BASE": profile["PRIORIDAD_BASE"],
                         "PRIORIDAD_RECURSO": round(profile["PRIORIDAD_BASE"] * item.FACTOR_PRIORIDAD, 4),
                         "SOLICITADO_EN": clock.isoformat(), "PLAZO_LOGISTICO_SIMULADO": (clock + pd.Timedelta(hours=deadline_h)).isoformat(),
                         "REQUIERE_SOLICITUD_AUTORIZADA": item.REQUIERE_SOLICITUD_AUTORIZADA,
                         "SOLICITUD_AUTORIZADA_SIMULADA": True,
                         "ORIGEN": "SIMULADO_NO_PEDIDO_REAL"})
    return pd.DataFrame(rows)


def build_donations(requests, centers, catalog, config):
    """Donaciones ficticias por ubicación: recibido no equivale a prometido."""
    clock = pd.Timestamp(config["reloj_escenario"])
    rows = []
    central = config["origen_central"]
    for center in centers.CENTRO_ID:
        demand = requests if center == central else requests.loc[requests.CENTRO_PREFERENTE_ID.eq(center)]
        for i, resource in enumerate(catalog.RECURSO_ID):
            total = demand.loc[demand.RECURSO_ID.eq(resource), "CANTIDAD_PENDIENTE"].sum()
            fraction = [.62, .7, .45, .5, .4, .6][i % 6] if center == central else .35
            for status, qty, received, released, expiry in [
                ("RECIBIDA", math.ceil(total * fraction), clock - pd.Timedelta(hours=2), True, clock + pd.Timedelta(days=30)),
                ("PROMETIDA", max(5, int(total)), None, False, None),
            ]:
                rows.append({"DONACION_ID": f"DON-{center}-{resource}-{status}", "CENTRO_ID": center,
                             "RECURSO_ID": resource, "CANTIDAD": qty, "ESTADO": status,
                             "RECIBIDA_EN": received.isoformat() if received is not None else "",
                             "LIBERADA_PARA_ENTREGA": released, "VENCE_EN": expiry.isoformat() if expiry is not None else "",
                             "ORIGEN": "SIMULADO", "ESCENARIO_ID": config["escenario_id"]})
    # Casos negativos para auditar: un registro recibido después del reloj y uno en cuarentena.
    for suffix, status, received, released, expiry in [
        ("FUTURA", "RECIBIDA", clock + pd.Timedelta(hours=2), True, clock + pd.Timedelta(days=10)),
        ("CUARENTENA", "RECIBIDA", clock - pd.Timedelta(hours=1), False, clock + pd.Timedelta(days=10)),
        ("VENCIDA", "RECIBIDA", clock - pd.Timedelta(days=3), True, clock - pd.Timedelta(days=1)),
    ]:
        rows.append({"DONACION_ID": f"DON-AGUA-{suffix}", "CENTRO_ID": central, "RECURSO_ID": "AGUA", "CANTIDAD": 999,
                     "ESTADO": status, "RECIBIDA_EN": received.isoformat(), "LIBERADA_PARA_ENTREGA": released,
                     "VENCE_EN": expiry.isoformat(), "ORIGEN": "SIMULADO", "ESCENARIO_ID": config["escenario_id"]})
    return pd.DataFrame(rows)


def inventory_at(donations, centers, catalog, clock):
    if not donations.DONACION_ID.is_unique:
        raise ValueError("Donación duplicada: riesgo de doble conteo.")
    if not donations.CENTRO_ID.isin(centers.CENTRO_ID).all() or not donations.RECURSO_ID.isin(catalog.RECURSO_ID).all():
        raise ValueError("Donación con ubicación o recurso desconocido.")
    if (donations.CANTIDAD < 0).any() or not donations.CANTIDAD.mod(1).eq(0).all():
        raise ValueError("Cantidades de donación deben ser enteras y no negativas.")
    now = pd.Timestamp(clock)
    received = pd.to_datetime(donations.RECIBIDA_EN.replace("", None), utc=True, errors="raise")
    expiry = pd.to_datetime(donations.VENCE_EN.replace("", None), utc=True, errors="raise")
    released = donations.LIBERADA_PARA_ENTREGA.astype(str).str.lower().eq("true")
    eligible = donations.ESTADO.eq("RECIBIDA") & released & received.le(now) & (expiry.isna() | expiry.gt(now))
    ledger = donations.loc[eligible, ["DONACION_ID", "CENTRO_ID", "RECURSO_ID", "CANTIDAD", "RECIBIDA_EN"]].copy()
    ledger = ledger.rename(columns={"DONACION_ID": "DOCUMENTO_ORIGEN_ID", "CENTRO_ID": "DESTINO_ID", "RECIBIDA_EN": "FECHA"})
    ledger["MOVIMIENTO_ID"] = "ING-" + ledger.DOCUMENTO_ORIGEN_ID
    ledger["ORIGEN_ID"] = "EXTERNO"
    ledger["TIPO"] = "INGRESO_DONACION"
    index = pd.MultiIndex.from_product([centers.CENTRO_ID, catalog.RECURSO_ID], names=["CENTRO_ID", "RECURSO_ID"])
    totals = ledger.groupby(["DESTINO_ID", "RECURSO_ID"]).CANTIDAD.sum()
    totals.index.names = index.names
    inventory = totals.reindex(index, fill_value=0).rename("CANTIDAD_DISPONIBLE").reset_index()
    inventory["CANTIDAD_RESERVADA"] = 0
    inventory["ORIGEN"] = "SIMULADO"
    return inventory, ledger


def transfer_inventory(inventory, ledger, movement_id, origin, destination, resource, qty):
    """Movimiento atómico de prueba: conserva unidades. No despacha vehículos."""
    if movement_id in set(ledger.MOVIMIENTO_ID):
        raise ValueError("ID de movimiento repetido.")
    if origin == destination or not isinstance(qty, int) or qty <= 0:
        raise ValueError("Transferencia inválida.")
    stock = inventory.copy()
    a = stock.CENTRO_ID.eq(origin) & stock.RECURSO_ID.eq(resource)
    b = stock.CENTRO_ID.eq(destination) & stock.RECURSO_ID.eq(resource)
    if a.sum() != 1 or b.sum() != 1:
        raise ValueError("Centro o recurso desconocido.")
    if stock.loc[a, "CANTIDAD_DISPONIBLE"].iloc[0] - stock.loc[a, "CANTIDAD_RESERVADA"].iloc[0] < qty:
        raise ValueError("Inventario libre insuficiente.")
    stock.loc[a, "CANTIDAD_DISPONIBLE"] -= qty
    stock.loc[b, "CANTIDAD_DISPONIBLE"] += qty
    movement = {"MOVIMIENTO_ID": movement_id, "ORIGEN_ID": origin, "DESTINO_ID": destination,
                "RECURSO_ID": resource, "CANTIDAD": qty, "TIPO": "TRANSFERENCIA_PRUEBA_NO_DESPACHO",
                "DOCUMENTO_ORIGEN_ID": "PRUEBA_CONSERVACION", "FECHA": ""}
    return stock, pd.concat([ledger, pd.DataFrame([movement])], ignore_index=True)


def build_fleet(config):
    rows = []
    for i, kg, volume in [(1, 650, 3.0), (2, 900, 4.5), (3, 1200, 6.0)]:
        rows.append({"VEHICULO_ID": f"VEH-{i:02}", "ORIGEN_RUTA_ID": config["origen_central"],
                     "POSICION_ACTUAL_ID": config["origen_central"], "RETORNO_ID": config["origen_central"],
                     "CAPACIDAD_KG": kg, "CAPACIDAD_M3": volume, "CARGA_INICIAL_KG": 0,
                     "CARGA_INICIAL_M3": 0, "DISPONIBLE_DESDE": config["reloj_escenario"],
                     "DISPONIBLE_HASTA": (pd.Timestamp(config["reloj_escenario"]) + pd.Timedelta(hours=config["horizonte_horas"])).isoformat(),
                     "SERVICIO_MIN_POR_PARADA": 15, "ORIGEN": "SIMULADO", "COMPATIBILIDAD_VIAL_VALIDADA": False})
    return pd.DataFrame(rows)


def candidate_legs(points, profiles, config):
    central = config["origen_central"]
    rows = []
    for p in points.loc[points.TIPO.eq("RECEPCION"), "PUNTO_ID"]:
        rows.append((central, p, "ENTREGA_DIRECTA_CANDIDATA"))
    for hub in points.loc[points.TIPO.eq("HUB"), "PUNTO_ID"]:
        rows.extend([(central, hub, "TRANSFERENCIA_CANDIDATA"), (hub, central, "RECOGIDA_DONACIONES_CANDIDATA")])
        rows.extend((hub, p, "REDISTRIBUCION_CANDIDATA") for p in profiles.loc[profiles.CENTRO_PREFERENTE_ID.eq(hub), "PUNTO_ID"])
    frame = pd.DataFrame(rows, columns=["ORIGEN_ID", "DESTINO_ID", "USO"])
    frame["CENTRO_COORDINADOR_ID"] = central
    frame["ES_ASIGNACION"] = False
    return frame


def resource_balance(requests, inventory, catalog):
    demand = requests.groupby("RECURSO_ID").CANTIDAD_PENDIENTE.sum()
    stock = inventory.groupby("RECURSO_ID").CANTIDAD_DISPONIBLE.sum()
    frame = catalog[["RECURSO_ID", "UNIDAD"]].copy().set_index("RECURSO_ID")
    frame["DEMANDA_UNIDADES"] = demand
    frame["STOCK_TOTAL_UBICADO"] = stock
    frame["BRECHA_AGREGADA_UNIDADES"] = (demand - stock).clip(lower=0)
    frame["EXCEDENTE_AGREGADO_UNIDADES"] = (stock - demand).clip(lower=0)
    frame["COBERTURA_AGREGADA"] = np.where(demand > 0, np.minimum(stock / demand.replace(0, np.nan), 1), 1)
    frame["INTERPRETACION"] = "DIAGNOSTICO_NO_ASIGNACION_STOCK_EN_CENTROS_DISTINTOS"
    return frame.reset_index()


def create_logistics_map(points, legs, routes, profiles):
    m = folium.Map(location=[float(points.LATITUD.mean()), float(points.LONGITUD.mean())], tiles="OpenStreetMap", zoom_start=9, control_scale=True)
    allowed = set(zip(legs.ORIGEN_ID, legs.DESTINO_ID))
    features = [f for f in routes["features"] if (f["properties"]["ORIGEN"], f["properties"]["DESTINO"]) in allowed]
    folium.GeoJson({"type": "FeatureCollection", "features": features}, name="Trayectos candidatos OSM; sin reparto decidido",
                   style_function=lambda f: {"color": "#167c80" if f["properties"]["ORIGEN"] == "HUB_PARURO" else "#6986b8", "weight": 3, "opacity": .65},
                   tooltip=folium.GeoJsonTooltip(fields=["ORIGEN", "DESTINO", "DISTANCIA_KM", "DURACION_MIN"], aliases=["Desde", "Hasta", "km estimados", "min estimados"])).add_to(m)
    palette = {"CENTRAL": "blue", "HUB": "purple", "RECEPCION": "orange"}
    for p in points.itertuples():
        text = f"<b>{html.escape(p.NOMBRE)}</b><br>{html.escape(p.PUNTO_ID)} · {p.TIPO}<br>Escenario simulado. Ubicación operativa sin validar.<br>{html.escape(p.FUENTE_COORDENADA)}<br>Separación al nodo: {p.DISTANCIA_A_NODO_M:.0f} m"
        if p.TIPO == "RECEPCION":
            profile = profiles.set_index("PUNTO_ID").loc[p.PUNTO_ID]
            text += f"<br>Personal simulado: {profile.PERSONAL_DESPLEGADO}<br>Fauna simulada: {profile.FAUNA_REQUIERE_ATENCION}<br>Referencia histórica: {html.escape(p.INCENDIO_ID)}"
        folium.Marker([p.LATITUD, p.LONGITUD], tooltip=p.NOMBRE, popup=folium.Popup(text, max_width=360), icon=folium.Icon(color=palette[p.TIPO], icon="home" if p.TIPO != "RECEPCION" else "flag")).add_to(m)
        folium.PolyLine([[p.LATITUD, p.LONGITUD], [p.LATITUD_NODO, p.LONGITUD_NODO]], color="#555", weight=1, dash_array="3 5", tooltip="Acceso al nodo sin validar").add_to(m)
    m.fit_bounds([[float(points.LATITUD.min()), float(points.LONGITUD.min())], [float(points.LATITUD.max()), float(points.LONGITUD.max())]])
    folium.LayerControl().add_to(m)
    m.get_root().html.add_child(folium.Element('<div style="position:fixed;bottom:25px;left:20px;z-index:9999;background:white;padding:12px;border:1px solid #bbb;max-width:380px"><b>Fase 03 · Logística desde COER Cusco</b><br>Central y centros locales propuestos; sitios sin validar.<br>Demandas y stock simulados. Líneas: trayectos candidatos.<br>No indica incendios activos ni despachos programados.<br>© OpenStreetMap contributors · ODbL 1.0</div>'))
    return m


def export_phase3(root, config, points, centers, catalog, profiles, requests, donations, inventory, ledger, fleet, legs, manifest, costs):
    simulated, opt = root / "data/simulated/phase3", root / "data/optimization/phase3"
    for folder in [simulated, opt, root / "outputs/maps", root / "outputs/reports"]:
        folder.mkdir(parents=True, exist_ok=True)
    distances, times, reachable, pairs, routes = costs
    # Los arcos lógicos conservan su estado de conectividad: nunca se reemplaza infinito por cero.
    legs = legs.merge(pairs[["ORIGEN", "DESTINO", "ALCANZABLE", "DISTANCIA_KM", "DURACION_MIN", "RED_VERSION"]], left_on=["ORIGEN_ID", "DESTINO_ID"], right_on=["ORIGEN", "DESTINO"], validate="one_to_one").drop(columns=["ORIGEN", "DESTINO"])
    tables = {"puntos_logisticos": points, "centros": centers, "catalogo_recursos": catalog, "perfiles_incidentes": profiles,
              "solicitudes": requests, "donaciones": donations, "inventario_por_centro": inventory,
              "movimientos_inventario": ledger, "flota": fleet, "arcos_logisticos_candidatos": legs,
              "brecha_por_recurso": resource_balance(requests, inventory, catalog)}
    for name, table in tables.items():
        table.to_csv(simulated / f"{name}.csv", index=False, encoding="utf-8-sig", lineterminator="\n")
    for name, table in [("distance_matrix", distances), ("duration_matrix", times), ("reachability_matrix", reachable)]:
        table.to_csv(opt / f"{name}.csv", encoding="utf-8-sig", lineterminator="\n")
    pairs.to_csv(opt / "pares_viales.csv", index=False, encoding="utf-8-sig", lineterminator="\n")
    (root / "data/geo/phase3/rutas_pares.geojson.gz").write_bytes(gzip.compress(json.dumps(routes, ensure_ascii=False, separators=(",", ":")).encode(), mtime=0))
    map_object = create_logistics_map(points, legs, routes, profiles)
    map_object.save(root / "outputs/maps/03_centros_y_recursos.html")
    report = {"escenario_id": config["escenario_id"], "reloj_simulado": config["reloj_escenario"], "horizonte_horas": config["horizonte_horas"],
              "centro_coordinador": config["origen_central"], "centros": len(centers), "receptores": len(profiles), "recursos": len(catalog),
              "lineas_solicitud": len(requests), "vehiculos": len(fleet), "nodos_viales": manifest["nodos"], "arcos_viales": manifest["arcos_dirigidos"],
              "red_version": manifest["red_version"], "arcos_logisticos_candidatos": len(legs),
              "arcos_candidatos_inalcanzables": int((~legs.ALCANZABLE).sum()), "max_snap_m": float(points.DISTANCIA_A_NODO_M.max()),
              "entidad_reportante_historica_preservada": True, "operaciones_despachadas": 0,
              "stock_unidades_por_recurso": inventory.groupby("RECURSO_ID").CANTIDAD_DISPONIBLE.sum().to_dict(),
              "demanda_unidades_por_recurso": requests.groupby("RECURSO_ID").CANTIDAD_PENDIENTE.sum().to_dict(),
              "supuestos": ["Operación, prioridades, cantidades, plazos, flota y puntos son simulados.", "COER_CUSCO es origen y coordinador por requisito del escenario, no por inferencia histórica.", "No se suman recursos de unidades distintas ni se asignan por proximidad euclídea.", "Los centros mantienen inventario separado; las transferencias no crean recursos.", "Las recepciones y la sede exacta del COER requieren validación operativa.", "No se afirma actividad actual ni se calcula pronóstico de expansión del fuego."],
              "inputs_sha256": {rel: sha256_file(root / rel) for rel in ["config/phase3.json", config["puntos"], config["centros"], config["catalogo"], config["perfiles"], "data/processed/incendios_para_mapeo.csv"]}}
    (root / "outputs/reports/phase3_summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report, map_object, legs
