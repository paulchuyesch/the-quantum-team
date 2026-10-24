"""Limpieza reproducible del historial. No modifica la entrada ni simula demanda."""
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class CleaningConfig:
    department: str = "CUSCO"
    year_start: int = 2022
    year_end: int = 2026
    # Completar SOLO después de verificar documentalmente la unidad de COB_AFECTA.
    coverage_unit: str | None = None  # None, "ha" o "m2"

    def __post_init__(self):
        if self.year_start > self.year_end:
            raise ValueError("El inicio del rango debe ser menor o igual al final.")
        if self.coverage_unit not in (None, "ha", "m2"):
            raise ValueError("coverage_unit debe ser None, 'ha' o 'm2'.")


@dataclass
class CleaningResult:
    historical: pd.DataFrame
    excluded: pd.DataFrame
    duplicates: pd.DataFrame
    quality: pd.DataFrame
    manifest: dict
    summary: dict


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def text(value: object) -> str:
    return " ".join(unicodedata.normalize("NFC", str(value)).split())


def canonical(value: object) -> str:
    value = unicodedata.normalize("NFKD", text(value))
    return "".join(c for c in value if not unicodedata.combining(c)).upper()


def number(value: object) -> float | None:
    value = text(value)
    if not re.fullmatch(r"[+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+)", value):
        return None
    parsed = float(value.replace(",", "."))
    return parsed if math.isfinite(parsed) else None


def integer(value: object) -> int | None:
    parsed = number(value)
    return int(parsed) if parsed is not None and parsed.is_integer() else None


def iso_date(value: object) -> str:
    value = text(value)
    if not value:
        return ""
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    return ""


def _id_set(values) -> str:
    return ";".join(sorted({part.strip() for v in values for part in str(v).split(";") if part.strip()}))


def read_source(path: Path) -> pd.DataFrame:
    # Texto al ingresar: conserva IDs y ceros iniciales; NA como texto no se borra.
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    aliases = {"ANO": "ANIO", "YEAR": "ANIO"}
    names = [aliases.get(canonical(c), canonical(c)) for c in frame.columns]
    if len(names) != len(set(names)):
        raise ValueError("La normalización genera nombres de columna repetidos.")
    frame.columns = names
    required = {"OBJECTID_12", "NOMBDEP", "NOMBPROV", "NOMBDIST", "ANIO", "FEC_EMERGE",
                "INCENDIO", "LONGITUD_WGS84", "LATITUD_WGS84", "COB_AFECTA"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Faltan columnas requeridas: {missing}")
    return frame


def clean_source(path: str | Path, config: CleaningConfig | None = None) -> CleaningResult:
    path = Path(path).resolve()
    config = config or CleaningConfig()
    digest = sha256_file(path)
    frame = read_source(path)
    original_columns = frame.columns.tolist()
    frame = frame.apply(lambda column: column.map(text))
    frame["FILA_ENTRADA"] = range(2, len(frame) + 2)
    years = frame["ANIO"].map(integer)
    departments = frame["NOMBDEP"].map(canonical)
    in_scope = departments.eq(canonical(config.department)) & years.map(
        lambda y: y is not None and not pd.isna(y) and config.year_start <= y <= config.year_end
    )
    excluded = frame.loc[~in_scope].copy()
    excluded["MOTIVO_EXCLUSION"] = [
        ";".join(filter(None, [
            "departamento_fuera_de_ambito" if departments.loc[i] != canonical(config.department) else "",
            "anio_fuera_de_rango_o_invalido" if pd.isna(years.loc[i]) or not config.year_start <= years.loc[i] <= config.year_end else "",
        ])) for i in excluded.index
    ]

    # Los metadatos de una limpieza anterior no definen la identidad del evento.
    ignored = {"OBJECTID_12", "IDS_FUENTE", "OBSERVACIONES_CALIDAD", "FECHA_INICIO_ISO", "FECHA_TERMINO_ISO"}
    fingerprint_fields = sorted(set(original_columns) - ignored)
    groups: dict[str, dict] = {}
    duplicate_rows = []
    for _, series in frame.loc[in_scope].iterrows():
        row = series.to_dict()
        fingerprint = hashlib.sha256(json.dumps(
            {k: row[k] for k in fingerprint_fields}, ensure_ascii=False, sort_keys=True
        ).encode("utf-8")).hexdigest()
        source_ids = _id_set([row["OBJECTID_12"], row.get("IDS_FUENTE", "")])
        if fingerprint in groups:
            kept = groups[fingerprint]
            kept["_IDS"] = _id_set([kept["_IDS"], source_ids])
            kept["_FILAS"].append(row["FILA_ENTRADA"])
            duplicate_rows.append({
                "FILA_CONSERVADA": kept["FILA_ENTRADA"], "FILA_DUPLICADA": row["FILA_ENTRADA"],
                "ID_CONSERVADO": kept["OBJECTID_12"], "ID_DUPLICADO": row["OBJECTID_12"],
                "REGLA": "contenido_normalizado_identico_excepto_ids_y_metadatos_derivados",
            })
        else:
            row.update(_IDS=source_ids, _FILAS=[row["FILA_ENTRADA"]], _FP=fingerprint)
            groups[fingerprint] = row

    records = list(groups.values())
    id_counts = pd.Series([r["OBJECTID_12"] for r in records], dtype="str").value_counts().to_dict()
    output_rows = []
    for row in records:
        flags = []
        source_id = row["OBJECTID_12"]
        if not source_id:
            incident_id = "MINAM-SIN-ID-" + row["_FP"][:16]
            flags.append("sin_id_original")
        elif id_counts[source_id] > 1:
            incident_id = f"MINAM-{source_id}-{row['_FP'][:12]}"
            flags.append("id_original_con_contenidos_distintos")
        else:
            incident_id = "MINAM-" + source_id

        start = iso_date(row["FEC_EMERGE"])
        end_original = row.get("FEC_TERMIN", "")
        end = iso_date(end_original)
        year = integer(row["ANIO"])
        consistent_year = bool(start) and int(start[:4]) == year
        if not start:
            flags.append("fecha_inicio_invalida_o_ausente")
        elif not consistent_year:
            flags.append("anio_no_coincide_con_fecha")
        if end_original and not end:
            flags.append("fecha_termino_invalida")
        if end and start and end < start:
            flags.append("termino_anterior_al_inicio")

        lat, lon = number(row["LATITUD_WGS84"]), number(row["LONGITUD_WGS84"])
        # Validación amplia de plausibilidad. No reemplaza una frontera de Cusco.
        coordinates_ok = lat is not None and lon is not None and -18.6 <= lat <= 0.6 and -82.1 <= lon <= -68.0
        if not coordinates_ok:
            flags.append("coordenadas_invalidas_o_fuera_de_peru")
        confirmed = canonical(row["INCENDIO"]) == "SI"
        if not confirmed:
            flags.append("incendio_no_verificado")
        if not row.get("LOCALIDAD", ""):
            flags.append("sin_localidad")

        coverage = number(row["COB_AFECTA"])
        crops = number(row.get("CULTI_AFEC", ""))
        if coverage is None:
            flags.append("cobertura_ausente_o_no_numerica")
        elif coverage < 0:
            flags.append("cobertura_negativa")
        elif coverage == 0:
            flags.append("cobertura_reportada_cero_sin_magnitud_confirmada")
        elif config.coverage_unit is None:
            flags.append("unidad_cobertura_no_confirmada")
        area_ha = None
        if coverage is not None and coverage > 0 and config.coverage_unit is not None:
            area_ha = coverage if config.coverage_unit == "ha" else coverage / 10_000
        output_rows.append({
            "INCENDIO_ID": incident_id, "ID_MINAM_ORIGINAL": source_id, "IDS_FUENTE": row["_IDS"],
            "DEPARTAMENTO": canonical(row["NOMBDEP"]), "PROVINCIA": canonical(row["NOMBPROV"]),
            "DISTRITO": canonical(row["NOMBDIST"]), "LOCALIDAD": row.get("LOCALIDAD", ""),
            "FECHA_INICIO": start, "FECHA_TERMINO": end, "ANIO": year,
            "FEC_EMERGE_ORIGINAL": row["FEC_EMERGE"], "FEC_TERMIN_ORIGINAL": end_original,
            "LATITUD": lat, "LONGITUD": lon, "INCENDIO_CONFIRMADO": confirmed,
            "CONFIRMACION_ORIGINAL": row["INCENDIO"], "DESCRIPCION": row.get("DES_EMERGE", ""),
            "DANOS_REPORTADOS": row.get("DES_DANO", ""), "FUENTE": row.get("FTE_INF", ""),
            "ENTIDAD_REPORTANTE": row.get("DES_FUENTE", ""),
            "COB_AFECTA_ORIGINAL": row["COB_AFECTA"], "COB_AFECTA_VALOR": coverage,
            "CULTI_AFEC_ORIGINAL": row.get("CULTI_AFEC", ""), "CULTI_AFEC_VALOR": crops,
            "UNIDAD_COBERTURA": config.coverage_unit or "NO_CONFIRMADA", "AREA_HA": area_ha,
            "APTO_MAPEO": bool(coordinates_ok and confirmed and consistent_year),
            "OBSERVACIONES_CALIDAD": ";".join(flags),
            "OBSERVACIONES_PREVIAS": row.get("OBSERVACIONES_CALIDAD", ""),
            "ARCHIVO_FUENTE": path.name, "SHA256_FUENTE": digest,
            "FILAS_FUENTE": ";".join(map(str, sorted(row["_FILAS"]))),
        })

    if not output_rows:
        raise ValueError("No hay registros en el ámbito seleccionado; revise los filtros y la entrada.")
    historical = pd.DataFrame(output_rows).sort_values(
        ["FECHA_INICIO", "INCENDIO_ID"], ascending=[False, True], kind="stable"
    ).reset_index(drop=True)
    for column in ("LATITUD", "LONGITUD", "COB_AFECTA_VALOR", "CULTI_AFEC_VALOR", "AREA_HA"):
        historical[column] = pd.to_numeric(historical[column], errors="coerce").astype("Float64")
    historical["ANIO"] = historical["ANIO"].astype("Int64")
    assert historical["INCENDIO_ID"].is_unique
    assert len(historical) + len(duplicate_rows) + len(excluded) == len(frame)
    assert sha256_file(path) == digest, "La entrada no debe modificarse."

    quality_rows = []
    def quality(rule, affected, total, severity):
        quality_rows.append({"REGLA": rule, "N_AFECTADAS": int(affected), "DENOMINADOR": int(total),
                             "PORCENTAJE": round(100 * affected / total, 2) if total else 0.0,
                             "SEVERIDAD": severity})
    n = len(historical)
    quality("filas_fuera_de_ambito", len(excluded), len(frame), "INFO")
    quality("duplicados_exactos_retirados", len(duplicate_rows), int(in_scope.sum()), "INFO")
    for flag, severity in [
        ("sin_id_original", "WARN"), ("id_original_con_contenidos_distintos", "WARN"),
        ("fecha_inicio_invalida_o_ausente", "WARN"), ("anio_no_coincide_con_fecha", "WARN"),
        ("fecha_termino_invalida", "WARN"), ("termino_anterior_al_inicio", "WARN"),
        ("coordenadas_invalidas_o_fuera_de_peru", "WARN"), ("incendio_no_verificado", "WARN"),
        ("sin_localidad", "WARN"), ("cobertura_ausente_o_no_numerica", "WARN"),
        ("cobertura_negativa", "WARN"), ("cobertura_reportada_cero_sin_magnitud_confirmada", "WARN"),
        ("unidad_cobertura_no_confirmada", "WARN"),
    ]:
        quality(flag, sum(flag in value.split(";") for value in historical["OBSERVACIONES_CALIDAD"]), n, severity)
    quality("registros_no_aptos_para_mapeo", (~historical["APTO_MAPEO"]).sum(), n, "WARN")
    quality("sin_area_ha_verificada", historical["AREA_HA"].isna().sum(), n, "WARN")
    dates = historical.loc[historical["FECHA_INICIO"].ne(""), "FECHA_INICIO"]
    summary = {
        "filas_entrada": len(frame), "filas_en_ambito_antes_deduplicacion": int(in_scope.sum()),
        "registros_historicos": n, "duplicados_exactos_retirados": len(duplicate_rows),
        "filas_fuera_de_ambito": len(excluded), "aptos_para_mapeo": int(historical["APTO_MAPEO"].sum()),
        "no_aptos_para_mapeo": int((~historical["APTO_MAPEO"]).sum()),
        "fecha_minima": dates.min() if len(dates) else None, "fecha_maxima": dates.max() if len(dates) else None,
        "registros_por_anio": {str(int(k)): int(v) for k, v in historical.groupby("ANIO").size().items()},
        "provincias_representadas": int(historical["PROVINCIA"].nunique()),
        "cobertura_cero": int(historical["COB_AFECTA_VALOR"].eq(0).sum()),
        "cobertura_positiva_sin_confirmar_unidad": int((historical["COB_AFECTA_VALOR"].gt(0) & historical["UNIDAD_COBERTURA"].eq("NO_CONFIRMADA")).sum()),
        "area_ha_verificada": int(historical["AREA_HA"].notna().sum()),
    }
    manifest = {
        "archivo_fuente": path.name, "sha256": digest, "filas_fuente": len(frame),
        "formato": "CSV UTF-8 con BOM", "lectura": "texto, sin inferir faltantes NA",
        "ambito": {"departamento": config.department, "anio_inicio": config.year_start, "anio_fin": config.year_end},
        "unidad_COB_AFECTA_confirmada": config.coverage_unit,
        "fecha_descarga_original": None,
        "fecha_maxima_registro": summary["fecha_maxima"],
        "origen": "Archivo proporcionado por la usuaria, previamente filtrado y depurado; conservado sin modificar.",
        "servicio_fuente_documentado": "https://geoservidorperu.minam.gob.pe/arcgis/rest/services/CFOI_Dashboard_mensuales_pruebas/MapServer/0",
        "alcance_temporal": "La fecha máxima registrada no acredita cobertura completa del año ni actualización en vivo.",
        "coordenadas": "WGS84 suministradas; control amplio de Perú, sin certificación de pertenencia al polígono de Cusco.",
    }
    duplicates = pd.DataFrame(duplicate_rows, columns=["FILA_CONSERVADA", "FILA_DUPLICADA", "ID_CONSERVADO", "ID_DUPLICADO", "REGLA"])
    return CleaningResult(historical, excluded, duplicates, pd.DataFrame(quality_rows), manifest, summary)


def export_result(result: CleaningResult, root: str | Path) -> dict[str, Path]:
    root = Path(root)
    processed, reports = root / "data" / "processed", root / "outputs" / "reports"
    processed.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)
    historical = result.historical
    tables = {
        "incendios_historicos.csv": historical,
        "incendios_para_mapeo.csv": historical.loc[historical["APTO_MAPEO"]],
        "incendios_con_observaciones.csv": historical.loc[historical["OBSERVACIONES_CALIDAD"].ne("")],
        "registros_fuera_de_ambito.csv": result.excluded,
        "duplicados_retirados.csv": result.duplicates,
        "data_quality_report.csv": result.quality,
    }
    paths = {}
    for name, frame in tables.items():
        target = processed / name
        frame.to_csv(target, index=False, encoding="utf-8-sig", lineterminator="\n")
        paths[name] = target
    for name, payload in [("source_manifest.json", result.manifest), ("limpieza_resumen.json", result.summary)]:
        target = reports / name
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        paths[name] = target
    return paths
