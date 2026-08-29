#!/usr/bin/env python3
"""Banco de pruebas de la medición de resolución.

Las páginas de muestra están en `muestras/`. Son casos reales que rompieron la
medición alguna vez, así que conviene no sacarlos: fotos de celular, partitura
grabada achicada por Canva, manuscritas (derecha y torcida), y páginas que NO
son partitura y no tienen que medir nada.

Uso: python3 test_resolucion.py
"""
import sys
from pathlib import Path

from resolucion import medir_interlinea

MUESTRAS = Path(__file__).parent / "muestras"

# (archivo, descripción, interlínea esperada en px o None si no hay pentagramas)
CASOS = [
    ("foto-celular-coral-6-pentagramas.jpg", "foto de celular, coral a 6 pentagramas", 11.8),
    ("foto-celular-coral-satb.jpg",          "foto de celular, coral SATB",            13.0),
    ("canva-120ppp-grabada.jpg",             "grabada, achicada por Canva a 120 ppp",   7.7),
    ("manuscrita.jpg",                       "manuscrita, hoja derecha",               14.9),
    ("manuscrita-torcida.jpg",               "manuscrita, hoja torcida",               14.9),
    ("grabada-210ppp.jpg",                   "grabada a 210 ppp",                      17.9),
    ("sin-pentagramas-biografia.jpg",        "página de texto con foto",                None),
    ("sin-pentagramas-nota-manuscrita.jpg",  "nota manuscrita, sin pentagramas",        None),
    ("sin-pentagramas-portada.jpg",          "portada de una canción",                  None),
    ("sin-pentagramas-texto.jpg",            "página de texto",                         None),
]

TOLERANCIA = 0.6  # px


def main():
    if not MUESTRAS.is_dir():
        print(f"falta la carpeta {MUESTRAS}")
        return 1
    fallas = 0
    for archivo, descripcion, esperado in CASOS:
        ruta = MUESTRAS / archivo
        if not ruta.exists():
            print(f"FALTA  {archivo}")
            fallas += 1
            continue
        medido = medir_interlinea(str(ruta))
        if esperado is None:
            ok = medido is None
        else:
            ok = medido is not None and abs(medido - esperado) <= TOLERANCIA
        fallas += 0 if ok else 1
        got = "sin pentagramas" if medido is None else f"{medido:.1f} px"
        exp = "sin pentagramas" if esperado is None else f"{esperado} px"
        print(f"{'ok  ' if ok else 'FALLA'} {descripcion:42} {got:>16}  (esperado {exp})")
    print("todo bien" if not fallas else f"{fallas} falla(s)")
    return 0 if not fallas else 1


if __name__ == "__main__":
    sys.exit(main())
