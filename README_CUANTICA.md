# Ampliación cuántica de QFire Cusco — fase 05

La notebook 4 adjunta es clásica MILP/HiGHS. La notebook 05 incorpora asignación clásica y selección de rutas con QAOA simulado por vector de estado; se preservan las notebooks 01–04. No se ejecutó hardware cuántico.

## Resultado ejecutado

- Plan principal predefinido: p=3, semilla 42, 4.096 shots, hasta 250 evaluaciones COBYLA.
- Objetivo completo: 3821.502833003; mismo valor óptimo MILP del adjunto.
- Distancia: 248.758394316 km; tiempo vial: 291.416888082 min; dos vehículos.
- QUBO: 14 tours y 2 bits de holgura, 16 qubits. Asignación previa independiente del MILP.
- Diez semillas por profundidad: p=1 logró 10/10 óptimos; p=3 logró 9/10. Peor brecha total p=3: 1,1683 %.
- El método híbrido simulado tarda más que el MILP local y no mejora el objetivo; no se demuestra ventaja cuántica.
- Todas las corridas p=3 agotaron el presupuesto de evaluaciones. Se distinguen factibilidad del plan y convergencia del optimizador.

## Reproducción

Requiere Python 3.12 y el proyecto completo descomprimido. Desde esta carpeta:

```bash
python -m pip install -r requirements-quantum.txt
python scripts/run_quantum.py
python -m unittest discover -s tests -p test_quantum.py -v
python -m unittest discover -s tests -p test_classical.py -v
```

Abrir `notebooks/05_optimizacion_cuantica_comparacion.ipynb` y ejecutar las celdas. El script regenera el benchmark completo; la notebook recalcula la corrida principal y presenta el benchmark guardado. No se requieren credenciales, descargas de carreteras ni cuentas cuánticas. Los tiempos varían por equipo; las conclusiones estáticas describen el benchmark entregado.

## Integración con Qiskit (v2.6.1)

El proyecto utiliza **Qiskit** como biblioteca cuántica fundamental para modelar, simular y exportar el circuito variacional:
- **`qiskit.circuit.QuantumCircuit`**: Construcción explícita del circuito QAOA paramétrico ($p$ capas, compuertas $H$, $R_Z$, $R_{ZZ}$ y mezclador $R_X$).
- **`qiskit.quantum_info.Statevector`**: Validación rigurosa de los vectores de estado y cálculo de fidelidad cuántica ($F = 1.0$) frente al simulador analítico.
- **`qiskit.qasm3`**: Serialización del circuito a OpenQASM 3 (`data/results/phase5/circuito_qaoa.qasm`) compatible con el ecosistema IBM Quantum.
- **`circuit.draw(output='text')`**: Renderizado del circuito esquemático en `data/results/phase5/circuito_qaoa.txt`.

## Archivos principales

- `src/qfire_cusco/optimization_quantum.py`: asignación, QUBO, QAOA, circuito Qiskit y decodificación.
- `scripts/run_quantum.py`: protocolo de veinte corridas y control uniforme; registra configuración y versiones.
- `data/results/phase5/`: QUBO, matriz, energías, factibilidad, ángulos, conteos de shots, trazas, planes y benchmark.
- `outputs/reports/informe_comparacion_cuantica.html`: informe sin dependencias web.
- `outputs/figures/05_*.png`: gráficos de calidad, tiempo y cobertura.
- `tests/test_quantum.py`: pruebas de asignación contra LP independiente, supuestos de capacidad, tamaño, rechazo de fallos y coincidencia con Qiskit.

El script exporta resultados nuevos sólo en `phase5` y no modifica el puntero `phase4/latest.json`. Normaliza a `/` las claves de hashes en memoria para conservar el ID del escenario al ejecutar en Windows. Las entradas se mantienen intactas. Las afirmaciones de documentos originales de que la fase 05 era futura describen la entrega previa; esta ampliación se documenta aquí.

## Alcance científico

La asignación previa maximiza beneficio por recurso y fija lotes; la selección de tours admite una visita por destino. Se exige que toda la carga asignada quepa en cualquier vehículo y que los tours sean comunes. Si no se cumple, o el QUBO excede 18 qubits, se informa un error. No se aplica esta reducción automáticamente al problema general.

El entrenamiento usa esperanza exacta de un simulador ideal y el muestreo finito se aplica al final. No hay ruido ni conectividad física modelados. El óptimo exhaustivo y el MILP se usan para evaluación posterior, sin reparar muestras. La igualdad con el óptimo MILP certifica este plan por comparación, sin atribuir una prueba de optimalidad a QAOA.

Los tiempos QAOA incluyen preparación, optimización y muestreo; excluyen decodificación final y verificaciones. MILP incluye resolución y materialización. Ambos excluyen carga de datos e informes. No se infiere aceleración de hardware. Los recursos y situaciones son simulados; COER y accesos mantienen los límites del adjunto.
