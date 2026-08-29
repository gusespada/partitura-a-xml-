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

## Antes de convertir: la resolución del PDF

Este es **el factor que más decide** si el resultado sirve o es basura, y no se ve
a simple vista. Al subir el PDF la herramienta lo mide sola y te avisa antes de
hacerte esperar diez minutos al pedo.

Lo que se mide no son los ppp del archivo ni los megapíxeles de la cámara, sino
**cuántos píxeles hay entre dos líneas del pentagrama** (la *interlínea*). Audiveris
usa esa distancia para calcular el tamaño de todo lo demás — cabezas de nota, plicas,
alteraciones, puntillos — y por debajo de cierto umbral no las puede distinguir.

| Interlínea | Qué esperar |
|---|---|
| 25 px o más | Lectura casi limpia |
| 20-25 px | Anda, con algunos errores |
| 15-20 px | Bastantes errores |
| menos de 15 px | Audiveris no encuentra ni las barras de compás |

Por eso no alcanza con decir "sacala a 300 ppp": **una partitura coral a 5 o 6
pentagramas por sistema está impresa mucho más chica que una de piano**, así que con
los mismos ppp la coral puede quedar por debajo del umbral mientras la de piano pasa
cómoda. Hay que medir, no suponer.

### Si la sacás con el celular

**No uses el modo "Escanear documentos"** (el de la app Notas o Archivos en iPhone, o
el equivalente en Android). Endereza la hoja y recorta lindo, pero **te baja la imagen
a unos 200 ppp**, y en una partitura coral eso da una interlínea de 11 a 13 px: por
debajo del umbral. Es la causa más común de que la conversión salga mal.

Usá la **cámara normal**, que tiene el doble o el triple de píxeles:

| Cómo la sacaste | Resolución sobre una hoja A4 |
|---|---|
| Modo "Escanear documentos" | ~200 ppp |
| Foto común, cámara de 12 MP | ~345 ppp |
| Foto común, cámara de 48 MP | ~690 ppp |
| Escáner plano | los que le pongas (usá 400-600) |

Con la cámara normal, además:

- Poné la hoja **bien plana** — un vidrio o un libro pesado encima. La comba de la
  hoja curva los pentagramas y eso también rompe la lectura.
- La cámara **paralela** a la hoja, no en diagonal.
- Que la hoja **llene el encuadre**: si sobra mesa alrededor, estás tirando píxeles.
- Buena luz pareja, sin sombra ni brillo.

### Si tenés escáner

Es lo más seguro: 400-600 ppp en escala de grises, y de paso te ahorrás la comba de la
hoja. Para partituras corales chicas, mejor 600.

## Uso

1. Abrí Docker Desktop (tiene que estar corriendo en segundo plano)
2. Corré:
   ```bash
   python3 app.py
   ```
3. Abrí **http://localhost:8000** en tu navegador
4. Subí un PDF. Primero se mide la resolución (un par de segundos): si no alcanza te
   lo dice ahí mismo, con el número medido y cuánta falta, y podés volver a sacar la
   foto en vez de esperar la conversión entera. Si querés intentarlo igual, hay un
   botón para eso.
5. Esperá — puede tardar varios minutos según el largo de la partitura
6. Descargá el `.musicxml` resultante

Si MuseScore no está instalado en la ruta habitual de tu sistema, definí la variable de entorno `MUSESCORE_PATH` con la ruta completa a su ejecutable antes de correr `app.py`.

## Límites conocidos

Estos son límites reales del motor de reconocimiento (Audiveris), no bugs de este script — ya están probados y documentados con partituras reales:

- Si la interlínea del PDF baja de 15 px no hay nada que hacer: se pierden las barras de compás
  y el resultado sale inservible aunque la partitura original esté impresa perfecta (ver
  [Antes de convertir](#antes-de-convertir-la-resolución-del-pdf))

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
