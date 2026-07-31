# partitura-a-xml

Convierte partituras en PDF a MusicXML editable, corriendo **enteramente en tu computadora** — sin servidor, sin costo, sin subir nada a ningún lado. Usa [Audiveris](https://github.com/Audiveris/audiveris) (reconocimiento óptico de música) y [MuseScore](https://musescore.org) para limpiar el resultado.

El resultado es siempre un **borrador editable**, no un producto terminado: la calidad depende del PDF de origen y va a necesitar correcciones a mano (ver [Límites conocidos](#límites-conocidos) más abajo).

## Requisitos

- **[Docker Desktop](https://www.docker.com/products/docker-desktop/)** (gratis para uso personal) — corre el motor de reconocimiento (Audiveris)
- **[MuseScore 4](https://musescore.org/es/download)** (gratis) — normaliza el resultado para que Sibelius lo pueda abrir sin problemas
- **[Ghostscript](https://www.ghostscript.com/)** y **poppler-utils** (`pdfinfo`, `pdfimages`) — reparan PDFs con problemas antes de pasarlos a Audiveris
- **Python 3.9 o más nuevo**

### Instalar los requisitos

**macOS** (con [Homebrew](https://brew.sh)):
```bash
brew install ghostscript poppler
```
Después instalá Docker Desktop y MuseScore 4 descargándolos de sus sitios oficiales (arriba).

**Windows:**
1. Instalá [Docker Desktop](https://www.docker.com/products/docker-desktop/) y [MuseScore 4](https://musescore.org/es/download) desde sus instaladores oficiales.
2. Instalá [Ghostscript](https://www.ghostscript.com/releases/gsdnld.html) y [poppler para Windows](https://github.com/oschwartz10612/poppler-windows/releases/) (bajá el zip, descomprimilo, y agregá su carpeta `bin` al PATH del sistema).

**Linux (Debian/Ubuntu):**
```bash
sudo apt install docker.io ghostscript poppler-utils
sudo snap install musescore  # o instalar MuseScore desde musescore.org
```

## Instalación

```bash
git clone <URL-de-este-repo>
cd partitura-a-xml
python3 -m venv .venv
source .venv/bin/activate   # en Windows: .venv\Scripts\activate
pip install -r requirements.txt
docker pull toprock/audiveris
```

## Uso

1. Abrí Docker Desktop (tiene que estar corriendo en segundo plano)
2. Corré:
   ```bash
   python3 app.py
   ```
3. Abrí **http://localhost:8000** en tu navegador
4. Subí un PDF y esperá — puede tardar varios minutos según el largo de la partitura
5. Descargá el `.musicxml` resultante

Si MuseScore no está instalado en la ruta habitual de tu sistema, definí la variable de entorno `MUSESCORE_PATH` con la ruta completa a su ejecutable antes de correr `app.py`.

## Límites conocidos

Estos son límites reales del motor de reconocimiento (Audiveris), no bugs de este script — ya están probados y documentados con partituras reales:

- No reconoce pentagramas de percusión corporal ni de instrumentos de acompañamiento (se pierden por completo)
- No reconoce cabezas de nota en cruz (ritmo hablado, no cantado) — esos compases quedan en blanco
- Compases con compases complejos o poco frecuentes a veces se malinterpretan
- Puede insertar cambios de clave que no existen en el original
- Indicaciones dinámicas, de tempo ("rit.", "rall.") y metronómicas a veces no se reconocen o quedan como texto suelto sin efecto real
- Letras con acentos pueden leerse mal (ej. "í" confundida con "l")
- En partituras a 4 voces sin nombres reconocibles se asume Soprano/Alto/Tenor/Bajo (de arriba hacia abajo); otras combinaciones (SAB, SSA, etc.) pueden quedar sin etiquetar
- Ocasionalmente Audiveris falla en una página puntual (un bug conocido y sin resolver del propio proyecto, [issue #583](https://github.com/Audiveris/audiveris/issues/583)) y la descarta del resultado sin avisar — este script detecta cuándo pasa y te avisa en pantalla, pero no puede recuperar el contenido perdido. Si ves ese aviso, revisá el resultado contra el PDF original.

## Por qué pasa por MuseScore y no solo por Audiveris

Audiveris exporta MusicXML técnicamente válido, pero Sibelius igual lo rechaza al abrirlo (su importador de MusicXML es frágil). MuseScore lo acepta sin problema, y al reexportarlo desde ahí queda un archivo que Sibelius sí abre. Por eso el pipeline siempre pasa por los dos pasos.

## Licencia

[AGPLv3](LICENSE) — heredada de Audiveris. Si corrés este código como un servicio de red al que otras personas acceden (no solo vos en tu compu), la licencia te obliga a publicar el código fuente completo, incluidas tus modificaciones.
