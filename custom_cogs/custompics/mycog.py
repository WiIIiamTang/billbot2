from redbot.core import commands
from discord.ext import tasks
from io import BytesIO
import sys
import json
import os
import pymongo

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
        self.tracking_users_in_channel = []
        self.tracking_statuses = []
        self.tracking_activities = []
        self.min_delete_time = 15
        self.hchannel = None
        self.owner = None
        self.main_server = None
        self.mongo_client = pymongo.MongoClient(os.getenv("MONGO_DB_URI", None))
        if os.getenv("OWNER_ID", None) is not None:
            self.allowed_users.append(os.getenv("OWNER_ID", None))

        self.stats = {
            "tracking_since": datetime.now().strftime("%m/%d/%Y"),
            "waifu": {"count_by_channel": {"_TOTAL": 0}, "count_by_users": {}},
            "genshin": {"count_by_channel": {"_TOTAL": 0}, "count_by_users": {}},
            "openai": {"count_by_channel": {"_TOTAL": 0}, "count_by_users": {}},
            "wolfram": {"count_by_channel": {"_TOTAL": 0}, "count_by_users": {}},
            "messages": {"count_by_channel": {"_TOTAL": 0}, "count_by_users": {}},
            "voice": {"count_by_channel": {"_TOTAL": 0}, "count_by_users": {}},
            "audio": {"count_by_channel": {"_TOTAL": 0}, "count_by_users": {}},
            "status": {"count_by_channel": {"_TOTAL": -1}, "count_by_users": {}},
            "activity": {"count_by_channel": {"_TOTAL": -1}, "count_by_users": {}},
        }

        self.sync_stats_from_db()

        self.delete_messages_task.start()
        self.sync_stats_task.start()

    def cog_unload(self):
        self.delete_messages_task.cancel()
        self.sync_stats_task.cancel()

    def sync_stats_from_db(self):
        db = self.mongo_client["billbot"]
        stats_collection = db["stats"]
        new_stats = {}
        date = stats_collection.find_one({"category": "tracking_time"})
        new_stats["tracking_since"] = date["tracking_since"]

        # Get the stats from the database
        for k, v in self.stats.items():
            old = stats_collection.find_one({"category": k})

            if old is None:
                continue

            new_stats[k] = {}
            new_stats[k]["count_by_channel"] = old["count_by_channel"]
            new_stats[k]["count_by_users"] = old["count_by_users"]

        self.stats = new_stats

    async def increment_count(
        self, category, channel, author, guild, increment_value=1
    ):
        if self.main_server is None:
            self.main_server = await self.bot.fetch_guild(os.getenv("SERVER_ID", None))

        if guild.id != self.main_server.id:
            return

        stats_count = self.stats[category]["count_by_channel"]
        stats_user = self.stats[category]["count_by_users"]

        stats_count["_TOTAL"] += increment_value
        stats_count[channel.name] = stats_count.get(channel.name, 0) + increment_value
        stats_user[author.name] = stats_user.get(author.name, 0) + increment_value

    @commands.Cog.listener("on_message")
    async def track_message_stat(self, message):
        if message.author.bot or message.content.startswith("."):
            return

        await self.increment_count(
            "messages", message.channel, message.author, message.guild
        )

    @commands.command()
    async def get_current_activities(self, ctx):
        await ctx.send("{} | {}".format(ctx.author.activities, ctx.author.activity))

    @commands.command()
    async def force_db_sync(self, ctx):
        owner = await self.bot.fetch_user(os.getenv("OWNER_ID", None))
        if owner is None or ctx.author.id != owner.id:
            return

        await self.sync_stats_task()
        await ctx.send("Done")

    @commands.Cog.listener("on_voice_state_update")
    async def track_voice_stat(self, member, before, after):
        # Start tracking time if a user joins a voice channel
        if before.channel is None and after.channel is not None:
            self.tracking_users_in_channel.append(
                {"user": member, "join_time": datetime.now()}
            )
        # Else, stop tracking time if a user leaves a voice channel
        elif before.channel is not None and after.channel is None:
            user = [x for x in self.tracking_users_in_channel if x["user"] == member][0]
            self.tracking_users_in_channel = [
                x for x in self.tracking_users_in_channel if x["user"] != member
            ]
            # Add the time passed to the stats in minutes
            time_passed = datetime.now() - user["join_time"]
            await self.increment_count(
                "voice",
                before.channel,
                member,
                member.guild,
                round(time_passed.total_seconds() / 60, 2),
            )

    @commands.Cog.listener("on_member_update")
    async def track_status_stat(self, before, after):
        ###################################################################
        # Activity updates
        ###################################################################
        # TODO: When discord.py updates to v2, move this to on_presence_update
        if before.activities != after.activities:
            user_info = [x for x in self.tracking_activities if x["user"] == after]
            if not user_info:
                if after.activity is not None:
                    user_info = {
                        "user": after,
                        "activity": after.activity,
                        "time": datetime.now(),
                    }
                    self.tracking_activities.append(user_info)
            else:
                user_info = user_info[0]
                # Add the time passed to the stats in minutes
                time_passed = datetime.now() - user_info["time"]
                minutes = round(time_passed.total_seconds() / 60, 2)

                stats = self.stats["activity"]["count_by_users"]
                stats[user_info["activity"].name] = stats.get(
                    user_info["activity"].name, {}
                )
                stats[user_info["activity"].name][user_info["user"].name] = (
                    stats[user_info["activity"].name].get(user_info["user"].name, 0)
                    + minutes
                )
                stats[user_info["activity"].name]["_TOTAL"] = (
                    stats[user_info["activity"].name].get("_TOTAL", 0) + minutes
                )

                if after.activity is None:
                    self.tracking_activities = [
                        x for x in self.tracking_activities if x["user"] != after
                    ]
                else:
                    user_info["activity"] = after.activity
                    user_info["time"] = datetime.now()

        ###################################################################
        # Status updates
        ###################################################################
        if before.status == after.status:
            return

        user_info = [x for x in self.tracking_statuses if x["user"] == after]
        if not user_info:
            user_info = {"user": after, "status": after.status, "time": datetime.now()}
            self.tracking_statuses.append(user_info)
        else:
            user_info = user_info[0]
            # Add the time passed to the stats in minutes
            time_passed = datetime.now() - user_info["time"]
            minutes = round(time_passed.total_seconds() / 60, 2)

            stats = self.stats["status"]["count_by_users"]
            stats[user_info["user"].name] = stats.get(user_info["user"].name, {})

            user_stats_status = stats[user_info["user"].name]
            user_stats_status[str(user_info["status"])] = (
                user_stats_status.get(str(user_info["status"]), 0) + minutes
            )

            user_info["status"] = after.status
            user_info["time"] = datetime.now()

    @commands.Cog.listener("on_message")
    async def track_audio_stat(self, message):
        content = message.content.lower()
        if content.startswith(".p") or content.startswith(".play"):
            await self.increment_count(
                "audio", message.channel, message.author, message.guild
            )

    @commands.command()
    async def stats(self, ctx):
        formatted = json.dumps(self.stats, indent=2)
        if len(formatted) > 1900:
            while len(formatted) > 0:
                await ctx.send("```\n{}\n```".format(formatted[:1900]))
                formatted = formatted[1900:]
        else:
            await ctx.send("```\n{}\n```".format(formatted))

    @commands.command()
    async def wolfram(self, ctx, *args):
        if len(args) == 0:
            await ctx.send("Please provide a query.")
            return

        r = get_wolfram_simple(" ".join(args))
        await ctx.send(file=discord.File(BytesIO(r.content), "wolfram.png"))
        await self.increment_count("wolfram", ctx.channel, ctx.author, ctx.guild)

    @commands.command()
    async def waifu(self, ctx: commands.Context):
        img = await get_waifu()
        await ctx.send(img)
        await self.increment_count("waifu", ctx.channel, ctx.author, ctx.guild)

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
            await self.increment_count("genshin", ctx.channel, ctx.author, ctx.guild)
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
        await self.increment_count("openai", ctx.channel, ctx.author, ctx.guild)

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
            except discord.errors.HTTPException:
                pass

    @tasks.loop(hours=12)
    async def sync_stats_task(self):
        db = self.mongo_client["billbot"]
        stats_collection = db["stats"]

        # Update the date in case it changed
        stats_collection.update_one(
            {"category": "tracking_time"},
            {
                "$set": {
                    "category": "tracking_time",
                    "tracking_since": self.stats["tracking_since"],
                }
            },
        )

        # Update each of the categories in stats:
        for k, v in self.stats.items():
            old = stats_collection.find_one({"category": k})
            if old is None:
                continue

            for k2, v2 in v.items():
                for k3, v3 in v2.items():
                    old[k2][k3] = v3

            stats_collection.update_one({"category": k}, {"$set": old}, upsert=False)
