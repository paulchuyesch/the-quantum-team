# Receptores de fase 04

La selección de provincias procede del historial. Este registro define puntos geográficos de referencia para la demostración. Las capitales se identifican con etiquetas `place`, `capital` y, cuando existe, `pe:ubigeo` del mismo PBF OSM utilizado para las carreteras. El vínculo provincial se documenta por capital y código administrativo; no se infiere del lugar del incendio.

Las coordenadas representan centros de localidades, no instalaciones de emergencia ni accesos acreditados. Los receptores de fase 03 permanecen como alternativas, con su procedencia y limitaciones originales. La coordenada COER se conserva provisional.

| Provincia | ID | Localidad/punto | Latitud | Longitud | Predeterminado | Fuente |
|---|---|---|---:|---:|---|---|
| ACOMAYO | CAP_0802 | Acomayo: referencia de localidad OSM (no almacén validado) | -13.9192017 | -71.6834556 | True | https://www.openstreetmap.org/node/2317137705 |
| ANTA | CAP_0803 | Anta: referencia de localidad OSM (no almacén validado) | -13.4707489 | -72.1491038 | True | https://www.openstreetmap.org/node/2367668493 |
| ANTA | RE01 | Receptor demo Anta | -13.457 | -72.148 | False | PUNTO_DEMO_NO_PUNTO_SEGURO_VERIFICADO |
| CALCA | CAP_0804 | Calca: referencia de localidad OSM (no almacén validado) | -13.3216818 | -71.9560084 | True | https://www.openstreetmap.org/node/436613486 |
| CALCA | RE03 | Receptor demo Calca | -13.322 | -71.955 | False | PUNTO_DEMO_NO_PUNTO_SEGURO_VERIFICADO |
| CANAS | CAP_0805 | Yanaoca: referencia de localidad OSM (no almacén validado) | -14.2169433 | -71.4320333 | True | https://www.openstreetmap.org/node/441888431 |
| CANCHIS | CAP_0806 | Sicuani: referencia de localidad OSM (no almacén validado) | -14.2729288 | -71.2265322 | True | https://www.openstreetmap.org/node/262945603 |
| CHUMBIVILCAS | CAP_0807 | Santo Tomás: referencia de localidad OSM (no almacén validado) | -14.4497342 | -72.0821971 | True | https://www.openstreetmap.org/node/467653110 |
| CUSCO | CAP_0801 | Cusco (OSM: Cuzco): referencia de localidad, no almacén validado | -13.5170887 | -71.9785356 | True | https://www.openstreetmap.org/node/59115290 |
| ESPINAR | CAP_0808 | Yauri: referencia de localidad OSM (no almacén validado) | -14.7930081 | -71.412802 | True | https://www.openstreetmap.org/node/267367682 |
| LA CONVENCION | CAP_0809 | Quillabamba: referencia de localidad OSM (no almacén validado) | -12.8634092 | -72.6930334 | True | https://www.openstreetmap.org/node/1990593833 |
| PARURO | CAP_0810 | Paruro: referencia de localidad OSM (no almacén validado) | -13.761311 | -71.8474048 | True | https://www.openstreetmap.org/node/2314231210 |
| PARURO | RE04 | Receptor demo Accha | -13.971146 | -71.8315418 | False | OSM_NODE_2314230985_CENTRO_LOCALIDAD_NO_RECEPCION_VALIDADA |
| PARURO | RE05 | Receptor demo Huanoquite | -13.6816043 | -72.0174185 | False | OSM_NODE_588509149_CENTRO_LOCALIDAD_NO_RECEPCION_VALIDADA |
| PAUCARTAMBO | CAP_0811 | Paucartambo: referencia de localidad OSM (no almacén validado) | -13.3176052 | -71.5959691 | True | https://www.openstreetmap.org/node/292250901 |
| QUISPICANCHI | CAP_0812 | Urcos: referencia de localidad OSM (no almacén validado) | -13.6879153 | -71.6255835 | True | https://www.openstreetmap.org/node/1052796010 |
| URUBAMBA | CAP_0813 | Urubamba: referencia de localidad OSM (no almacén validado) | -13.305953 | -72.1159706 | True | https://www.openstreetmap.org/node/441008049 |
| URUBAMBA | RE02 | Receptor demo Urubamba | -13.304 | -72.116 | False | PUNTO_DEMO_NO_PUNTO_SEGURO_VERIFICADO |

Evidencia de los nodos y etiquetas: `data/raw/receptores_osm_phase4.json`. Procedencia del extracto: `data/raw/osm_phase4_metadata.json`. Distancias reales al nodo y validez del umbral: `data/geo/phase4/snap_report.csv`.

© OpenStreetMap contributors; PBF Geofabrik; ODbL 1.0. Dos ubicaciones pueden asociarse al mismo nodo vial: su costo entre nodos es cero y el acceso físico final sigue sin validar.
