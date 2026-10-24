# Plan arquitectónico — QFire Cusco, fase clásica hasta notebook 04

Fecha: 2026-10-24. Solicitud autorizada: revisar y completar hasta notebook 04, parte clásica.
El texto adjunto es una especificación de referencia; las secciones de notebook 05, QAOA y web no amplían esta solicitud.

## Átomos y validación
1. Extraer copia segura del ZIP en outputs/qfire-cusco; preservar ZIP y datos fuente.
2. Auditar notebooks 01–03, módulos, configuraciones, matrices, procedencia y pruebas.
3. Conservar funciones válidas y documentar defectos comprobados.
4. Crear escenario dinámico con provincias de datos procesados, perfiles y demanda editables; ninguna solicitud en provincias inactivas.
5. Integrar receptores documentados, matrices dirigidas y cobertura verificable; destinos no preparados deben reportar limitación explícita.
6. Implementar prioridades y optimización clásica reproducible de depósito único COER, inventario confirmado, capacidad, demanda, plazos y rutas autorizadas.
7. Crear notebook 04 ejecutable, runner CLI, exportaciones reutilizables y documentación de supuestos.
8. Ejecutar pruebas originales y nuevas; ejecutar notebooks; conciliar resultados y empaquetar repositorio.

## Criterios de aceptación
- Provincias dinámicas, selección vacía/arbitraria y eliminación de resultados obsoletos mediante escenarios puros identificados por hash.
- Sin rutas inventadas, inventario duplicado ni entregas superiores a demanda/capacidad.
- Todos los vehículos parten del COER; prioridad influye en asignación.
- Notebook 04 ejecutado de principio a fin con resultados reales del cómputo y límites declarados.
- Conservar notebooks 01–03 y archivos raw originales; informar cambios y pruebas.

## Decisiones
La orden expresa «REVISA Y HAZ» autoriza la construcción local del alcance clásico. No se requiere nueva confirmación para esos cambios reversibles.
No se implementará notebook 05 ni una aplicación web en este hito.

## Cierre verificado
Átomos 1–8 completos. Notebooks 01–04 ejecutados; 67 pruebas aprobadas; matrices para las 13 provincias preparadas; 342 caminos contrastados con arcos del grafo. Se conserva la entrada raw original. Entrega en outputs/qfire-cusco y ZIP actualizado.
