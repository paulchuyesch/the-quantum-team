"""Ejecutar fase 04. Sin provincias crea un escenario vacío, nunca usa la historia como alerta."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from qfire_cusco.scenario import load_inputs,create_scenario
from qfire_cusco.optimization_classical import solve_classical,export_plan


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--provincias',nargs='*',default=[])
    parser.add_argument('--perfiles',type=Path,help='JSON: provincia -> campos del perfil')
    parser.add_argument('--receptores',type=Path,help='JSON: provincia -> PUNTO_ID')
    parser.add_argument('--pesos',type=Path,help='JSON: magnitud,personal,fauna,urgencia; suma 1')
    args=parser.parse_args()
    def read(p):return json.loads(p.read_text()) if p else None
    scenario=create_scenario(load_inputs(ROOT),args.provincias,read(args.perfiles),read(args.receptores),read(args.pesos))
    plan=solve_classical(scenario);folder=export_plan(scenario,plan)
    print(json.dumps({'resultados':str(folder.relative_to(ROOT)),**plan.metrics},indent=2,ensure_ascii=False))

if __name__=='__main__':main()
