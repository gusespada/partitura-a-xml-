#!/usr/bin/env python3
"""
Mide si un PDF tiene resolución suficiente para que Audiveris pueda leerlo.

La medida que importa NO son los ppp del archivo ni los megapíxeles de la cámara,
sino cuántos píxeles hay entre dos líneas del pentagrama (la "interlínea"). Es lo
que usa Audiveris para calcular el tamaño de todo lo demás — cabezas de nota,
plicas, alteraciones — y por debajo de cierto umbral no puede distinguirlas.

Una partitura coral a 6 pentagramas por sistema está impresa mucho más chica que
una de piano, así que con los mismos ppp puede quedar por debajo del umbral
mientras la de piano pasa cómoda. Por eso hay que medir, no suponer.
"""
import glob
import os
import subprocess
import tempfile

import numpy as np
from PIL import Image

# Umbrales de interlínea en píxeles (recomendación del propio proyecto Audiveris)
INTERLINEA_COMODA = 25      # de acá para arriba, lectura casi limpia
INTERLINEA_MINIMA = 20      # de acá para abajo, Audiveris empieza a fallar feo
INTERLINEA_INUTIL = 15      # de acá para abajo, no vale la pena ni intentarlo


def _otsu(a):
    hist, _ = np.histogram(a, bins=256, range=(0, 256))
    total = a.size
    suma = np.dot(np.arange(256), hist)
    suma_b = 0.0
    peso_b = 0.0
    mejor = (-1.0, 128)
    for t in range(256):
        peso_b += hist[t]
        if peso_b == 0:
            continue
        peso_f = total - peso_b
        if peso_f == 0:
            break
        suma_b += t * hist[t]
        media_b = suma_b / peso_b
        media_f = (suma - suma_b) / peso_f
        var = peso_b * peso_f * (media_b - media_f) ** 2
        if var > mejor[0]:
            mejor = (var, t)
    return mejor[1]


def _perfil_de_lineas(imagen_path):
    """Perfil por filas de los píxeles que son 'línea horizontal fina'.

    Se queda solo con la tinta cuya corrida vertical es corta: eso deja las
    líneas del pentagrama y descarta cabezas de nota, plicas y letra, que son
    verticalmente gruesas. Sobre ese perfil, las cinco líneas de cada pentagrama
    aparecen como picos regularmente espaciados.
    """
    im = Image.open(imagen_path).convert("L")
    a = np.array(im)
    alto, _ = a.shape
    tinta = a < _otsu(a)

    arriba = np.zeros_like(tinta, dtype=np.int16)
    abajo = np.zeros_like(tinta, dtype=np.int16)
    for y in range(alto):
        arriba[y] = np.where(tinta[y], (arriba[y - 1] + 1 if y > 0 else 1), 0)
    for y in range(alto - 1, -1, -1):
        abajo[y] = np.where(tinta[y], (abajo[y + 1] + 1 if y < alto - 1 else 1), 0)
    corrida = np.where(tinta, arriba + abajo - 1, 0)

    grosor_max = max(2, int(alto / 500))  # una línea de pentagrama es finita
    perfil = (tinta & (corrida <= grosor_max)).sum(axis=1).astype(float)
    return perfil - perfil.mean(), alto


def medir_interlinea(imagen_path):
    """Interlínea en píxeles: separación vertical entre líneas del pentagrama."""
    perfil, alto = _perfil_de_lineas(imagen_path)

    # 1) autocorrelación: el primer pico fuerte es la interlínea
    mejor = None
    for lag in range(4, min(80, alto // 12)):
        c = float(np.dot(perfil[:-lag], perfil[lag:])) / (alto - lag)
        if mejor is None or c > mejor[0]:
            mejor = (c, lag)
    aprox = mejor[1]

    # 2) refino con un peine de 5 líneas, que es lo que realmente es un pentagrama
    refinada = None
    for sp in np.arange(aprox - 1.5, aprox + 1.5, 0.05):
        filas = np.arange(0, alto - int(4 * sp) - 1)
        puntaje = sum(perfil[filas + int(round(k * sp))] for k in range(5)).max()
        if refinada is None or puntaje > refinada[0]:
            refinada = (puntaje, float(sp))
    return refinada[1]


def diagnosticar(pdf_path, alto_pagina_mm=297.0):
    """Mide una página del medio del PDF y devuelve un diagnóstico.

    Se usa una página del medio y no la primera porque la primera suele llevar
    título y menos sistemas, y da una medida menos representativa.
    """
    carpeta = tempfile.mkdtemp(prefix="resolucion-")
    try:
        paginas = int(
            subprocess.run(
                ["pdfinfo", str(pdf_path)], capture_output=True, text=True, check=True
            ).stdout.split("Pages:")[1].split()[0]
        )
        pagina = max(1, (paginas + 1) // 2)
        subprocess.run(
            ["pdfimages", "-png", "-f", str(pagina), "-l", str(pagina),
             str(pdf_path), os.path.join(carpeta, "p")],
            check=True, capture_output=True,
        )
        archivos = sorted(glob.glob(os.path.join(carpeta, "p*.png")))
        if not archivos:
            return None  # PDF vectorial (ya digital): no hay nada que medir
        imagen = archivos[0]
        ancho, alto = Image.open(imagen).size
        interlinea = medir_interlinea(imagen)
        ppp = alto / (alto_pagina_mm / 25.4)

        if interlinea >= INTERLINEA_COMODA:
            nivel, veredicto = "ok", "Resolución holgada: Audiveris debería leerla casi limpia."
        elif interlinea >= INTERLINEA_MINIMA:
            nivel, veredicto = "ok", "Resolución suficiente: va a andar, con algunos errores."
        elif interlinea >= INTERLINEA_INUTIL:
            nivel, veredicto = "justo", "Resolución justa: esperá bastantes errores."
        else:
            nivel, veredicto = "insuficiente", "Resolución insuficiente: Audiveris no va a poder leerla."

        return {
            "nivel": nivel,
            "veredicto": veredicto,
            "interlinea_px": round(interlinea, 1),
            "ppp": round(ppp),
            "pagina_medida": pagina,
            "tamano_px": f"{ancho}x{alto}",
            "ppp_necesarios": round(ppp * INTERLINEA_MINIMA / interlinea) if interlinea < INTERLINEA_MINIMA else None,
            "factor_necesario": round(INTERLINEA_MINIMA / interlinea, 1) if interlinea < INTERLINEA_MINIMA else None,
        }
    finally:
        import shutil as _shutil
        _shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    import sys
    for p in sys.argv[1:]:
        print(f"== {os.path.basename(p)}")
        d = diagnosticar(p)
        if d is None:
            print("  el PDF no tiene imágenes (parece ya digital): no hace falta medir")
            continue
        print(f"  página medida : {d['pagina_medida']}  ({d['tamano_px']} px, ~{d['ppp']} ppp)")
        print(f"  interlínea    : {d['interlinea_px']} px")
        print(f"  {d['veredicto']}")
        if d["ppp_necesarios"]:
            print(f"  hace falta {d['factor_necesario']}x más resolución (~{d['ppp_necesarios']} ppp)")
