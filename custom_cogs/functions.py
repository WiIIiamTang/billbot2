import booru
import requests
import os
import urllib.parse
from dotenv import load_dotenv

load_dotenv()


async def get_waifu():
    r = requests.get("https://api.waifu.im/search/")
    return r.json()["images"][0]["url"]


def get_wolfram_simple(query, test=False):
    if test:
        return requests.get("http://api.wolframalpha.com/v1/simple")
    else:
        app_id = os.getenv("WOLFRAM_APPID")
    query = urllib.parse.quote(query)
    url = f"http://api.wolframalpha.com/v1/simple?appid={app_id}&i={query}"

    return requests.get(url)


async def get_gelbooru(gel, query):
    res = await gel.search(
        query=f"{query}_(genshin_impact) -rating:explicit -rating:questionable",
        limit=1,
        random=True,
        gacha=True,
    )
    data = booru.resolve(res)
    return data
