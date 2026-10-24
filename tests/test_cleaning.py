"""Casos de calidad que cambian qué datos podrán usar las fases siguientes."""
import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from qfire_cusco.cleaning import CleaningConfig, clean_source, export_result, sha256_file


def observation(**changes):
    row = {"OBJECTID_12": "0007", "IDS_FUENTE": "0007", "NOMBDEP": "CUSCO",
           "NOMBPROV": "CALCA", "NOMBDIST": "PISAC", "LOCALIDAD": "SECTOR A",
           "ANIO": "2026", "FEC_EMERGE": "05/08/2026", "FEC_TERMIN": "",
           "INCENDIO": "SI", "LONGITUD_WGS84": "-71.85", "LATITUD_WGS84": "-13.42",
           "COB_AFECTA": "0.0", "CULTI_AFEC": "0.0", "DES_EMERGE": "INCENDIO FORESTAL"}
    row.update(changes)
    return row


class CleaningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def clean(self, rows, config=None):
        path = self.root / "input.csv"
        fields = sorted({key for row in rows for key in row})
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        before = sha256_file(path)
        result = clean_source(path, config)
        self.assertEqual(sha256_file(path), before)
        return result

    def test_exact_duplicates_merge_source_ids_without_losing_lineage(self):
        result = self.clean([observation(), observation(OBJECTID_12="0008", IDS_FUENTE="0008")])
        self.assertEqual(len(result.historical), 1)
        self.assertEqual(result.historical.iloc[0]["IDS_FUENTE"], "0007;0008")
        self.assertEqual(result.historical.iloc[0]["FILAS_FUENTE"], "2;3")
        self.assertEqual(len(result.duplicates), 1)

    def test_conflicting_source_id_keeps_both_observations_with_unique_ids(self):
        result = self.clean([observation(), observation(LOCALIDAD="OTRO SECTOR")])
        self.assertEqual(len(result.historical), 2)
        self.assertTrue(result.historical["INCENDIO_ID"].is_unique)
        self.assertTrue(result.historical["OBSERVACIONES_CALIDAD"].str.contains("id_original_con_contenidos_distintos").all())

    def test_zero_coverage_is_preserved_and_is_not_a_verified_area(self):
        row = self.clean([observation()]).historical.iloc[0]
        self.assertEqual(row["COB_AFECTA_ORIGINAL"], "0.0")
        self.assertEqual(row["COB_AFECTA_VALOR"], 0)
        self.assertTrue(__import__("pandas").isna(row["AREA_HA"]))

    def test_positive_coverage_needs_an_explicit_verified_unit(self):
        row = self.clean([observation(COB_AFECTA="10000")]).historical.iloc[0]
        self.assertTrue(__import__("pandas").isna(row["AREA_HA"]))
        verified = self.clean([observation(COB_AFECTA="10000")], CleaningConfig(coverage_unit="m2"))
        self.assertEqual(verified.historical.iloc[0]["AREA_HA"], 1)

    def test_coordinates_and_confirmation_control_map_eligibility(self):
        rows = [observation(), observation(OBJECTID_12="2", LATITUD_WGS84="0", LONGITUD_WGS84="0"),
                observation(OBJECTID_12="3", INCENDIO="NO VERIFICADO")]
        result = self.clean(rows)
        self.assertEqual(len(result.historical), 3)
        self.assertEqual(int(result.historical["APTO_MAPEO"].sum()), 1)

    def test_year_date_conflict_is_kept_for_review_and_excluded_from_mapping(self):
        row = self.clean([observation(FEC_EMERGE="05/08/2025")]).historical.iloc[0]
        self.assertFalse(row["APTO_MAPEO"])
        self.assertIn("anio_no_coincide_con_fecha", row["OBSERVACIONES_CALIDAD"])
        self.assertEqual(row["ANIO"], 2026)

    def test_invalid_end_date_does_not_turn_into_a_fake_closure_date(self):
        row = self.clean([observation(FEC_TERMIN="1")]).historical.iloc[0]
        self.assertEqual(row["FEC_TERMIN_ORIGINAL"], "1")
        self.assertEqual(row["FECHA_TERMINO"], "")
        self.assertIn("fecha_termino_invalida", row["OBSERVACIONES_CALIDAD"])

    def test_scope_is_department_plus_inclusive_year_range(self):
        result = self.clean([observation(ANIO="2022", FEC_EMERGE="01/01/2022"),
                             observation(OBJECTID_12="2", ANIO="2021"),
                             observation(OBJECTID_12="3", NOMBDEP="PUNO")])
        self.assertEqual(len(result.historical), 1)
        self.assertEqual(len(result.excluded), 2)

    def test_source_ids_keep_leading_zeros(self):
        row = self.clean([observation()]).historical.iloc[0]
        self.assertEqual(row["ID_MINAM_ORIGINAL"], "0007")
        self.assertEqual(row["INCENDIO_ID"], "MINAM-0007")

    def test_fallback_ids_are_stable_when_row_order_changes(self):
        rows = [observation(OBJECTID_12="", IDS_FUENTE=""), observation(OBJECTID_12="9", LOCALIDAD="B")]
        first = self.clean(rows).historical.set_index("LOCALIDAD")["INCENDIO_ID"].to_dict()
        second = self.clean(list(reversed(rows))).historical.set_index("LOCALIDAD")["INCENDIO_ID"].to_dict()
        self.assertEqual(first, second)

    def test_exports_are_reproducible_and_reports_reconcile(self):
        result = self.clean([observation()])
        paths = export_result(result, self.root)
        before = {key: sha256_file(path) for key, path in paths.items()}
        again = export_result(result, self.root)
        self.assertEqual(before, {key: sha256_file(path) for key, path in again.items()})
        self.assertEqual(result.summary["filas_entrada"], result.summary["registros_historicos"] + result.summary["duplicados_exactos_retirados"] + result.summary["filas_fuera_de_ambito"])

    def test_supplied_dataset_and_raw_file_are_preserved(self):
        path = ROOT / "data/raw/incendios_Cusco_2022_2026.csv"
        result = clean_source(path)
        self.assertEqual(result.summary["registros_historicos"], 3365)
        self.assertEqual(result.summary["registros_por_anio"]["2026"], 93)
        self.assertEqual(result.summary["fecha_maxima"], "2026-08-26")


if __name__ == "__main__":
    unittest.main()
