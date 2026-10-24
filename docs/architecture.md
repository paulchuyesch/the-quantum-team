# Arquitectura del prototipo: entrega de recursos ante incendios forestales en Cusco

## 1. Objetivo y alcance acordados

Planificar el transporte terrestre de recursos recibidos por donación desde centros de acopio hasta puntos de recepción de brigadas asociadas a incendios forestales en el departamento de Cusco. Priorizar las solicitudes pendientes según magnitud, personal desplegado, fauna que requiere atención y urgencia, y recalcular las entregas pendientes cuando se reporte un bloqueo vial.

El producto responde: **qué recurso enviar, cuánto, a qué punto de recepción, en qué vehículo, en qué orden y por qué carreteras**.

El escenario tiene COER_CUSCO como origen central y coordinador por requisito de la usuaria. Todos los vehículos comienzan allí. Un centro local propuesto en Paruro admite transferencias, recogida de donaciones y redistribución. El inventario conserva su ubicación física: una transferencia resta en el origen y suma en el destino. Solo las donaciones recibidas, liberadas y vigentes se incorporan al stock disponible. La entidad reportante histórica permanece separada del centro coordinador y no se sustituye por COER. Los puntos del incendio y de entrega son entidades diferentes: las coordenadas históricas de un incendio no se convierten automáticamente en un destino accesible para un vehículo.

La cobertura territorial comprende todo Cusco. Cada ejecución trabaja con los incidentes y solicitudes seleccionados para ese escenario, no con todos los registros históricos simultáneamente.

## 2. Referencias revisadas y adaptación

Los notebooks suministrados de Q-Med siguen esta secuencia:

1. Limpieza y control de calidad de RENIPRESS.
2. EDA geoespacial y matrices viales con OSRM.
3. Fuente logística y demanda simulada de medicamentos.
4. Ruteo capacitado y comparación de métodos.
5. QUBO y benchmark QAOA de una subruta de tres destinos.

Las dos copias suministradas de la fase 3, con sufijos `(1)` y `(2)`, tienen el mismo contenido de celdas. Se conserva la separación por fases, sustituyendo IPRESS y medicamentos por incidentes, solicitudes, inventario de recursos y puntos de recepción.

El cambio de ruteo principal es mantener una red de tramos que podamos modificar. Las consultas actuales de los notebooks al servicio OSRM no incluyen los bloqueos introducidos por nuestra interfaz. Para el prototipo se propone una red de OpenStreetMap almacenada localmente, preparada con OSMnx y consultada con NetworkX. Las geometrías del mapa, los costos y las rutas se obtendrán de la misma versión de esa red.

## 3. Base histórica de partida

Archivo disponible: `incendios_Cusco_2022_2026.csv`.

| Año | Registros |
|---|---:|
| 2022 | 1.291 |
| 2023 | 590 |
| 2024 | 669 |
| 2025 | 722 |
| 2026 | 93 |
| Total | 3.365 |

La fecha más reciente de emergencia presente en esta descarga es 2026-08-26. Esto no permite inferir que después de esa fecha no ocurrieron otros incendios.

En 3.136 registros, `COB_AFECTA` vale cero; 229 tienen un valor positivo. Se preserva el valor original. Cero no se convierte automáticamente en una medida confirmada de magnitud, y cualquier conversión a hectáreas exige confirmar primero la unidad de la fuente.

El historial aporta ubicaciones, fechas y atributos reportados. No contiene inventario de donaciones, solicitudes de brigadas, flota, carga actual de vehículos o reportes de carreteras bloqueadas. Esas entradas se simularán de forma reproducible para la demostración o se ingresarán mediante formularios identificando su origen.

## 4. Datasets y contratos

Los CSV son tablas del prototipo; no es necesario llenarlos todos manualmente. Los notebooks generan los derivados y la interfaz registra pedidos, movimientos, bloqueos y entregas.

### A. Historial y escenario

| Archivo | Una fila representa | Campos principales | Origen |
|---|---|---|---|
| `incendios_historicos.csv` | Un registro histórico depurado | `incendio_id`, identificadores de fuente, departamento, provincia, distrito, localidad, fecha original e ISO, latitud, longitud, cobertura original, observaciones de calidad | MINAM, derivado de la base descargada |
| `incendios_escenario.csv` | Un incidente incluido en un escenario | `escenario_id`, `incidente_id`, `incendio_id`, estado del escenario, magnitud, unidad, fecha de magnitud, origen de magnitud, prioridad | Selección del historial y datos reportados o simulados |
| `escenarios.json` | Configuración de cada experimento | ID, semilla, reloj del escenario, IDs seleccionados, fuentes, supuestos, versión de red y política de prioridad | Configuración reproducible |

`incendio_id` es estable y trazable al registro de origen. `incidente_id` identifica su utilización en un escenario. Las fechas simuladas y la magnitud simulada no sobrescriben las observaciones históricas. Los campos simulados se identifican por campo y fuente, no solo mediante una etiqueta general del archivo.

### B. Recursos y operación logística

| Archivo | Una fila representa | Campos principales |
|---|---|---|
| `puntos_logisticos.csv` | Un acopio o punto de recepción | `punto_id`, `escenario_id`, tipo, nombre, `incidente_id` opcional, latitud, longitud, nodo vial asociado, origen/validación de ubicación |
| `recursos.csv` | Un tipo y presentación de recurso | `recurso_id`, nombre, unidad, peso por unidad, volumen por unidad y origen de esas medidas |
| `movimientos_inventario.csv` | Un movimiento recibido, cargado, entregado o corregido | `movimiento_id`, escenario, fecha/hora, recurso, cantidad, ubicación de origen y destino, tipo, referencia de donación/entrega, origen del dato |
| `solicitudes.csv` | Una línea de un pedido de recurso | `linea_id`, `pedido_id`, escenario, incidente, punto de recepción, recurso, cantidad solicitada, fecha/hora, estado y origen del dato |
| `vehiculos.csv` | Un vehículo en un escenario | `vehiculo_id`, capacidades en kg y m³, ubicación actual, fecha de ubicación, estado, disponibilidad y origen del dato |

Ejemplos de unidades: botella de una presentación concreta, caja de un contenido definido o herramienta individual. Agua, mascarillas y palas no se suman como si ocuparan o pesaran lo mismo. La demanda conserva cantidades por recurso; la capacidad usa el peso y volumen correspondientes. Un peso o volumen faltante debe completarse como supuesto explícito o como dato verificado antes de planificar esa carga.

Las ubicaciones del inventario pueden ser un acopio, un vehículo o un punto de entrega. Así, cargar un vehículo reduce el stock del acopio y aumenta la carga a bordo. Entregar reduce la carga y registra la recepción. Los eventos se identifican para evitar contabilizar dos veces la misma donación o entrega. Solo las donaciones recibidas forman parte del stock físico disponible; las promesas permanecen pendientes.

La carga actual, el inventario por ubicación y la demanda pendiente son vistas calculadas a partir de estos registros y de las reservas del plan vigente. No se mantienen totales manuales desconectados de sus movimientos.

### C. Red vial y bloqueos

| Archivo | Contenido | Campos o claves principales |
|---|---|---|
| `red_vial_Cusco.graphml` | Grafo dirigido base de OpenStreetMap | Nodos viales, arcos, longitudes, sentidos, atributos de acceso y tiempos estimados |
| `tramos_viales.geojson` | Geometrías seleccionables en el mapa | `red_version`, `tramo_id`, `u`, `v`, `key`, geometría, longitud |
| `bloqueos.csv` | Asociación de un reporte con cada tramo afectado | `bloqueo_id`, escenario, versión de red, tramo, sentido, inicio, fin, motivo, fuente y estado |

Un bloqueo puede afectar varios tramos. Un cierre total debe deshabilitar los arcos afectados en ambos sentidos cuando existan; un cierre parcial solo los sentidos indicados. No se elimina permanentemente la red original: la red operativa se deriva del conjunto de bloqueos vigentes.

Las velocidades y tiempos imputados se etiquetan como estimaciones. La ausencia de un reporte no certifica la transitabilidad. El alcance geográfico de la descarga debe conservar las conexiones necesarias para evitar cortar artificialmente rutas que crucen una frontera administrativa.

### D. Salidas y registro de decisiones

| Archivo | Contenido |
|---|---|
| `asignaciones.csv` | Reservas por plan, línea de solicitud, recurso, cantidad y vehículo |
| `rutas_paradas.csv` | Plan, vehículo, orden de paradas, tiempos estimados, kilómetros y estado de la parada |
| `rutas.geojson` | Geometría del recorrido calculado, asociada al plan y a los tramos de su versión de red |
| `entregas.csv` | Confirmaciones por línea de solicitud, recurso, cantidad, vehículo, fecha/hora y plan |
| `planes.json` | Versiones del plan, escenario, versión de red, instante de cálculo, método y métricas |

La demanda pendiente se calcula como cantidad solicitada menos entregas confirmadas. Las entregas parciales están permitidas y quedan visibles. Las reservas impiden que dos vehículos reciban el mismo stock; al sustituir un plan se liberan únicamente las reservas pendientes que correspondan.

## 5. Prioridad y optimización

La política de fase 03 combina magnitud relativa (35%), personal desplegado (25%), fauna (25%) y urgencia (15%), con pesos configurables. Todos esos perfiles son simulados en el escenario incluido. Una magnitud histórica desconocida conserva ese estado; no se transforma COB_AFECTA en hectáreas sin verificar su unidad. Agua escala con personal, herramientas con trabajo manual y paquetes veterinarios solicitados con fauna. Las fórmulas son demostrativas y reemplazables por solicitudes verificadas.

La política debe tener efectos en dos decisiones:

1. **Asignación:** atender las solicitudes de mayor prioridad con los recursos realmente disponibles. La prioridad no crea necesidades que nadie haya solicitado. Las cantidades que no puedan cubrirse se muestran como faltantes.
2. **Programación de entregas:** favorecer tiempos de llegada menores para los pedidos de mayor prioridad y, después, reducir recorridos y costos. Minimizar únicamente kilómetros no garantiza atender antes al incendio mayor.

Las comparaciones de cobertura usan fracciones de pedido satisfechas por recurso o métricas normalizadas: no se comparan directamente cien mascarillas con cien palas como si representaran el mismo servicio.

Las restricciones incluyen stock por recurso y centro, capacidad de carga y volumen en cada parada, disponibilidad y posición de vehículos, precedencia de llegada de transferencias antes de redistribuir, recogidas y descargas, plazos, sentidos/acceso vial, cierres vigentes y conectividad con los puntos de recepción. La replanificación de un vehículo ya cargado conserva su carga; cambiarla requiere una parada y un movimiento en un acopio.

Se construirá primero una solución clásica verificable. Para escenarios pequeños se puede calcular una referencia exacta; para escenarios mayores se utilizará una heurística sin atribuirle optimalidad no demostrada.

## 6. Secuencia propuesta de notebooks

| Notebook | Trabajo | Salidas principales |
|---|---|---|
| `01_data_cleaning_incendios.ipynb` | Leer originales, preservar IDs y procedencia, normalizar fechas/texto, filtrar Cusco 2022–2026, revisar duplicados, coordenadas y magnitud | Historial limpio, registros con incidencias de calidad y reporte de limpieza |
| `02_eda_geospatial_vial.ipynb` | EDA del historial, preparar/cachear red vial, definir acopio y puntos receptores del escenario, revisar acceso y asociación a la red | Grafo, tramos y puntos logísticos |
| `03_recursos_donaciones_solicitudes.ipynb` | Crear catálogo y escenario reproducible de donaciones recibidas, solicitudes, flota y prioridades | Entradas logísticas y configuración del escenario |
| `04_asignacion_ruteo_prioridades.ipynb` | Construir costos desde la red vigente, asignar existencias, cargar vehículos y planificar entregas | Reservas, rutas, paradas, faltantes y métricas clásicas |
| `05_qaoa_qubo_benchmark.ipynb` | Comparar QAOA y un método clásico en el mismo subproblema pequeño, con idénticos nodos, costos y restricciones | QUBO, muestras, factibilidad, brecha y métricas |
| `06_bloqueos_replanificacion.ipynb` | Ensayar cierres, reapertura, camiones en recorrido y entregas parciales | Planes antes/después, comparación de recorridos y registros de replanificación |

Los notebooks documentan y prueban el trabajo. Las funciones reutilizables de inventario, red vial, optimización y replanificación irán en módulos Python compartidos para que la interfaz pueda invocarlas sin ejecutar manualmente todas las celdas.

## 7. Evento de bloqueo y recálculo automático

1. El operador registra en el mapa un reporte y selecciona los tramos afectados. Un clic aproximado se asocia a tramos concretos para poder identificar qué se cerró.
2. El sistema guarda el reporte con su hora y fuente, genera una nueva versión operativa de la red y marca como desactualizados los planes afectados.
3. Se recalculan conectividad y costos entre los puntos necesarios. No basta cambiar una celda de distancia entre dos brigadas: un mismo tramo puede formar parte de muchas conexiones.
4. Cada vehículo conserva su posición registrada o simulada, carga a bordo y entregas ya realizadas. Los recorridos ejecutados no se vuelven a planificar desde el almacén.
5. Se calcula el desvío hacia el destino pendiente. Cuando el cierre afecta el orden o la asignación viable, se reoptimiza el resto del plan respetando la carga, las reservas y las entregas confirmadas.
6. Si no existe un camino admisible, el punto queda identificado como inaccesible bajo los datos actuales. No se sustituye por una línea recta ni por un costo finito inventado.
7. Se publica una nueva versión del plan y se actualizan ruta, kilómetros, tiempo estimado y faltantes en el mapa. Un cálculo que termine para una versión vieja de la red no reemplaza un plan calculado para una versión más reciente.

Al reabrir un tramo, se reconstruye su habilitación a partir de todos los reportes aún vigentes. Cerrar y abrir un reporte no debe anular otro bloqueo activo sobre el mismo tramo.

La ubicación del vehículo no se conoce automáticamente por tener un mapa: en el prototipo se avanzará por nodos de la ruta de forma simulada o se ingresará una posición. Una integración GPS sería una fuente adicional identificada.

## 8. Lugar de la parte cuántica

La fase 5 puede conservar la idea del notebook anterior: seleccionar una subruta pequeña y construir su QUBO. La asignación de recursos y la planificación completa siguen teniendo una descripción explícita de qué resolvió cada método.

La subruta que ensaya QAOA debe usar la misma red vigente que su referencia clásica. Si se declara que optimiza prioridades, su función de costo debe incluirlas; un QUBO que solo minimiza kilómetros compara exclusivamente ese objetivo, con una asignación y prioridades fijadas previamente.

Los resultados se validan por factibilidad antes de incorporarlos a un plan. La respuesta a un bloqueo debe disponer de una solución clásica aunque el experimento cuántico tarde o no encuentre una solución válida. Se reportan calidad, factibilidad, tiempo de ejecución y límites de tamaño. La simulación no constituye por sí misma evidencia de ventaja cuántica.

## 9. Primera demostración verificable

El escenario incluido usa COER_CUSCO, un centro local propuesto en Paruro, tres vehículos y cinco incidentes seleccionados del historial, con magnitud relativa y necesidades simuladas. El mapa permitirá observar el inventario, las solicitudes y los recorridos.

Se verificará que:

- una donación recibida incremente únicamente el recurso y acopio correspondientes;
- una carga no exceda stock, peso o volumen;
- los pedidos prioritarios afecten la asignación y programación según la política elegida;
- un bloqueo retire los tramos correspondientes del cálculo y del recorrido dibujado;
- el nuevo plan parta de la posición vigente del vehículo y conserve entregas y carga;
- una desconexión produzca un faltante inaccesible, no una ruta artificial;
- confirmar una entrega dos veces no duplique los suministros recibidos;
- reabrir un reporte no quite otros cierres activos;
- la comparación clásica–QAOA use la misma instancia y versión de red.

## 10. Próximo paso

Las fases 01, 02 y 03 están implementadas. La fase 03 añade recursos, solicitudes, donaciones, inventario por centro, flota y una red ampliada hacia Paruro. Los detalles y contratos de archivos están en `docs/phase3.md`. La siguiente fase asignará recursos escasos y construirá rutas que admitan recogidas, entregas y transferencias; después se comparará una subinstancia con QAOA y se implementarán bloqueos. La fase 01 conserva las magnitudes sin unidad verificada como pendientes de interpretación.

## Fuentes y materiales

- MINAM, servicio de la base histórica usada: https://geoservidorperu.minam.gob.pe/arcgis/rest/services/CFOI_Dashboard_mensuales_pruebas/MapServer/0
- Notebooks adjuntos de Q-Med: fases 1 a 5, incluidos los dos ejemplares de la fase 3.
- OSMnx, documentación de red vial y almacenamiento: https://osmnx.readthedocs.io/en/stable/user-reference.html
- NetworkX, caminos mínimos: https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.shortest_paths.generic.shortest_path.html
- NetworkX, eliminación de arcos de un MultiDiGraph: https://networkx.org/documentation/stable/reference/classes/generated/networkx.MultiDiGraph.remove_edges_from.html
- OSRM, contrato de API y opciones de consulta: https://project-osrm.org/docs/v5.24.0/api/

Documento de diseño preparado el 24 de octubre de 2026. Las fases 01–03 están implementadas en este paquete. Las fases 04–06 y la interfaz de replanificación permanecen como diseño. Los datos originales suministrados y los derivados de limpieza están incluidos.

La ubicación del COER es provisional y las referencias locales de OSM no certifican almacenes ni acceso operativo. Las entradas simuladas no son reportes actuales. Ver `docs/phase3.md` para la separación de fuentes y el estado de implementación.


## Implementación clásica de fase 04

`scenario.py` carga provincias dinámicamente, valida perfiles y receptores, reutiliza demanda de `logistics.py` y crea identidad SHA-256. `prioritization.py` aplica pesos configurables. `optimization_classical.py` enumera tours factibles, selecciona rutas y cantidades mediante MILP, reconcilia restricciones y exporta un plan. `scripts/run_classical.py` y notebook 04 consumen el mismo código. No se regenera stock al cambiar selección.

Fase 04 utiliza su propio extracto OSM, grafo, geometrías y matrices, con receptores de las 13 provincias y alternativas anteriores. El modelo inicial usa solo COER y conserva stock local sin consumir. El contrato completo y las simplificaciones están en `docs/phase4.md`.
