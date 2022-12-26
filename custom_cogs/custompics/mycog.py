from redbot.core import commands
from discord.ext import tasks
from io import BytesIO
import sys
import json
import copy
import os
import logging
import pickle
from nltk import word_tokenize, download
from string import punctuation
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
        self.tracking_interactions = []
        self.min_delete_time = 15
        self.hchannel = None
        self.owner = None
        self.main_server = None
        self.logger = logging.getLogger("red.custom_cogs.custompics")
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
            "words": {"count_by_channel": {"_TOTAL": -1}, "count_by_users": {}},
            "status_time_stream": {
                "count_by_channel": {"_TOTAL": -1},
                "count_by_users": {},
            },
            "interaction_voice": {
                "count_by_channel": {"_TOTAL": -1},
                "count_by_users": {"pairs": []},
            },
            "voice_state": {"count_by_channel": {"_TOTAL": -1}, "count_by_users": {}},
        }

        # launch startup tasks, including periodic loop tasks
        self.bot.loop.create_task(self.startup_tasks())

    def cog_unload(self):
        self.delete_messages_task.cancel()
        self.sync_stats_task.cancel()
        self.sync_stats_archive_task.cancel()
        self.sync_cog_cache_task.cancel()

    async def sync_stats_from_db(self):
        self.logger.info("Getting stats from database...")
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

        self.logger.info("Done.")
        self.logger.info("Loading cog cache from database...")
        ###################
        # load the cog cache if it exists
        cog_cache_collection = db["cog_cache"]
        cog_cache = cog_cache_collection.find_one({"cog": "custompics"})
        if cog_cache is not None:
            # unpickle the data
            data = pickle.loads(cog_cache["data"])

            # set the lists to the data
            self.allowed_users = data["allowed_users"]
            self.delete_message_from_these_users = data[
                "delete_message_from_these_users"
            ]

            # we need to load the discord objects in these lists from client cache

            # Exception: the list of messages object will be LOST (this should just be **empty**)
            self.messages_to_delete = data["messages_to_delete"]

            # Rest is getting members - hopefully they're still cached, otherwise its lost
            members = list(self.bot.get_all_members())

            self.tracking_users_in_channel = data["tracking_users_in_channel"]
            for m in self.tracking_users_in_channel:
                m["user"] = discord.utils.get(members, id=m["user"])

            self.tracking_statuses = data["tracking_statuses"]
            for m in self.tracking_statuses:
                m["user"] = discord.utils.get(members, id=m["user"])

            self.tracking_activities = data["tracking_activities"]
            for m in self.tracking_activities:
                m["user"] = discord.utils.get(members, id=m["user"])

            self.tracking_interactions = data["tracking_interactions"]

        self.logger.info("Done.")

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

    async def startup_tasks(self):
        await self.bot.wait_until_ready()
        self.logger.info("Bot should be ready now. Starting up tasks...")

        download("punkt")
        await self.sync_stats_from_db()

        self.logger.info("looping tasks are starting:")
        self.logger.info("Deleting messages task...")
        self.delete_messages_task.start()
        self.logger.info("Done.")
        self.sync_stats_task.start()
        self.sync_stats_archive_task.start()

        # Using an old cache is better than no cache when booting up
        # However, if the restart time is too long, the information CAN become outdated (so you'll get wrong stats)
        self.sync_cog_cache_task.start()

    @commands.Cog.listener("on_message")
    async def track_message_stat(self, message):
        if message.author.bot or message.content.startswith("."):
            return

        await self.increment_count(
            "messages", message.channel, message.author, message.guild
        )

    @commands.command()
    async def review(self, ctx):
        await ctx.send(
            "https://cdn.discordapp.com/attachments/642483639719952384/859958140005908500/ll7f77rl7d871.png"
        )

    @commands.Cog.listener("on_message")
    async def track_words_stat(self, message):
        if message.author.bot or message.content.startswith("."):
            return

        content = message.content.lower()
        punc = list(punctuation)
        tokens = [
            s.strip("".join(punc)) for s in word_tokenize(content) if s not in punc
        ]

        word_stats = self.stats["words"]["count_by_users"]
        word_stats[message.author.name] = word_stats.get(message.author.name, {})

        for token in tokens:
            word_stats[message.author.name][token] = (
                word_stats[message.author.name].get(token, 0) + 1
            )

    @commands.command()
    async def get_cog_cache(self, ctx):
        cache_lists = {
            "allowed_users": self.allowed_users,
            "delete_messages": self.delete_message_from_these_users,
            "messages_to_delete": self.messages_to_delete,
            "tracking_users_in_channel": self.tracking_users_in_channel,
            "tracking_statuses": self.tracking_statuses,
            "tracking_activities": self.tracking_activities,
            "tracking_interactions": self.tracking_interactions,
        }

        # Send the cache_lists str as a file since it will be too long as a normal message
        # BytesIo is used to convert the string to a file
        buffer = BytesIO(str(cache_lists).encode("utf-8"))
        await ctx.send(file=discord.File(fp=buffer, filename="cache_lists.txt"))

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

    @commands.command()
    async def force_db_archive_sync(self, ctx):
        owner = await self.bot.fetch_user(os.getenv("OWNER_ID", None))
        if owner is None or ctx.author.id != owner.id:
            return

        await self.sync_stats_archive_task()
        await ctx.send("Done")

    @commands.command()
    async def force_cog_cache_sync(self, ctx):
        owner = await self.bot.fetch_user(os.getenv("OWNER_ID", None))
        if owner is None or ctx.author.id != owner.id:
            return

        await self.sync_cog_cache_task()
        await ctx.send("Done")

    @commands.command()
    async def flush_cog_cache(self, ctx):
        owner = await self.bot.fetch_user(os.getenv("OWNER_ID", None))
        if owner is None or ctx.author.id != owner.id:
            return

        self.logger.warning(
            "Flushing cog cache - this will cause the bot to lose all tracking data"
        )

        # allowed_users - do nothing
        # delete_message_from_these_users - do nothing

        # messages_to_delete
        while self.messages_to_delete:
            m = self.messages_to_delete.pop()
            try:
                await m["message"].delete()
            except discord.errors.HTTPException:
                pass

        assert not self.messages_to_delete

        # tracking_users_in_channel
        for u in self.tracking_users_in_channel:
            try:
                await self.increment_count(
                    "voice",
                    u["user"].voice.channel,
                    u["user"],
                    u["user"].guild,
                    round((datetime.now() - u["join_time"]).total_seconds() / 60, 2),
                )
            except Exception:
                # If the user is not in a voice channel (might happen depending on delay?), Member.voice.channel will be None
                pass

        self.tracking_users_in_channel = []

        # tracking_statuses
        for s in self.tracking_statuses:
            user_info = s
            # Add the time passed to the stats in minutes
            time_passed = datetime.now() - user_info["time"]
            minutes = round(time_passed.total_seconds() / 60, 2)

            stats = self.stats["status"]["count_by_users"]
            stats[user_info["user"].name] = stats.get(user_info["user"].name, {})

            user_stats_status = stats[user_info["user"].name]
            user_stats_status[str(user_info["status"])] = (
                user_stats_status.get(str(user_info["status"]), 0) + minutes
            )

        self.tracking_statuses = []

        # tracking_activities
        for a in self.tracking_activities:
            user_info = a
            # Add the time passed to the stats in minutes
            time_passed = datetime.now() - user_info["time"]
            minutes = round(time_passed.total_seconds() / 60, 2)

            stats = self.stats["activity"]["count_by_users"]

            if user_info["activity"] is None:
                activity_name = "Unknown"
            else:
                activity_name = user_info["activity"]

            stats[activity_name] = stats.get(activity_name, {})
            stats[activity_name][user_info["user"].name] = (
                stats[activity_name].get(user_info["user"].name, 0) + minutes
            )
            stats[activity_name]["_TOTAL"] = (
                stats[activity_name].get("_TOTAL", 0) + minutes
            )

        self.tracking_activities = []

        # tracking interactions
        stat_interaction = self.stats["interaction_voice"]["count_by_users"]["pairs"]
        for p in self.tracking_interactions:
            # Get the partner
            partner = p["user1"]
            member = p["user2"]

            # Add the time passed to the stats in minutes
            time_passed = datetime.now() - p["first_time_met"]
            minutes = round(time_passed.total_seconds() / 60, 2)

            # Check if the pair already exists in the stats
            pair_in_stats = [
                pp
                for pp in stat_interaction
                if (pp["user1"] == member and pp["user2"] == partner)
                or (pp["user1"] == partner and pp["user2"] == member)
            ]
            if not pair_in_stats:
                stat_interaction.append(
                    {"user1": member, "user2": partner, "time": minutes}
                )
            else:
                existing_pair = pair_in_stats[0]
                existing_pair["time"] += minutes

        self.tracking_interactions = []

        await ctx.send("Stats were written with current cache and reset.")

    @commands.Cog.listener("on_voice_state_update")
    async def track_interaction_stat(self, member, before, after):
        # If a user joins a voice channel, start tracking interactions
        # They should not exist in the cog cache yet, so add them in for each member.
        if before.channel is None and after.channel is not None:
            # for each member in the after channel, add the pair to the tracking_interactions
            for m in after.channel.members:
                if m != member:
                    # Only append if the pair does not exist yet
                    pair = [
                        p
                        for p in self.tracking_interactions
                        if (p["user1"] == member.name and p["user2"] == m.name)
                        or (p["user1"] == m.name and p["user2"] == member.name)
                    ]
                    if not pair:
                        self.tracking_interactions.append(
                            {
                                "user1": member.name,
                                "user2": m.name,
                                "first_time_met": datetime.now(),
                            }
                        )  # This is only added if the pair does not exist yet

        # Else, stop tracking interactions if a user leaves a voice channel,
        # or when they change channels
        elif (before.channel is not None and after.channel is None) or (
            before.channel is not None
            and after.channel is not None
            and before.channel != after.channel
        ):
            # First grab the stat interactions
            stat_interaction = self.stats["interaction_voice"]["count_by_users"][
                "pairs"
            ]

            # Get the pairs that member was involved in
            pairs = [
                p
                for p in self.tracking_interactions
                if p["user1"] == member.name or p["user2"] == member.name
            ]

            # For each pair, add the time passed with their partner to the stats in minutes
            for p in pairs:
                # Get the partner
                partner = p["user1"] if p["user2"] == member.name else p["user2"]

                # Add the time passed to the stats in minutes
                time_passed = datetime.now() - p["first_time_met"]
                minutes = round(time_passed.total_seconds() / 60, 2)

                # Check if the pair already exists in the stats
                pair_in_stats = [
                    pp
                    for pp in stat_interaction
                    if (pp["user1"] == member.name and pp["user2"] == partner)
                    or (pp["user1"] == partner and pp["user2"] == member.name)
                ]
                if not pair_in_stats:
                    stat_interaction.append(
                        {"user1": member.name, "user2": partner, "time": minutes}
                    )
                else:
                    existing_pair = pair_in_stats[0]
                    existing_pair["time"] += minutes

            # Remove the pair from tracking_interactions
            self.tracking_interactions = [
                p for p in self.tracking_interactions if p not in pairs
            ]

    # TODO: this is getting really bad, there is too much code duplication
    @commands.Cog.listener("on_voice_state_update")
    async def track_voice_stat(self, member, before, after):
        # Start tracking time if a user joins a voice channel
        if before.channel is None and after.channel is not None:
            self.tracking_users_in_channel.append(
                {"user": member, "join_time": datetime.now()}
            )
        # Else, stop tracking time if a user leaves a voice channel
        elif before.channel is not None and after.channel is None:
            try:
                user = [
                    x for x in self.tracking_users_in_channel if x["user"] == member
                ][0]
            except IndexError:
                return
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

            # update interaction_voice
            # interaction_voice = self.stats["interaction_voice"]["count_by_users"]
            # interaction_voice[member.name] = interaction_voice.get(member.name, {})
            # interaction_voice[member.name][before.channel.name] = interaction_voice[
            #     member.name
            # ].get(before.channel.name, {})

            # for other_members in before.channel.members:
            #     if other_members == member:
            #         continue

            #     interaction_voice[member.name][before.channel.name][
            #         other_members.name
            #     ] = interaction_voice[member.name][before.channel.name].get(
            #         other_members.name, 0
            #     )
            #     interaction_voice[other_members.name] = interaction_voice.get(
            #         other_members.name, {}
            #     )
            #     interaction_voice[other_members.name][
            #         before.channel.name
            #     ] = interaction_voice[other_members.name].get(before.channel.name, {})
            #     interaction_voice[other_members.name][before.channel.name][
            #         member.name
            #     ] = interaction_voice[other_members.name][before.channel.name].get(
            #         member.name, 0
            #     )

            #     interaction_voice[member.name][before.channel.name][
            #         other_members.name
            #     ] = interaction_voice[member.name][before.channel.name].get(
            #         other_members.name, 0
            #     ) + round(
            #         time_passed.total_seconds() / 60, 2
            #     )
            #     interaction_voice[other_members.name][before.channel.name][
            #         member.name
            #     ] = interaction_voice[member.name][before.channel.name].get(
            #         other_members.name, 0
            #     ) + round(
            #         time_passed.total_seconds() / 60, 2
            #     )

            # update voice_state
            voice_state = self.stats["voice_state"]["count_by_users"]
            voice_state[member.name] = voice_state.get(member.name, {})
            voice_state_channel = self.stats["voice_state"]["count_by_channel"]
            voice_state_channel[before.channel.name] = voice_state_channel.get(
                before.channel.name, {}
            )
            voice_state_channel[before.channel.name][member.name] = voice_state_channel[
                before.channel.name
            ].get(member.name, {})
            voice_state_channel_user = voice_state_channel[before.channel.name][
                member.name
            ]

            if before.self_mute:
                voice_state[member.name]["self_mute"] = voice_state[member.name].get(
                    "self_mute", 0
                ) + round(time_passed.total_seconds() / 60, 2)
                voice_state_channel_user["self_mute"] = voice_state_channel_user.get(
                    "self_mute", 0
                ) + round(time_passed.total_seconds() / 60, 2)
            elif before.self_deaf:
                voice_state[member.name]["self_deaf"] = voice_state[member.name].get(
                    "self_deaf", 0
                ) + round(time_passed.total_seconds() / 60, 2)
                voice_state_channel_user["self_deaf"] = voice_state_channel_user.get(
                    "self_deaf", 0
                ) + round(time_passed.total_seconds() / 60, 2)
            elif before.self_stream:
                voice_state[member.name]["self_stream"] = voice_state[member.name].get(
                    "self_stream", 0
                ) + round(time_passed.total_seconds() / 60, 2)
                voice_state_channel_user["self_stream"] = voice_state_channel_user.get(
                    "self_stream", 0
                ) + round(time_passed.total_seconds() / 60, 2)
            elif before.self_video:
                voice_state[member.name]["self_video"] = voice_state[member.name].get(
                    "self_video", 0
                ) + round(time_passed.total_seconds() / 60, 2)
                voice_state_channel_user["self_video"] = voice_state_channel_user.get(
                    "self_video", 0
                ) + round(time_passed.total_seconds() / 60, 2)

        elif (
            before.channel != after.channel
            and after.channel is not None
            and before.channel is not None
        ):
            try:
                user = [
                    x for x in self.tracking_users_in_channel if x["user"] == member
                ][0]
            except IndexError:
                return
            # Add the time passed to the stats in minutes
            time_passed = datetime.now() - user["join_time"]
            await self.increment_count(
                "voice",
                before.channel,
                member,
                member.guild,
                round(time_passed.total_seconds() / 60, 2),
            )
            user["join_time"] = datetime.now()

            # update interaction_voice
            # interaction_voice = self.stats["interaction_voice"]["count_by_users"]
            # interaction_voice[member.name] = interaction_voice.get(member.name, {})
            # interaction_voice[member.name][before.channel.name] = interaction_voice[
            #     member.name
            # ].get(before.channel.name, {})

            # for other_members in before.channel.members:
            #     if other_members == member:
            #         continue

            #     interaction_voice[member.name][before.channel.name][
            #         other_members.name
            #     ] = interaction_voice[member.name][before.channel.name].get(
            #         other_members.name, 0
            #     )
            #     interaction_voice[other_members.name] = interaction_voice.get(
            #         other_members.name, {}
            #     )
            #     interaction_voice[other_members.name][
            #         before.channel.name
            #     ] = interaction_voice[other_members.name].get(before.channel.name, {})
            #     interaction_voice[other_members.name][before.channel.name][
            #         member.name
            #     ] = interaction_voice[other_members.name][before.channel.name].get(
            #         member.name, 0
            #     )

            #     interaction_voice[member.name][before.channel.name][
            #         other_members.name
            #     ] = interaction_voice[member.name][before.channel.name].get(
            #         other_members.name, 0
            #     ) + round(
            #         time_passed.total_seconds() / 60, 2
            #     )
            #     interaction_voice[other_members.name][before.channel.name][
            #         member.name
            #     ] = interaction_voice[member.name][before.channel.name].get(
            #         other_members.name, 0
            #     ) + round(
            #         time_passed.total_seconds() / 60, 2
            #     )

            # update voice_state
            voice_state = self.stats["voice_state"]["count_by_users"]
            voice_state[member.name] = voice_state.get(member.name, {})
            voice_state_channel = self.stats["voice_state"]["count_by_channel"]
            voice_state_channel[before.channel.name] = voice_state_channel.get(
                before.channel.name, {}
            )
            voice_state_channel[before.channel.name][member.name] = voice_state_channel[
                before.channel.name
            ].get(member.name, {})
            voice_state_channel_user = voice_state_channel[before.channel.name][
                member.name
            ]

            if before.self_mute:
                voice_state[member.name]["self_mute"] = voice_state[member.name].get(
                    "self_mute", 0
                ) + round(time_passed.total_seconds() / 60, 2)
                voice_state_channel_user["self_mute"] = voice_state_channel_user.get(
                    "self_mute", 0
                ) + round(time_passed.total_seconds() / 60, 2)
            elif before.self_deaf:
                voice_state[member.name]["self_deaf"] = voice_state[member.name].get(
                    "self_deaf", 0
                ) + round(time_passed.total_seconds() / 60, 2)
                voice_state_channel_user["self_deaf"] = voice_state_channel_user.get(
                    "self_deaf", 0
                ) + round(time_passed.total_seconds() / 60, 2)
            elif before.self_stream:
                voice_state[member.name]["self_stream"] = voice_state[member.name].get(
                    "self_stream", 0
                ) + round(time_passed.total_seconds() / 60, 2)
                voice_state_channel_user["self_stream"] = voice_state_channel_user.get(
                    "self_stream", 0
                ) + round(time_passed.total_seconds() / 60, 2)
            elif before.self_video:
                voice_state[member.name]["self_video"] = voice_state[member.name].get(
                    "self_video", 0
                ) + round(time_passed.total_seconds() / 60, 2)
                voice_state_channel_user["self_video"] = voice_state_channel_user.get(
                    "self_video", 0
                ) + round(time_passed.total_seconds() / 60, 2)

        elif after.channel == before.channel and after != before:
            try:
                user = [
                    x for x in self.tracking_users_in_channel if x["user"] == member
                ][0]
            except IndexError:
                return
            # Add the time passed to the stats in minutes
            time_passed = datetime.now() - user["join_time"]
            user["join_time"] = datetime.now()

            # update voice_state
            voice_state = self.stats["voice_state"]["count_by_users"]
            voice_state[member.name] = voice_state.get(member.name, {})
            voice_state_channel = self.stats["voice_state"]["count_by_channel"]
            voice_state_channel[before.channel.name] = voice_state_channel.get(
                before.channel.name, {}
            )
            voice_state_channel[before.channel.name][member.name] = voice_state_channel[
                before.channel.name
            ].get(member.name, {})
            voice_state_channel_user = voice_state_channel[before.channel.name][
                member.name
            ]

            if before.self_mute:
                voice_state[member.name]["self_mute"] = voice_state[member.name].get(
                    "self_mute", 0
                ) + round(time_passed.total_seconds() / 60, 2)
                voice_state_channel_user["self_mute"] = voice_state_channel_user.get(
                    "self_mute", 0
                ) + round(time_passed.total_seconds() / 60, 2)
            elif before.self_deaf:
                voice_state[member.name]["self_deaf"] = voice_state[member.name].get(
                    "self_deaf", 0
                ) + round(time_passed.total_seconds() / 60, 2)
                voice_state_channel_user["self_deaf"] = voice_state_channel_user.get(
                    "self_deaf", 0
                ) + round(time_passed.total_seconds() / 60, 2)
            elif before.self_stream:
                voice_state[member.name]["self_stream"] = voice_state[member.name].get(
                    "self_stream", 0
                ) + round(time_passed.total_seconds() / 60, 2)
                voice_state_channel_user["self_stream"] = voice_state_channel_user.get(
                    "self_stream", 0
                ) + round(time_passed.total_seconds() / 60, 2)
            elif before.self_video:
                voice_state[member.name]["self_video"] = voice_state[member.name].get(
                    "self_video", 0
                ) + round(time_passed.total_seconds() / 60, 2)
                voice_state_channel_user["self_video"] = voice_state_channel_user.get(
                    "self_video", 0
                ) + round(time_passed.total_seconds() / 60, 2)

    @commands.Cog.listener("on_member_update")
    async def track_status_stat(self, before, after):
        ###################################################################
        # Activity updates
        ###################################################################
        # TODO: When discord.py updates to v2, move this to on_presence_update

        # ignore if bot
        if before.activities != after.activities and not after.bot:
            user_info = [x for x in self.tracking_activities if x["user"] == after]
            if not user_info:
                if after.activity is not None:
                    user_info = {
                        "user": after,
                        "activity": after.activity.name,
                        "time": datetime.now(),
                    }
                    self.tracking_activities.append(user_info)
            else:
                user_info = user_info[0]
                # Add the time passed to the stats in minutes
                time_passed = datetime.now() - user_info["time"]
                minutes = round(time_passed.total_seconds() / 60, 2)

                stats = self.stats["activity"]["count_by_users"]

                if user_info["activity"] is None:
                    activity_name = "Unknown"
                else:
                    activity_name = user_info["activity"]

                stats[activity_name] = stats.get(activity_name, {})
                stats[activity_name][user_info["user"].name] = (
                    stats[activity_name].get(user_info["user"].name, 0) + minutes
                )
                stats[activity_name]["_TOTAL"] = (
                    stats[activity_name].get("_TOTAL", 0) + minutes
                )

                if after.activity is None:
                    self.tracking_activities = [
                        x for x in self.tracking_activities if x["user"] != after
                    ]
                else:
                    user_info["activity"] = after.activity.name
                    user_info["time"] = datetime.now()

        ###################################################################
        # Status updates
        ###################################################################
        if before.status == after.status:
            return

        user_info = [x for x in self.tracking_statuses if x["user"] == after]
        if not user_info:
            user_info = {
                "user": after,
                "status": str(after.status),
                "time": datetime.now(),
            }
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

            user_info["status"] = str(after.status)
            user_info["time"] = datetime.now()

            # We need to only track the main server
            # Later can expand to track other servers by separating stats db
            if self.main_server is None:
                self.main_server = await self.bot.fetch_guild(
                    os.getenv("SERVER_ID", None)
                )

            if before.guild.id != self.main_server.id:
                return

            time_stream = self.stats["status_time_stream"]["count_by_users"]
            time_stream[user_info["user"].name] = time_stream.get(
                user_info["user"].name, []
            )

            time_stream[user_info["user"].name].append(
                {
                    "status": str(after.status),
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            )

    @commands.Cog.listener("on_message")
    async def track_audio_stat(self, message):
        content = message.content.lower()
        if content.startswith(".p") or content.startswith(".play"):
            await self.increment_count(
                "audio", message.channel, message.author, message.guild
            )

    @commands.command(help="Shows the stats without any pretty printing.")
    async def raw_stats(self, ctx):
        formatted = json.dumps(self.stats)
        buffer = BytesIO(str(formatted).encode("utf-8"))
        await ctx.send(file=discord.File(fp=buffer, filename="stats.txt"))

    @commands.command(
        help="This may not show all stats in the chat, download the file instead."
    )
    async def formatted_stats(self, ctx):
        formatted = json.dumps(self.stats, indent=1)
        buffer = BytesIO(str(formatted).encode("utf-8"))
        await ctx.send(file=discord.File(fp=buffer, filename="stats.txt"))

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
        await self.bot.wait_until_ready()
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
            except discord.errors.Forbidden:
                self.messages_to_delete.remove(x)
            except discord.errors.NotFound:
                self.messages_to_delete.remove(x)
            except discord.errors.HTTPException:
                pass

    @tasks.loop(hours=8)
    async def sync_stats_archive_task(self):
        await self.bot.wait_until_ready()
        self.logger.info("Syncing stats archive...")
        db = self.mongo_client["billbot"]
        stats_archive_collection = db["stats_archive"]

        # Add the current date to the stats object
        stats = copy.deepcopy(self.stats)
        stats["date"] = datetime.now().strftime("%Y-%m-%d")

        # Update the stats document, or create it if it doesn't exist
        stats_archive_collection.update_one(
            {"date": stats["date"]}, {"$set": stats}, upsert=True
        )

        self.logger.info("Done.")

    @tasks.loop(hours=8)
    async def sync_cog_cache_task(self):
        await self.bot.wait_until_ready()
        self.logger.info("Syncing cog cache...")
        db = self.mongo_client["billbot"]
        cog_cache_collection = db["cog_cache"]

        cache_lists = {
            "allowed_users": self.allowed_users,
            "delete_message_from_these_users": self.delete_message_from_these_users,
            "messages_to_delete": self.messages_to_delete,
            "tracking_users_in_channel": self.tracking_users_in_channel,
            "tracking_statuses": self.tracking_statuses,
            "tracking_activities": self.tracking_activities,
            "tracking_interactions": self.tracking_interactions,
        }

        new_cache_lists = {}

        # Convert the Discord objects to serializable items
        # SKIP MESSAGES BECAUSE ITS HARD TO GET BACK
        new_cache_lists["allowed_users"] = copy.deepcopy(cache_lists["allowed_users"])
        new_cache_lists["delete_message_from_these_users"] = copy.deepcopy(
            cache_lists["delete_message_from_these_users"]
        )
        new_cache_lists["messages_to_delete"] = []

        new_cache_lists["tracking_interactions"] = copy.deepcopy(
            cache_lists["tracking_interactions"]
        )

        new_cache_lists["tracking_users_in_channel"] = []
        for m in cache_lists["tracking_users_in_channel"]:
            new_cache_lists["tracking_users_in_channel"].append(
                {"user": m["user"].id, "join_time": m["join_time"]}
            )

        new_cache_lists["tracking_statuses"] = []
        for m in cache_lists["tracking_statuses"]:
            new_cache_lists["tracking_statuses"].append(
                {"user": m["user"].id, "status": m["status"], "time": m["time"]}
            )

        new_cache_lists["tracking_activities"] = []
        for m in cache_lists["tracking_activities"]:
            new_cache_lists["tracking_activities"].append(
                {"user": m["user"].id, "activity": m["activity"], "time": m["time"]}
            )

        # pickle the cache_lists
        data = pickle.dumps(new_cache_lists)

        # Update the cog_cache document, or create it if it doesn't exist
        cog_cache_collection.update_one(
            {"cog": "custompics"},
            {"$set": {"cog": "custompics", "data": data}},
            upsert=True,
        )

        self.logger.info("Done.")

    @tasks.loop(hours=12)
    async def sync_stats_task(self):
        await self.bot.wait_until_ready()
        self.logger.info("Syncing stats...")
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

        self.logger.info("Done.")
