FROM phasecorex/red-discordbot:full

COPY custom_cogs /app/custom_cogs/
COPY setup-env.sh /app/functions/
COPY main-loop.sh /app/functions/
COPY notify_starting.py /app/functions/
COPY tests /app/
COPY conftest.py /app/

RUN pip3 install python-dotenv pytest pytest-asyncio booru==1.0.15 requests openai

WORKDIR /app

CMD ["sh", "/app/start-redbot.sh"]