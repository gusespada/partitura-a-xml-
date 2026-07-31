#!/usr/bin/env python3
"""
Lógica de conversión: PDF -> MusicXML, usando Audiveris (Docker) + MuseScore
(instalado en la compu) para normalizar el resultado, más un par de arreglos
para errores conocidos de Audiveris. Sin cola de trabajos ni email — se usa
de forma sincrónica desde app.py: un PDF entra, un MusicXML sale.
"""
import platform
import re
import shutil
import subprocess
from pathlib import Path

DISCLAIMER = (
    "Este archivo es un borrador generado automáticamente a partir del PDF. "
    "La calidad depende de la partitura original y puede requerir correcciones manuales "
    "(dinámicas, letra silabeada, indicaciones de tempo, alguna octava, pentagramas de "
    "percusión corporal o de instrumentos de acompañamiento, que no se reconocen). "
    "Abrilo en MuseScore o Sibelius para revisarlo y corregirlo antes de usarlo."
)


def find_musescore():
    """Busca el ejecutable de MuseScore según el sistema operativo. Se puede
    forzar la ruta con la variable de entorno MUSESCORE_PATH si no lo encuentra."""
    import os

    override = os.environ.get("MUSESCORE_PATH")
    if override and Path(override).exists():
        return override

    system = platform.system()
    candidates = []
    if system == "Darwin":
        candidates = [
            "/Applications/MuseScore 4.app/Contents/MacOS/mscore",
            "/Applications/MuseScore 3.app/Contents/MacOS/mscore",
        ]
    elif system == "Windows":
        candidates = [
            r"C:\Program Files\MuseScore 4\bin\MuseScore4.exe",
            r"C:\Program Files\MuseScore 3\bin\MuseScore3.exe",
        ]
    else:  # Linux
        candidates = ["mscore", "musescore4", "musescore"]

    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
        found = shutil.which(candidate)
        if found:
            return found

    raise RuntimeError(
        "No encontré MuseScore instalado. Instalalo desde musescore.org, o si está en "
        "una ruta no estándar, definí la variable de entorno MUSESCORE_PATH con la ruta "
        "completa al ejecutable."
    )


def preprocess_pdf(pdf_path: Path, job_dir: Path) -> Path:
    """Sanea el PDF antes de pasarlo a Audiveris. Devuelve la ruta a usar
    (el original si no hizo falta cambiar nada).

    Dos problemas reales encontrados con PDFs reales:
    1. Estructura interna corrupta que el parser de Audiveris no puede leer
       ("catalog invalid") pero que sí abren lectores más permisivos como
       Ghostscript. Re-serializar con Ghostscript la repara en la mayoría
       de los casos.
    2. Algunos escaneos declaran un tamaño de página físico absurdo (bug
       típico de ciertos escáneres/DPI mal seteado): la imagen real puede
       ser de resolución normal, pero cualquier lector la infla a decenas
       de millones de píxeles al renderizarla, y Audiveris la rechaza
       ("Too large image"). Se detecta por el tamaño de página declarado
       y, si la página es casi toda una imagen incrustada, se extrae esa
       imagen nativa y arma un PDF nuevo con un DPI razonable.
    """
    repaired = job_dir / f"{pdf_path.stem}_repaired.pdf"
    try:
        subprocess.run(
            ["gs", "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=pdfwrite", f"-o{repaired}", str(pdf_path)],
            check=True, capture_output=True, timeout=120,
        )
        working = repaired if repaired.exists() else pdf_path
    except Exception:
        working = pdf_path  # si Ghostscript falla, seguimos con el original

    info = subprocess.run(["pdfinfo", str(working)], capture_output=True, text=True, timeout=30)
    match = re.search(r"Page size:\s+([\d.]+) x ([\d.]+) pts", info.stdout)
    page_count_match = re.search(r"Pages:\s+(\d+)", info.stdout)
    if not match or not page_count_match:
        return working
    width_in, height_in = float(match.group(1)) / 72, float(match.group(2)) / 72
    if width_in <= 14 and height_in <= 14:
        return working  # tamaño de página razonable, no hace falta nada más

    extract_dir = job_dir / "native_extract"
    extract_dir.mkdir(exist_ok=True)
    subprocess.run(["pdfimages", "-png", str(working), str(extract_dir / "img")], timeout=60)
    images = sorted(extract_dir.glob("img-*.png"))
    page_count = int(page_count_match.group(1))
    if len(images) != page_count:
        return working  # no es un escaneo de una imagen por página (probable PDF vectorial) -> no tocar

    from PIL import Image
    pil_images = [Image.open(f).convert("RGB") for f in images]
    rebuilt = job_dir / f"{pdf_path.stem}_rebuilt.pdf"
    pil_images[0].save(rebuilt, save_all=True, append_images=pil_images[1:], resolution=300.0)
    return rebuilt


def run_audiveris(job_dir: Path, job_id: str, pdf_path: Path):
    """Corre Audiveris en Docker sobre el PDF (ya preprocesado).

    Devuelve (mxl_path, paginas_descartadas). Audiveris a veces falla en una
    página puntual (crash interno, imagen ilegible) y la descarta en silencio
    sin abortar el resto del libro — el .mxl final se genera igual, pero le
    falta esa página, sin ningún aviso. Se detecta buscando en el log las dos
    frases que usa Audiveris para señalar que una página quedó afuera
    ("flagged as invalid" para imágenes ilegibles, "Error in performing"
    para crashes internos durante el procesamiento) — es un bug conocido de
    Audiveris (https://github.com/Audiveris/audiveris/issues/583, sigue
    abierto), no hay forma de evitarlo desde acá, solo avisar.
    """
    audiveris_input_dir = job_dir / "audiveris_input"
    audiveris_input_dir.mkdir(exist_ok=True)
    shutil.copy(pdf_path, audiveris_input_dir / f"{job_id}.pdf")

    out_dir = job_dir / "audiveris_out"
    out_dir.mkdir(exist_ok=True)
    result = subprocess.run(
        [
            "docker", "run", "--rm",
            "-v", f"{audiveris_input_dir}:/input:ro",
            "-v", f"{out_dir}:/output",
            "toprock/audiveris",
        ],
        capture_output=True, text=True, timeout=900,
    )
    mxl_path = out_dir / job_id / f"{job_id}.mxl"
    if not mxl_path.exists():
        raise RuntimeError(f"Audiveris no generó salida.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}")
    paginas_descartadas = len(re.findall(r"flagged as invalid|Error in performing \[", result.stdout))
    return mxl_path, paginas_descartadas


def run_musescore_normalize(mxl_path: Path, job_dir: Path, job_id: str) -> Path:
    """Abre el .mxl en MuseScore y lo reexporta como .musicxml limpio.

    Necesario porque Audiveris exporta MusicXML técnicamente válido que Sibelius
    igual rechaza (importador frágil); MuseScore lo acepta y al reexportarlo
    queda un archivo que Sibelius sí abre. Ver README para el detalle.

    Usa -f/--force: cuando Audiveris no reconoce del todo un compás (pentagramas
    en blanco, ritmos que no pudo transcribir) el compás queda con duración
    incompleta, y sin -f MuseScore rechaza el archivo entero en vez de solo
    ese compás. Con -f lo carga igual, completando lo que falta con silencios.
    """
    out_path = job_dir / f"{job_id}.musicxml"
    musescore = find_musescore()
    result = subprocess.run(
        [musescore, "-f", "-o", str(out_path), str(mxl_path)],
        capture_output=True, text=True, timeout=300,
    )
    if not out_path.exists():
        raise RuntimeError(f"MuseScore no generó salida.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}")
    return out_path


VOICE_SOUND_MAP = [
    (re.compile(r"SOPRANO", re.I), "voice.soprano", None),
    (re.compile(r"MEZZO", re.I), "voice.mezzo-soprano", None),
    (re.compile(r"CONTRALTO|ALTO", re.I), "voice.alto", None),
    (re.compile(r"TENOR", re.I), "voice.tenor", None),
    (re.compile(r"BAR[IÍ]TONO|BARITONE", re.I), "voice.baritone", "Baritone"),
    (re.compile(r"BAJO|BASS", re.I), "voice.bass", "Bass"),
]

GENERIC_SATB_NAMES = ["Soprano", "Contralto", "Tenor", "Bajo"]


def fix_voice_instruments(musicxml_path: Path):
    """Corrige el sonido de instrumento y agrupa las voces con una llave.

    Audiveris exporta todas las partes con instrument-sound="keyboard.piano"
    (un placeholder incorrecto) y sin part-group, pero corregir solo eso no
    alcanza: Sibelius ignora ese campo al importar y adivina el instrumento
    por el nombre de la parte contra su propio diccionario interno — y no
    tiene "BAJO" mapeado a voz, así que cae en un instrumento transpositor
    de metales (tipo tuba/contrabajo), lo que corre la nota una octava en la
    partitura aunque el tono real (el que se escucha) sea correcto y además
    la deja afuera del grupo del coro. Para las voces graves (bajo/barítono)
    separamos el nombre "canónico" (en inglés, que Sibelius sí reconoce como
    voz) del nombre impreso (el original, en español) con part-name-display.

    Si Audiveris no pudo leer ningún nombre y las 4 partes quedaron con el
    mismo nombre genérico (ej. "Voice"), se asume SATB de arriba hacia abajo
    — el caso más común para un coro de 4 voces. Con otras combinaciones
    (SAB, SSA, etc.) no se adivina nada.
    """
    text = musicxml_path.read_text()

    part_names = re.findall(r"<part-name>(.*?)</part-name>", text)
    if len(part_names) == 4 and len(set(part_names)) == 1:
        for new_name in GENERIC_SATB_NAMES:
            text = text.replace(f"<part-name>{part_names[0]}</part-name>", f"<part-name>{new_name}</part-name>", 1)

    def fix_part(match):
        block = match.group(0)
        name_match = re.search(r"<part-name>(.*?)</part-name>", block)
        if not name_match:
            return block
        name = name_match.group(1)
        for pattern, sound, canonical_name in VOICE_SOUND_MAP:
            if pattern.search(name):
                block = re.sub(
                    r"<instrument-sound>.*?</instrument-sound>",
                    f"<instrument-sound>{sound}</instrument-sound>",
                    block,
                )
                if canonical_name:
                    block = block.replace(
                        f"<part-name>{name}</part-name>",
                        f'<part-name print-object="no">{canonical_name}</part-name>\n'
                        f"      <part-name-display>\n"
                        f"        <display-text>{name}</display-text>\n"
                        f"        </part-name-display>",
                    )
                return block
        return block

    text = re.sub(r'<score-part id="[^"]+">.*?</score-part>', fix_part, text, flags=re.S)

    if "<part-group" not in text:
        text = text.replace(
            "<part-list>",
            '<part-list>\n    <part-group type="start" number="1">\n'
            "      <group-symbol>bracket</group-symbol>\n"
            "      <group-barline>yes</group-barline>\n"
            "      </part-group>",
            1,
        )
        text = text.replace(
            "</part-list>",
            '    <part-group type="stop" number="1"/>\n  </part-list>',
            1,
        )

    musicxml_path.write_text(text)


def fix_tenor_octave(musicxml_path: Path):
    """Corrige la octava del Tenor cuando Audiveris no detectó el pequeño "8"
    bajo la clave de sol (el tenor debería sonar una octava más grave de lo
    escrito, convención estándar en partituras corales).

    Señal usada: la parte de Tenor tiene clave de sol simple (sin
    clef-octave-change) Y su tono promedio queda igual o más agudo que el de
    la Contralto — estructuralmente imposible en un SATB bien escrito, así
    que es una corrección segura basada en comparar contra la otra voz de
    la misma partitura, no una adivinanza a ciegas.
    """
    text = musicxml_path.read_text()

    id_to_name = {}
    for pid, block in re.findall(r'<score-part id="(P\d+)">(.*?)</score-part>', text, re.S):
        name_match = re.search(r"<part-name[^>]*>([^<]*)</part-name>", block)
        id_to_name[pid] = name_match.group(1) if name_match else ""

    tenor_id = next((pid for pid, name in id_to_name.items() if re.search(r"TENOR", name, re.I)), None)
    alto_id = next((pid for pid, name in id_to_name.items() if re.search(r"CONTRALTO|ALTO", name, re.I)), None)
    if not tenor_id or not alto_id:
        return

    def part_block(pid):
        m = re.search(rf'<part id="{pid}">.*?(?=<part id="|</score-partwise>)', text, re.S)
        return m.group(0) if m else ""

    tenor_block = part_block(tenor_id)
    alto_block = part_block(alto_id)
    tenor_octaves = [int(o) for o in re.findall(r"<octave>(\d)</octave>", tenor_block)]
    alto_octaves = [int(o) for o in re.findall(r"<octave>(\d)</octave>", alto_block)]
    if not tenor_octaves or not alto_octaves:
        return

    if "<clef-octave-change>" in tenor_block:
        return  # ya tiene la marca de octava, no hace falta tocar nada
    if sum(tenor_octaves) / len(tenor_octaves) < sum(alto_octaves) / len(alto_octaves):
        return  # el tenor ya está por debajo de la contralto, está bien como está

    fixed_block = re.sub(r"(<octave>)(\d)(</octave>)", lambda m: f"{m.group(1)}{int(m.group(2)) - 1}{m.group(3)}", tenor_block)
    fixed_block = re.sub(
        r"(<clef>\s*<sign>G</sign>\s*<line>2</line>\s*)(</clef>)",
        r"\1<clef-octave-change>-1</clef-octave-change>\n          \2",
        fixed_block,
    )
    text = text.replace(tenor_block, fixed_block, 1)
    musicxml_path.write_text(text)


def convert(pdf_path: Path, job_dir: Path, job_id: str):
    """Corre el pipeline completo. Devuelve (musicxml_path, paginas_descartadas)."""
    pdf_to_use = preprocess_pdf(pdf_path, job_dir)
    mxl_path, paginas_descartadas = run_audiveris(job_dir, job_id, pdf_to_use)
    musicxml_path = run_musescore_normalize(mxl_path, job_dir, job_id)
    fix_voice_instruments(musicxml_path)
    fix_tenor_octave(musicxml_path)
    return musicxml_path, paginas_descartadas
