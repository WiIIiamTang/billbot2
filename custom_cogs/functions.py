import booru
import requests
import os
import random
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


async def get_gelbooru(gel, query, tries=0, limit=100):
    try:
        res = await gel.search(
            query=f"{query}_(genshin_impact) -rating:explicit -rating:questionable",
            limit=limit,
            random=True,
        )
    except ValueError:
        if tries < 3:
            return await get_gelbooru(gel, query, tries + 1, limit - 30)
        else:
            raise ValueError("No results found.")
    data = booru.resolve(res)

    # return a random element because the bot should try to send different images
    return random.choice(data)
