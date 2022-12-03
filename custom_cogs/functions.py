import booru
import requests


async def get_waifu():
    r = requests.get("https://api.waifu.im/search/")
    return r.json()["images"][0]["url"]


async def get_gelbooru(gel, query):
    res = await gel.search(
        query=f"{query}_(genshin_impact) -rating:explicit,questionable",
        limit=1,
        random=True,
        gacha=True,
    )
    data = booru.resolve(res)
    return data
