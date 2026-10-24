"""Construir cobertura fase 04 desde el extracto local, preservando fases 02/03.

Si cambia config/receptores_fase4.csv, regenere el extracto antes:
python scripts/build_osm_extract.py /ruta/peru-latest.osm.pbf --config config/phase4.json --output data/raw/osm_vias_phase4.osm.gz --metadata data/raw/osm_phase4_metadata.json
python scripts/prepare_phase4_network.py
"""
from pathlib import Path
import gzip,json,sys
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from qfire_cusco.geospatial import prepare_network,snap_points,build_costs


def main():
    config=json.loads((ROOT/'config/phase4.json').read_text())
    points=pd.read_csv(ROOT/config['puntos'],encoding='utf-8-sig')
    graph,manifest,mode=prepare_network(ROOT,points,config)
    snapped=snap_points(graph,points,config['max_snap_m'])
    folder=ROOT/config['storage_folder'];folder.mkdir(parents=True,exist_ok=True)
    snapped.to_csv(folder/'snap_report.csv',index=False,encoding='utf-8-sig')
    valid=snapped.loc[snapped.SNAP_OK].copy()
    if config['origen_central'] not in set(valid.PUNTO_ID): raise ValueError('COER fuera del umbral de asociación a la red.')
    distances,times,reachable,pairs,routes=build_costs(graph,valid)
    # Dos ubicaciones distintas pueden asociarse al mismo nodo. El tramo vial es
    # cero y no representa el acceso final entre instalaciones.
    present={(f['properties']['ORIGEN'],f['properties']['DESTINO']) for f in routes['features']}
    by_id=valid.set_index('PUNTO_ID')
    for a in distances.index:
        for b in distances.columns:
            if a!=b and reachable.loc[a,b] and (a,b) not in present:
                if int(by_id.loc[a,'NODO_VIAL'])!=int(by_id.loc[b,'NODO_VIAL']): raise ValueError('Falta geometría de un camino no trivial.')
                xy=[float(by_id.loc[a,'LONGITUD_NODO']),float(by_id.loc[a,'LATITUD_NODO'])]
                routes['features'].append({'type':'Feature','geometry':{'type':'LineString','coordinates':[xy,xy]},'properties':{
                    'ORIGEN':a,'DESTINO':b,'DISTANCIA_KM':0.,'DURACION_MIN':0.,'RED_VERSION':manifest['red_version'],
                    'TRAMO_IDS':[],'MISMO_NODO_VIAL':True,'ACCESO_ENTRE_UBICACIONES_VALIDADO':False}})
    opt=ROOT/config['matrices'];opt.mkdir(parents=True,exist_ok=True)
    for name,table in [('distance_matrix',distances),('duration_matrix',times),('reachability_matrix',reachable)]:
        table.to_csv(opt/f'{name}.csv',encoding='utf-8-sig')
    pairs.to_csv(opt/'pares_viales.csv',index=False,encoding='utf-8-sig')
    (ROOT/config['geometrias']).write_bytes(gzip.compress(json.dumps(routes,ensure_ascii=False).encode(),mtime=0))
    print(json.dumps({'modo':mode,'nodos':len(graph),'arcos':graph.number_of_edges(),'puntos':len(points),'snaps_aptos':len(valid),'max_snap_m':float(snapped.DISTANCIA_A_NODO_M.max()),'red_version':manifest['red_version']},indent=2))

if __name__=='__main__':main()
