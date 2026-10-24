# Fase 03: logística desde COER Cusco

Abrir `notebooks/03_recursos_donaciones_solicitudes.ipynb` en el proyecto completo o ejecutar `python scripts/run_logistics.py`. No se requiere descargar carreteras para el escenario incluido. Las entradas son deterministas: iguales configuraciones y fuentes producen las mismas tablas.

## Reglas de operación del escenario

COER_CUSCO es el origen de las rutas, posición inicial de los tres vehículos y centro coordinador de todas las solicitudes. Es una regla indicada por la usuaria, no un atributo inferido del historial. En una replanificación futura, un vehículo que ya salió continuará desde su posición vigente.

HUB_PARURO es un centro local propuesto vinculado a la OGRD de la Municipalidad Provincial de Paruro. Puede recibir transferencias desde el COER, aportar donaciones recibidas allí y abastecer receptores. Se admite entrega central directa como alternativa. Los centros locales no se denominan automáticamente COER. COES MININTER, cuando aparece como reportante, no identifica por sí solo un almacén físico.

`ENTIDAD_REPORTANTE` conserva exactamente el valor del historial, incluso cuando está vacío. Se almacena por separado de `CENTRO_COORDINADOR_ID`. Los cinco incidentes son una selección histórica utilizada en un escenario ficticio simultáneo: no hay confirmación de actividad actual ni pronóstico de expansión.

## Configuración editable

| Archivo | Qué cambiar |
|---|---|
| `config/phase3.json` | Reloj con zona horaria, horizonte, coeficientes de demanda, pesos de prioridad y cobertura vial |
| `config/centros_fase3.csv` | Dependencia de centros respecto al COER y entidad local de referencia |
| `config/puntos_logisticos_fase3.csv` | Ubicaciones y procedencia de coordenadas, roles y referencias históricas |
| `config/perfiles_fase3.csv` | Personal, fauna, trabajo manual, humo, magnitud relativa, urgencia y centro preferente |
| `config/recursos_fase3.csv` | Presentaciones, pesos, volúmenes y factor de prioridad por recurso |

Para añadir otro centro deben agregarse su fila en centros y su punto en puntos, ambos con el mismo ID; después pueden vincularse receptores mediante `CENTRO_PREFERENTE_ID`. Los pedidos por fórmulas se implementan en `demand_quantities` de `src/qfire_cusco/logistics.py`; añadir un recurso nuevo requiere definir también su demanda. Los perfiles y coeficientes incluidos son demostrativos; las solicitudes reales deberán ingresarse y verificarse como tales.

## Coordenadas y red ampliada

La coordenada central es provisional: **no representa una sede oficial del COER verificada**. Paruro usa el nodo de localidad OSM 2314231210; Accha el nodo 2314230985 y Huanoquite el 588509149. Son centros de localidades, no instalaciones receptoras o puntos seguros acreditados. Los receptores restantes conservan los puntos demostrativos de la fase 02. Todas las ubicaciones operativas permanecen sin validar.

Esta fase incluye 22.508 nodos y 58.712 arcos dirigidos en `data/geo/phase3/red_vial_escenario.graphml.gz`, con fuente comprimida en `data/raw/osm_vias_phase3.osm.gz`. La procedencia está en `data/raw/osm_phase3_metadata.json`. Los siete puntos quedan a menos de 50 m de su nodo asociado; eso comprueba la asociación geométrica, no el acceso final. La versión del grafo acompaña puntos, pares y geometrías de caminos.

Las matrices de `data/optimization/phase3/` corresponden a esta red ampliada. No se mezclan con las matrices de fase 02. Cada km y minuto proviene del mismo camino de menor tiempo estimado. No hay tráfico, cierres en vivo, comprobación de gálibo/peso de cada vehículo ni restricciones de giro OSM basadas en relaciones. Un punto nuevo fuera de cobertura exige ampliar el extracto; el programa no reutiliza silenciosamente una red insuficiente.

Para actualizar el extracto desde un PBF de Perú obtenido de Geofabrik, instalar `requirements-osm-refresh.txt` y ejecutar desde la raíz:

```bash
python scripts/build_osm_extract.py /ruta/peru-latest.osm.pbf --config config/phase3.json --output data/raw/osm_vias_phase3.osm.gz --metadata data/raw/osm_phase3_metadata.json
python scripts/run_logistics.py
```

El PBF nacional no se incluye en el repositorio. El grafo y extracto del escenario sí están incluidos.

## Demanda y prioridad

Agua aumenta con personal; herramientas aumentan con la fracción de trabajo manual; paquetes veterinarios aumentan con fauna que requiere atención. Menos fauna no se interpreta como terreno desértico. Las fórmulas del notebook redondean hacia arriba y conservan cantidades por recurso, peso y volumen. Todos los coeficientes, contenidos unitarios y plazos son supuestos de simulación, no normas de consumo o criterios clínicos.

Los productos sanitarios se representan mediante paquetes cerrados solicitados, sin composición ni dosificación. Las autorizaciones del ejemplo también son simuladas. Una integración real necesitará la solicitud autorizada correspondiente.

La prioridad base combina magnitud relativa (35%), personal (25%), fauna (25%) y urgencia (15%), normalizados dentro del escenario. El factor de recurso ajusta esa prioridad. Las cantidades pendientes son independientes de esa puntuación. En fase 04 el objetivo deberá usar cobertura o fracciones de pedido satisfechas, evitando que una gran cantidad de botellas domine por sumar unidades incompatibles.

## Inventario y conservación

Las donaciones cuentan solo si fueron recibidas antes del reloj, liberadas y no vencidas en ese instante. Las prometidas, futuras, en cuarentena y vencidas se conservan como registros pero no ingresan al stock disponible. No se supone que un recurso se traslada por pertenecer al mismo escenario.

`movimientos_inventario.csv` contiene los ingresos habilitados y referencias únicas a sus donaciones. `inventario_por_centro.csv` es la vista resultante por centro y recurso. La función de transferencia usada en la comprobación resta y suma en una operación, respeta reservas y rechaza faltantes o IDs repetidos. La transferencia de prueba no se exporta como operación del escenario.

La brecha agregada compara cada recurso por separado. Puede haber stock suficiente en términos agregados y falta local por conectividad, tiempos o capacidad. Esta tabla no constituye una asignación.

## Preparación para la fase 04

Los nueve arcos logísticos son candidatos. No se han elegido vehículos, cantidades ni secuencias de entrega. La siguiente fase requiere un problema de recogidas, entregas y transferencias con inventario por centro; un CVRP de depósito único sin transferencias no representa todo este escenario.

Se deberán conservar carga y recursos en cada parada, reservar stock una sola vez, limitar peso y volumen, respetar ventanas y tiempos de servicio, disponibilidad y vigencia a la entrega, y permitir redistribuir solo después de recibir una transferencia. Todos los vehículos incluidos comienzan y retornan al COER; una descarga seguida de recogida en Paruro debe reflejar ambos movimientos y el cambio de carga. La decisión de pasar por Paruro debe compararse con la entrega directa.

La fase 06 usará reportes de bloqueo sobre la misma versión vial; conservará entregas confirmadas, carga a bordo y posiciones actuales. Esta fase no implementa aún esos formularios ni despachos.

## Salidas y comprobación

`data/simulated/phase3/` contiene once tablas: puntos, centros, catálogo, perfiles, solicitudes, donaciones, inventario, movimientos, flota, arcos y brechas. `outputs/maps/03_centros_y_recursos.html` permite explorar el escenario; sus recursos web requieren conexión. Los tres PNG de fase 03 pueden revisarse sin conexión.

`outputs/reports/phase3_summary.json` guarda conteos, supuestos y hashes de las entradas. `notebook03_validation.json` distingue la ejecución secuencial de celdas de una ejecución mediante kernel. La validación en este entorno usa Python con espacio de nombres compartido y captura de salidas porque los sockets de kernel están restringidos; el notebook mantiene un kernelspec normal para abrirlo en Jupyter.

Ejecutar `python -m unittest discover -s tests -v`. Las 40 pruebas del paquete incluyen origen central, trazabilidad histórica, diferencias de demanda, inventario por centro, exclusión de donaciones no disponibles, conservación en transferencias y prevención de doble conteo, además de limpieza y costos viales.

Referencia institucional consultada: [INDECI, centros de operaciones de emergencia](https://portal.indeci.gob.pe/coen/centros-de-operacion-de-emergencia/). Fuente vial: [OpenStreetMap](https://www.openstreetmap.org/copyright) mediante [Geofabrik Perú](https://download.geofabrik.de/south-america/peru.html), atribución ODbL 1.0. No se afirma que los centros propuestos estén acreditados como almacenes.
