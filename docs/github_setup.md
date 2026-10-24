# Subir el proyecto a GitHub

## Desde la web

1. Descomprimir `qfire-cusco.zip` en la computadora.
2. Abrir la carpeta `qfire-cusco`. Dentro estarán `README.md`, `data`, `notebooks`, `outputs`, `src` y los demás archivos.
3. Crear un repositorio, por ejemplo `qfire-cusco`, o abrir el repositorio nuevo destinado a este proyecto. Si se crea uno vacío, la página inicial ofrece la opción de subir un archivo existente.
4. En un repositorio existente, elegir **Add file → Upload files**.
5. Arrastrar **los elementos que están dentro de la carpeta** a la zona de carga. Así `README.md` quedará en la raíz, en vez de dentro de una segunda carpeta `qfire-cusco`.
6. Escribir un mensaje de commit, por ejemplo `Agregar fases 01-03 de logística de recursos en Cusco`.
7. Revisar la lista de archivos y confirmar con **Commit changes**.

El ZIP es el paquete de entrega. Para que GitHub muestre el notebook y las carpetas, se sube su contenido descomprimido.

## Qué debe verse en la raíz

| Elemento | Qué revisar |
|---|---|
| `README.md` | GitHub muestra la presentación del proyecto |
| `data/raw/incendios_Cusco_2022_2026.csv` | Entrada incluida en su carpeta |
| `notebooks/01_data_cleaning_incendios.ipynb` | Notebook con código, explicación y resultados registrados |
| `src/qfire_cusco/` | Funciones de limpieza, red vial y logística |
| `notebooks/03_recursos_donaciones_solicitudes.ipynb` | Pedidos, donaciones, centros e inventario |
| `data/simulated/phase3/` | Tablas logísticas generadas |
| `config/phase3.json` | Reglas del escenario COER Cusco |
| `requirements.txt` | Dependencias del proyecto |
| `outputs/` | Figuras y reportes generados |

Las carpetas futuras contienen un archivo `.gitkeep` para que Git pueda conservarlas aunque todavía no tengan datasets. Algunos selectores de archivos ocultan esos archivos; al arrastrar carpetas desde el explorador, revisar que se hayan incluido si se quieren mostrar las carpetas vacías.

## Con Git instalado

Abrir una terminal dentro de `qfire-cusco`. Sustituir `TU_USUARIO` y el nombre del repositorio por los reales. Estos comandos se usan para un **repositorio remoto nuevo y vacío**:

```bash
git init
git add .
git commit -m "Agregar fases 01-03 de logística de recursos en Cusco"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/qfire-cusco.git
git push -u origin main
```

Para un repositorio que ya contiene trabajo, clonarlo primero y añadir los archivos revisando los cambios. No reemplazar el repositorio anterior de Q-Med por accidente.

Referencia: [GitHub Docs — Adding a file to a repository](https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository).
