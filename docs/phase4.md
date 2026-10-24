# Fase 04: asignación y ruteo clásicos

## Ejecución

Python 3.11 o posterior. Desde la carpeta completa del proyecto:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
jupyter lab
```

Abrir `notebooks/04_asignacion_ruteo_prioridades.ipynb` y ejecutar en orden. Las fases anteriores y sus datos ya están incluidos. Para regenerar todo: `python scripts/execute_notebooks.py`. El runner usa el intérprete activo y un kernel temporal, sin instalar kernels globales.

CLI sin selección (exporta un plan vacío):

```bash
python scripts/run_classical.py
```

Casos:

```bash
python scripts/run_classical.py --provincias URUBAMBA
python scripts/run_classical.py --provincias CANAS ESPINAR
python scripts/run_classical.py --provincias CALCA ANTA CHUMBIVILCAS
python scripts/run_classical.py --provincias CANAS ESPINAR "LA CONVENCION" PAUCARTAMBO
python scripts/run_classical.py --provincias ANTA CALCA URUBAMBA PARURO --perfiles config/ejemplo_perfiles_fase4.json
```

`--perfiles` acepta un JSON provincia -> campos. No admite campos de provincias inactivas. `--receptores` acepta provincia -> PUNTO_ID y `--pesos` los cuatro pesos que suman uno. Un perfil omitido usa `perfil_predeterminado` de `config/phase4.json`.

## Perfiles

- `BOMBEROS`, `PERSONAL_APOYO`: enteros no negativos; se suman para demanda personal.
- `FAUNA_AFECTADA`: booleano; si es falso, `ANIMALES_AFECTADOS` no genera veterinaria automática.
- `ANIMALES_AFECTADOS`: entero no negativo.
- `MAGNITUD_RELATIVA`: 0–100, sin unidad física.
- `URGENCIA_RELATIVA`, `FRACCION_TRABAJO_MANUAL`: 0–1.
- `FACTOR_HUMO`: 0–5.
- `HERRAMIENTAS_NECESARIAS`: booleano; falso elimina herramientas automáticas.
- `PLAZO_HORAS`: 0–horizonte; la descarga debe terminar antes de ese plazo.
- `SOLICITUDES_ADICIONALES`: recurso -> unidades enteras no negativas; se suman a las automáticas.

Cambiar cantidad, selección o pesos crea un escenario nuevo. El dato histórico no se transforma en incendio activo; los IDs `SIM-*` identifican la simulación y no referencias históricas simultáneas.

## Modelo y límites

MILP con SciPy/HiGHS. Se enumeran todos los órdenes de visita factibles de hasta tres receptores por vehículo, sobre las matrices dirigidas. Se eligen conjuntamente tour y cantidades enteras, con máximo un tour por vehículo. La función objetivo suma costo por km, costo por minuto vial y penalización por fracción de demanda no cubierta, ponderada por prioridad y factor del recurso. Los valores están en `config/phase4.json`.

Un estado de óptimo corresponde al modelo restringido a esos tours. No demuestra óptimo del VRP general. Las capacidades se verifican en kg y m³; cada tour parte cargado del COER, solo descarga y retorna vacío. Cada parada entrega al menos una unidad. Se permiten entregas parciales y diferentes vehículos al mismo receptor, sin exceder demanda total.

El stock se limita simultáneamente a inventario libre (disponible menos reservado) y donaciones elegibles. Solo lotes recibidos, liberados al inicio y vigentes durante todo el horizonte. La exclusión de lotes que vencen durante el horizonte es conservadora. No se cuentan futuras recepciones ni promesas. **El stock no se recalcula a partir de la demanda seleccionada.**

Depósito único: el inventario local de Paruro se conserva sin gastar. No hay recogidas, transferencias, recargas ni viajes múltiples en esta fase. Todos los vehículos parten del punto COER heredado de la demo, cuya ubicación oficial no está verificada. Los nuevos receptores son referencias de localidades OSM, no almacenes certificados. No se modelan tráfico, bloqueos, restricciones de giro por relaciones, ni compatibilidad vial de vehículos específicos. La conducción y el último acceso son aproximaciones sin validación operativa.

## Cobertura y regeneración

`config/receptores_fase4.csv` conserva receptores por provincia y permite alternativas. `config/puntos_logisticos_fase4.csv` contiene COER y todos los receptores para generar matrices; ambos registros deben actualizarse conjuntamente. Cada provincia del historial siempre puede seleccionarse aunque no tenga red; entonces se conservan pedidos/faltantes y se informa el error, sin rutas inventadas.

Para regenerar desde un PBF público de Geofabrik ya descargado:

```bash
python -m pip install -r requirements-osm-refresh.txt
python scripts/build_osm_extract.py /ruta/peru-latest.osm.pbf --config config/phase4.json --output data/raw/osm_vias_phase4.osm.gz --metadata data/raw/osm_phase4_metadata.json
python scripts/prepare_phase4_network.py
```

Se conserva el hash del PBF, extracto, manifiesto y red. Si un punto queda a más de 300 m del nodo vial, se excluye de las matrices y se informa su falta de preparación. No se presenta un tramo de acceso recto como carretera. Fases 02/03 mantienen sus grafos y matrices.

## Resultados

`data/results/phase4/<sha256>/` contiene `perfiles.csv`, `solicitudes.csv`, `cobertura.csv`, `asignaciones.csv`, `faltantes.csv`, `paradas.csv`, `rutas.json`, `rutas.geojson`, `metricas.json` y `configuracion.json`. Los recursos conservan sus unidades. `paradas.csv` registra carga antes/después de descargar. El GeoJSON conserva IDs de arcos y versión de red.

`latest.json` apunta a la última exportación, incluso vacía. Los escenarios anteriores conservan su propia carpeta y su ID; un consumidor debe cargar el puntero vigente y comprobar la identidad antes de mostrar resultados. `validate_plan` rechaza otro escenario y concilia cantidades, stock, capacidades, conexiones, cronología y solicitudes. El notebook produce gráficos y un mapa HTML etiquetado con el hash; no es una aplicación de operación.

## Verificación

```bash
python -m unittest discover -s tests -v
python scripts/execute_notebooks.py
```

El informe de ejecución registra kernels reales y celdas completadas. El contrato del selector se verifica sobre 8.192 subconjuntos; casos operativos representativos ejecutan el optimizador completo. Esto no equivale a resolver 8.192 MILP. La semilla declarada es 42; el algoritmo no utiliza aleatoriedad. Se guardan hashes para distinguir datos y configuración y la brecha del solver cuando corresponde.

El notebook 05, QAOA, la página Streamlit y la replanificación quedan fuera de esta entrega, solicitada hasta notebook 04 clásico.
