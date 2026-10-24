# QFire Cusco

**Ampliación entregada: fase 05 cuántica.** Ver [README_CUANTICA.md](README_CUANTICA.md) y `notebooks/05_optimizacion_cuantica_comparacion.ipynb`. La notebook 04 se conserva como referencia clásica. El contenido siguiente documenta la entrega original.

Planificación de entrega terrestre de recursos a brigadas que atienden incendios forestales en el departamento de Cusco.

El proyecto organizará donaciones recibidas, solicitudes por recurso y vehículos disponibles para planificar entregas a puntos de recepción de las brigadas. Los bloqueos viales permitirán recalcular recorridos pendientes desde la posición de cada vehículo. Esta entrega implementa **las fases 01 a 04: preparación de datos, red vial, recursos logísticos y optimización clásica**. COER Cusco es el origen central del escenario; se admiten transferencias y donaciones en centros locales propuestos, como la OGRD de Paruro.

## Inicio rápido

Requiere Python 3.11 o posterior; se recomienda Python 3.12. Descomprimir el proyecto completo y abrir una terminal en esta carpeta, donde está este README.

```bash
python -m pip install -r requirements.txt
jupyter lab
```

Abrir `notebooks/01_data_cleaning_incendios.ipynb`, seleccionar el kernel Python del entorno instalado y ejecutar las celdas en orden. Después abrir los notebooks 02, 03 y `notebooks/04_asignacion_ruteo_prioridades.ipynb`. También se puede abrir la carpeta completa en VS Code y usar la extensión Jupyter.

Para generar los datos sin abrir Jupyter:

```bash
python scripts/run_cleaning.py
```

## Organización

| Ruta | Uso |
|---|---|
| `data/raw/` | Archivo aportado, conservado byte por byte y con su fuente documentada |
| `data/processed/` | Historial normalizado, muestra utilizable para EDA y reportes de calidad |
| `data/geo/` | Red vial, tramos, historial geográfico y puntos logísticos del escenario |
| `data/simulated/` | Escenarios de donaciones, solicitudes y flota de la fase 03 |
| `data/optimization/` | Matrices viales de fase 02 y `phase3/` para la cobertura ampliada |
| `data/results/phase4/` | Asignaciones, faltantes, paradas, geometrías y métricas por escenario SHA-256 |
| `notebooks/` | Análisis y documentación por fases |
| `src/qfire_cusco/` | Funciones reutilizables de limpieza, red vial e inventario multirrecurso |
| `scripts/` | Ejecución directa de las fases 01 a 04 y verificación de notebooks |
| `outputs/figures/` | Figuras descriptivas producidas por el notebook |
| `outputs/maps/` | Mapa interactivo del historial y del escenario |
| `config/` | Puntos, centros, perfiles, recursos y reglas editables de los escenarios |
| `outputs/reports/` | Resumen de limpieza y manifiesto del archivo fuente |
| `docs/` | Arquitectura, diccionario y guía para GitHub |
| `tests/` | Casos de calidad y trazabilidad |

## Datos incluidos

La entrada es `data/raw/incendios_Cusco_2022_2026.csv`: el archivo suministrado por la usuaria, previamente filtrado y depurado, almacenado aquí sin cambios en su contenido. No es una descarga nueva ni el histórico nacional completo. El servicio MINAM documentado para su procedencia es [Base de datos de Incendios](https://geoservidorperu.minam.gob.pe/arcgis/rest/services/CFOI_Dashboard_mensuales_pruebas/MapServer/0).

| Año | Registros de entrada |
|---|---:|
| 2022 | 1.291 |
| 2023 | 590 |
| 2024 | 669 |
| 2025 | 722 |
| 2026 | 93 |
| Total | 3.365 |

El último registro de emergencia presente en este archivo es del **26 de agosto de 2026**. No se afirma que la información cubra todos los incendios ocurridos después ni que sea un servicio en vivo.

El SHA-256 del archivo se conserva en `data/raw/source_metadata.json` y se vuelve a calcular al ejecutar la limpieza. No se inventa una fecha de descarga original que no está documentada.

## Salidas de la fase 01

| Archivo | Contenido |
|---|---|
| `data/processed/incendios_historicos.csv` | Registros únicos dentro de Cusco y del rango inclusivo 2022–2026 |
| `data/processed/incendios_para_mapeo.csv` | Registros confirmados con fecha coherente y coordenadas plausibles para iniciar el EDA |
| `data/processed/incendios_con_observaciones.csv` | Registros que requieren interpretar o revisar algún atributo |
| `data/processed/registros_fuera_de_ambito.csv` | Filas excluidas por departamento o año, con su motivo |
| `data/processed/duplicados_retirados.csv` | Duplicados exactos retirados por esta ejecución y su trazabilidad |
| `data/processed/data_quality_report.csv` | Reglas, denominadores, recuentos y porcentajes |
| `outputs/reports/source_manifest.json` | Fuente, hash, parámetros y límites de interpretación |
| `outputs/reports/limpieza_resumen.json` | Resumen y conteos por año |

`incendios_con_observaciones.csv` y `incendios_para_mapeo.csv` son vistas del historial, no tablas que deban concatenarse entre sí.

### Interpretación de la magnitud

En la entrada, **3.136 registros tienen `COB_AFECTA = 0`** y 229 tienen un valor positivo. La unidad de ese campo no está confirmada en los metadatos examinados. Por ello se preservan los valores y `AREA_HA` queda vacía hasta verificar la unidad. Un cero no se utiliza automáticamente como un incendio de tamaño cero.

La aptitud para mapeo es un control de calidad del historial, no una certificación de acceso vial, actividad actual del incendio o ubicación de un punto receptor. La fase 02 debe contrastar la ubicación y definir los puntos logísticos correspondientes.

## Secuencia de trabajo

| Fase | Estado en este paquete | Objetivo |
|---|---|---|
| 01 — Limpieza | Implementada | Historial y reporte de calidad |
| 02 — Red vial y puntos logísticos | Implementada | Red OSM, puntos simulados, mapa y costos |
| 03 — Recursos, donaciones y solicitudes | Implementada | Origen COER, centro Paruro, inventario por centro, pedidos y flota |
| 04 — Asignación y ruteo clásicos | Implementada | Cantidades, vehículos, rutas dirigidas, prioridades y faltantes |
| 05 — QAOA y benchmark con Qiskit | Implementada | Optimización cuántica variacional (Qiskit 2.6.1 / QAOA) y benchmark con MILP |
| 06 — Bloqueos y replanificación | Diseñada | Recalcular con carga, posición y entregas vigentes |

Los notebooks de las fases futuras se crearán cuando se implemente cada fase. Los registros históricos no se consideran incidentes simultáneamente activos.

## Usar la fase 02

Abrir el notebook 02 o ejecutar:

```bash
python scripts/run_geospatial.py
```

El mapa está en `outputs/maps/02_historial_y_logistica.html`. Abrirlo en el navegador; sus teselas y bibliotecas JavaScript requieren Internet. Los gráficos PNG y el cálculo sobre la red guardada están disponibles sin consultar un servidor de rutas.

El historial conserva 3.363 registros utilizables de las 13 provincias. La red vial incluida cubre **el área del escenario**, con un acopio y tres receptores **simulados** en Cusco, Anta, Urubamba y Calca. No se presenta como red de todo el departamento ni como ubicaciones receptoras acreditadas. Las conexiones dibujadas todavía no son un plan de reparto.

Para editar el escenario, modificar `config/puntos_logisticos_demo.csv` y `config/phase2.json`. Si la nueva configuración necesita otra cobertura, el código solicita ampliarla; no reutiliza un grafo insuficiente sin avisar. La guía completa está en [docs/phase2.md](docs/phase2.md).

Los datos viales proceden de [OpenStreetMap](https://www.openstreetmap.org/copyright), mediante [Geofabrik Perú](https://download.geofabrik.de/south-america/peru.html). Se incluye su extracto y procedencia. Los tiempos se estiman con supuestos por clase y etiquetas disponibles; no incluyen tráfico en vivo o restricciones de giro basadas en relaciones. No certifican transitabilidad o capacidad de acceso de un camión concreto.

## Usar la fase 03

Abrir `notebooks/03_recursos_donaciones_solicitudes.ipynb` o ejecutar:

```bash
python scripts/run_logistics.py
```

La demo incluye un origen lógico **COER_CUSCO**, un centro local propuesto en Paruro, cinco receptores, seis recursos y tres vehículos. Todas las solicitudes se coordinan desde el COER y todos los vehículos comienzan allí. El inventario local permanece en su centro; una transferencia debe restarse del origen y sumarse al destino.

Los pedidos distinguen agua según personal, herramientas según trabajo manual y paquetes veterinarios según fauna que requiere atención. La prioridad considera magnitud, personal, fauna y urgencia. Se incluyen donaciones recibidas y prometidas, y casos de disponibilidad para comprobar que solo el stock habilitado pueda utilizarse.

**Los perfiles, cantidades, flota, plazos y sitios operativos son simulados. La sede exacta del COER y los puntos receptores no están verificados.** La entidad reportante del historial permanece separada del origen logístico. Los cinco registros históricos no se consideran incendios activos reales ni simultáneos.

Esta fase amplía la cobertura vial hacia Paruro, Accha y Huanoquite sin modificar la red de fase 02. Los datasets están en `data/simulated/phase3/`, las matrices en `data/optimization/phase3/` y el mapa en `outputs/maps/03_centros_y_recursos.html`. Las conexiones son candidatas; el plan de reparto se implementará en fase 04. Ver [docs/phase3.md](docs/phase3.md) para editar y ampliar el escenario.

## Usar la fase 04 clásica

Abrir `notebooks/04_asignacion_ruteo_prioridades.ipynb` o ejecutar:

```bash
python scripts/run_classical.py --provincias CANAS ESPINAR
python scripts/run_classical.py --provincias ANTA CALCA URUBAMBA PARURO --perfiles config/ejemplo_perfiles_fase4.json
```

Sin `--provincias` exporta un escenario vacío. Las 13 provincias se obtienen de los datos procesados. Hay receptores de localidades OSM documentados para cada provincia; los receptores demo anteriores siguen disponibles como alternativas. La red ampliada de fase 04 conserva los archivos de fases anteriores. Un destino no preparado mantiene sus solicitudes y muestra una limitación explícita.

El MILP decide cantidades y tours, con inventario fijo del COER, capacidad en kg/m³, plazos y retorno. La prioridad entra en la penalización por necesidad no cubierta. Se usan únicamente donaciones recibidas/liberadas y lotes vigentes durante todo el horizonte; el stock de hubs no se consume. **Simplificación: un viaje por vehículo y hasta tres paradas de entrega.** El óptimo, si se prueba, corresponde a ese modelo restringido.

Los resultados se guardan en `data/results/phase4/<sha256>/` y `latest.json` identifica el escenario vigente. El notebook genera mapa y gráficos. No se incluye aplicación web ni notebook 05. Instalación, configuración, regeneración vial y límites en [docs/phase4.md](docs/phase4.md). Auditoría en [docs/auditoria_fase4.md](docs/auditoria_fase4.md).

## Usar la fase 05 cuántica con Qiskit

Esta fase implementa la optimización cuántica variacional mediante **Qiskit (v2.6.1)** para resolver la selección y ruteo de brigadas logísticas ante emergencias de incendios forestales.

### ¿Cómo se utiliza Qiskit en el proyecto?

- **Modelado Cuántico:** El problema logístico se formula como un problema de optimización binaria sin restricciones (**QUBO**) y se traduce a un **Hamiltoniano de Ising** de 16 cúbits (14 rutas candidatas + 2 cúbits de holgura).
- **Circuito QAOA con `QuantumCircuit`:** En `src/qfire_cusco/optimization_quantum.py`, la función `qiskit_circuit(problem, theta)` construye explícitamente el circuito cuántico con compuertas Hadamard ($H$), operadores de costo $R_Z(2\gamma h_i)$ y $R_{ZZ}(2\gamma J_{ij})$, y operadores mezcladores $R_X(2\beta)$.
- **Simulación y Validación de Estados:** En `scripts/run_quantum.py` y `tests/test_quantum.py`, se utiliza `qiskit.quantum_info.Statevector` para verificar matemáticamente que la evolución del estado cuántico coincide exactamente con la solución analítica, logrando una **fidelidad cuántica del 100% ($F = 1.0$)**.
- **Exportación en OpenQASM 3:** El circuito compilado (16 cúbits lógicos, 68 compuertas) se exporta usando `qiskit.qasm3` a `data/results/phase5/circuito_qaoa.qasm` y en diagrama ASCII a `data/results/phase5/circuito_qaoa.txt`, dejándolo listo para su despacho directo a procesadores cuánticos (QPU) de IBM Quantum.

### Ejecución del pipeline cuántico

```bash
python -m pip install -r requirements-quantum.txt
python scripts/run_quantum.py
```

Para visualizar el circuito, analizar la convergencia de COBYLA y comparar los resultados frente al solver clásico MILP (HiGHS), abrir el notebook interactivo `notebooks/05_optimizacion_cuantica_comparacion.ipynb`. Guía completa y detalles científicos en [README_CUANTICA.md](README_CUANTICA.md).

## Comprobación

Desde la raíz del proyecto:

```bash
python -m unittest discover -s tests -v
```

Las pruebas originales y las nuevas cubren limpieza, sentidos viales, selección de las 13 provincias, origen COER, demanda, prioridad efectiva, stock fijo, capacidades, plazos y resultados obsoletos. El contrato del selector se comprueba sobre los 8.192 subconjuntos; escenarios representativos ejecutan el modelo completo. Resultados en `outputs/reports/classical_validation.json` y `outputs/reports/notebooks_execution.json`.

## GitHub

La guía está en [docs/github_setup.md](docs/github_setup.md). Al subir por la web, cargar **el contenido descomprimido** para que `data`, `notebooks`, `outputs`, `src` y `README.md` queden directamente en la raíz del repositorio.

La fuente pública debe conservarse atribuida a MINAM. No se adjunta una licencia de reutilización para los datos que no haya sido verificada.
