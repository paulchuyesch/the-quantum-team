# Resultado calculado de la demostración del notebook 04

Escenario simulado: Anta, Calca, Paruro y Urubamba, con perfiles diferenciados del archivo `config/ejemplo_perfiles_fase4.json`. El inventario disponible es el de fase 03, fijo, sin sumar promesas ni existencias de hubs.

El solver encontró el óptimo del modelo restringido a un viaje por vehículo y hasta tres paradas: utiliza dos vehículos, atiende las cuatro provincias seleccionadas y recorre 248,758 km viales, incluyendo retornos al COER. La cobertura es parcial porque el stock no alcanza para todas las necesidades.

| Recurso | Solicitado | Asignado | Faltante |
|---|---:|---:|---:|
| Botellas de agua de 625 ml | 980 | 670 | 310 |
| Mascarillas | 308 | 258 | 50 |
| Palas | 51 | 27 | 24 |
| Hachas | 20 | 12 | 8 |
| Paquetes veterinarios | 17 | 8 | 9 |
| Botiquines | 12 | 8 | 4 |

No se suman cantidades de recursos de distinta unidad. El valor objetivo pasa de 14.432,887 sin entregas a 3.821,503 con el plan, dentro de la política de costos declarada; no son soles ni dólares. Se verifican stock, peso, volumen, plazos, rutas dirigidas, paradas y escenario activo.

La red de fase 04 contiene 55.511 nodos y 143.740 arcos dirigidos, con 342 caminos entre los 19 puntos. Los 13 receptores provinciales predeterminados tienen ida y retorno al origen. El mayor alejamiento de un punto al nodo vial asociado es de 74,731 m; esa asociación no valida el acceso final.

La sede COER permanece provisional. Los receptores son referencias de localidades OSM, los incidentes y recursos son simulados y no se han realizado despachos. La comparación cuántica y la web quedan para otra fase.
