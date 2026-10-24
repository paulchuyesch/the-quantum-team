"""Ejecutar notebooks con el intérprete activo, sin instalar un kernel global."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import time
import nbformat
from nbclient import NotebookClient
from jupyter_client import KernelManager
from jupyter_client.kernelspec import KernelSpecManager
ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--numbers',nargs='+',default=['01','02','03','04'])
    args=parser.parse_args();reports=[]
    with tempfile.TemporaryDirectory() as directory:
        kernels=Path(directory);spec=kernels/'qfire-validation';spec.mkdir()
        (spec/'kernel.json').write_text(json.dumps({'argv':[sys.executable,'-m','ipykernel_launcher','-f','{connection_file}'],'display_name':'QFire validation','language':'python'}))
        for number in args.numbers:
            matches=list((ROOT/'notebooks').glob(number+'_*.ipynb'))
            if len(matches)!=1:raise ValueError(f'Notebook no único: {number}')
            path=matches[0];nb=nbformat.read(path,as_version=4)
            km=KernelManager(kernel_name='qfire-validation',kernel_spec_manager=KernelSpecManager(kernel_dirs=[str(kernels)]))
            started=time.perf_counter()
            NotebookClient(nb,km=km,timeout=600,resources={'metadata':{'path':str(ROOT/'notebooks')}},allow_errors=False).execute()
            nb.metadata.kernelspec={'name':'python3','language':'python','display_name':'Python 3'}
            nbformat.write(nb,path)
            reports.append({'notebook':path.name,'estado':'EJECUTADO_SIN_ERRORES','celdas_codigo':sum(c.cell_type=='code' for c in nb.cells),'segundos':time.perf_counter()-started})
            print(json.dumps(reports[-1]),flush=True)
    report_path=ROOT/'outputs/reports/notebooks_execution.json'
    previous=json.loads(report_path.read_text()) if report_path.exists() else []
    updated={r['notebook']:r for r in previous}
    updated.update({r['notebook']:r for r in reports})
    report_path.write_text(json.dumps([updated[k] for k in sorted(updated)],indent=2)+'\n')

if __name__=='__main__':main()
