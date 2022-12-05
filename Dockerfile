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
COPY custom_cogs /app/custom_cogs/
COPY setup-env.sh /app/functions/
COPY tests /app/
COPY conftest.py /app/

RUN pip3 install waitress Flask python-dotenv pytest pytest-asyncio booru requests praw asyncpraw

WORKDIR /app

CMD ["sh", "/app/run.sh"]