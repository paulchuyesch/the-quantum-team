"""Regresiones de selección, demanda y conservación del plan clásico."""
import copy
import itertools
import json
from pathlib import Path
import sys
import tempfile
import unittest
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from qfire_cusco.scenario import (load_inputs,create_scenario,provinces_from_history,
    normalize_selection,usable_stock)
from qfire_cusco.optimization_classical import solve_classical,validate_plan,export_plan


class ClassicalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.data=load_inputs(ROOT)

    def scenario(self,selected,overrides=None,data=None,**kwargs):
        return create_scenario(data or self.data,selected,overrides,**kwargs)

    def test_dynamic_provinces_and_no_duplicates(self):
        names=provinces_from_history(self.data.history)
        self.assertEqual(len(names),13);self.assertEqual(names,sorted(set(names)))
        small=pd.DataFrame({'PROVINCIA':[' calca ','Cálca',None,'Urubamba']})
        self.assertEqual(provinces_from_history(small),['CALCA','URUBAMBA'])

    def test_all_8192_subsets_accepted_by_selector_contract(self):
        names=provinces_from_history(self.data.history)
        for size in range(14):
            for subset in itertools.combinations(names,size):
                self.assertEqual(normalize_selection(self.data.history,subset),list(subset))

    def test_normalized_selection_deduplicates(self):
        s=self.scenario([' calca ','Cálca','URUBAMBA'])
        self.assertEqual(s.selected,['CALCA','URUBAMBA'])
        self.assertTrue(s.requests.SOLICITUD_ID.is_unique)

    def test_unknown_province_rejected(self):
        with self.assertRaises(ValueError): self.scenario(['ACCHA'])

    def test_only_urubamba_and_required_subsets(self):
        cases=[['URUBAMBA'],['CANAS','ESPINAR'],['CALCA','ANTA','CHUMBIVILCAS'],
            ['CANAS','ESPINAR','LA CONVENCION','PAUCARTAMBO']]
        for selected in cases:
            s=self.scenario(selected);plan=solve_classical(s)
            self.assertEqual(set(s.requests.PROVINCIA),set(selected))
            self.assertTrue(set(plan.assignments.PROVINCIA)<=set(selected))
            self.assertTrue(validate_plan(s,plan))

    def test_all_thirteen_provinces_keep_demands_and_report_limits(self):
        selected=provinces_from_history(self.data.history)
        s=self.scenario(selected);p=solve_classical(s)
        self.assertEqual(s.requests.PROVINCIA.nunique(),13)
        self.assertEqual(len(s.coverage),13)
        self.assertTrue(validate_plan(s,p))
        self.assertTrue(p.unmet.CANTIDAD_FALTANTE.ge(0).all())
        self.assertEqual(len(p.metrics['recursos']),6)
        self.assertTrue(p.metrics['limites'])

    def test_empty_selection_has_no_demands_deliveries_or_routes(self):
        s=self.scenario([]);p=solve_classical(s)
        self.assertTrue(s.requests.empty);self.assertTrue(p.assignments.empty)
        self.assertFalse(p.routes);self.assertFalse(p.geojson['features'])
        self.assertEqual(p.metrics['estado_solver'],'ESCENARIO_VACIO')

    def test_selection_change_invalidates_old_results(self):
        a=self.scenario(['CALCA','URUBAMBA']);p=solve_classical(a)
        b=self.scenario(['CALCA'])
        self.assertNotEqual(a.scenario_id,b.scenario_id)
        with self.assertRaisesRegex(ValueError,'obsoleto'):validate_plan(b,p)
        self.assertNotIn('URUBAMBA',set(b.requests.PROVINCIA))

    def test_personnel_and_smoke_affect_demands(self):
        a=self.scenario(['CALCA'],{'CALCA':{'BOMBEROS':8}})
        b=self.scenario(['CALCA'],{'CALCA':{'BOMBEROS':25,'FACTOR_HUMO':2}})
        for resource in ['AGUA','MASCARILLA','BOTIQUIN_BRIGADA']:
            self.assertGreater(int(b.requests.loc[b.requests.RECURSO_ID.eq(resource),'CANTIDAD_SOLICITADA'].iloc[0]),int(a.requests.loc[a.requests.RECURSO_ID.eq(resource),'CANTIDAD_SOLICITADA'].iloc[0]))
        self.assertFalse(bool(a.profiles.MAS_DE_DIEZ_BOMBEROS.iloc[0]));self.assertTrue(bool(b.profiles.MAS_DE_DIEZ_BOMBEROS.iloc[0]))

    def test_fauna_on_and_off_changes_only_automatic_veterinary_demand(self):
        a=self.scenario(['URUBAMBA'],{'URUBAMBA':{'FAUNA_AFECTADA':True,'ANIMALES_AFECTADOS':30}})
        b=self.scenario(['URUBAMBA'],{'URUBAMBA':{'FAUNA_AFECTADA':False,'ANIMALES_AFECTADOS':30}})
        def qty(s):return int(s.requests.loc[s.requests.RECURSO_ID.eq('PAQUETE_VETERINARIO'),'CANTIDAD_SOLICITADA'].iloc[0])
        self.assertEqual(qty(a),8);self.assertEqual(qty(b),0)

    def test_manual_quantities_and_tool_switch(self):
        s=self.scenario(['CALCA'],{'CALCA':{'HERRAMIENTAS_NECESARIAS':False,'SOLICITUDES_ADICIONALES':{'PALA':3}}})
        self.assertEqual(int(s.requests.loc[s.requests.RECURSO_ID.eq('PALA'),'CANTIDAD_SOLICITADA'].iloc[0]),3)
        self.assertEqual(int(s.requests.loc[s.requests.RECURSO_ID.eq('HACHA'),'CANTIDAD_SOLICITADA'].iloc[0]),0)

    def test_invalid_profiles_weights_or_inactive_overrides_fail(self):
        for change in [{'BOMBEROS':-1},{'BOMBEROS':2.2},{'FACTOR_HUMO':float('nan')},{'FAUNA_AFECTADA':'False'},{'PLAZO_HORAS':99}]:
            with self.assertRaises(ValueError):self.scenario(['CALCA'],{'CALCA':change})
        with self.assertRaises(ValueError):self.scenario(['CALCA'],{'URUBAMBA':{}})
        with self.assertRaises(ValueError):self.scenario(['CALCA'],weights={'magnitud':1})

    def test_receptor_choice_must_belong_to_selected_province(self):
        other=self.data.receivers.loc[self.data.receivers.PROVINCIA.eq('ANTA'),'PUNTO_ID'].iloc[0]
        with self.assertRaises(ValueError):self.scenario(['CALCA'],receiver_choices={'CALCA':other})

    def test_missing_coverage_preserves_province_and_reports_error(self):
        data=copy.deepcopy(self.data)
        data.receivers=data.receivers.loc[~data.receivers.PROVINCIA.eq('ESPINAR')]
        s=self.scenario(['ESPINAR'],data=data);p=solve_classical(s)
        self.assertTrue(p.assignments.empty)
        self.assertFalse(bool(s.coverage.PREPARADO.iloc[0]))
        self.assertTrue(p.unmet.loc[p.unmet.CANTIDAD_PENDIENTE.gt(0),'MOTIVO'].str.contains('SIN_COBERTURA_VIAL').all())

    def test_every_province_has_documented_receiver_and_coverage_state(self):
        s=self.scenario(provinces_from_history(self.data.history))
        self.assertTrue(s.coverage.NOMBRE.ne('').all())
        self.assertTrue(s.coverage.FUENTE_COORDENADA.ne('').all())
        self.assertTrue(s.coverage.ESTADO.ne('').all())

    def test_fixed_inventory_does_not_scale_with_selection(self):
        before=usable_stock(self.data,self.data.config)
        self.scenario(['CALCA']);self.scenario(provinces_from_history(self.data.history))
        self.assertEqual(before,usable_stock(self.data,self.data.config))
        self.assertEqual(before['AGUA'],670)

    def test_pending_local_and_future_donations_not_spent(self):
        data=copy.deepcopy(self.data)
        base=usable_stock(data,data.config)
        data.donations.loc[data.donations.ESTADO.eq('PROMETIDA'),'CANTIDAD']=999999
        data.donations.loc[data.donations.CENTRO_ID.eq('HUB_PARURO'),'CANTIDAD']=999999
        self.assertEqual(base,usable_stock(data,data.config))

    def test_reserved_and_soon_expiring_stock_excluded(self):
        data=copy.deepcopy(self.data)
        mask=data.inventory.CENTRO_ID.eq('COER_CUSCO')&data.inventory.RECURSO_ID.eq('AGUA')
        data.inventory.loc[mask,'CANTIDAD_RESERVADA']=10
        self.assertEqual(usable_stock(data,data.config)['AGUA'],660)
        mask=data.donations.DONACION_ID.eq('DON-COER_CUSCO-AGUA-RECIBIDA')
        data.donations.loc[mask,'VENCE_EN']='2026-10-24T10:00:00-05:00'
        self.assertEqual(usable_stock(data,data.config)['AGUA'],0)

    def test_zero_deadline_has_no_delivery(self):
        s=self.scenario(['CALCA'],{'CALCA':{'PLAZO_HORAS':0}});p=solve_classical(s)
        self.assertTrue(p.assignments.empty)
        self.assertTrue(p.unmet.loc[p.unmet.CANTIDAD_PENDIENTE.gt(0),'MOTIVO'].str.contains('PLAZO').all())

    def test_capacity_both_dimensions_and_inventory_conservation(self):
        data=copy.deepcopy(self.data)
        data.fleet=data.fleet.iloc[:1].copy()
        data.fleet['CAPACIDAD_KG']=10.;data.fleet['CAPACIDAD_M3']=.002
        s=self.scenario(['CALCA','URUBAMBA'],data=data);p=solve_classical(s)
        self.assertTrue(validate_plan(s,p))
        self.assertTrue(p.unmet.CANTIDAD_ASIGNADA.le(p.unmet.CANTIDAD_PENDIENTE).all())
        for r in p.routes:
            self.assertLessEqual(r['CARGA_INICIAL_KG'],10+1e-6);self.assertLessEqual(r['VOLUMEN_INICIAL_M3'],.002+1e-6)
            self.assertEqual(r['SECUENCIA'][0],'COER_CUSCO');self.assertEqual(r['SECUENCIA'][-1],'COER_CUSCO')

    def test_priority_changes_actual_allocation_under_scarcity(self):
        data=copy.deepcopy(self.data)
        data.fleet=data.fleet.iloc[:1].copy()
        data.config['costo_por_km']=data.config['costo_por_minuto']=0
        mask=data.inventory.CENTRO_ID.eq('COER_CUSCO')&data.inventory.RECURSO_ID.eq('AGUA')
        data.inventory.loc[mask,'CANTIDAD_DISPONIBLE']=1
        weights={'magnitud':1.,'personal':0.,'fauna':0.,'urgencia':0.}
        winners=[]
        for high in ['CALCA','URUBAMBA']:
            overrides={p:{'BOMBEROS':1,'PERSONAL_APOYO':0,'MAGNITUD_RELATIVA':100 if p==high else 1} for p in ['CALCA','URUBAMBA']}
            s=self.scenario(['CALCA','URUBAMBA'],overrides,data=data,weights=weights)
            s.requests=s.requests.loc[s.requests.RECURSO_ID.eq('AGUA')].copy()
            plan=solve_classical(s)
            winners.append(plan.assignments.PROVINCIA.tolist())
        self.assertEqual(winners,[['CALCA'],['URUBAMBA']])

    def test_small_milp_objective_matches_exhaustive_reference(self):
        data=copy.deepcopy(self.data)
        data.fleet=data.fleet.iloc[:1].copy()
        data.fleet['CAPACIDAD_KG']=1.3
        mask=data.inventory.CENTRO_ID.eq('COER_CUSCO')&data.inventory.RECURSO_ID.eq('AGUA')
        data.inventory.loc[mask,'CANTIDAD_DISPONIBLE']=2
        data.config['costo_por_minuto']=0
        s=self.scenario(['CALCA','URUBAMBA'],{p:{'BOMBEROS':1,'PERSONAL_APOYO':0} for p in ['CALCA','URUBAMBA']},data=data)
        s.requests=s.requests.loc[s.requests.RECURSO_ID.eq('AGUA')].copy()
        p=solve_classical(s)
        rows=list(s.requests.itertuples());base='COER_CUSCO';best=float('inf')
        for quantities in itertools.product(range(3),repeat=2):
            if sum(quantities)>2:continue
            destinations=[r.PUNTO_ID for r,q in zip(rows,quantities) if q]
            if destinations:
                transport=min(sum(float(data.distances.loc[a,b]) for a,b in zip([base,*seq],[*seq,base])) for seq in itertools.permutations(destinations))
            else:transport=0.
            missing=sum(data.config['penalizacion_faltante']*r.PRIORIDAD_RECURSO/100*(1-q/r.CANTIDAD_PENDIENTE) for r,q in zip(rows,quantities))
            best=min(best,transport*data.config['costo_por_km']+missing)
        self.assertAlmostEqual(p.metrics['objetivo'],best,places=6)

    def test_reproducible_plan_and_configuration_hash(self):
        a=self.scenario(['CALCA','URUBAMBA']);b=self.scenario(['URUBAMBA','CALCA'])
        self.assertEqual(a.scenario_id,b.scenario_id)
        p=solve_classical(a);q=solve_classical(b)
        pd.testing.assert_frame_equal(p.assignments,q.assignments)
        self.assertEqual(p.routes,q.routes)
        changed=self.scenario(['CALCA','URUBAMBA'],{'CALCA':{'BOMBEROS':22}})
        self.assertNotEqual(changed.scenario_id,a.scenario_id)

    def test_geometry_uses_real_directed_edges_without_extra_delivery_stops(self):
        s=self.scenario(['URUBAMBA']);p=solve_classical(s)
        self.assertEqual(set(p.stops.PROVINCIA),{'URUBAMBA'})
        for feature in p.geojson['features']:
            self.assertTrue(feature['properties']['TRAMO_IDS'])
            self.assertEqual(feature['properties']['RED_VERSION'],self.data.manifest['red_version'])
            # Los vértices de carretera no se convierten en paradas de entrega.
            self.assertGreater(len(feature['geometry']['coordinates']),2)

    def test_empty_export_replaces_latest_and_cannot_export_stale_result(self):
        with tempfile.TemporaryDirectory() as directory:
            data=copy.deepcopy(self.data);data.root=Path(directory)
            a=self.scenario(['URUBAMBA'],data=data);p=solve_classical(a);export_plan(a,p)
            b=self.scenario([],data=data);folder=export_plan(b,solve_classical(b))
            latest=json.loads((folder.parent/'latest.json').read_text())
            self.assertEqual(latest['escenario_id'],b.scenario_id)
            self.assertTrue(pd.read_csv(folder/'asignaciones.csv').empty)
            with self.assertRaises(ValueError):export_plan(b,p)

    def test_validator_rejects_forged_overdelivery(self):
        s=self.scenario(['URUBAMBA']);p=solve_classical(s)
        p.assignments.loc[p.assignments.index[0],'CANTIDAD_ASIGNADA']=999999
        with self.assertRaises(ValueError):validate_plan(s,p)

if __name__=='__main__':unittest.main()
