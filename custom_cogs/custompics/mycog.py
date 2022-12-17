from redbot.core import commands
from discord.ext import tasks
from io import BytesIO
import sys
import json
import os

from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

print(os.getcwd())
print(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from functions import (  # noqa: E402
    get_gelbooru,
    get_waifu,
    get_wolfram_simple,
    get_openai_img,
)  # noqa: E402
import booru  # noqa: E402
import discord  # noqa: E402


class CustomPics(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.gel = booru.Gelbooru()
        self.listening_to = []
        self.chatbot = None
        self.min_chat_waittime = 10
        self.conv_length = 0
        self.timeout = 2
        self.allowed_users = []
        self.delete_message_from_these_users = []
        self.messages_to_delete = []
        self.response_times = []
        self.min_delete_time = 15
        self.hchannel = None
        self.owner = None
        self.main_server = None
        if os.getenv("OWNER_ID", None) is not None:
            self.allowed_users.append(os.getenv("OWNER_ID", None))

        self.stats = {
            "tracking_since": datetime.now().strftime("%m/%d/%Y"),
            "waifu": {"count_by_channel": {"_TOTAL": 0}, "count_by_users": {}},
            "genshin": {"count_by_channel": {"_TOTAL": 0}, "count_by_users": {}},
            "openai": {"count_by_channel": {"_TOTAL": 0}, "count_by_users": {}},
            "wolfram": {"count_by_channel": {"_TOTAL": 0}, "count_by_users": {}},
            "messages": {"count_by_channel": {"_TOTAL": 0}, "count_by_users": {}},
        }

        self.delete_messages_task.start()

    def cog_unload(self):
        self.delete_messages_task.cancel()

    def increment_count(self, category, channel, author):
        stats_count = self.stats[category]["count_by_channel"]
        stats_user = self.stats[category]["count_by_users"]

        stats_count["_TOTAL"] += 1
        stats_count[channel.name] = stats_count.get(channel.name, 0) + 1
        stats_user[author.name] = stats_user.get(author.name, 0) + 1

    @commands.Cog.listener("on_message")
    async def track_message_stat(self, message):
        if message.author.bot or message.content.startswith("."):
            return

        if self.main_server is None:
            self.main_server = await self.bot.fetch_guild(os.getenv("SERVER_ID", None))

        # if message.guild.id != self.main_server.id:
        #     return

        self.increment_count("messages", message.channel, message.author)

    @commands.command()
    async def stats(self, ctx):
        await ctx.send("```\n{}\n```".format(json.dumps(self.stats, indent=4)))

    @commands.command()
    async def wolfram(self, ctx, *args):
        if len(args) == 0:
            await ctx.send("Please provide a query.")
            return

        r = get_wolfram_simple(" ".join(args))
        await ctx.send(file=discord.File(BytesIO(r.content), "wolfram.png"))
        self.increment_count("wolfram", ctx.channel, ctx.author)

    @commands.command()
    async def waifu(self, ctx: commands.Context):
        img = await get_waifu()
        await ctx.send(img)
        self.increment_count("waifu", ctx.channel, ctx.author)

    @commands.command()
    async def genshin(self, ctx: commands.Context, *, query: str):
        try:
            data = await get_gelbooru(self.gel, query)
            embed = discord.Embed(
                title=f"Search: {query}",
                color=0x00FF00,
            )
            embed.set_image(url=data["file_url"])
            embed.add_field(name="Created at", value=data["created_at"], inline=True)
            embed.add_field(name="Rating", value=data["rating"], inline=True)
            embed.set_footer(text=f"Tags: {' '.join(data['tags'].split(' ')[:10])} ...")

            await ctx.send(embed=embed)
            self.increment_count("genshin", ctx.channel, ctx.author)
        except ValueError as e:
            await ctx.send(f"Error: `{e}`")

    @commands.command()
    async def openai(self, ctx, *args):
        if len(args) == 0:
            await ctx.send("Please provide a query.")
            return

        r, data = get_openai_img(" ".join(args))

        if not r:
            if data["status"] == "flagged":
                await ctx.send(
                    "Hi {}, your query was flagged for violating the OpenAI ToS and content policy.\n\
My account will get banned if you keep on doing this.\n\
These are the categories your query was flagged for: {}".format(
                        ctx.author.mention, ", ".join(data["categories"])
                    )
                )
            elif data["status"] == "openai_error":
                await ctx.send(
                    "Hi {}, that didn't work.\n\
A lot of the times this is because your query broke OpenAI ToS and/or content policy.\n\
The server responded with an error: `{}`".format(
                        ctx.author.mention, ": ".join(data["error"])
                    )
                )
            return
        await ctx.send(data["img_url"])
        self.increment_count("openai", ctx.channel, ctx.author)

    @commands.command(
        help="Delete your messages after a certain amount of SECONDS, minimum 15. May be delayed by up to 15 seconds."
    )
    async def auto_delete(self, ctx, *, wait_time: int):
        try:
            wait_time = int(wait_time)
        except ValueError:
            await ctx.send("Please provide a valid integer.")
            return

        if wait_time < self.min_delete_time:
            await ctx.send(f"Please provide an integer above {self.min_delete_time}.")
            return

        existing_user_info = [
            x for x in self.delete_message_from_these_users if x["id"] == ctx.author.id
        ]
        if len(existing_user_info) > 0:
            existing_user_info[0]["time"] = wait_time
        else:
            self.delete_message_from_these_users.append(
                {"id": ctx.author.id, "time": wait_time}
            )

        await ctx.send(
            "Added/Updated. Your messages will auto-delete after {} seconds.\n\
Deletion may be delayed by up to 15 seconds. Your messages are *not* saved past deletion.\n\
Run `.auto_delete_remove` to stop auto deleting.".format(
                wait_time
            )
        )

    @commands.command()
    async def auto_delete_remove(self, ctx):
        self.delete_message_from_these_users = [
            x for x in self.delete_message_from_these_users if x["id"] != ctx.author.id
        ]
        await ctx.send("Removed")

    @commands.Cog.listener("on_message")
    async def auto_delete_bot(self, message):
        if message.author.bot:
            return

        ids_to_check = [x["id"] for x in self.delete_message_from_these_users]
        if message.author.id not in ids_to_check:
            return

        self.messages_to_delete.append({"message": message, "time": datetime.now()})

    @tasks.loop(seconds=15)
    async def delete_messages_task(self):
        tmp = self.messages_to_delete.copy()
        for x in tmp:
            try:
                author = x["message"].author
                message_time = x["time"]
                wait_time = [
                    x
                    for x in self.delete_message_from_these_users
                    if x["id"] == author.id
                ][0]["time"]

                if (datetime.now() - message_time).total_seconds() >= wait_time:
                    await x["message"].delete()
                    self.messages_to_delete.remove(x)
            except IndexError:
                pass
