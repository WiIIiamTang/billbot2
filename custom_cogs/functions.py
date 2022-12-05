import booru
import requests
import asyncpraw
import os
from dotenv import load_dotenv

load_dotenv()


async def get_waifu():
    r = requests.get("https://api.waifu.im/search/")
    return r.json()["images"][0]["url"]


async def get_gelbooru(gel, query):
    res = await gel.search(
        query=f"{query}_(genshin_impact) -rating:explicit -rating:questionable",
        limit=1,
        random=True,
        gacha=True,
    )
    data = booru.resolve(res)
    return data


async def get_answer_from_reddit(question):
    reddit = asyncpraw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT"),
        client_secret=os.getenv("REDDIT_SECRET"),
        user_agent="Search answer script",
    )
    subreddit = await reddit.subreddit("all")
    result = "I don't know"

    async for submission in subreddit.search(f'title:"{question}"', sort="top"):
        comments = await submission.comments()
        await comments.replace_more(limit=0)
        for top_level_comment in comments:
            if top_level_comment.stickied:
                continue
            else:
                result = top_level_comment.body.strip()
                break
        break

    if result != "I don't know":
        return result

    async for submission in subreddit.search(f"{question}", sort="top"):
        comments = await submission.comments()
        await comments.replace_more(limit=0)
        for top_level_comment in comments:
            if top_level_comment.stickied:
                continue
            else:
                result = top_level_comment.body.strip()
                break
        break

    return result
