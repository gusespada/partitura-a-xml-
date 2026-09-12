#!/usr/bin/env python3
"""
Preprocesamiento de imagen ANTES de pasarle la partitura a Audiveris.

Pensado para el caso real de esta herramienta: gente con carpetas de fotocopias
de hace décadas, que las fotografía con el celular. Esas imágenes llegan
torcidas, a color, con sombra del espiral y luz despareja. Audiveris asume
pentagramas horizontales y buen contraste, así que buena parte de los errores
no son del reconocimiento sino de la imagen que le damos.

Tres pasos, todos con numpy + Pillow (sin dependencias nuevas):

1. enderezar          - corrige la rotación (Audiveris busca líneas
                        horizontales, y una foto suele venir 1-3 grados rotada)
2. emparejar_iluminacion - divide la imagen por su propio fondo desenfocado, lo
                        que borra la sombra del lomo y el degradé de luz
3. binarizar_sauvola  - umbral LOCAL en vez de global, para separar la tinta del
                        papel amarillento de una fotocopia vieja

IMPORTANTE — qué conviene usar, medido y no supuesto (2026-09-02, banco propio
sobre una fotocopia de CamScanner, midiendo compases cuya duración cierra):

    sin preprocesar (PDF original) .............. 81/147 compases bien
    solo re-renderizar sin pérdida .............. 84/147   <- mejor
    + enderezar ................................. 84/147   (igual: la hoja ya venía derecha)
    + emparejar iluminación ..................... 69/147   <- EMPEORA
    + binarizar ................................. 69/147, y se pierden 76 notas

Por eso el valor por omisión es solo `enderezar` (que además implica el
re-renderizado sin pérdida, que es de donde viene la mejora real).
**La iluminación y la binarización quedan disponibles pero APAGADAS**: Audiveris
ya binariza internamente y lo hace mejor que nosotros; encimarle una
binarización propia le saca información y le hace perder notas. Con la versión
5.3 el efecto era catastrófico (detectaba 22 compases de 49).

ACTUALIZACIÓN 2026-09-12 — NO SE USA EN pipeline.py. Se midió el valor por
omisión (re-render a TIFF + enderezar) con Audiveris 5.11 sobre los 15 escaneos
reales que convirtió el servicio de suscriptores, contra el mismo PDF sin tocar:
mejoró 6 (uno de 0 a 128 compases bien, porque la 5.11 dejó de abortar), empeoró
3 (uno de 986 a 683 notas), 5 iguales y 1 dudoso (más compases bien, pero el coro
partido en más voces). Ninguna hoja venía torcida más de 1 grado, así que el
efecto es del re-render, no del enderezado, y no hay regla que diga de antemano en
cuál conviene. El "65% -> 73%" de más abajo era una hoja torcida apenas 0,5 grados:
ruido del mismo tipo, no una ganancia del enderezado. Resultados en el VPS:
/opt/audiveris511/regresion3/resultados.json.
"""
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

DPI_RENDER = 300


# --------------------------------------------------------------- enderezar
def _puntaje_horizontalidad(a):
    """Qué tan horizontales están las líneas. Un pentagrama derecho concentra
    la tinta en pocas filas, así que el perfil por filas tiene picos altos y
    su derivada mucha varianza. Torcido, la tinta se reparte y el perfil se
    aplana."""
    perfil = (255.0 - a).sum(axis=1)
    return float(np.diff(perfil).var())


def _mejor_angulo(img, grados, paso):
    mejor, mejor_p = 0.0, -1.0
    ang = -grados
    while ang <= grados + 1e-9:
        rot = img.rotate(ang, resample=Image.BILINEAR, fillcolor=255)
        p = _puntaje_horizontalidad(np.asarray(rot, dtype=np.float32))
        if p > mejor_p:
            mejor, mejor_p = ang, p
        ang += paso
    return mejor


def enderezar(gris, max_grados=4.0):
    """Devuelve (imagen_enderezada, angulo_aplicado). Busca grueso y después
    afina alrededor del mejor, sobre una copia chica para que sea rápido."""
    img = Image.fromarray(gris)
    ancho = 1000
    if img.width > ancho:
        chica = img.resize((ancho, int(img.height * ancho / img.width)), Image.BILINEAR)
    else:
        chica = img

    grueso = _mejor_angulo(chica, max_grados, 0.5)
    fino = grueso + _mejor_angulo(chica.rotate(grueso, resample=Image.BILINEAR, fillcolor=255), 0.5, 0.1)

    if abs(fino) < 0.05:
        return gris, 0.0
    enderezada = img.rotate(fino, resample=Image.BICUBIC, fillcolor=255)
    return np.asarray(enderezada), round(fino, 2)


# ----------------------------------------------------- emparejar iluminacion
def emparejar_iluminacion(gris, radio=None):
    """Divide la imagen por su fondo (una versión muy desenfocada de sí misma).
    Lo que queda es la tinta sin la sombra ni el degradé de luz."""
    if radio is None:
        radio = max(15, gris.shape[1] // 40)
    fondo = np.asarray(
        Image.fromarray(gris).filter(ImageFilter.GaussianBlur(radio)), dtype=np.float32
    )
    corregida = gris.astype(np.float32) * 255.0 / np.maximum(fondo, 1.0)
    return np.clip(corregida, 0, 255).astype(np.uint8)


# --------------------------------------------------------------- binarizar
def _integral(a):
    return np.pad(a.cumsum(0).cumsum(1), ((1, 0), (1, 0)))


def binarizar_sauvola(gris, ventana=31, k=0.2, R=128.0):
    """Umbral local de Sauvola. Cada píxel se compara contra la media y el
    desvío de su vecindario, no contra un único umbral global: por eso funciona
    en fotocopias con el papel manchado o la luz despareja."""
    if ventana % 2 == 0:
        ventana += 1
    a = gris.astype(np.float64)
    i1, i2 = _integral(a), _integral(a * a)
    alto, ancho = a.shape
    r = ventana // 2

    y0 = np.clip(np.arange(alto) - r, 0, alto)[:, None]
    y1 = np.clip(np.arange(alto) + r + 1, 0, alto)[:, None]
    x0 = np.clip(np.arange(ancho) - r, 0, ancho)[None, :]
    x1 = np.clip(np.arange(ancho) + r + 1, 0, ancho)[None, :]

    cuenta = ((y1 - y0) * (x1 - x0)).astype(np.float64)
    s1 = i1[y1, x1] - i1[y0, x1] - i1[y1, x0] + i1[y0, x0]
    s2 = i2[y1, x1] - i2[y0, x1] - i2[y1, x0] + i2[y0, x0]
    del i1, i2

    media = s1 / cuenta
    desv = np.sqrt(np.maximum(s2 / cuenta - media * media, 0.0))
    del s1, s2
    umbral = media * (1.0 + k * (desv / R - 1.0))
    return np.where(a > umbral, 255, 0).astype(np.uint8)


# ----------------------------------------------------------------- pipeline
def preprocesar_imagen(gris, interlinea=None, pasos=("enderezar",)):
    """Aplica los pasos pedidos y devuelve (imagen, info)."""
    info = {}
    if "enderezar" in pasos:
        gris, angulo = enderezar(gris)
        info["angulo"] = angulo
    if "iluminacion" in pasos:
        gris = emparejar_iluminacion(gris)
    if "binarizar" in pasos:
        # la ventana tiene que abarcar varias líneas del pentagrama
        ventana = int(max(15, (interlinea or 20) * 2 + 1))
        gris = binarizar_sauvola(gris, ventana=ventana)
        info["ventana"] = ventana
    return gris, info


def _dpi_nativo(pdf_path):
    """Resolución de las imágenes que ya tiene adentro el PDF, si es un escaneo.

    Importa para no tirar información: si alguien escaneó a 600 ppp y nosotros
    renderizamos a 300, le estaríamos bajando la resolución a la mitad justo en
    el paso que debería mejorarla. Devuelve None si el PDF no trae imágenes
    (o sea, es vectorial y se puede renderizar a lo que queramos).
    """
    try:
        salida = subprocess.run(["pdfimages", "-list", str(pdf_path)],
                                capture_output=True, text=True, timeout=60).stdout
    except Exception:
        return None
    # Se toma la resolución de la imagen MÁS GRANDE, no la mayor de todas: un
    # escaneo de CamScanner mete además una franja chica de marca de agua a 504
    # ppp, y quedarse con ese número haría renderizar la partitura (292 ppp) al
    # doble, agrandando el archivo sin agregar ni un dato.
    mejor_area, mejor_ppp = 0, None
    for linea in salida.splitlines()[2:]:
        campos = linea.split()
        if len(campos) < 14:
            continue
        try:
            area = int(campos[3]) * int(campos[4])
            ppp = int(campos[12])
        except ValueError:
            continue
        if area > mejor_area:
            mejor_area, mejor_ppp = area, ppp
    return mejor_ppp


def preprocesar_pdf(pdf_path, salida_pdf, interlinea=None, pasos=("enderezar",),
                    dpi=None):
    """Renderiza el PDF, preprocesa cada página y arma un PDF nuevo.
    Devuelve la lista de info por página."""
    pdf_path, salida_pdf = Path(pdf_path), Path(salida_pdf)
    if dpi is None:
        nativo = _dpi_nativo(pdf_path)
        # nunca por debajo de 300 (si el escaneo es peor, no ganamos nada bajando
        # más), ni por encima de 600 (a partir de ahí solo agranda el archivo y
        # el tiempo de proceso, sin darle más información a Audiveris)
        dpi = max(DPI_RENDER, min(nativo, 600)) if nativo else DPI_RENDER
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            ["pdftoppm", "-gray", "-png", "-r", str(dpi), str(pdf_path), str(Path(tmp) / "pag")],
            check=True, timeout=300,
        )
        paginas = sorted(Path(tmp).glob("pag-*.png"))
        if not paginas:
            raise RuntimeError("pdftoppm no generó ninguna página")

        procesadas, infos = [], []
        for p in paginas:
            gris = np.asarray(Image.open(p).convert("L"))
            gris, info = preprocesar_imagen(gris, interlinea=interlinea, pasos=pasos)
            infos.append(info)
            # Si quedó en blanco y negro puro, se guarda como imagen de 1 bit.
            # NO es un detalle: Pillow escribe las imágenes en escala de grises
            # dentro del PDF como JPEG, y el JPEG sobre una imagen binarizada
            # deja halos alrededor de cada línea y cada cabeza de nota — o sea
            # que el paso que venía a limpiar la imagen la terminaba ensuciando.
            # En 1 bit Pillow usa compresión sin pérdida.
            binaria = np.unique(gris).size <= 2
            procesadas.append(Image.fromarray(gris).convert("1" if binaria else "L"))

        if salida_pdf.suffix.lower() in (".tif", ".tiff"):
            # Salida en escala de grises sin pérdida: dentro de un PDF, Pillow
            # solo sabe guardar los grises como JPEG. Audiveris lee TIFF igual
            # que PDF, y ahí sí se puede comprimir sin perder nada.
            procesadas[0].save(salida_pdf, save_all=True, append_images=procesadas[1:],
                               compression="tiff_deflate", resolution=float(dpi))
        else:
            procesadas[0].save(salida_pdf, save_all=True, append_images=procesadas[1:],
                               resolution=float(dpi))
    return infos
