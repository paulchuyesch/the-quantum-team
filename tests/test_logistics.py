import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from qfire_cusco.geospatial import read_history
from qfire_cusco.logistics import (read_config, load_inputs, demand_quantities, build_requests,
    build_donations, inventory_at, transfer_inventory, build_fleet, candidate_legs,
    resource_balance, validate_centers)


class LogisticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = read_config(ROOT)
        cls.history = read_history(ROOT)
        cls.points, cls.centers, cls.catalog, cls.profiles = load_inputs(ROOT, cls.history, cls.config)
        cls.requests = build_requests(cls.profiles, cls.catalog, cls.config)
        cls.donations = build_donations(cls.requests, cls.centers, cls.catalog, cls.config)

    def stock(self):
        return inventory_at(self.donations, self.centers, self.catalog, self.config["reloj_escenario"])

    def test_all_requests_and_vehicle_origins_use_coer(self):
        self.assertTrue(self.requests.CENTRO_COORDINADOR_ID.eq("COER_CUSCO").all())
        fleet = build_fleet(self.config)
        self.assertTrue(fleet.ORIGEN_RUTA_ID.eq("COER_CUSCO").all())
        self.assertTrue(fleet.POSICION_ACTUAL_ID.eq("COER_CUSCO").all())

    def test_original_reporting_entity_is_preserved(self):
        expected = self.history.set_index("INCENDIO_ID").ENTIDAD_REPORTANTE
        for row in self.profiles.itertuples():
            self.assertEqual(row.ENTIDAD_REPORTANTE, expected[row.INCENDIO_ID])
        self.assertIn("", set(self.profiles.ENTIDAD_REPORTANTE))

    def test_water_scales_with_staff_and_is_present_for_every_receiver(self):
        p = self.profiles.iloc[0].copy()
        before = demand_quantities(p, self.config["coeficientes_demanda"])["AGUA"]
        p.PERSONAL_DESPLEGADO *= 2
        self.assertEqual(demand_quantities(p, self.config["coeficientes_demanda"])["AGUA"], before * 2)
        self.assertTrue((self.requests.loc[self.requests.RECURSO_ID.eq("AGUA"), "CANTIDAD_PENDIENTE"] > 0).all())

    def test_veterinary_packages_follow_fauna_not_size(self):
        p = self.profiles.iloc[0].copy()
        p.FAUNA_REQUIERE_ATENCION = 0
        self.assertEqual(demand_quantities(p, self.config["coeficientes_demanda"])["PAQUETE_VETERINARIO"], 0)
        p.FAUNA_REQUIERE_ATENCION = 30
        self.assertEqual(demand_quantities(p, self.config["coeficientes_demanda"])["PAQUETE_VETERINARIO"], 8)

    def test_manual_work_increases_tools_without_changing_fauna(self):
        p = self.profiles.iloc[1].copy()
        before = demand_quantities(p, self.config["coeficientes_demanda"])
        p.FRACCION_TRABAJO_MANUAL = 1
        after = demand_quantities(p, self.config["coeficientes_demanda"])
        self.assertGreater(after["PALA"], before["PALA"])
        self.assertEqual(after["PAQUETE_VETERINARIO"], before["PAQUETE_VETERINARIO"])

    def test_pending_future_quarantine_and_expired_donations_not_counted(self):
        stock, ledger = self.stock()
        self.assertFalse(ledger.DOCUMENTO_ORIGEN_ID.str.contains("PROMETIDA|FUTURA|CUARENTENA|VENCIDA").any())
        eligible = self.donations.loc[self.donations.DONACION_ID.isin(ledger.DOCUMENTO_ORIGEN_ID)]
        pd.testing.assert_series_equal(stock.groupby("RECURSO_ID").CANTIDAD_DISPONIBLE.sum(), eligible.groupby("RECURSO_ID").CANTIDAD.sum(), check_names=False)

    def test_local_stock_stays_at_local_center(self):
        stock, ledger = self.stock()
        local = stock.loc[stock.CENTRO_ID.eq("HUB_PARURO"), "CANTIDAD_DISPONIBLE"].sum()
        self.assertGreater(local, 0)
        central = stock.loc[stock.CENTRO_ID.eq("COER_CUSCO"), "CANTIDAD_DISPONIBLE"].sum()
        central_ledger = ledger.loc[ledger.DESTINO_ID.eq("COER_CUSCO"), "CANTIDAD"].sum()
        self.assertEqual(central, central_ledger)

    def test_duplicate_donation_fails(self):
        duplicated = pd.concat([self.donations, self.donations.iloc[[0]]], ignore_index=True)
        with self.assertRaises(ValueError):
            inventory_at(duplicated, self.centers, self.catalog, self.config["reloj_escenario"])

    def test_atomic_transfer_conserves_stock_and_does_not_mutate_input(self):
        stock, ledger = self.stock()
        original = stock.copy(deep=True)
        moved, updated = transfer_inventory(stock, ledger, "TR-1", "COER_CUSCO", "HUB_PARURO", "AGUA", 10)
        pd.testing.assert_frame_equal(stock, original)
        pd.testing.assert_series_equal(moved.groupby("RECURSO_ID").CANTIDAD_DISPONIBLE.sum(), stock.groupby("RECURSO_ID").CANTIDAD_DISPONIBLE.sum())
        self.assertEqual(len(updated), len(ledger) + 1)

    def test_transfer_cannot_overspend_or_reuse_movement_id(self):
        stock, ledger = self.stock()
        with self.assertRaises(ValueError):
            transfer_inventory(stock, ledger, "TR-X", "COER_CUSCO", "HUB_PARURO", "AGUA", 100000)
        moved, ledger = transfer_inventory(stock, ledger, "TR-1", "COER_CUSCO", "HUB_PARURO", "AGUA", 1)
        with self.assertRaises(ValueError):
            transfer_inventory(moved, ledger, "TR-1", "COER_CUSCO", "HUB_PARURO", "AGUA", 1)

    def test_reserved_stock_cannot_be_transferred(self):
        stock, ledger = self.stock()
        mask = stock.CENTRO_ID.eq("COER_CUSCO") & stock.RECURSO_ID.eq("AGUA")
        stock.loc[mask, "CANTIDAD_RESERVADA"] = stock.loc[mask, "CANTIDAD_DISPONIBLE"]
        with self.assertRaises(ValueError):
            transfer_inventory(stock, ledger, "TR-1", "COER_CUSCO", "HUB_PARURO", "AGUA", 1)

    def test_request_weight_and_volume_use_resource_unit(self):
        water = self.requests.loc[self.requests.RECURSO_ID.eq("AGUA")].iloc[0]
        self.assertAlmostEqual(water.PESO_PENDIENTE_KG, water.CANTIDAD_PENDIENTE * .65)
        self.assertAlmostEqual(water.VOLUMEN_PENDIENTE_M3, water.CANTIDAD_PENDIENTE * .0008)
        self.assertTrue(self.requests.CANTIDAD_PENDIENTE.mod(1).eq(0).all())

    def test_hub_routes_support_direct_delivery_transfer_and_redistribution(self):
        legs = candidate_legs(self.points, self.profiles, self.config)
        pairs = set(zip(legs.ORIGEN_ID, legs.DESTINO_ID))
        self.assertTrue({("COER_CUSCO", "HUB_PARURO"), ("HUB_PARURO", "RE04"), ("HUB_PARURO", "RE05"), ("COER_CUSCO", "RE04"), ("HUB_PARURO", "COER_CUSCO")} <= pairs)
        self.assertFalse(legs.ES_ASIGNACION.any())

    def test_center_cycles_are_rejected(self):
        broken = self.centers.copy()
        broken.loc[broken.CENTRO_ID.eq("HUB_PARURO"), "CENTRO_PADRE_ID"] = "HUB_PARURO"
        with self.assertRaises(ValueError):
            validate_centers(broken, self.points, "COER_CUSCO")

    def test_balance_compares_each_resource_without_mixing_units(self):
        stock, _ = self.stock()
        balance = resource_balance(self.requests, stock, self.catalog)
        self.assertEqual(len(balance), len(self.catalog))
        self.assertTrue((balance.BRECHA_AGREGADA_UNIDADES > 0).any())
        self.assertTrue(balance.COBERTURA_AGREGADA.between(0, 1).all())

    def test_scenario_does_not_claim_operational_or_current_incident_validation(self):
        self.assertFalse(self.points.VALIDADO_OPERATIVAMENTE.any())
        self.assertFalse(self.profiles.INCENDIO_ACTIVO_CONFIRMADO.any())
        self.assertTrue(self.profiles.ORIGEN.eq("SIMULADO").all())
        self.assertNotIn("AREA_HA", self.profiles.columns)


if __name__ == "__main__":
    unittest.main()
