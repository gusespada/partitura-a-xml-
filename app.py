#!/usr/bin/env python3
"""Servidor local: subís un PDF, esperás (puede tardar varios minutos), y te
descarga el MusicXML directo. Sin cola de trabajos ni email — pensado para
que una sola persona lo use en su propia compu.

Uso: python3 app.py, después abrir http://localhost:8000
"""
import shutil
import tempfile
import uuid
from pathlib import Path

from flask import Flask, request, Response, abort

from pipeline import DISCLAIMER, convert
from resolucion import diagnosticar

MAX_UPLOAD_MB = 20

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024

# trabajos ya convertidos, esperando que el usuario los descargue: job_id -> (musicxml_path, job_dir, download_name)
READY = {}

PAGE = """
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Partitura a MusicXML</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 560px; margin: 3rem auto; padding: 0 1.5rem; color: #222; }}
    @media (prefers-color-scheme: dark) {{ body {{ color: #eee; background: #1c1c1a; }} .aviso {{ color: #aaa !important; }} }}
    h1 {{ font-size: 1.3rem; }}
    label {{ display: block; margin-top: 1.2rem; font-weight: bold; font-size: 0.95rem; }}
    input[type=file] {{ display: block; margin-top: 0.4rem; width: 100%; padding: 0.6rem; box-sizing: border-box; }}
    button {{ margin-top: 1.6rem; padding: 0.7rem 1.6rem; font-size: 1rem; cursor: pointer; }}
    .msg {{ margin-top: 1.5rem; padding: 1rem; border-radius: 6px; }}
    .msg.error {{ background: #fce8e6; color: #611a15; }}
    .msg.aviso {{ background: #fef7e0; color: #5c4413; }}
    .msg.ok {{ background: #e6f4ea; color: #14532d; }}
    .msg h2 {{ font-size: 1rem; margin: 0 0 0.6rem; }}
    .msg ul {{ margin: 0.6rem 0 0; padding-left: 1.2rem; }}
    .medida {{ font-family: ui-monospace, monospace; font-size: 0.85rem; }}
    .aviso-titulo {{ margin-top: 2.5rem; font-weight: bold; text-transform: uppercase; font-size: 0.9rem; }}
    .aviso {{ margin-top: 0.5rem; font-size: 0.85rem; color: #555; line-height: 1.5; }}
  </style>
</head>
<body>
  <h1>Digitalizá tu partitura (PDF → MusicXML)</h1>
  {message}
  <form method="post" enctype="multipart/form-data">
    <label>PDF de la partitura
      <input type="file" name="pdf" accept="application/pdf" required>
    </label>
    <button type="submit">Convertir</button>
  </form>
  <p class="aviso-titulo">Por favor, leé esto atentamente</p>
  <ul class="aviso">
    <li>La conversión puede tardar varios minutos, según el largo de la partitura — la página
      va a quedar esperando, no la cierres.</li>
    <li><b>Antes de convertir se mide la resolución del PDF</b> y te avisa si no alcanza, así no
      esperás al pedo. Lo que se mide es cuántos píxeles hay entre dos líneas del pentagrama:
      hacen falta 20 como mínimo, 25 o más para que salga limpio.</li>
    <li><b>Si la sacás con el celular, usá la cámara normal, no el modo "Escanear documentos".</b>
      Ese modo endereza la hoja pero te la baja a unos 200 ppp, que en una partitura coral de 4 a 6
      pentagramas por sistema no alcanza. Una foto común de la misma cámara tiene el doble o el
      triple de píxeles. Poné la hoja bien plana (un vidrio o un libro pesado encima), la cámara
      paralela a la hoja, buena luz y que la hoja llene el encuadre.</li>
    <li>Un escáner plano a 400-600 ppp es lo más seguro, sobre todo porque además evita la comba
      de la hoja, que también molesta.</li>
    <li>{disclaimer}</li>
  </ul>
</body>
</html>
"""


def _bloque_medida(d):
    """Resumen legible de la medición de resolución."""
    linea = (
        f'<p class="medida">página medida: {d["pagina_medida"]} &middot; {d["tamano_px"]} px '
        f'(~{d["ppp"]} ppp) &middot; interlínea: <b>{d["interlinea_px"]} px</b></p>'
    )
    return linea


PENDIENTES = {}  # job_id -> (pdf_path, job_dir, original_stem)


@app.route("/", methods=["GET"])
def index():
    return PAGE.format(message="", disclaimer=DISCLAIMER)


@app.route("/", methods=["POST"])
def upload():
    pdf_file = request.files.get("pdf")
    if not pdf_file or not pdf_file.filename:
        return PAGE.format(message='<div class="msg error">Subí un archivo PDF.</div>', disclaimer=DISCLAIMER)
    if not pdf_file.filename.lower().endswith(".pdf"):
        return PAGE.format(message='<div class="msg error">El archivo tiene que ser un PDF.</div>', disclaimer=DISCLAIMER)

    job_id = uuid.uuid4().hex
    job_dir = Path(tempfile.mkdtemp(prefix=f"partitura-{job_id}-"))
    original_stem = Path(pdf_file.filename).stem
    pdf_path = job_dir / f"{job_id}.pdf"
    pdf_file.save(pdf_path)

    diagnostico = None
    try:
        diagnostico = diagnosticar(pdf_path)
    except Exception:
        diagnostico = None  # si la medición falla, seguimos igual: es un aviso, no un requisito

    if diagnostico and diagnostico["nivel"] == "sin_pentagrama":
        # no es motivo para frenar: puede ser un PDF ya digital (sin imágenes),
        # o que la página del medio sea una portada o un índice
        diagnostico = None

    if diagnostico and diagnostico["nivel"] == "insuficiente":
        PENDIENTES[job_id] = (pdf_path, job_dir, original_stem)
        aviso = (
            '<div class="msg aviso">'
            "<h2>La resolución de este PDF no alcanza</h2>"
            f"<p>{diagnostico['veredicto']}</p>"
            + _bloque_medida(diagnostico) +
            f"<p>Para que Audiveris pueda leerla hacen falta unos <b>{diagnostico['ppp_necesarios']} ppp</b>"
            f" ({diagnostico['factor_necesario']}x más de lo que tiene ahora).</p>"
            "<ul>"
            "<li>Si la sacaste con el modo <b>Escanear documentos</b> del celular, repetila con la"
            " <b>cámara normal</b>: ese modo baja la imagen a unos 200 ppp y es justo lo que falta.</li>"
            "<li>Mejor todavía: escáner plano a 400-600 ppp.</li>"
            "</ul>"
            f'<form method="post" action="/convertir-igual/{job_id}">'
            '<button type="submit">Convertir igual</button></form>'
            "</div>"
        )
        return PAGE.format(message=aviso, disclaimer=DISCLAIMER)

    return _convertir(pdf_path, job_dir, job_id, original_stem, diagnostico)


@app.route("/convertir-igual/<job_id>", methods=["POST"])
def convertir_igual(job_id):
    entrada = PENDIENTES.pop(job_id, None)
    if not entrada:
        abort(404)
    pdf_path, job_dir, original_stem = entrada
    return _convertir(pdf_path, job_dir, job_id, original_stem, None)


def _convertir(pdf_path, job_dir, job_id, original_stem, diagnostico):
    try:
        musicxml_path, paginas_descartadas = convert(pdf_path, job_dir, job_id)
        aviso = ""
        if paginas_descartadas:
            aviso = (
                f'<div class="msg error">ATENCIÓN: Audiveris no pudo procesar {paginas_descartadas} '
                "página(s) del PDF y las descartó — es probable que al resultado le falte una parte de "
                "la partitura (a veces el principio). Revisalo contra el PDF original.</div>"
            )
        if diagnostico and diagnostico["nivel"] == "justo":
            aviso += (
                '<div class="msg aviso">La resolución del PDF está justa, así que esperá bastantes '
                "errores." + _bloque_medida(diagnostico) + "</div>"
            )
        READY[job_id] = (musicxml_path, job_dir, f"{original_stem}.musicxml")
        message = f'{aviso}<div class="msg ok"><a href="/download/{job_id}">Descargar {original_stem}.musicxml</a></div>'
        return PAGE.format(message=message, disclaimer=DISCLAIMER)
    except Exception as exc:
        shutil.rmtree(job_dir, ignore_errors=True)
        return PAGE.format(
            message=f'<div class="msg error">No se pudo convertir: {exc}</div>',
            disclaimer=DISCLAIMER,
        )


@app.route("/download/<job_id>", methods=["GET"])
def download(job_id):
    entry = READY.pop(job_id, None)
    if not entry:
        abort(404)
    musicxml_path, job_dir, download_name = entry
    content = musicxml_path.read_bytes()  # leer antes de borrar la carpeta temporal
    shutil.rmtree(job_dir, ignore_errors=True)
    return Response(
        content,
        mimetype="application/vnd.recordare.musicxml+xml",
        headers={"Content-Disposition": f'attachment; filename="{download_name}"'},
    )


if __name__ == "__main__":
    print("Abrí http://localhost:8000 en tu navegador")
    app.run(host="127.0.0.1", port=8000)
