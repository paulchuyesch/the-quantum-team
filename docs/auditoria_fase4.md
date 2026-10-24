# Auditoría del ZIP recibido y alcance de esta entrega

Fecha: 24 de octubre de 2026. Entrada: `qfire-cusco (3).zip`, 92 archivos. La solicitud directa es revisar y completar la parte clásica hasta notebook 04. El texto adjunto se usa como especificación de referencia, sin ampliar el trabajo a notebook 05 ni web.

## Inspección

Se revisaron las celdas de notebooks 01–03, `cleaning.py`, `geospatial.py`, `logistics.py`, configuraciones 02/03 y CSV, inventarios, donaciones, flota, matrices, geometrías, metadatos viales y las 40 pruebas originales.

Componentes conservados:

- Limpieza con trazabilidad, IDs estables, duplicados y separación de aptitud para mapeo.
- Histórico completo: 3.365 registros; vista geográfica: 3.363; 13 provincias, años 2022–2026.
- Magnitud histórica sin unidad: no se imputan hectáreas ni años 2020–2021.
- OSM dirigido, distancias y tiempos sobre el mismo camino, versión de red y geometrías de arcos.
- Demanda multirrecurso, unidades de carga, donaciones y conservación de inventario por centro.
- Coordenada COER provisional y receptores demo anteriores conservados como tales.

## Brechas comprobadas y tratamiento

| Hallazgo | Efecto | Tratamiento |
|---|---|---|
| No existía notebook 04 ni optimizador | Solo se generaban solicitudes y conexiones candidatas | Notebook ejecutable, MILP y exportaciones de planes |
| Cinco perfiles fijos y tres provincias inicialmente representadas en logística | No había selección arbitraria de las 13 | Catálogo dinámico desde historial y escenarios puros, sin entregas inactivas |
| Red 03 limitada al bbox del escenario de cinco receptores | Matrices insuficientes para otras provincias | Nueva cobertura OSM independiente, receptores documentados y estados explícitos |
| `read_history` fijaba 2022–2026 dentro de la función | Incorporar años requería editar implementación | Rango parametrizable, predeterminado 2020–2026, sin inventar registros |
| Donaciones demo se construyen a partir de demanda en fase 03 | Regenerarlas en cada selección cambiaría el stock disponible | Fase 04 reutiliza inventario fijo y confirma disponibilidad contra donaciones |
| Stock distribuido entre COER y hub | Agregarlo permitiría inventario teleportado | Modelo de depósito único: stock del hub no se consume |
| No se comprobaba expiración en un futuro plan de entrega | Riesgo de usar unidades que vencen antes de entregar | Solo lotes vigentes durante todo el horizonte, criterio conservador |
| No había asignación vinculada al ranking | Mostrar prioridad no cambiaba decisiones | Penalización ponderada por prioridad dentro del objetivo MILP |
| No había identidad para resultados cambiados | Posibilidad de mostrar un escenario anterior | SHA-256 de selección, perfiles, configuración y archivos; rechazo de plan obsoleto |

`docs/original_manifest.json` registra hashes del ZIP original. Las celdas de notebooks 01 y 03 se conservan; en notebook 02 solo se añade un color de respaldo para años nuevos. Sus salidas se vuelven a ejecutar para verificar la regresión. El CSV histórico raw original permanece byte por byte. `geospatial.read_history` admite rango configurable y la paleta del mapa añade un color de respaldo para años nuevos; los nuevos módulos no sustituyen limpieza ni logística de fase 03.

## Límites de aceptación

La selección y las solicitudes abarcan cualquier subconjunto. La atención efectiva depende de caminos dirigidos, stock, capacidad, plazo y límite de tres paradas por viaje. Se explicitan los faltantes. Las ubicaciones OSM acreditan referencias geográficas, no instalaciones, acceso seguro ni despacho real. La sede COER sigue provisional; no se sustituye por otra coordenada sin evidencia.

Los resultados y las pruebas de la entrega se documentan en `outputs/reports/`. No se afirma comparación cuántica, despliegue, aplicación web ni uso oficial.
