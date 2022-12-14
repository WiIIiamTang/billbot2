from redbot.core import commands
from discord.ext import tasks
from io import BytesIO
import sys
import os

# import asyncio
# from revChatGPT.revChatGPT import AsyncChatbot as Chatbot
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
    #    get_chatgpt,
)  # noqa: E402
import booru  # noqa: E402
import discord  # noqa: E402


class CustomPics(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.gel = booru.Gelbooru()
        self.listening_to = []
        self.chat_token = os.getenv("SESSION_TOKEN", None)
        self.cf_clearance = os.getenv("CF_CLEARANCE", None)
        self.user_agent = os.getenv("USER_AGENT", None)
        self.chatbot = None
        self.min_chat_waittime = 10
        self.conv_length = 0
        self.allowed_users = []
        self.delete_message_from_these_users = []
        self.messages_to_delete = []
        self.min_delete_time = 15
        if os.getenv("OWNER_ID", None) is not None:
            self.allowed_users.append(os.getenv("OWNER_ID", None))

        self.delete_messages_task.start()

        # if not self._start_chatbot():
        #     raise RuntimeError(
        #         "Chatbot failed to start. At cog: CustomPics. Double check session token."
        #     )

    def cog_unload(self):
        self.delete_messages_task.cancel()

    # def _start_chatbot(self, token=None, cf_clearance=None, user_agent=None):
    #     if self.chat_token is None and token is None:
    #         return False

    #     config = {
    #         "session_token": self.chat_token if token is None else token,
    #         "cf_clearance": self.cf_clearance if cf_clearance is None else cf_clearance,
    #         "user_agent": self.user_agent if user_agent is None else user_agent,
    #     }
    #     self.chatbot = Chatbot(config=config, conversation_id=None)
    #     return True

    # @commands.command()
    # async def restart_chatbot(self, ctx):
    #     oid = os.getenv("OWNER_ID", None)
    #     if (oid is None) or (str(ctx.author.id) != str(oid)):
    #         await ctx.send("Unable to restart chatbot.")
    #         return

    #     load_dotenv()
    #     self.chat_token = os.getenv("SESSION_TOKEN", None)
    #     if not self._start_chatbot():
    #         raise RuntimeError("Chatbot failed to start. At cog: CustomPics.")
    #     else:
    #         await ctx.send("Chatbot restarted.")

    @commands.command()
    async def wolfram(self, ctx, *args):
        if len(args) == 0:
            await ctx.send("Please provide a query.")
            return

        r = get_wolfram_simple(" ".join(args))
        await ctx.send(file=discord.File(BytesIO(r.content), "wolfram.png"))

    @commands.command()
    async def waifu(self, ctx: commands.Context):
        img = await get_waifu()
        await ctx.send(img)

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
            author = x["message"].author
            message_time = x["time"]
            wait_time = [
                x for x in self.delete_message_from_these_users if x["id"] == author.id
            ][0]["time"]

            if (datetime.now() - message_time).total_seconds() >= wait_time:
                await x["message"].delete()
                self.messages_to_delete.remove(x)

    @commands.command(help="You can't use this anymore")
    async def startchat(self, ctx):
        await ctx.send(
            "{}, you can't use this command anymore!\n\
Cloudflare was recently added to the chatGPT site, which prevents a lot of botting.\n\
You should wait for an official API to be released, sorry".format(  # noqa: E501
                ctx.author.mention
            )
        )
        return
        # Add the author to the listening_to list
        self.listening_to.append(
            {"user": ctx.author, "time": datetime.now(), "first": True}
        )

        # await ctx.send(
        #     "Ok, {}! I'll listen to your messages. Type `.stopchat` to stop. You'll be timed out after 5 minutes".format(
        #         ctx.author.mention
        #     )
        # )

    # @commands.command()
    # async def add_allowed_user(self, ctx, id: str):
    #     oid = os.getenv("OWNER_ID", None)
    #     if (oid is None) or (str(ctx.author.id) != str(oid)):
    #         return

    #     if id not in self.allowed_users:
    #         self.allowed_users.append(str(id))
    #         await ctx.send("Added {} to allowed users.".format(id))
    #     else:
    #         await ctx.send("{} is already an allowed user.".format(id))

    # @commands.command()
    # async def stopchat(self, ctx):
    #     # Remove the author from the listening_to list
    #     original_length = len(self.listening_to)
    #     self.listening_to = [i for i in self.listening_to if i["user"] != ctx.author]

    #     if len(self.listening_to) == original_length:
    #         await ctx.send(
    #             "I'm not listening to you already, {}.".format(ctx.author.mention)
    #         )
    #         return
    #     else:
    #         await ctx.send(
    #             "Ok, {}! I'll stop listening to your messages.".format(
    #                 ctx.author.mention
    #             )
    #         )

    #     self.chatbot.reset_chat()
    #     self.conv_length = 0


#     @commands.command()
#     async def chat_auth_session(self, ctx):
#         oid = os.getenv("OWNER_ID", None)
#         if (
#             (oid is None)
#             or (str(ctx.author.id) != str(oid))
#             or (str(ctx.author.id) not in self.allowed_users)
#         ):
#             await ctx.send("Unable to authenticate chatbot.")
#             return

#         await ctx.channel.send("Ok, I'll send you a DM.")

#         message = await ctx.author.send(
#             "Send me your session auth token, cloudflare clearance and user agent.\n\
# It must be a .txt file. The session auth token must be first, then the cloudflare clearance token, then user agent.\n\
# By making these changes, you are modifying the entire bot instance and can cause it to break.\n\
# Enter `cancel` to cancel."
#         )

#         def check(m):
#             return m.author == ctx.author and m.channel == message.channel

#         reply = await self.bot.wait_for("message", check=check, timeout=60)

#         # Cancel if the reply says cancel
#         if reply.content.lower() == "cancel":
#             await ctx.author.send("Cancelled.")
#             return

#         # self.chat_token = reply.content
#         # await reply.attachments[0].save("/app/key.txt")
#         fp = BytesIO()
#         await reply.attachments[0].save(fp)
#         await asyncio.sleep(1)
#         response = fp.getvalue().decode("utf-8")
#         lines = response.split("\n")
#         self.chat_token = lines[0].strip()
#         self.cf_clearance = lines[1].strip()
#         self.user_agent = lines[2].strip()
#         await ctx.author.send(
#             f"{self.chat_token[:100]}...\n{self.cf_clearance}\n{self.user_agent}"
#         )
#         # with open("/app/key.txt", "r") as f:
#         #     self.chat_token = f.read()

#         # await ctx.author.send(self.chat_token)
#         await ctx.author.send(
#             "Ok, I'll use those settings from now on. Trying to start the bot..."
#         )
#         if self._start_chatbot(self.chat_token, self.cf_clearance, self.user_agent):
#             await ctx.author.send("Success!")
#         else:
#             await ctx.author.send("Failed to start the bot. Get help!")

#     @commands.Cog.listener("on_message")
#     async def chatgpt(self, message):
#         query = message.content.strip()
#         if not query or query.startswith("."):
#             return

#         user_keys = [i["user"] for i in self.listening_to]

#         if message.author in user_keys:
#             current_time = datetime.now()
#             user = None
#             for i in self.listening_to:
#                 if i["user"] == message.author:
#                     user = i
#                     break

#             if user is None:
#                 await message.channel.send("Something went wrong.")
#                 return

#             # Do not respond if it's been greater than 5 minutes since the last message
#             if (current_time - user["time"]).total_seconds() > 300:
#                 self.listening_to = [
#                     i for i in self.listening_to if i["user"] != message.author
#                 ]
#                 self.chatbot.reset_chat()
#                 self.conv_length = 0
#                 return
#             # Do not respond if it's been less than min_chat_waittime seconds since the last message
#             elif (
#                 current_time - user["time"]
#             ).total_seconds() < self.min_chat_waittime and not user["first"]:
#                 await message.channel.send(
#                     "Hey {}, my single brain cell is being overworked.\n\
# For now, I'm only responding to one message every {}secs because it gets too exhausting.\n\
# If you want to end the chat session, type `.stopchat`.".format(
#                         message.author.mention, self.min_chat_waittime
#                     )
#                 )
#                 return
#             else:
#                 user["time"] = current_time

#             if not query:
#                 await message.channel.send("Please provide a query.")
#                 return

#             try:
#                 response = await get_chatgpt(query, self.chatbot, test=False)
#                 user["first"] = False
#                 response_length = len(response)

#                 if response_length <= 1990:
#                     await message.channel.send(response)
#                     self.conv_length += 1
#                 else:
#                     while response_length > 0:
#                         await message.channel.send(response[:1990])
#                         self.conv_length += 1
#                         response = response[1990:]
#                         response_length -= 1990
#             except Exception as e:
#                 await message.channel.send("Something went wrong: {}".format(e))
#                 await message.channel.send(
#                     "One problem is that conversation has a max length. \
# Try .stopchat then .startchat to reset the conversation."
#                 )
#                 if self.conv_length < 5:
#                     # Get the bot owner Member
#                     owner = await self.bot.fetch_user(os.getenv("OWNER_ID", None))
#                     await message.channel.send(
#                         "Hey {}, the conversation length is < 5 so it doesn't seem to be the issue. \n\
# Can you reset my session token?".format(
#                             owner
#                         )
#                     )
