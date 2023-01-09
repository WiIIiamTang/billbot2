# Docker build

[![release image](https://github.com/WiIIiamTang/billbot2/actions/workflows/docker_build.yml/badge.svg)](https://github.com/WiIIiamTang/billbot2/actions/workflows/docker_build.yml)

```
docker build -t imagetag .
```

Or from docker-compose (preferred),

```
docker-compose up --force-recreate --build
```

Environment variables are required:

- `TOKEN`
- `PREFIX`
- `RUNTIME_ENV`
- `WOLFRAM_APPID`
- `OPENAI_API_KEY`
- `OWNER_ID`
- `SERVER_ID`

## Tests

```
docker run -e RUNTIME_ENV='docker' -e OPENAI_API_KEY=${{ secrets.OPENAI_API_KEY }} billbot2 pytest -p no:warnings
```

Or locally,

```
RUNTIME_ENV=dev pytest
```

## Post setup

Custom cogs from `custom_cogs` are copied to the image at build time. These can be loaded after the bot is started:

```
[p]addpath /app/custom-cogs
[p]load cogname
```

# About

A discord bot built on top of redbot, with koi automation for deployment pre/post setup

# Architecture

![arch drawio](https://user-images.githubusercontent.com/48343678/211228032-d5f87b86-5f75-4c28-a1f3-3abd8e46f6d1.png)

Repos in this project:
- billbot2 (here)
- [koi](https://github.com/WiIIiamTang/koi)
- [discordwrapped](https://github.com/WiIIiamTang/discordwrapped)

