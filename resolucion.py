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

# Parámetros de la medición. Ajustados contra un banco de páginas reales:
# fotos de celular, partitura grabada reducida por Canva, manuscritas (derechas
# y torcidas), y páginas de texto, foto y portada que no tienen que medir nada.
BANDAS = 10                 # franjas verticales en que se parte la página
FRACCION_ANCHO = 0.30       # cuánto de la franja tiene que cruzar una línea
PASO_BUSQUEDA = 0.5         # resolución de la búsqueda gruesa, en píxeles


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


def _perfiles_de_lineas(imagen_path, bandas=BANDAS):
    """Perfil por filas de los píxeles que son 'línea horizontal fina',
    calculado por separado en `bandas` franjas verticales de la página.

    Se queda solo con la tinta cuya corrida vertical es corta: eso deja las
    líneas del pentagrama y descarta cabezas de nota, plicas y letra, que son
    verticalmente gruesas.

    Se mide por franjas y no sobre la página entera porque casi ninguna hoja
    está perfectamente derecha: con dos grados de inclinación una misma línea
    de pentagrama se reparte entre varias filas y deja de verse como un pico.
    Dentro de una franja angosta la línea sí cae casi toda en la misma fila.
    """
    im = Image.open(imagen_path).convert("L")
    a = np.array(im)
    alto, ancho = a.shape
    tinta = a < _otsu(a)

    arriba = np.zeros_like(tinta, dtype=np.int16)
    abajo = np.zeros_like(tinta, dtype=np.int16)
    for y in range(alto):
        arriba[y] = np.where(tinta[y], (arriba[y - 1] + 1 if y > 0 else 1), 0)
    for y in range(alto - 1, -1, -1):
        abajo[y] = np.where(tinta[y], (abajo[y + 1] + 1 if y < alto - 1 else 1), 0)
    corrida = np.where(tinta, arriba + abajo - 1, 0)

    grosor_max = max(2, int(alto / 500))  # una línea de pentagrama es finita
    fino = tinta & (corrida <= grosor_max)

    ancho_banda = ancho // bandas
    perfiles = []
    for b in range(bandas):
        x0 = b * ancho_banda
        x1 = ancho if b == bandas - 1 else (b + 1) * ancho_banda
        perfil = fino[:, x0:x1].sum(axis=1).astype(float)
        # ensanchamos cada pico una fila para arriba y otra para abajo: aunque
        # la franja sea angosta, si la hoja está torcida la línea sigue cayendo
        # en dos filas vecinas y si no, el peine no la engancha
        perfiles.append(np.maximum(np.maximum(perfil, np.roll(perfil, 1)), np.roll(perfil, -1)))
    return perfiles, alto, ancho_banda


def _puntaje_peine(perfil, alto, sp, umbral):
    """Qué tan bien un peine de cinco líneas separadas `sp` explica el perfil.

    Devuelve (filas_acertadas, tinta_acumulada). Se puntúa con el MÍNIMO de las
    cinco filas, no con la suma: el candidato solo puntúa si las cinco líneas
    están presentes de verdad. Eso descarta solo los múltiplos y submúltiplos
    (con sp/2 las filas intermedias están vacías; con 2*sp las dos últimas caen
    fuera del pentagrama) y las zonas de mucha tinta que no son pentagrama.
    """
    tope = alto - int(np.ceil(4 * sp)) - 1
    if tope <= 0:
        return (0, 0.0)
    filas = np.arange(tope, dtype=float)
    indices = np.arange(alto, dtype=float)
    peine = None
    for k in range(5):
        valores = np.interp(filas + k * sp, indices, perfil)
        peine = valores if peine is None else np.minimum(peine, valores)
    aciertos = peine >= umbral
    return (int(aciertos.sum()), float(peine[aciertos].sum()))


def medir_interlinea(imagen_path):
    """Interlínea en píxeles, o None si en la página no hay pentagramas.

    Devolver None es parte del resultado, no un error: en un cancionero hay
    portadas, índices y páginas de texto donde no hay nada que medir.
    """
    perfiles, alto, ancho_banda = _perfiles_de_lineas(imagen_path)
    umbral = FRACCION_ANCHO * ancho_banda
    sp_max = min(70.0, alto / 12)

    ganadores = []
    for perfil in perfiles:
        mejor = None
        sp = 4.0
        while sp <= sp_max:
            puntaje = _puntaje_peine(perfil, alto, sp, umbral)
            if puntaje[0] and (mejor is None or puntaje > mejor[0]):
                mejor = (puntaje, sp, perfil)
            sp += PASO_BUSQUEDA
        if mejor:
            ganadores.append(mejor)

    # una sola franja puede acertar por casualidad (un renglón de texto, un
    # recuadro); pedimos que al menos dos franjas coincidan en la separación
    if len(ganadores) < 2:
        return None
    candidatos = sorted(g[1] for g in ganadores)
    mediana = candidatos[len(candidatos) // 2]
    de_acuerdo = [g for g in ganadores if abs(g[1] - mediana) <= max(1.0, 0.1 * mediana)]
    if len(de_acuerdo) < 2:
        return None

    # refino sobre la franja que mejor puntuó de las que están de acuerdo
    puntaje, entero, perfil = max(de_acuerdo, key=lambda g: g[0])
    refinada = (puntaje, entero)
    for sp in np.arange(max(4.0, entero - 1.0), entero + 1.001, 0.05):
        nuevo = _puntaje_peine(perfil, alto, float(sp), umbral)
        if nuevo > refinada[0]:
            refinada = (nuevo, float(sp))
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
        if interlinea is None:
            return {
                "nivel": "sin_pentagrama",
                "veredicto": "En la página medida no se encontraron pentagramas.",
                "interlinea_px": None, "ppp": round(ppp), "pagina_medida": pagina,
                "tamano_px": f"{ancho}x{alto}", "ppp_necesarios": None, "factor_necesario": None,
            }

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
