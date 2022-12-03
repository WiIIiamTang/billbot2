# Docker build

```
docker build -t imagetag .
```

Or from docker-compose (preferred),

```
docker-compose up
```

Two environment variables are required:

- `TOKEN`: discord bot token
- `PREFIX`: command prefix

The http server is exposed on port 5000 by default inside the container, and is accessed locally through port 8000. `/` returns 403 Forbidden, `/ack/health` returns 200 OK for scheduled checks to ping.

## Post setup

Custom cogs from `custom-cogs` are copied to the image at build time. These can be loaded after the bot is started:

```
[p]addpath /app/custom-cogs
[p]load cogname
```
