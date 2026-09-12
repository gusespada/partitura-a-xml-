# Audiveris 5.11.0 desde el .deb oficial (trae su propio JRE, no hace falta JDK).
#
# Cuatro cosas que no son obvias:
#  - Se desempaqueta con `dpkg-deb -x` en vez de instalarlo con apt: el
#    post-install del .deb solo hace integracion de escritorio (iconos, menus,
#    mime types) y falla en un contenedor headless.
#  - Aunque se use en modo batch, al arrancar consulta GTK para averiguar el
#    escalado HiDPI de la pantalla, asi que libgtk-3 tiene que estar igual.
#  - El .deb NO trae idiomas para el reconocimiento de texto: sin ellos Audiveris
#    avisa "No installed OCR languages" y no lee ni la letra, ni el titulo, ni
#    los nombres de las voces. Se bajan los modelos de Tesseract y se apunta
#    TESSDATA_PREFIX. Va el espanol (la imagen vieja toprock/audiveris no lo
#    tenia: leia las letras con los modelos de ingles, aleman y frances, y de
#    ahi la "i" con tilde leida como "l"), mas los idiomas del repertorio coral.
#    Son los modelos "estandar" (motor viejo + LSTM), que sirven para cualquier
#    modo de Tesseract.
#  - El lanzador reserva hasta 8 GB de memoria (-Xmx8G). En el VPS de 3,7 GB eso
#    termina en el kernel matando el proceso a mitad de una partitura larga; con
#    un tope de 2 GB Java se administra adentro de lo que hay.
FROM ubuntu:24.04
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      wget ca-certificates fontconfig libfreetype6 libgtk-3-0t64 \
 && rm -rf /var/lib/apt/lists/*
ARG URL=https://github.com/Audiveris/audiveris/releases/download/5.11.0/Audiveris-5.11.0-ubuntu24.04-x86_64.deb
RUN wget -q -O /tmp/audiveris.deb "${URL}" \
 && dpkg-deb -x /tmp/audiveris.deb / \
 && rm -f /tmp/audiveris.deb \
 && test -x /opt/audiveris/bin/Audiveris \
 && sed -i 's/^java-options=-Xmx8G$/java-options=-Xmx2g/' /opt/audiveris/lib/app/Audiveris.cfg \
 && grep -q '^java-options=-Xmx2g$' /opt/audiveris/lib/app/Audiveris.cfg
ARG TESSDATA=https://github.com/tesseract-ocr/tessdata/raw/4.1.0
RUN mkdir -p /opt/tessdata \
 && for l in eng spa ita lat por fra deu; do \
      wget -q -O /opt/tessdata/$l.traineddata "${TESSDATA}/$l.traineddata" || exit 1; \
    done \
 && ls -la /opt/tessdata
ENV TESSDATA_PREFIX=/opt/tessdata
ENTRYPOINT ["/opt/audiveris/bin/Audiveris"]
