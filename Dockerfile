FROM phasecorex/red-discordbot:full

RUN apt-get update; \
    apt-get install -y --no-install-recommends \
    other \
    packages \
    ; \
    rm -rf /var/lib/apt/lists/*;

COPY run.sh /app/
COPY server/flaskapp.py /app/
COPY run.py /app/
COPY custom-cogs /app/custom-cogs/
COPY setup-env.sh /app/functions/

RUN pip3 install waitress Flask python-dotenv

CMD ["sh", "/app/run.sh"]