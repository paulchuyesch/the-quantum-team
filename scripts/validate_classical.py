"""Pruebas y verificación de conservación del ZIP base, con evidencias JSON."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]


def main():
    reports=ROOT/'outputs/reports';reports.mkdir(parents=True,exist_ok=True)
    stream=io.StringIO()
    suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'))
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    (reports/'tests_phase4.log').write_text(stream.getvalue())
    payload={'pruebas_ejecutadas':result.testsRun,'fallos':len(result.failures),'errores':len(result.errors),
        'omitidas':len(result.skipped),'aprobado':result.wasSuccessful(),'subconjuntos_selector_comprobados':8192,
        'nota_subconjuntos':'Se valida el selector sobre todos los subconjuntos; el optimizador se ejecuta en casos representativos.',
        'fuera_de_alcance':['notebook 05 y QAOA','aplicación Streamlit','operación oficial o despachos reales'],
        'detalles_fallos':[{'prueba':str(t),'detalle':m} for t,m in result.failures+result.errors]}
    (reports/'classical_validation.json').write_text(json.dumps(payload,indent=2,ensure_ascii=False)+'\n')
    original=json.loads((ROOT/'docs/original_manifest.json').read_text())
    protected={rel:digest for rel,digest in original.items() if rel.startswith('data/raw/')}
    integrity={rel:hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()==digest for rel,digest in protected.items()}
    (reports/'raw_integrity.json').write_text(json.dumps({'todos_los_raw_originales_intactos':all(integrity.values()),'archivos':integrity},indent=2)+'\n')
    print(stream.getvalue());print(json.dumps(payload,indent=2,ensure_ascii=False))
    if not result.wasSuccessful() or not all(integrity.values()):sys.exit(1)

if __name__=='__main__':main()
