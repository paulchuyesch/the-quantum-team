# Diccionario de la fase 01

El CSV de entrada se conserva íntegro en `data/raw`. La tabla normalizada usa los siguientes grupos de campos.

| Campos | Significado |
|---|---|
| `INCENDIO_ID` | Identificador del registro histórico, derivado del ID de origen. No agrupa automáticamente varios reportes de un mismo incendio físico. |
| `ID_MINAM_ORIGINAL`, `IDS_FUENTE` | Identificador conservado y conjunto de identificadores de procedencia. Se leen como texto. |
| `DEPARTAMENTO`, `PROVINCIA`, `DISTRITO`, `LOCALIDAD` | Ubicación administrativa reportada. No se completa una localidad faltante con un nombre inventado. |
| `FECHA_INICIO`, `FECHA_TERMINO` | Fechas normalizadas ISO, vacías cuando el valor no se puede interpretar. La fecha de término faltante no significa que un incendio continúe activo. |
| `FEC_EMERGE_ORIGINAL`, `FEC_TERMIN_ORIGINAL` | Textos originales para revisar fechas inválidas o contradictorias. |
| `ANIO` | Año reportado en la entrada; se contrasta con la fecha de inicio. |
| `LATITUD`, `LONGITUD` | Coordenadas WGS84 proporcionadas. Se comprueba plausibilidad amplia en Perú; todavía no se hace una intersección con límites administrativos. |
| `INCENDIO_CONFIRMADO`, `CONFIRMACION_ORIGINAL` | Confirmación derivada del campo `INCENDIO` y su texto original. No es el estado operativo actual. |
| `DESCRIPCION`, `DANOS_REPORTADOS` | Descripción y daños como fueron reportados, con espacios normalizados. |
| `FUENTE`, `ENTIDAD_REPORTANTE` | Fuente y entidad reportante, cuando están consignadas. |
| `COB_AFECTA_ORIGINAL`, `CULTI_AFEC_ORIGINAL` | Textos de cobertura y cultivo afectados en el archivo proporcionado. |
| `COB_AFECTA_VALOR`, `CULTI_AFEC_VALOR` | Conversión numérica sin asignar una unidad no confirmada. El cero se conserva. |
| `UNIDAD_COBERTURA` | `NO_CONFIRMADA` por defecto. Puede configurarse como `ha` o `m2` después de verificar documentalmente la unidad. |
| `AREA_HA` | Área derivada únicamente con un valor positivo y una unidad confirmada. No se imputa por promedio ni por localidad. |
| `APTO_MAPEO` | Verdadero si hay confirmación, coordenadas plausibles y fecha de inicio coherente con el año. Es una preselección para EDA, no un punto de entrega validado. |
| `OBSERVACIONES_CALIDAD` | Reglas de esta ejecución, separadas por punto y coma. |
| `OBSERVACIONES_PREVIAS` | Observaciones que ya traía el archivo suministrado, conservadas por trazabilidad. |
| `ARCHIVO_FUENTE`, `SHA256_FUENTE`, `FILAS_FUENTE` | Nombre de entrada, hash y posiciones de los registros contribuyentes contando el encabezado como primera fila lógica. |

## Duplicados

Solo se retiran registros con contenido normalizado idéntico, excluyendo identificadores y metadatos derivados de una limpieza anterior. Se conservan todos sus IDs y filas de procedencia. Coincidir en fecha o coordenadas por sí solo no provoca una eliminación.

Dos filas con el mismo ID original y contenido distinto se mantienen, reciben IDs derivados diferentes y quedan señaladas para revisión. Si falta el ID se usa una huella determinista del contenido; la fila permanece marcada.

## Aptitud y magnitud

Las filas con problemas se mantienen en el historial y en la vista de observaciones. Las que no cumplen los requisitos geográficos, temporales o de confirmación se excluyen únicamente de `incendios_para_mapeo.csv`.

Los valores de área sin unidad confirmada no permiten ordenar rigurosamente incendios por hectáreas. La fase 03 incorporará magnitudes reportadas o simuladas con su procedencia. La fase 01 no crea donaciones, solicitudes, prioridades operativas o bloqueos ficticios.


## Entradas logísticas de fase 03

Contrato detallado en `docs/phase3.md`. Los CSV de `data/simulated/phase3/` usan IDs en mayúsculas.

| Campo o entidad | Significado y origen |
|---|---|
| `CENTRO_COORDINADOR_ID` | COER_CUSCO por regla del escenario; no modifica al reportante histórico |
| `CENTRO_PADRE_ID` | Padre logístico del centro local; vacío solo en el COER raíz |
| `CENTRO_PREFERENTE_ID` | Centro sugerido para atender al receptor; no es asignación decidida |
| `ENTIDAD_REPORTANTE` | Valor histórico original, preservado incluso si falta |
| `PUNTO_ID` / `INCENDIO_ID` | Receptor propuesto y referencia histórica; ubicaciones diferentes |
| `FUENTE_COORDENADA` | Procedencia de latitud/longitud del punto propuesto; ninguna instalación está validada |
| `MAGNITUD_RELATIVA` | Puntuación simulada sin unidad física; no hectáreas |
| `PERSONAL_DESPLEGADO`, `FAUNA_REQUIERE_ATENCION` | Recuentos simulados para generar pedidos |
| `FRACCION_TRABAJO_MANUAL`, `FACTOR_HUMO`, `URGENCIA_RELATIVA` | Factores simulados, sin inferir ecosistema o expansión |
| `PRIORIDAD_BASE` / `PRIORIDAD_RECURSO` | Puntuación ponderada del perfil y ajuste del recurso; no cobertura ni asignación |
| `CANTIDAD_PENDIENTE` | Solicitada menos entregada; unidades de su recurso |
| `PESO_KG_UNIDAD`, `VOLUMEN_M3_UNIDAD` | Supuestos de carga por presentación |
| `DONACION_ID` | Identificador único que evita registrar dos ingresos de una misma donación |
| `MOVIMIENTO_ID` | Identificador único del movimiento de inventario |
| `CANTIDAD_DISPONIBLE` | Existencia habilitada por centro y recurso; al reservar se consulta libre = disponible menos reservada |
| `REQUIERE_SOLICITUD_AUTORIZADA` | Recurso sanitario cuyo pedido requiere autorización; en la demo la autorización es simulada |
| `BRECHA_AGREGADA_UNIDADES` | Déficit por recurso al comparar inventario total ubicado con demanda; no asignación |
| `RED_VERSION` | Huella del grafo utilizado para nodos, pares y geometrías |

El contenido operativo del escenario es simulado. Las columnas históricas dentro de perfiles mantienen su origen histórico; `ORIGEN=SIMULADO` identifica los atributos de perfil añadidos, no convierte los campos de la fuente en observaciones nuevas.
