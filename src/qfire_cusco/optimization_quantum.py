"""QAOA de partición de rutas, simulado por vector de estado.

La asignación entera se calcula clásicamente sin consultar el MILP de referencia.
La reducción exige capacidad suficiente y tours comunes a todos los vehículos.
No se usa el óptimo exacto para entrenar ni para reparar las muestras cuánticas.
"""
from __future__ import annotations
from dataclasses import dataclass
import copy
import math
import time
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from .scenario import usable_stock
from .optimization_classical import (Plan, ASSIGNMENT_COLUMNS, STOP_COLUMNS,
    enumerate_routes, validate_plan)


@dataclass
class RouteQUBO:
    allocation: pd.DataFrame
    tours: list
    points: list
    Q: np.ndarray  # triangular superior: E=offset+sum_{i<=j} Q[i,j]x_i x_j
    offset: float
    penalty: float
    fleet_size: int
    slack_weights: list
    preparation_seconds: float

    @property
    def n(self): return len(self.Q)


def priority_allocation(scenario):
    """Óptimo por recurso con stock y demanda; elimina capacidades y ruteo.

    Beneficio por unidad = lambda * prioridad / (100 * demanda).
    Cada unidad del mismo pedido tiene el mismo beneficio: orden voraz exacto.
    Esta relajación puede restringir el óptimo conjunto en otros escenarios.
    """
    stock = usable_stock(scenario.inputs, scenario.config)
    allocation = scenario.requests.copy().reset_index(drop=True)
    allocation['CANTIDAD_ASIGNADA'] = 0
    allocation['BENEFICIO_UNIDAD'] = [
        scenario.config['penalizacion_faltante'] * float(r.PRIORIDAD_RECURSO)
        / 100 / max(1, int(r.CANTIDAD_PENDIENTE)) for r in allocation.itertuples()]
    for resource, group in allocation.groupby('RECURSO_ID'):
        available = stock[resource]
        order = sorted(group.index, key=lambda i:(-allocation.loc[i,'BENEFICIO_UNIDAD'],
                                                 allocation.loc[i,'SOLICITUD_ID']))
        for i in order:
            row = allocation.loc[i]
            authorized = str(row.SOLICITUD_AUTORIZADA_SIMULADA).lower() == 'true'
            allowed = str(row.REQUIERE_SOLICITUD_AUTORIZADA).lower() != 'true' or authorized
            qty = min(available,int(row.CANTIDAD_PENDIENTE)) if allowed and row.BENEFICIO_UNIDAD>0 else 0
            allocation.loc[i,'CANTIDAD_ASIGNADA'] = qty
            available -= qty
    return allocation


def prepare_qubo(scenario, max_qubits=18):
    started = time.perf_counter()
    allocation = priority_allocation(scenario)
    catalog = scenario.inputs.catalog.set_index('RECURSO_ID')
    fleet = scenario.inputs.fleet.sort_values('VEHICULO_ID')
    weight = sum(r.CANTIDAD_ASIGNADA*float(catalog.loc[r.RECURSO_ID,'PESO_KG_UNIDAD']) for r in allocation.itertuples())
    volume = sum(r.CANTIDAD_ASIGNADA*float(catalog.loc[r.RECURSO_ID,'VOLUMEN_M3_UNIDAD']) for r in allocation.itertuples())
    if not len(fleet) or not (fleet.CAPACIDAD_KG.ge(weight-1e-9).all() and fleet.CAPACIDAD_M3.ge(volume-1e-9).all()):
        raise ValueError('La reducción requiere que toda la carga asignada quepa en cualquier vehículo.')
    points = sorted(allocation.loc[allocation.CANTIDAD_ASIGNADA.gt(0),'PUNTO_ID'].unique())
    if not points: raise ValueError('No hay lotes positivos para construir el QUBO de rutas.')
    pools = [enumerate_routes(scenario,v) for v in fleet.itertuples()]
    def signature(t):
        return (tuple(t['sequence']),t['start'],t['return'],tuple(sorted(t['completion'].items())))
    common = set(signature(t) for t in pools[0])
    for pool in pools[1:]: common &= set(signature(t) for t in pool)
    # Para lotes ya fijados y vehículos intercambiables, el tour de menor costo
    # de cada conjunto domina los otros órdenes con igual conjunto visitado.
    candidates = {}
    for tour in pools[0]:
        subset = tuple(sorted(tour['sequence']))
        if signature(tour) not in common or not set(subset)<=set(points): continue
        cost = scenario.config['costo_por_km']*tour['km']+scenario.config['costo_por_minuto']*tour['minutes']
        candidate = dict(tour,cost=cost,subset=subset)
        if subset not in candidates or (cost,tour['sequence']) < (candidates[subset]['cost'],candidates[subset]['sequence']):
            candidates[subset] = candidate
    tours = [candidates[k] for k in sorted(candidates,key=lambda k:(len(k),k))]
    if not set(points)<=set(p for t in tours for p in t['sequence']):
        raise ValueError('Falta un tour común para algún lote; esta reducción no es aplicable.')
    fleet_size = len(fleet)
    slack_weights = [2**k for k in range(math.ceil(math.log2(fleet_size+1)))]
    n = len(tours)+len(slack_weights)
    if n>max_qubits: raise ValueError(f'{n} qubits superan el límite de simulación {max_qubits}.')
    Q = np.zeros((n,n)); offset = 0.
    # A > suma de todos los costos: ninguna violación entera puede ser óptima
    # si existe una partición factible. Verificar factibilidad por separado.
    penalty = 1.+sum(t['cost'] for t in tours)
    def square(terms,rhs):
        nonlocal offset
        offset += penalty*rhs*rhs
        for i,w in terms:
            Q[i,i] += penalty*(w*w-2*rhs*w)
        for a,(i,wi) in enumerate(terms):
            for j,wj in terms[a+1:]: Q[min(i,j),max(i,j)] += 2*penalty*wi*wj
    for k,t in enumerate(tours): Q[k,k] += t['cost']
    for point in points:
        square([(k,1) for k,t in enumerate(tours) if point in t['sequence']],1)
    square([(k,1) for k in range(len(tours))]+[(len(tours)+k,w) for k,w in enumerate(slack_weights)],fleet_size)
    return RouteQUBO(allocation,tours,points,Q,offset,penalty,fleet_size,slack_weights,time.perf_counter()-started)


def basis_table(problem):
    indices = np.arange(2**problem.n,dtype=np.uint32)
    bits = ((indices[:,None] >> np.arange(problem.n,dtype=np.uint32)) & 1).astype(np.int8)
    energy = np.full(len(indices),problem.offset)
    for i,j in zip(*np.nonzero(problem.Q)):
        energy += problem.Q[i,j]*(bits[:,i]*bits[:,j])
    cover = np.zeros((len(bits),len(problem.points)),dtype=np.int16)
    for k,t in enumerate(problem.tours):
        cover += bits[:,k,None]*np.array([p in t['sequence'] for p in problem.points],dtype=np.int16)
    count = bits[:,:len(problem.tours)].sum(axis=1)
    slack = bits[:,len(problem.tours):]@np.array(problem.slack_weights)
    feasible = np.all(cover==1,axis=1) & (count+slack==problem.fleet_size)
    if not feasible.any(): raise ValueError('El QUBO no tiene una partición factible para estos lotes.')
    return bits,energy,feasible


def statevector(theta,energy):
    """H^n; por capa exp(-i gamma H_C) y exp(-i beta sum X).

    energy ya está escalada por A. Orden little endian: x_i es el qubit i.
    """
    n = int(round(math.log2(len(energy))))
    state = np.full(len(energy),1/math.sqrt(len(energy)),dtype=np.complex128)
    depth = len(theta)//2
    for gamma,beta in zip(theta[:depth],theta[depth:]):
        state *= np.exp(-1j*gamma*energy)
        c,s = math.cos(beta),-1j*math.sin(beta)
        for qubit in range(n):
            blocks = state.reshape(-1,2,1<<qubit)
            left,right = blocks[:,0,:].copy(),blocks[:,1,:].copy()
            blocks[:,0,:] = c*left+s*right
            blocks[:,1,:] = s*left+c*right
    return state


def qaoa_sample(problem,energy,feasible,depth=3,seed=42,shots=4096,maxiter=200):
    started = time.perf_counter(); rng = np.random.default_rng(seed)
    normalized = energy/problem.penalty
    spread = float(np.std(normalized))
    # Reescala los parámetros gamma por la desviación del Hamiltoniano bajo
    # la distribución uniforme; no utiliza mínimo, factibilidad ni solución.
    initial = np.r_[rng.uniform(0.05,0.7,depth),rng.uniform(-0.6,-0.1,depth)]
    def physical(theta):
        return np.r_[theta[:depth]/spread,theta[depth:]]
    history = []
    def objective(theta):
        probabilities = np.abs(statevector(physical(theta),normalized))**2
        value = float(probabilities@normalized)/spread
        history.append(value)
        return value
    fit = minimize(objective,initial,method='COBYLA',
                   options={'maxiter':maxiter,'rhobeg':0.25,'tol':1e-5})
    # Se usa el mejor vector evaluado por COBYLA, sin acceso al oráculo exacto.
    theta = physical(fit.x)
    state = statevector(theta,normalized)
    probs = np.abs(state)**2; probs /= probs.sum()
    counts = rng.multinomial(shots,probs)
    observed = np.flatnonzero((counts>0)&feasible)
    chosen = int(observed[np.argmin(energy[observed])]) if len(observed) else None
    runtime = time.perf_counter()-started
    # Sólo diagnóstico posterior; NO interviene en optimize, sample o decode.
    exact = float(energy[feasible].min())
    optimal_mask = feasible & np.isclose(energy,exact,atol=1e-7,rtol=0)
    return {'depth':depth,'seed':seed,'shots':shots,'evaluations':len(history),
        'optimizer_success':bool(fit.success),'optimizer_message':str(fit.message),
        'theta':theta.tolist(),'gamma_parameter_spread':spread,'expectation_scaled':float(probs@normalized),
        'feasible_probability':float(probs[feasible].sum()),
        'optimal_probability':float(probs[optimal_mask].sum()),
        'feasible_shots':int(counts[feasible].sum()),'chosen_state':chosen,
        'transport_cost':float(energy[chosen]) if chosen is not None else None,
        'relative_gap_pct':float(100*(energy[chosen]-exact)/exact) if chosen is not None else None,
        'optimal_sampled':bool(chosen is not None and optimal_mask[chosen]),
        'seconds':runtime,'history':history,'counts':counts}


def qiskit_circuit(problem,theta):
    """Conversión QUBO a Ising, sin constante global: x_i=(I-Z_i)/2.

    h_i=-Qii/2-sum(Qij)/4; Jij=Qij/4. Escala H_C por A.
    RZ(2 gamma h_i/A), RZZ(2 gamma Jij/A), RX(2 beta).
    """
    from qiskit import QuantumCircuit
    n=problem.n; h=-np.diag(problem.Q).copy()/2; edges=[]
    for i in range(n):
        for j in range(i+1,n):
            if problem.Q[i,j]:
                coupling=problem.Q[i,j]/4
                h[i]-=coupling; h[j]-=coupling; edges.append((i,j,coupling))
    circuit=QuantumCircuit(n);circuit.h(range(n));depth=len(theta)//2
    for gamma,beta in zip(theta[:depth],theta[depth:]):
        for i in range(n): circuit.rz(2*gamma*h[i]/problem.penalty,i)
        for i,j,coupling in edges: circuit.rzz(2*gamma*coupling/problem.penalty,i,j)
        for i in range(n): circuit.rx(2*beta,i)
    return circuit


def materialize_plan(scenario,problem,bits,chosen_state):
    """Decodifica sólo una muestra factible; ninguna reparación ni fallback MILP."""
    if chosen_state is None: raise ValueError('QAOA no produjo un plan factible con este presupuesto de shots.')
    x=bits[chosen_state];chosen=[t for k,t in enumerate(problem.tours) if x[k]]
    if len(chosen)>problem.fleet_size or any(sum(p in t['sequence'] for t in chosen)!=1 for p in problem.points):
        raise ValueError('Muestra no factible.')
    catalog=scenario.inputs.catalog.set_index('RECURSO_ID');base=scenario.config['origen_central']
    fleet=scenario.inputs.fleet.sort_values('VEHICULO_ID')
    geo={(f['properties']['ORIGEN'],f['properties']['DESTINO']):f for f in scenario.inputs.geometries['features']}
    assignments=[];stops=[];routes=[];features=[]
    for tour,vehicle in zip(chosen,fleet.itertuples()):
        rows=[]
        for r in problem.allocation.itertuples():
            if r.PUNTO_ID not in tour['sequence'] or r.CANTIDAD_ASIGNADA<=0: continue
            item=catalog.loc[r.RECURSO_ID];qty=int(r.CANTIDAD_ASIGNADA)
            rows.append({'SOLICITUD_ID':r.SOLICITUD_ID,'PROVINCIA':r.PROVINCIA,'PUNTO_ID':r.PUNTO_ID,
                'RECURSO_ID':r.RECURSO_ID,'VEHICULO_ID':vehicle.VEHICULO_ID,'CANTIDAD_ASIGNADA':qty,'UNIDAD':r.UNIDAD,
                'PESO_KG':qty*item.PESO_KG_UNIDAD,'VOLUMEN_M3':qty*item.VOLUMEN_M3_UNIDAD,
                'ENTREGA_EN':tour['completion'][r.PUNTO_ID],'ESCENARIO_ID':scenario.scenario_id})
        assignments.extend(rows);kg=sum(r['PESO_KG'] for r in rows);vol=sum(r['VOLUMEN_M3'] for r in rows)
        initial_kg,initial_vol=kg,vol
        for order,point in enumerate(tour['sequence'],1):
            drops=[r for r in rows if r['PUNTO_ID']==point]
            after_kg=kg-sum(r['PESO_KG'] for r in drops);after_vol=vol-sum(r['VOLUMEN_M3'] for r in drops)
            stops.append({'VEHICULO_ID':vehicle.VEHICULO_ID,'ORDEN':order,'PUNTO_ID':point,'PROVINCIA':drops[0]['PROVINCIA'],
                'LLEGADA_EN':tour['arrivals'][point],'ENTREGA_EN':tour['completion'][point],
                'CARGA_ANTES_KG':kg,'CARGA_DESPUES_KG':max(0,after_kg),
                'VOLUMEN_ANTES_M3':vol,'VOLUMEN_DESPUES_M3':max(0,after_vol)})
            kg,vol=after_kg,after_vol
        sequence=[base,*tour['sequence'],base]
        for order,(a,b) in enumerate(zip(sequence,sequence[1:]),1):
            f=copy.deepcopy(geo[a,b]);f['properties'].update(VEHICULO_ID=vehicle.VEHICULO_ID,ORDEN_TRAMO=order,ESCENARIO_ID=scenario.scenario_id)
            features.append(f)
        routes.append({'VEHICULO_ID':vehicle.VEHICULO_ID,'SECUENCIA':sequence,'SALIDA_EN':tour['start'],
            'RETORNO_EN':tour['return'],'DISTANCIA_KM':tour['km'],'DURACION_VIAL_MIN':tour['minutes'],
            'CARGA_INICIAL_KG':initial_kg,'VOLUMEN_INICIAL_M3':initial_vol,
            'CAPACIDAD_KG':float(vehicle.CAPACIDAD_KG),'CAPACIDAD_M3':float(vehicle.CAPACIDAD_M3)})
    assignments=pd.DataFrame(assignments,columns=ASSIGNMENT_COLUMNS);stops=pd.DataFrame(stops,columns=STOP_COLUMNS)
    unmet=scenario.requests.copy();totals=assignments.groupby('SOLICITUD_ID').CANTIDAD_ASIGNADA.sum()
    unmet['CANTIDAD_ASIGNADA']=unmet.SOLICITUD_ID.map(totals).fillna(0).astype(int)
    unmet['CANTIDAD_FALTANTE']=unmet.CANTIDAD_PENDIENTE.astype(int)-unmet.CANTIDAD_ASIGNADA
    unmet['COBERTURA']=np.where(unmet.CANTIDAD_PENDIENTE.gt(0),unmet.CANTIDAD_ASIGNADA/unmet.CANTIDAD_PENDIENTE.replace(0,np.nan),1.)
    unmet['MOTIVO']=np.where(unmet.CANTIDAD_FALTANTE.eq(0),'CUBIERTA','STOCK_ASIGNACION_PREVIA_QAOA')
    config=scenario.config;penalty=float(config['penalizacion_faltante'])
    residual=sum(penalty*float(r.PRIORIDAD_RECURSO)/100*(1-r.COBERTURA) for r in unmet.itertuples() if r.CANTIDAD_PENDIENTE>0)
    baseline=sum(penalty*float(r.PRIORIDAD_RECURSO)/100 for r in unmet.itertuples() if r.CANTIDAD_PENDIENTE>0)
    km=sum(r['DISTANCIA_KM'] for r in routes);minutes=sum(r['DURACION_VIAL_MIN'] for r in routes)
    transport=config['costo_por_km']*km+config['costo_por_minuto']*minutes
    stock=usable_stock(scenario.inputs,config);resources={}
    for resource,group in unmet.groupby('RECURSO_ID'):
        demand=int(group.CANTIDAD_PENDIENTE.sum());delivered=int(group.CANTIDAD_ASIGNADA.sum())
        resources[resource]={'solicitado':demand,'asignado':delivered,'faltante':demand-delivered,
            'stock_coer_utilizable':stock[resource],'saldo_coer':stock[resource]-delivered,'cobertura':delivered/demand if demand else 1.}
    metrics={'escenario_id':scenario.scenario_id,'metodo':'ASIGNACION_CLASICA_QAOA_SIMULADO',
        'estado_solver':'MUESTRA_QAOA_FACTIBLE_VALIDADA','provincias_seleccionadas':scenario.selected,
        'provincias_atendidas':sorted(set(assignments.PROVINCIA)),'vehiculos_utilizados':len(routes),
        'distancia_km':km,'duracion_vial_min':minutes,'penalizacion_faltantes':residual,
        'costo_transporte':transport,'objetivo':residual+transport,'objetivo_sin_entregas':baseline,
        'qubits':problem.n,'tours_candidatos_reducidos':len(problem.tours),'recursos':resources,
        'red_version':scenario.inputs.manifest['red_version'],'inputs_sha256':scenario.inputs.hashes,
        'max_paradas_por_vehiculo':config['max_paradas_por_vehiculo'],
        'limites':['Simulación ideal por vector de estado; sin ejecución en QPU.',
            'Asignación por recurso fijada antes de QAOA; rutas comunes, sin dividir lotes.',
            'La igualdad con MILP se verifica para esta instancia; no se generaliza.',
            'Operación simulada y coordenadas/accesos sin validación operativa.']}
    plan=Plan(scenario.scenario_id,assignments,unmet,stops,routes,{'type':'FeatureCollection','features':features},metrics)
    validate_plan(scenario,plan)
    return plan
