"""Política de prioridad demostrativa, separada de las cantidades solicitadas."""
import math
import numpy as np

FACTORS = {'magnitud': 'MAGNITUD_RELATIVA', 'personal': 'PERSONAL_DESPLEGADO',
           'fauna': 'FAUNA_REQUIERE_ATENCION', 'urgencia': 'URGENCIA_RELATIVA'}


def prioritize(profiles, weights):
    if set(weights) != set(FACTORS) or any(not math.isfinite(float(v)) or v < 0 for v in weights.values()) or not math.isclose(sum(weights.values()), 1):
        raise ValueError('Los cuatro pesos deben ser finitos, no negativos y sumar uno.')
    result = profiles.copy()
    score = np.zeros(len(result))
    for key, column in FACTORS.items():
        if len(result):
            values = result[column].astype(float)
            if not np.isfinite(values).all() or values.lt(0).any():
                raise ValueError(f'Factor de prioridad inválido: {column}')
            score += weights[key] * (values / values.max() if values.max() > 0 else 0)
    result['PRIORIDAD_BASE'] = np.round(score * 100, 4)
    return result
