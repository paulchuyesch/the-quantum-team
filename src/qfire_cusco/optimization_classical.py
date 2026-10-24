"""MILP de cantidades y selección conjunta de rutas dirigidas de depósito único.

Se enumeran tours factibles hasta max_paradas_por_vehiculo. Óptimo, si se prueba,
corresponde a ese modelo restringido, no al VRP sin límite de paradas.
"""
from __future__ import annotations
from dataclasses import dataclass
import copy
import itertools
import json
import math
from pathlib import Path
import time
import numpy as np
import pandas as pd
from scipy.optimize import milp, Bounds, LinearConstraint
from scipy.sparse import coo_matrix
from .scenario import usable_stock

ASSIGNMENT_COLUMNS=['SOLICITUD_ID','PROVINCIA','PUNTO_ID','RECURSO_ID','VEHICULO_ID',
    'CANTIDAD_ASIGNADA','UNIDAD','PESO_KG','VOLUMEN_M3','ENTREGA_EN','ESCENARIO_ID']
STOP_COLUMNS=['VEHICULO_ID','ORDEN','PUNTO_ID','PROVINCIA','LLEGADA_EN','ENTREGA_EN',
    'CARGA_ANTES_KG','CARGA_DESPUES_KG','VOLUMEN_ANTES_M3','VOLUMEN_DESPUES_M3']


@dataclass
class Plan:
    scenario_id: str
    assignments: pd.DataFrame
    unmet: pd.DataFrame
    stops: pd.DataFrame
    routes: list
    geojson: dict
    metrics: dict


def enumerate_routes(scenario, vehicle):
    config=scenario.config; data=scenario.inputs; base=config['origen_central']
    start=max(pd.Timestamp(config['reloj_escenario']),pd.Timestamp(vehicle.DISPONIBLE_DESDE))
    end=min(pd.Timestamp(vehicle.DISPONIBLE_HASTA),pd.Timestamp(config['reloj_escenario'])+pd.Timedelta(hours=config['horizonte_horas']))
    deadlines=scenario.requests.groupby('PUNTO_ID').PLAZO_LOGISTICO_SIMULADO.min().map(pd.Timestamp).to_dict()
    requested=set(scenario.requests.loc[scenario.requests.CANTIDAD_PENDIENTE.gt(0),'PUNTO_ID'])
    ready=sorted(set(scenario.coverage.loc[scenario.coverage.PREPARADO,'PUNTO_ID']) & requested)
    service=float(vehicle.SERVICIO_MIN_POR_PARADA)
    if not math.isfinite(service) or service<0: raise ValueError('Tiempo de servicio inválido.')
    limit=config['max_paradas_por_vehiculo']
    if isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=3: raise ValueError('max_paradas_por_vehiculo debe ser 1, 2 o 3.')
    result=[]
    for count in range(1,min(len(ready),limit)+1):
        for seq in itertools.permutations(ready,count):
            previous=base;now=start;km=0.;minutes=0.;arrivals={};completion={};ok=True
            for pid in seq:
                if not data.reachable.loc[previous,pid]: ok=False;break
                delta=float(data.durations.loc[previous,pid]);km+=float(data.distances.loc[previous,pid]);minutes+=delta
                now+=pd.Timedelta(minutes=delta);arrivals[pid]=now.isoformat()
                now+=pd.Timedelta(minutes=service);completion[pid]=now.isoformat()
                if now>deadlines[pid] or now>end: ok=False;break
                previous=pid
            if not ok or not data.reachable.loc[previous,base]: continue
            delta=float(data.durations.loc[previous,base]);now+=pd.Timedelta(minutes=delta)
            if now>end: continue
            result.append({'sequence':seq,'start':start.isoformat(),'return':now.isoformat(),'arrivals':arrivals,
                'completion':completion,'km':km+float(data.distances.loc[previous,base]),'minutes':minutes+delta})
    return result


def solve_classical(scenario):
    started=time.perf_counter();data=scenario.inputs;config=scenario.config
    requests=scenario.requests.reset_index(drop=True);fleet=data.fleet.sort_values('VEHICULO_ID').reset_index(drop=True)
    stock=usable_stock(data,config);items=data.catalog.set_index('RECURSO_ID')
    penalty=float(config['penalizacion_faltante']);km_cost=float(config['costo_por_km']);minute_cost=float(config['costo_por_minuto'])
    if not all(math.isfinite(v) and v>=0 for v in [penalty,km_cost,minute_cost]) or penalty==0:
        raise ValueError('Costos no negativos y penalización positiva requeridos.')
    baseline=sum(penalty*float(r.PRIORIDAD_RECURSO)/100 for r in requests.itertuples() if r.CANTIDAD_PENDIENTE>0)
    # Variables y(v,tour) binarias; q(v,solicitud) enteras. Todos los tours vuelven al COER.
    pools=[enumerate_routes(scenario,v) for v in fleet.itertuples()]
    costs=[];upper=[];y={};q={}
    for v,pool in enumerate(pools):
        for k,tour in enumerate(pool):
            y[v,k]=len(costs);costs.append(km_cost*tour['km']+minute_cost*tour['minutes']);upper.append(1)
    for v in range(len(fleet)):
        visited=set(p for tour in pools[v] for p in tour['sequence'])
        for i,r in requests.iterrows():
            q[v,i]=len(costs)
            authorized=str(r.SOLICITUD_AUTORIZADA_SIMULADA).lower()=='true'
            allowed=not (str(r.REQUIERE_SOLICITUD_AUTORIZADA).lower()=='true') or authorized
            cap=int(r.CANTIDAD_PENDIENTE) if r.PUNTO_ID in visited and allowed else 0
            upper.append(cap)
            costs.append(-penalty*float(r.PRIORIDAD_RECURSO)/100/max(1,int(r.CANTIDAD_PENDIENTE)))
    rows=[];cols=[];values=[];lo=[];hi=[]
    def constraint(terms, lower=-np.inf, higher=np.inf):
        row=len(lo);lo.append(lower);hi.append(higher)
        for col,value in terms:
            if value: rows.append(row);cols.append(col);values.append(value)
    for v in range(len(fleet)):
        constraint([(y[v,k],1) for k in range(len(pools[v]))],higher=1)
        for dim,capacity in [('PESO_KG_UNIDAD','CAPACIDAD_KG'),('VOLUMEN_M3_UNIDAD','CAPACIDAD_M3')]:
            constraint([(q[v,i],float(items.loc[r.RECURSO_ID,dim])) for i,r in requests.iterrows()],higher=float(fleet.loc[v,capacity]))
        for pid,group in requests.groupby('PUNTO_ID'):
            visit=[(y[v,k],1) for k,tour in enumerate(pools[v]) if pid in tour['sequence']]
            # Toda parada operativa entrega al menos una unidad; no visitas fantasma.
            constraint(visit+[(q[v,i],-1) for i in group.index],higher=0)
            for i,r in group.iterrows():
                constraint([(q[v,i],1)]+[(col,-int(r.CANTIDAD_PENDIENTE)*coef) for col,coef in visit],higher=0)
    for i,r in requests.iterrows():
        constraint([(q[v,i],1) for v in range(len(fleet))],higher=int(r.CANTIDAD_PENDIENTE))
    for resource,group in requests.groupby('RECURSO_ID'):
        constraint([(q[v,i],1) for v in range(len(fleet)) for i in group.index],higher=stock[resource])
    solution=np.zeros(len(costs));status='ESCENARIO_VACIO' if not scenario.selected else 'SIN_PLAN_FACTIBLE_DE_ENTREGA';gap=None
    if costs and any(upper):
        matrix=coo_matrix((values,(rows,cols)),shape=(len(lo),len(costs))).tocsc()
        result=milp(np.array(costs),integrality=np.ones(len(costs)),bounds=Bounds(np.zeros(len(costs)),upper),
            constraints=LinearConstraint(matrix,lo,hi),options={'time_limit':float(config['limite_solver_segundos']),'mip_rel_gap':0.0})
        if result.x is None: raise RuntimeError(f'Solver sin solución verificable: {result.message}')
        if np.max(np.abs(result.x-np.rint(result.x)))>1e-5: raise RuntimeError('Solución no entera.')
        solution=np.rint(result.x)
        if (matrix@solution < np.array(lo)-1e-6).any() or (matrix@solution > np.array(hi)+1e-6).any(): raise RuntimeError('Solución viola restricciones del MILP.')
        status='OPTIMO_DEL_MODELO_RESTRINGIDO' if result.status==0 else 'FACTIBLE_CON_LIMITE_SOLVER'
        gap=float(result.mip_gap) if getattr(result,'mip_gap',None) is not None else None
    assignments=[];stops=[];routes=[];features=[]
    geos={(f['properties']['ORIGEN'],f['properties']['DESTINO']):f for f in data.geometries['features']}
    for v,vehicle in fleet.iterrows():
        chosen=[tour for k,tour in enumerate(pools[v]) if solution[y[v,k]]>.5]
        for tour in chosen:
            vehicle_rows=[]
            for i,r in requests.iterrows():
                qty=int(solution[q[v,i]])
                if qty:
                    item=items.loc[r.RECURSO_ID]
                    vehicle_rows.append({'SOLICITUD_ID':r.SOLICITUD_ID,'PROVINCIA':r.PROVINCIA,'PUNTO_ID':r.PUNTO_ID,
                        'RECURSO_ID':r.RECURSO_ID,'VEHICULO_ID':vehicle.VEHICULO_ID,'CANTIDAD_ASIGNADA':qty,'UNIDAD':r.UNIDAD,
                        'PESO_KG':qty*item.PESO_KG_UNIDAD,'VOLUMEN_M3':qty*item.VOLUMEN_M3_UNIDAD,
                        'ENTREGA_EN':tour['completion'][r.PUNTO_ID],'ESCENARIO_ID':scenario.scenario_id})
            assignments.extend(vehicle_rows)
            kg=sum(a['PESO_KG'] for a in vehicle_rows);volume=sum(a['VOLUMEN_M3'] for a in vehicle_rows)
            load_kg,load_volume=kg,volume
            for order,pid in enumerate(tour['sequence'],1):
                drop=[a for a in vehicle_rows if a['PUNTO_ID']==pid]
                after_kg=load_kg-sum(a['PESO_KG'] for a in drop);after_volume=load_volume-sum(a['VOLUMEN_M3'] for a in drop)
                stops.append({'VEHICULO_ID':vehicle.VEHICULO_ID,'ORDEN':order,'PUNTO_ID':pid,'PROVINCIA':drop[0]['PROVINCIA'],
                    'LLEGADA_EN':tour['arrivals'][pid],'ENTREGA_EN':tour['completion'][pid],
                    'CARGA_ANTES_KG':load_kg,'CARGA_DESPUES_KG':max(0,after_kg),'VOLUMEN_ANTES_M3':load_volume,'VOLUMEN_DESPUES_M3':max(0,after_volume)})
                load_kg,load_volume=after_kg,after_volume
            sequence=[config['origen_central'],*tour['sequence'],config['origen_central']]
            for order,(a,b) in enumerate(zip(sequence,sequence[1:]),1):
                feature=copy.deepcopy(geos[a,b]);feature['properties'].update({'VEHICULO_ID':vehicle.VEHICULO_ID,'ORDEN_TRAMO':order,'ESCENARIO_ID':scenario.scenario_id})
                features.append(feature)
            routes.append({'VEHICULO_ID':vehicle.VEHICULO_ID,'SECUENCIA':sequence,'SALIDA_EN':tour['start'],'RETORNO_EN':tour['return'],
                'DISTANCIA_KM':tour['km'],'DURACION_VIAL_MIN':tour['minutes'],'CARGA_INICIAL_KG':kg,'VOLUMEN_INICIAL_M3':volume,
                'CAPACIDAD_KG':float(vehicle.CAPACIDAD_KG),'CAPACIDAD_M3':float(vehicle.CAPACIDAD_M3)})
    assignments=pd.DataFrame(assignments,columns=ASSIGNMENT_COLUMNS);stops=pd.DataFrame(stops,columns=STOP_COLUMNS)
    unmet=requests.copy()
    totals=assignments.groupby('SOLICITUD_ID').CANTIDAD_ASIGNADA.sum() if len(assignments) else pd.Series(dtype=int)
    unmet['CANTIDAD_ASIGNADA']=unmet.SOLICITUD_ID.map(totals).fillna(0).astype(int)
    unmet['CANTIDAD_FALTANTE']=unmet.CANTIDAD_PENDIENTE.astype(int)-unmet.CANTIDAD_ASIGNADA
    unmet['COBERTURA']=np.where(unmet.CANTIDAD_PENDIENTE.astype(float)>0,unmet.CANTIDAD_ASIGNADA/unmet.CANTIDAD_PENDIENTE.astype(float).replace(0,np.nan),1.)
    prepared=scenario.coverage.set_index('PUNTO_ID').ESTADO.to_dict()
    routable={p for pool in pools for tour in pool for p in tour['sequence']}
    unmet['MOTIVO']=unmet.apply(lambda r:'CUBIERTA' if r.CANTIDAD_FALTANTE==0 else prepared[r.PUNTO_ID] if prepared[r.PUNTO_ID]!='PREPARADO_DEMO' else 'SIN_TOUR_DENTRO_DE_PLAZO_Y_HORIZONTE' if r.PUNTO_ID not in routable else 'STOCK_CAPACIDAD_COSTO_O_LIMITE_DE_PARADAS',axis=1) if len(unmet) else pd.Series(dtype=str)
    km=sum(r['DISTANCIA_KM'] for r in routes);minutes=sum(r['DURACION_VIAL_MIN'] for r in routes)
    unmet_penalty=sum(penalty*float(r.PRIORIDAD_RECURSO)/100*(1-float(r.COBERTURA)) for r in unmet.itertuples() if r.CANTIDAD_PENDIENTE>0)
    per_resource={}
    for resource,group in unmet.groupby('RECURSO_ID'):
        demand=int(group.CANTIDAD_PENDIENTE.sum());delivered=int(group.CANTIDAD_ASIGNADA.sum())
        per_resource[resource]={'solicitado':demand,'asignado':delivered,'faltante':demand-delivered,'stock_coer_utilizable':stock[resource],'saldo_coer':stock[resource]-delivered,'cobertura':delivered/demand if demand else 1.}
    metrics={'escenario_id':scenario.scenario_id,'estado_solver':status,'metodo':'MILP_SciPy_HiGHS_tours_enumerados',
        'provincias_seleccionadas':scenario.selected,'provincias_atendidas':sorted(set(assignments.PROVINCIA)),
        'provincias_sin_cobertura_vial':scenario.coverage.loc[~scenario.coverage.PREPARADO,'PROVINCIA'].tolist(),
        'vehiculos_utilizados':len(routes),'distancia_km':km,'duracion_vial_min':minutes,
        'penalizacion_faltantes':unmet_penalty,'costo_transporte':km_cost*km+minute_cost*minutes,
        'objetivo':unmet_penalty+km_cost*km+minute_cost*minutes,'objetivo_sin_entregas':baseline,
        'mip_gap':gap,'tours_candidatos':sum(map(len,pools)),'max_paradas_por_vehiculo':config['max_paradas_por_vehiculo'],
        'semilla_declarada':config['semilla'],'uso_aleatoriedad':False,'red_version':data.manifest['red_version'],
        'inputs_sha256':data.hashes,'recursos':per_resource,'segundos_computo':time.perf_counter()-started,
        'limites':['Un viaje por vehículo, retorno al COER, hasta tres paradas de entrega por viaje.',
            'Solo stock libre del COER confirmado al inicio y vigente durante todo el horizonte; no se recoge stock de hubs.',
            'Finalización de descarga dentro del plazo. La aptitud vehicular y accesos finales no están validados.',
            'Óptimo restringido a tours enumerados y al costo declarado; no certifica óptimo VRP general ni uso oficial.']}
    plan=Plan(scenario.scenario_id,assignments,unmet,stops,routes,{'type':'FeatureCollection','features':features},metrics)
    validate_plan(scenario,plan)
    return plan


def validate_plan(scenario,plan):
    """Reconciliación independiente de las restricciones físicas y temporales exportadas."""
    if plan.scenario_id!=scenario.scenario_id: raise ValueError('Resultado obsoleto: escenario diferente.')
    data=scenario.inputs;base=scenario.config['origen_central'];stock=usable_stock(data,scenario.config)
    requests=scenario.requests.set_index('SOLICITUD_ID');catalog=data.catalog.set_index('RECURSO_ID');fleet=data.fleet.set_index('VEHICULO_ID')
    a=plan.assignments
    if not set(a.PROVINCIA)<=set(scenario.selected) or not set(a.SOLICITUD_ID)<=set(requests.index): raise ValueError('Entrega en destino inactivo.')
    if len(a):
        if not a.CANTIDAD_ASIGNADA.gt(0).all() or not a.CANTIDAD_ASIGNADA.mod(1).eq(0).all(): raise ValueError('Entrega no entera o negativa.')
        for resource,group in a.groupby('RECURSO_ID'):
            if group.CANTIDAD_ASIGNADA.sum()>stock[resource]: raise ValueError('Inventario superado.')
        for rid,group in a.groupby('SOLICITUD_ID'):
            if group.CANTIDAD_ASIGNADA.sum()>int(requests.loc[rid,'CANTIDAD_PENDIENTE']): raise ValueError('Demanda superada.')
        for row in a.itertuples():
            request=requests.loc[row.SOLICITUD_ID]
            if row.PUNTO_ID!=request.PUNTO_ID or row.PROVINCIA!=request.PROVINCIA or row.RECURSO_ID!=request.RECURSO_ID: raise ValueError('Entrega sin correspondencia con solicitud.')
            if str(request.REQUIERE_SOLICITUD_AUTORIZADA).lower()=='true' and str(request.SOLICITUD_AUTORIZADA_SIMULADA).lower()!='true': raise ValueError('Solicitud sin autorización simulada.')
            if row.ESCENARIO_ID!=scenario.scenario_id: raise ValueError('Asignación obsoleta.')
            if pd.Timestamp(row.ENTREGA_EN)>pd.Timestamp(request.PLAZO_LOGISTICO_SIMULADO): raise ValueError('Entrega fuera de plazo.')
            if not math.isclose(row.PESO_KG,row.CANTIDAD_ASIGNADA*catalog.loc[row.RECURSO_ID,'PESO_KG_UNIDAD'],abs_tol=1e-6): raise ValueError('Peso inconsistente.')
            if not math.isclose(row.VOLUMEN_M3,row.CANTIDAD_ASIGNADA*catalog.loc[row.RECURSO_ID,'VOLUMEN_M3_UNIDAD'],abs_tol=1e-6): raise ValueError('Volumen inconsistente.')
    if len({r['VEHICULO_ID'] for r in plan.routes})!=len(plan.routes): raise ValueError('Vehículo duplicado.')
    route_vehicles={r['VEHICULO_ID'] for r in plan.routes}
    if set(plan.stops.VEHICULO_ID)!=route_vehicles: raise ValueError('Parada sin ruta.')
    if set(a.VEHICULO_ID)!=route_vehicles: raise ValueError('Entrega sin ruta o ruta sin carga.')
    expected_geometry=[]
    for route in plan.routes:
        expected_geometry.extend((route['VEHICULO_ID'],order,left,right) for order,(left,right) in enumerate(zip(route['SECUENCIA'],route['SECUENCIA'][1:]),1))
    actual=[(f['properties']['VEHICULO_ID'],f['properties']['ORDEN_TRAMO'],f['properties']['ORIGEN'],f['properties']['DESTINO']) for f in plan.geojson['features']]
    if actual!=expected_geometry: raise ValueError('Geometrías y tramos del plan no coinciden.')
    geos={(f['properties']['ORIGEN'],f['properties']['DESTINO']):f for f in data.geometries['features']}
    for feature in plan.geojson['features']:
        p=feature['properties'];source=geos[p['ORIGEN'],p['DESTINO']]
        if p['ESCENARIO_ID']!=scenario.scenario_id or p['RED_VERSION']!=data.manifest['red_version'] or feature['geometry']!=source['geometry'] or p['TRAMO_IDS']!=source['properties']['TRAMO_IDS']:
            raise ValueError('Geometría vial alterada u obsoleta.')
    for route in plan.routes:
        seq=route['SECUENCIA'];v=route['VEHICULO_ID'];vehicle=fleet.loc[v]
        if seq[0]!=base or seq[-1]!=base: raise ValueError('Origen o retorno incorrecto.')
        operational=plan.stops.loc[plan.stops.VEHICULO_ID.eq(v)].sort_values('ORDEN')
        if operational.PUNTO_ID.tolist()!=seq[1:-1] or set(seq[1:-1])!=set(a.loc[a.VEHICULO_ID.eq(v),'PUNTO_ID']): raise ValueError('Paradas y entregas inconsistentes.')
        kg=a.loc[a.VEHICULO_ID.eq(v),'PESO_KG'].sum();volume=a.loc[a.VEHICULO_ID.eq(v),'VOLUMEN_M3'].sum()
        if kg>vehicle.CAPACIDAD_KG+1e-6 or volume>vehicle.CAPACIDAD_M3+1e-6: raise ValueError('Capacidad vehicular superada.')
        now=max(pd.Timestamp(scenario.config['reloj_escenario']),pd.Timestamp(vehicle.DISPONIBLE_DESDE));km=minutes=0.
        if pd.Timestamp(route['SALIDA_EN'])!=now: raise ValueError('Salida fuera de disponibilidad.')
        for left,right in zip(seq,seq[1:]):
            if not data.reachable.loc[left,right]: raise ValueError('Tramo inalcanzable.')
            delta=float(data.durations.loc[left,right]);now+=pd.Timedelta(minutes=delta);minutes+=delta;km+=float(data.distances.loc[left,right])
            if right!=base:
                stop=operational.loc[operational.PUNTO_ID.eq(right)].iloc[0]
                if abs((now-pd.Timestamp(stop.LLEGADA_EN)).total_seconds())>1e-5: raise ValueError('Hora de llegada inconsistente.')
                drop=a.loc[a.VEHICULO_ID.eq(v)&a.PUNTO_ID.eq(right)]
                if not math.isclose(float(stop.CARGA_ANTES_KG),kg,abs_tol=1e-6) or not math.isclose(float(stop.VOLUMEN_ANTES_M3),volume,abs_tol=1e-6): raise ValueError('Carga a bordo inconsistente.')
                kg-=drop.PESO_KG.sum();volume-=drop.VOLUMEN_M3.sum()
                if not math.isclose(float(stop.CARGA_DESPUES_KG),kg,abs_tol=1e-6) or not math.isclose(float(stop.VOLUMEN_DESPUES_M3),volume,abs_tol=1e-6): raise ValueError('Descarga inconsistente.')
                now+=pd.Timedelta(minutes=float(vehicle.SERVICIO_MIN_POR_PARADA))
                if not drop.ENTREGA_EN.map(pd.Timestamp).eq(now).all(): raise ValueError('Entregas fuera de la parada.')
                if abs((now-pd.Timestamp(stop.ENTREGA_EN)).total_seconds())>1e-5: raise ValueError('Hora de servicio inconsistente.')
        end=min(pd.Timestamp(vehicle.DISPONIBLE_HASTA),pd.Timestamp(scenario.config['reloj_escenario'])+pd.Timedelta(hours=scenario.config['horizonte_horas']))
        if now>end or abs((now-pd.Timestamp(route['RETORNO_EN'])).total_seconds())>1e-5: raise ValueError('Retorno fuera de disponibilidad.')
        if not math.isclose(km,route['DISTANCIA_KM'],abs_tol=1e-6) or not math.isclose(minutes,route['DURACION_VIAL_MIN'],abs_tol=1e-6): raise ValueError('Costo de ruta inconsistente.')
    return True


def export_plan(scenario,plan):
    validate_plan(scenario,plan)
    folder=scenario.inputs.root/'data/results/phase4'/scenario.scenario_id
    folder.mkdir(parents=True,exist_ok=True)
    for name,frame in [('asignaciones',plan.assignments),('faltantes',plan.unmet),('paradas',plan.stops),('solicitudes',scenario.requests),('perfiles',scenario.profiles),('cobertura',scenario.coverage)]:
        frame.to_csv(folder/f'{name}.csv',index=False,encoding='utf-8-sig')
    for name,payload in [('metricas',plan.metrics),('rutas',plan.routes),('rutas.geojson',plan.geojson),('configuracion',scenario.config)]:
        target=folder/(name if name.endswith('.geojson') else name+'.json')
        target.write_text(json.dumps(payload,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    # Cada exportación, incluso la vacía, actualiza el puntero al escenario vigente.
    latest=folder.parent/'latest.json';tmp=latest.with_suffix('.tmp')
    tmp.write_text(json.dumps({'escenario_id':scenario.scenario_id,'carpeta':scenario.scenario_id},indent=2)+'\n');tmp.replace(latest)
    return folder
