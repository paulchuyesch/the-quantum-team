"""Escenarios puros de fase 04. Seleccionar no equivale a confirmar un incendio."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import copy
import gzip
import hashlib
import json
import math
import pandas as pd
import numpy as np
from .cleaning import canonical, sha256_file
from .logistics import build_requests, inventory_at
from .prioritization import prioritize

PROFILE_COLUMNS = ['PROVINCIA', 'PUNTO_ID', 'INCENDIO_ID', 'BOMBEROS', 'PERSONAL_APOYO',
    'MAS_DE_DIEZ_BOMBEROS', 'PERSONAL_DESPLEGADO', 'FAUNA_AFECTADA', 'FAUNA_REQUIERE_ATENCION',
    'FRACCION_TRABAJO_MANUAL', 'MAGNITUD_RELATIVA', 'FACTOR_HUMO', 'URGENCIA_RELATIVA',
    'HERRAMIENTAS_NECESARIAS', 'PLAZO_HORAS', 'CENTRO_PREFERENTE_ID', 'ORIGEN']
REQUEST_COLUMNS = ['SOLICITUD_ID', 'ESCENARIO_ID', 'INCENDIO_ID', 'PUNTO_ID', 'PROVINCIA',
    'CENTRO_COORDINADOR_ID', 'CENTRO_PREFERENTE_ID', 'RECURSO_ID', 'UNIDAD', 'CANTIDAD_SOLICITADA',
    'CANTIDAD_ENTREGADA', 'CANTIDAD_PENDIENTE', 'PESO_PENDIENTE_KG', 'VOLUMEN_PENDIENTE_M3',
    'PRIORIDAD_BASE', 'PRIORIDAD_RECURSO', 'SOLICITADO_EN', 'PLAZO_LOGISTICO_SIMULADO',
    'REQUIERE_SOLICITUD_AUTORIZADA', 'SOLICITUD_AUTORIZADA_SIMULADA', 'ORIGEN']


def provinces_from_history(history):
    if 'PROVINCIA' not in history: raise ValueError('Falta PROVINCIA.')
    return sorted({canonical(x) for x in history.PROVINCIA.dropna().unique() if str(x).strip()})


def normalize_selection(history, selected):
    result=sorted({canonical(p) for p in selected})
    if not set(result)<=set(provinces_from_history(history)): raise ValueError('Selección con provincias desconocidas.')
    return result


def read_table(path):
    return pd.read_csv(path, encoding='utf-8-sig', keep_default_na=False)


def stable_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def integer(value, name):
    if isinstance(value, bool): raise ValueError(f'{name} debe ser entero no negativo.')
    try: number = float(value)
    except (TypeError, ValueError): raise ValueError(f'{name} debe ser entero no negativo.')
    if not math.isfinite(number) or number < 0 or not number.is_integer():
        raise ValueError(f'{name} debe ser entero no negativo.')
    return int(number)


def bounded(value, name, low, high):
    number = float(value)
    if not math.isfinite(number) or not low <= number <= high:
        raise ValueError(f'{name} debe estar entre {low} y {high}.')
    return number


@dataclass
class Inputs:
    root: Path
    config: dict
    history: pd.DataFrame
    receivers: pd.DataFrame
    catalog: pd.DataFrame
    inventory: pd.DataFrame
    donations: pd.DataFrame
    fleet: pd.DataFrame
    distances: pd.DataFrame
    durations: pd.DataFrame
    reachable: pd.DataFrame
    geometries: dict
    manifest: dict
    hashes: dict


@dataclass
class Scenario:
    scenario_id: str
    selected: list
    profiles: pd.DataFrame
    requests: pd.DataFrame
    coverage: pd.DataFrame
    config: dict
    inputs: Inputs


def load_inputs(root):
    root = Path(root).resolve()
    config = json.loads((root / 'config/phase4.json').read_text())
    history = read_table(root / 'data/processed/incendios_historicos.csv')
    history = history.loc[history.DEPARTAMENTO.map(canonical).eq('CUSCO')].copy()
    receivers = read_table(root / config['receptores'])
    receivers['PROVINCIA'] = receivers.PROVINCIA.map(canonical)
    if not np.isfinite(receivers[['LATITUD','LONGITUD']].to_numpy(dtype=float)).all() or not receivers.LATITUD.between(-18.6,.6).all() or not receivers.LONGITUD.between(-82.1,-68).all(): raise ValueError('Coordenadas de receptores inválidas.')
    if not receivers.PUNTO_ID.is_unique or receivers.PUNTO_ID.eq('').any(): raise ValueError('Receptores duplicados o vacíos.')
    if not set(receivers.PROVINCIA) <= set(provinces_from_history(history)): raise ValueError('Provincia receptora desconocida.')
    catalog = read_table(root / config['catalogo'])
    if not np.isfinite(catalog[['PESO_KG_UNIDAD','VOLUMEN_M3_UNIDAD','FACTOR_PRIORIDAD']].to_numpy(dtype=float)).all(): raise ValueError('Catálogo no finito.')
    if not catalog.RECURSO_ID.is_unique or catalog[['PESO_KG_UNIDAD','VOLUMEN_M3_UNIDAD','FACTOR_PRIORIDAD']].le(0).any().any():
        raise ValueError('Catálogo inválido.')
    inv, dons, fleet = [read_table(root / config[k]) for k in ['inventario','donaciones','flota']]
    if inv.duplicated(['CENTRO_ID','RECURSO_ID']).any(): raise ValueError('Inventario duplicado.')
    for col in ['CANTIDAD_DISPONIBLE','CANTIDAD_RESERVADA']:
        if any(integer(v,col) != float(v) for v in inv[col]): raise ValueError('Inventario inválido.')
    if inv.CANTIDAD_RESERVADA.gt(inv.CANTIDAD_DISPONIBLE).any(): raise ValueError('Reservas superiores al inventario.')
    if not inv.RECURSO_ID.isin(catalog.RECURSO_ID).all(): raise ValueError('Recurso de inventario desconocido.')
    if not np.isfinite(fleet[['CAPACIDAD_KG','CAPACIDAD_M3','SERVICIO_MIN_POR_PARADA']].to_numpy(dtype=float)).all(): raise ValueError('Flota no finita.')
    if not fleet.VEHICULO_ID.is_unique or not fleet.ORIGEN_RUTA_ID.eq(config['origen_central']).all() or not fleet.RETORNO_ID.eq(config['origen_central']).all():
        raise ValueError('Flota duplicada o sin origen/retorno COER.')
    if not fleet.POSICION_ACTUAL_ID.eq(config['origen_central']).all() or fleet[['CARGA_INICIAL_KG','CARGA_INICIAL_M3']].ne(0).any().any():
        raise ValueError('La fase 04 requiere vehículos vacíos inicialmente en COER.')
    if not (fleet[['CAPACIDAD_KG','CAPACIDAD_M3']].gt(0).all().all()): raise ValueError('Capacidad inválida.')
    matrices = []
    for name in ['distance_matrix','duration_matrix','reachability_matrix']:
        table = pd.read_csv(root / config['matrices'] / f'{name}.csv', index_col=0, encoding='utf-8-sig')
        if not table.index.is_unique or list(table.index) != list(table.columns): raise ValueError('Matriz no cuadrada o IDs duplicados.')
        matrices.append(table)
    distances, durations, reachable = matrices
    snap_path=Path(config['storage_folder'])/'snap_report.csv'
    snapped=read_table(root/snap_path).set_index('PUNTO_ID')
    points=read_table(root/config['puntos']).set_index('PUNTO_ID')
    for receiver in receivers.itertuples():
        if receiver.PUNTO_ID in durations.index:
            if receiver.PUNTO_ID not in snapped.index: raise ValueError('Matriz sin evidencia de asociación vial.')
            saved=snapped.loc[receiver.PUNTO_ID]
            if not math.isclose(float(receiver.LATITUD),float(saved.LATITUD),abs_tol=1e-8) or not math.isclose(float(receiver.LONGITUD),float(saved.LONGITUD),abs_tol=1e-8):
                raise ValueError('Coordenadas cambiaron: regenere puntos, extracto y matrices de fase 04.')
            point=points.loc[receiver.PUNTO_ID]
            if not math.isclose(float(receiver.LATITUD),float(point.LATITUD),abs_tol=1e-8) or not math.isclose(float(receiver.LONGITUD),float(point.LONGITUD),abs_tol=1e-8):
                raise ValueError('Registro de receptores y puntos logísticos no coincide.')
    if not distances.index.equals(durations.index) or not distances.index.equals(reachable.index): raise ValueError('Matrices incompatibles.')
    reachable = reachable.astype(str).apply(lambda s: s.str.lower().eq('true'))
    with gzip.open(root / config['geometrias'], 'rt', encoding='utf-8') as f: geometries=json.load(f)
    manifest=json.loads((root / config['manifiesto_red']).read_text())
    geo={(f['properties']['ORIGEN'],f['properties']['DESTINO']):f for f in geometries['features']}
    for a in distances.index:
        for b in distances.columns:
            d,t=float(distances.loc[a,b]),float(durations.loc[a,b])
            if reachable.loc[a,b]:
                if not math.isfinite(d+t) or min(d,t)<0: raise ValueError('Costo vial inválido.')
                if a != b:
                    f=geo.get((a,b))
                    if not f or len(f['geometry']['coordinates'])<2: raise ValueError('Falta geometría vial.')
                    p=f['properties']
                    if p['RED_VERSION']!=manifest['red_version'] or not math.isclose(d,p['DISTANCIA_KM'],abs_tol=1e-6) or not math.isclose(t,p['DURACION_MIN'],abs_tol=1e-6):
                        raise ValueError('Geometrías y matrices no coinciden.')
            elif math.isfinite(d) or math.isfinite(t): raise ValueError('Par inalcanzable con costo finito.')
    paths=['config/phase4.json','data/processed/incendios_historicos.csv']+[config[k] for k in ['receptores','catalogo','inventario','donaciones','flota','geometrias','manifiesto_red']]
    paths += [str(Path(config['matrices'])/f'{name}.csv') for name in ['distance_matrix','duration_matrix','reachability_matrix']]
    paths += [str(snap_path),config['puntos']]
    hashes={p:sha256_file(root/p) for p in paths}
    return Inputs(root,config,history,receivers,catalog,inv,dons,fleet,distances,durations,reachable,geometries,manifest,hashes)


def create_scenario(inputs, selected, overrides=None, receiver_choices=None, weights=None):
    config=copy.deepcopy(inputs.config)
    if weights is not None: config['prioridad_pesos']=copy.deepcopy(weights)
    selected=normalize_selection(inputs.history, selected)
    overrides={canonical(k):v for k,v in (overrides or {}).items()}
    choices={canonical(k):v for k,v in (receiver_choices or {}).items()}
    if not (set(overrides) | set(choices)) <= set(selected): raise ValueError('Configuración de una provincia inactiva.')
    rows, coverage, manual = [], [], {}
    for province in selected:
        candidates=inputs.receivers.loc[inputs.receivers.PROVINCIA.eq(province)].sort_values(['PREDETERMINADO','PUNTO_ID'],ascending=[False,True])
        choice=choices.get(province)
        if choice is not None: candidates=candidates.loc[candidates.PUNTO_ID.eq(choice)]
        receiver=candidates.iloc[0] if len(candidates) else None
        if choice is not None and receiver is None: raise ValueError('Receptor no pertenece a la provincia seleccionada.')
        pid=str(receiver.PUNTO_ID) if receiver is not None else 'SIN_RECEPTOR_'+province.replace(' ','_')
        ready=receiver is not None and pid in inputs.durations.index
        reason='PREPARADO_DEMO' if ready else 'SIN_COBERTURA_VIAL: verificar receptor y regenerar con scripts/prepare_phase4_network.py'
        if ready and not (inputs.reachable.loc[config['origen_central'],pid] and inputs.reachable.loc[pid,config['origen_central']]):
            ready=False;reason='SIN_CONEXION_DIRIGIDA_IDA_Y_RETORNO'
        coverage.append({'PROVINCIA':province,'PUNTO_ID':pid,'PREPARADO':bool(ready),'ESTADO':reason,
            'NOMBRE':str(receiver.NOMBRE) if receiver is not None else '',
            'FUENTE_COORDENADA':str(receiver.FUENTE_COORDENADA) if receiver is not None else ''})
        values=copy.deepcopy(config['perfil_predeterminado'])
        delta=overrides.get(province,{})
        if set(delta)-set(values)-{'SOLICITUDES_ADICIONALES'}: raise ValueError('Campos de perfil desconocidos.')
        values.update(delta)
        staff=integer(values['BOMBEROS'],'BOMBEROS');support=integer(values['PERSONAL_APOYO'],'PERSONAL_APOYO')
        if not isinstance(values['FAUNA_AFECTADA'],bool) or not isinstance(values['HERRAMIENTAS_NECESARIAS'],bool): raise ValueError('Use booleanos para fauna y herramientas.')
        animals=integer(values['ANIMALES_AFECTADOS'],'ANIMALES_AFECTADOS') if values['FAUNA_AFECTADA'] else 0
        work=bounded(values['FRACCION_TRABAJO_MANUAL'],'Trabajo manual',0,1)
        deadline=bounded(values['PLAZO_HORAS'],'Plazo',0,config['horizonte_horas'])
        rows.append(dict(zip(PROFILE_COLUMNS,[province,pid,'SIM-'+province.replace(' ','_'),staff,support,staff>10,staff+support,values['FAUNA_AFECTADA'],animals,
            work if values['HERRAMIENTAS_NECESARIAS'] else 0,bounded(values['MAGNITUD_RELATIVA'],'Magnitud',0,100),
            bounded(values['FACTOR_HUMO'],'Humo',0,5),bounded(values['URGENCIA_RELATIVA'],'Urgencia',0,1),
            values['HERRAMIENTAS_NECESARIAS'],deadline,config['origen_central'],'SIMULADO_NO_INCENDIO_ACTUAL'])))
        extra=values.get('SOLICITUDES_ADICIONALES',{})
        if set(extra)-set(inputs.catalog.RECURSO_ID): raise ValueError('Recurso manual desconocido.')
        manual[pid]={r:integer(q,'Solicitud manual') for r,q in extra.items()}
    profiles=prioritize(pd.DataFrame(rows,columns=PROFILE_COLUMNS),config['prioridad_pesos'])
    requests=build_requests(profiles,inputs.catalog,config) if len(profiles) else pd.DataFrame(columns=REQUEST_COLUMNS)
    for i,row in requests.iterrows():
        profile=profiles.loc[profiles.PUNTO_ID.eq(row.PUNTO_ID)].iloc[0]
        qty=int(row.CANTIDAD_SOLICITADA)+manual[row.PUNTO_ID].get(row.RECURSO_ID,0)
        item=inputs.catalog.set_index('RECURSO_ID').loc[row.RECURSO_ID]
        requests.loc[i,['CANTIDAD_SOLICITADA','CANTIDAD_PENDIENTE','PESO_PENDIENTE_KG','VOLUMEN_PENDIENTE_M3']]=[qty,qty,qty*item.PESO_KG_UNIDAD,qty*item.VOLUMEN_M3_UNIDAD]
        requests.loc[i,'PROVINCIA']=profile.PROVINCIA
        requests.loc[i,'PLAZO_LOGISTICO_SIMULADO']=(pd.Timestamp(config['reloj_escenario'])+pd.Timedelta(hours=profile.PLAZO_HORAS)).isoformat()
    identity=stable_hash({'selected':selected,'profiles':profiles.to_dict('records'),'manual':manual,'config':config,'inputs':inputs.hashes})
    requests['ESCENARIO_ID']=identity
    return Scenario(identity,selected,profiles,requests.reindex(columns=REQUEST_COLUMNS),pd.DataFrame(coverage,columns=['PROVINCIA','PUNTO_ID','PREPARADO','ESTADO','NOMBRE','FUENTE_COORDENADA']),config,inputs)


def usable_stock(inputs, config):
    """Conservador: solo lotes recibidos al inicio y vigentes durante todo el horizonte."""
    centers=pd.DataFrame({'CENTRO_ID': sorted(set(inputs.inventory.CENTRO_ID))})
    end=pd.Timestamp(config['reloj_escenario'])+pd.Timedelta(hours=config['horizonte_horas'])
    expiry=pd.to_datetime(inputs.donations.VENCE_EN.replace('',None),utc=True)
    current_ids=inputs.donations.DONACION_ID.isin(inventory_at(inputs.donations,centers,inputs.catalog,config['reloj_escenario'])[1].DOCUMENTO_ORIGEN_ID)
    lots=inputs.donations.loc[current_ids & (expiry.isna() | expiry.gt(end))]
    safe=lots.groupby(['CENTRO_ID','RECURSO_ID']).CANTIDAD.sum()
    stock={}
    for row in inputs.inventory.itertuples():
        if row.CENTRO_ID==config['origen_central']:
            stock[row.RECURSO_ID]=max(0,min(int(row.CANTIDAD_DISPONIBLE-row.CANTIDAD_RESERVADA),int(safe.get((row.CENTRO_ID,row.RECURSO_ID),0))))
    return {r:stock.get(r,0) for r in inputs.catalog.RECURSO_ID}
