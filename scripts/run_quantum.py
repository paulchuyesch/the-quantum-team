"""Experimento reproducible fase 05; no requiere cuentas ni hardware cuántico."""
from pathlib import Path
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
os.environ.setdefault('OMP_NUM_THREADS','1')
import argparse
import hashlib
import importlib.metadata
import json
import platform
import sys
import time
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from qfire_cusco.scenario import load_inputs,create_scenario
from qfire_cusco.optimization_classical import solve_classical,validate_plan
from qfire_cusco.optimization_quantum import (prepare_qubo,basis_table,qaoa_sample,
    materialize_plan,statevector,qiskit_circuit)


def save_json(path,payload):
    Path(path).write_text(json.dumps(payload,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def export_local(folder,plan):
    folder.mkdir(parents=True,exist_ok=True)
    for name,frame in [('asignaciones',plan.assignments),('faltantes',plan.unmet),('paradas',plan.stops)]:
        frame.to_csv(folder/f'{name}.csv',index=False,encoding='utf-8-sig')
    save_json(folder/'metricas.json',plan.metrics);save_json(folder/'rutas.json',plan.routes)
    save_json(folder/'rutas.geojson',plan.geojson)


def run(root=ROOT,seeds=range(42,52),depths=(1,3),shots=4096,maxiter=250):
    root=Path(root);out=root/'data/results/phase5';out.mkdir(parents=True,exist_ok=True)
    data=load_inputs(root)
    # La fase 04 incorporaba separadores de rutas del SO al hash del escenario.
    # Normalización explícita para recuperar el ID original también en Windows.
    data.hashes={k.replace('\\','/'):v for k,v in data.hashes.items()}
    profiles=json.loads((root/'config/ejemplo_perfiles_fase4.json').read_text(encoding='utf-8'))
    scenario=create_scenario(data,['ANTA','CALCA','PARURO','URUBAMBA'],profiles)
    setup_started=time.perf_counter();problem=prepare_qubo(scenario)
    bits,energy,feasible=basis_table(problem);setup_seconds=time.perf_counter()-setup_started
    np.savez_compressed(out/'qubo.npz',Q=problem.Q,offset=problem.offset,penalty=problem.penalty,
                        energy=energy,feasible=feasible)
    problem.allocation.to_csv(out/'asignacion_previa.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame([{'QUBIT':i,'TIPO':'tour','DESTINOS':' → '.join(t['sequence']),
                   'DISTANCIA_KM':t['km'],'DURACION_MIN':t['minutes'],'COSTO':t['cost']}
                  for i,t in enumerate(problem.tours)]+[
                  {'QUBIT':len(problem.tours)+k,'TIPO':'holgura','DESTINOS':f'peso {w}'}
                  for k,w in enumerate(problem.slack_weights)]).to_csv(out/'variables_qubo.csv',index=False,encoding='utf-8-sig')
    seeds=list(seeds);depths=list(depths);runs=[];raw={};primary_plan=None
    # Óptimo exacto: sólo referencia posterior. No se entrega al optimizador.
    exact_transport=float(energy[feasible].min())
    for depth in depths:
        for seed in seeds:
            result=qaoa_sample(problem,energy,feasible,depth,seed,shots,maxiter)
            key=f'p{depth}_seed{seed}'
            raw[key]=result
            if result['chosen_state'] is not None:
                plan=materialize_plan(scenario,problem,bits,result['chosen_state'])
                validate_plan(scenario,plan)
                objective=plan.metrics['objetivo']
            else: plan=None;objective=None
            record={k:v for k,v in result.items() if k not in ['counts','history','theta']}
            record['objective_full']=objective
            record['total_pipeline_seconds']=setup_seconds+result['seconds']
            runs.append(record)
            pd.DataFrame({'STATE':np.flatnonzero(result['counts']),
                'COUNT':result['counts'][result['counts']>0]}).to_csv(out/f'counts_{key}.csv',index=False)
            save_json(out/f'angles_{key}.json',{k:v for k,v in result.items() if k not in ['counts','history']})
            save_json(out/f'trace_{key}.json',result['history'])
            if depth==3 and seed==42:
                primary_plan=plan;export_local(out/'qaoa_p3_seed42',plan) if plan is not None else None
            print(f'{key}: factibles={result["feasible_shots"]}/{shots}, objetivo={objective}, segundos={result["seconds"]:.3f}',flush=True)
    # Benchmark clásico independiente: no se usó como warm start ni para reparar.
    baseline_runs=[];baseline=None
    for repeat in range(10):
        measured=time.perf_counter();plan=solve_classical(scenario)
        baseline_runs.append({'repeat':repeat,'wall_seconds':time.perf_counter()-measured,
                              'solver_seconds':plan.metrics['segundos_computo'],'objective':plan.metrics['objetivo']})
        baseline=plan
    export_local(out/'milp_recalculado',baseline)
    for record in runs:
        value=record['objective_full']
        record['full_gap_pct']=100*(value-baseline.metrics['objetivo'])/baseline.metrics['objetivo'] if value is not None else None
    frame=pd.DataFrame(runs);frame.to_csv(out/'benchmark_qaoa.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(baseline_runs).to_csv(out/'benchmark_milp.csv',index=False)
    control=[]
    for seed in seeds:
        sampled=np.random.default_rng(seed).integers(0,len(energy),shots)
        valid=sampled[feasible[sampled]]
        cost=float(energy[valid].min()) if len(valid) else None
        control.append({'seed':seed,'shots':shots,'feasible_shots':int(len(valid)),
            'best_transport':cost,'optimal_sampled':bool(cost is not None and abs(cost-exact_transport)<1e-6)})
    pd.DataFrame(control).to_csv(out/'control_uniforme.csv',index=False)
    if primary_plan is None: raise RuntimeError('La corrida principal no obtuvo muestras factibles; revisar resultados sin fallback.')
    primary=raw['p3_seed42']
    from qiskit.quantum_info import Statevector
    circuit=qiskit_circuit(problem,primary['theta'])
    qiskit_state=Statevector.from_instruction(circuit).data
    custom_state=statevector(primary['theta'],energy/problem.penalty)
    fidelity=float(abs(np.vdot(qiskit_state,custom_state))**2)
    (out/'circuito_qaoa.txt').write_text(str(circuit.draw(output='text',fold=140)),encoding='utf-8')
    from qiskit import qasm3
    (out/'circuito_qaoa.qasm').write_text(qasm3.dumps(circuit),encoding='utf-8')
    original_folder=root/'data/results/phase4'/scenario.scenario_id
    original=json.loads((original_folder/'metricas.json').read_text(encoding='utf-8'))
    input_match={k.replace('\\','/'):v for k,v in original['inputs_sha256'].items()}==data.hashes
    # Validación algebraica independiente: expansión QUBO contra restricciones.
    direct=np.zeros(len(bits))
    for k,t in enumerate(problem.tours): direct+=t['cost']*bits[:,k]
    for point in problem.points:
        coverage=sum(bits[:,k] for k,t in enumerate(problem.tours) if point in t['sequence'])
        direct+=problem.penalty*(coverage-1)**2
    count=bits[:,:len(problem.tours)].sum(axis=1)
    slack=bits[:,len(problem.tours):]@np.array(problem.slack_weights)
    direct+=problem.penalty*(count+slack-problem.fleet_size)**2
    rows=[]
    for key in ['objetivo','costo_transporte','penalizacion_faltantes','distancia_km',
                'duracion_vial_min','vehiculos_utilizados']:
        rows.append({'METRICA':key,'NOTEBOOK04_ADJUNTO':original[key],
                     'MILP_RECALCULADO':baseline.metrics[key],'HIBRIDO_QAOA_P3_SEED42':primary_plan.metrics[key]})
    pd.DataFrame(rows).to_csv(out/'comparacion.csv',index=False,encoding='utf-8-sig')
    checks={'inputs_iguales_al_adjunto':input_match,'escenario_id_igual_al_adjunto':scenario.scenario_id==original['escenario_id'],
        'objetivo_milp_reproducido':mathclose(baseline.metrics['objetivo'],original['objetivo']),
        'qubo_error_maximo':float(np.max(np.abs(direct-energy))),
        'qubo_optimo_factible':bool(feasible[np.argmin(energy)]),
        'qiskit_fidelidad':fidelity,'plan_qaoa_valido':bool(validate_plan(scenario,primary_plan)),
        'plan_milp_valido':bool(validate_plan(scenario,baseline)),
        'asignacion_previa_igual_a_milp':bool(np.array_equal(
            primary_plan.unmet.sort_values('SOLICITUD_ID').CANTIDAD_ASIGNADA.to_numpy(),
            baseline.unmet.sort_values('SOLICITUD_ID').CANTIDAD_ASIGNADA.to_numpy())),
        'notebook04_sha256':hashlib.sha256((root/'notebooks/04_asignacion_ruteo_prioridades.ipynb').read_bytes()).hexdigest()}
    assert input_match and checks['objetivo_milp_reproducido'] and checks['qubo_error_maximo']<1e-6 and fidelity>1-1e-9
    save_json(out/'validacion.json',checks)
    config={'provincias':scenario.selected,'scenario_id':scenario.scenario_id,'seeds':seeds,'depths':depths,
            'shots':shots,'maxiter':maxiter,'optimizer':'COBYLA','training':'exact_statevector_expectation',
            'sampling':'numpy.multinomial','backend':'CPU ideal statevector; Qiskit independent verification',
            'penalty_A':problem.penalty,'qubits':problem.n,'routes':len(problem.tours),'feasible_basis_states':int(feasible.sum()),
            'preparation_seconds':setup_seconds,'exact_transport_cost':exact_transport,
            'primary_run':'p3_seed42','primary_selection':'predefinida; sin selección del mejor resultado entre semillas',
            'python':sys.version,'platform':platform.platform(),
            'packages':{p:importlib.metadata.version(p) for p in ['numpy','pandas','scipy','qiskit','matplotlib','nbformat','nbclient']},
            'qiskit_gate_counts':dict(circuit.count_ops()),'qiskit_logical_depth':circuit.depth(),
            'uniform_optimal_probability':float(np.isclose(energy,exact_transport,atol=1e-7,rtol=0).sum()/len(energy)),
            'uniform_feasible_probability':float(feasible.mean())}
    save_json(out/'experimento.json',config)
    print(json.dumps({'out':str(out),'checks':checks,'configuration':config},ensure_ascii=False,indent=2),flush=True)
    return scenario,problem,baseline,primary_plan


def mathclose(a,b):return abs(a-b)<1e-6


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--shots',type=int,default=4096)
    parser.add_argument('--maxiter',type=int,default=250)
    args=parser.parse_args();run(shots=args.shots,maxiter=args.maxiter)
