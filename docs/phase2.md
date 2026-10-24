# Fase 02: mapa, puntos logísticos y red vial

## Datos y alcance

El EDA usa `data/processed/incendios_para_mapeo.csv`: 3.363 registros del historial preparado, de 13 provincias. Los dos registros no confirmados permanecen en el historial principal de la fase 01.

La demostración vial contiene un acopio y tres receptores simulados. Son ubicaciones configuradas explícitamente, distintas de las coordenadas de los registros de incendios relacionados. Se utiliza la red OSM del área que necesitan esos puntos, más un margen. El resto del departamento sigue disponible en el historial.

## Archivos editables

| Archivo | Qué cambiar |
|---|---|
| `config/puntos_logisticos_demo.csv` | Acopio, receptores, coordenadas y vínculo con registros históricos |
| `config/phase2.json` | ID del escenario, margen de extracción, máximo alejamiento del nodo y velocidades supuestas |

`VALIDADO_OPERATIVAMENTE=False` conserva el carácter demostrativo. Una asociación a un nodo vial, aunque esté cerca, no verifica el acceso final al punto. Las matrices empiezan y terminan en nodos de la red; no incluyen un acceso ficticio en línea recta.

## Salidas

| Archivo | Unidad y significado |
|---|---|
| `data/geo/red_vial_escenario.graphml.gz` | Grafo dirigido completo del escenario, con versión de topología y costos |
| `data/geo/tramos_viales.geojson.gz` | Todos los arcos, con geometría, `TRAMO_ID`, `U`, `V`, `KEY`, `RED_VERSION` y costos |
| `data/geo/incendios_historicos.geojson` | Todos los registros históricos utilizables para EDA |
| `data/geo/puntos_logisticos.csv` | Puntos configurados, nodo asociado, distancia al nodo y origen del dato |
| `data/geo/snap_report.csv` | Revisión de separación entre punto y nodo vial, en metros |
| `data/geo/resumen_provincia_anio.csv` | Recuentos descriptivos del historial |
| `data/geo/network_manifest.json` | Cobertura, fuente, hash del extracto, supuestos, componentes y versión |
| `data/optimization/distance_matrix.csv` | Kilómetros de los caminos elegidos por menor tiempo estimado |
| `data/optimization/duration_matrix.csv` | Minutos de esos mismos caminos |
| `data/optimization/reachability_matrix.csv` | Conectividad dirigida entre puntos |
| `data/optimization/pares_viales.csv` | Costos, conectividad y distancia geodésica de control |
| `data/geo/rutas_pares.geojson` | Geometrías de las conexiones y lista de tramos utilizados |
| `outputs/maps/02_historial_y_logistica.html` | Mapa interactivo |
| `outputs/figures/02_*.png` | Figuras estáticas del EDA y de la red |
| `outputs/reports/phase2_summary.json` | Resumen de resultados |
| `outputs/reports/phase2_validation.json` | Método y límites de la verificación de esta entrega |

Los archivos comprimidos se leen directamente desde el código. Para inspeccionar manualmente un GeoJSON comprimido se puede usar `gzip.open(..., 'rt', encoding='utf-8')` y `json.load(...)`.

Los pares sin conexión tienen costo infinito y una marca de no alcanzable. La siguiente fase debe tratarlos como conexiones prohibidas. No rellenar esos valores con ceros ni sustituirlos por Haversine.

## Mapa

Abrir `outputs/maps/02_historial_y_logistica.html` con Internet para cargar las teselas y bibliotecas de visualización. El mapa inicia en el escenario. Activar capas por año y pulsar **Ver todo el historial** para explorar Cusco completo. **Ver escenario** vuelve a la zona de los receptores.

La capa visible de vías principales se reduce para mantener el HTML manejable. El grafo y el GeoJSON comprimido conservan los 46.542 arcos del extracto preparado, incluidos caminos secundarios locales utilizados por el ruteo. Las conexiones de referencia no equivalen a un plan con asignaciones de suministros.

## Origen vial y reproducción

El grafo se preparó a partir de un extracto de Perú de Geofabrik, derivado de OpenStreetMap. `data/raw/osm_extract_metadata.json` contiene URL, metadatos de descarga, área, hash PBF y hash XML. Se conserva el XML de vías del escenario para reconstruir el grafo sin descargar de nuevo el PBF nacional.

La API Overpass no estuvo disponible desde el entorno de preparación. Se utilizó la descarga PBF oficial de Geofabrik y una extracción reproducible de vías mediante Pyosmium. No se sustituyeron carreteras por líneas inventadas.

Para una cobertura nueva usando un PBF ya descargado:

```bash
python -m pip install -r requirements-osm-refresh.txt
python scripts/build_osm_extract.py /ruta/peru-latest.osm.pbf
python scripts/run_geospatial.py
```

Como alternativa, `python scripts/run_geospatial.py --allow-download` permite consultar Overpass si el servicio está accesible. El PBF nacional no se incluye en el paquete ni se debe subir al repositorio; el extracto local y el grafo son suficientes para repetir el escenario incluido.

## Preparación para bloqueos

`TRAMO_ID` identifica un arco dirigido y está ligado a `RED_VERSION`. Un reporte de bloqueo deberá referenciar esos identificadores. El cierre de una vía en ambos sentidos puede requerir varios arcos, especialmente en calzadas separadas: no basta inferir siempre el sentido inverso como `(v,u,key)`.

Las rutas incluyen sus IDs de arco, lo que permite revisar si un cierre afecta una conexión. La fase 06 registrará los reportes, construirá la red operativa y recalculará. Esta fase todavía no implementa el formulario de bloqueo ni la replanificación de vehículos en recorrido.

## Supuestos que permanecen visibles

- Red actual de OSM, no reconstrucción de carreteras de 2022–2026.
- Ubicaciones del escenario simuladas y accesos finales sin validar.
- Velocidades por clase configurables y etiquetadas como supuestos; tiempos sin tráfico en vivo.
- Se respetan los sentidos presentes en el grafo. Las relaciones OSM de restricciones de giro no se modelan en este prototipo.
- El historial no aporta solicitudes ni cantidades de donaciones. Estas se incorporarán en la fase 03.

## Atribución

Datos viales: © OpenStreetMap contributors, bajo [ODbL 1.0](https://www.openstreetmap.org/copyright). Extracto de [Geofabrik Perú](https://download.geofabrik.de/south-america/peru.html). Los archivos viales derivados conservan esta atribución. Esta referencia no asigna una licencia no verificada al dataset MINAM ni al código del proyecto.
