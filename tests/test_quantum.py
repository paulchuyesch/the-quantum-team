"""Pruebas de la reducción, conservación de cantidades y circuito cuántico."""
import copy
import json
from pathlib import Path
import sys
import unittest
import numpy as np
from scipy.optimize import linprog

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from qfire_cusco.scenario import load_inputs,create_scenario,usable_stock
from qfire_cusco.optimization_classical import validate_plan
from qfire_cusco.optimization_quantum import prepare_qubo,basis_table,materialize_plan,statevector,qiskit_circuit


class QuantumTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs=load_inputs(ROOT)
        cls.inputs.hashes={k.replace('\\','/'):v for k,v in cls.inputs.hashes.items()}
        profiles=json.loads((ROOT/'config/ejemplo_perfiles_fase4.json').read_text(encoding='utf-8'))
        cls.scenario=create_scenario(cls.inputs,['ANTA','CALCA','PARURO','URUBAMBA'],profiles)
        cls.problem=prepare_qubo(cls.scenario)
        cls.bits,cls.energy,cls.feasible=basis_table(cls.problem)

    def test_allocation_relaxation_matches_independent_linear_program(self):
        a=self.problem.allocation;resources=sorted(a.RECURSO_ID.unique())
        stock=usable_stock(self.inputs,self.scenario.config)
        matrix=np.array([a.RECURSO_ID.eq(r).astype(float) for r in resources])
        result=linprog(-a.BENEFICIO_UNIDAD.to_numpy(),A_ub=matrix,b_ub=[stock[r] for r in resources],
                      bounds=[(0,int(q)) for q in a.CANTIDAD_PENDIENTE],method='highs')
        self.assertTrue(result.success)
        self.assertAlmostEqual(float(-(a.BENEFICIO_UNIDAD*a.CANTIDAD_ASIGNADA).sum()),result.fun,places=6)

    def test_capacity_assumption_is_enforced(self):
        scenario=copy.copy(self.scenario);scenario.inputs=copy.copy(self.inputs)
        scenario.inputs.fleet=self.inputs.fleet.copy();scenario.inputs.fleet.loc[0,'CAPACIDAD_KG']=10
        with self.assertRaisesRegex(ValueError,'carga asignada'): prepare_qubo(scenario)

    def test_out_of_scope_size_does_not_silently_truncate(self):
        with self.assertRaisesRegex(ValueError,'límite'): prepare_qubo(self.scenario,max_qubits=8)

    def test_exact_reduced_plan_passes_original_physical_validator(self):
        index=int(np.flatnonzero(self.feasible)[np.argmin(self.energy[self.feasible])])
        plan=materialize_plan(self.scenario,self.problem,self.bits,index)
        self.assertTrue(validate_plan(self.scenario,plan))
        self.assertAlmostEqual(plan.metrics['objetivo'],3821.5028330028954,places=6)
        self.assertEqual(plan.metrics['vehiculos_utilizados'],2)

    def test_decoder_rejects_zero_state_instead_of_repairing(self):
        with self.assertRaisesRegex(ValueError,'no factible'):
            materialize_plan(self.scenario,self.problem,self.bits,0)
        with self.assertRaisesRegex(ValueError,'no produjo'):
            materialize_plan(self.scenario,self.problem,self.bits,None)

    def test_numpy_statevector_matches_qiskit_for_nontrivial_angles(self):
        from qiskit.quantum_info import Statevector
        theta=np.array([.013,-.023,.31,-.27])
        custom=statevector(theta,self.energy/self.problem.penalty)
        actual=Statevector.from_instruction(qiskit_circuit(self.problem,theta)).data
        self.assertGreater(float(abs(np.vdot(actual,custom))**2),1-1e-9)
        self.assertAlmostEqual(float(np.linalg.norm(custom)),1.,places=10)


if __name__=='__main__':unittest.main()
