from redbot.core import commands
from io import BytesIO
import sys
import os
from revChatGPT.revChatGPT import Chatbot
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
    get_chatgpt,
)  # noqa: E402
import booru  # noqa: E402
import discord  # noqa: E402


class CustomPics(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.gel = booru.Gelbooru()
        self.listening_to = []
        self.chat_token = os.getenv("SESSION_TOKEN", None)
        self.chatbot = None
        self.min_chat_waittime = 10
        if not self._start_chatbot():
            raise RuntimeError(
                "Chatbot failed to start. At cog: CustomPics. Double check session token."
            )

    def _start_chatbot(self):
        if self.chat_token is None:
            return False

        config = {
            "session_token": self.chat_token,
        }
        self.chatbot = Chatbot(config=config, conversation_id=None)
        return True

    @commands.command()
    async def restart_chatbot(self, ctx):
        oid = os.getenv("OWNER_ID", None)
        if oid is None or ctx.author.id != oid:
            return

        load_dotenv()
        self.chat_token = os.getenv("SESSION_TOKEN", None)
        if not self._start_chatbot():
            raise RuntimeError(
                "Chatbot failed to start. At cog: CustomPics. Double check session token."
            )
        else:
            await ctx.send("Chatbot restarted.")

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
        help="Start a chat with the bot. One person needs to authenticate with `.chat_auth_session` first!"
    )
    async def startchat(self, ctx):
        # Add the author to the listening_to list
        self.listening_to.append(
            {"user": ctx.author, "time": datetime.now(), "first": True}
        )

        await ctx.send(
            "Ok, {}! I'll listen to your messages. Type `.stopchat` to stop. You'll be timed out after 5 minutes".format(
                ctx.author.mention
            )
        )

    @commands.command()
    async def stopchat(self, ctx):
        # Remove the author from the listening_to list
        original_length = len(self.listening_to)
        self.listening_to = [i for i in self.listening_to if i["user"] != ctx.author]

        if len(self.listening_to) == original_length:
            await ctx.send(
                "I'm not listening to you already, {}.".format(ctx.author.mention)
            )
            return
        else:
            await ctx.send(
                "Ok, {}! I'll stop listening to your messages.".format(
                    ctx.author.mention
                )
            )

    # TODO: Can we remove this? It won't work because the message exceeds the free limit of 2000 characters

    # @commands.command()
    # async def chat_auth_session(self, ctx):
    #     await ctx.channel.send("Ok, I'll send you a DM.")

    #     message = await ctx.author.send("Send me your session auth token:")

    #     def check(m):
    #         return m.author == ctx.author and m.channel == message.channel

    #     reply = await self.bot.wait_for("message", check=check, timeout=60)
    #     self.chat_token = reply.content

    #     await ctx.author.send(self.chat_token)
    #     await ctx.author.send(
    #         "Ok, I'll use that token from now on. Trying to start the bot..."
    #     )
    #     if self._start_chatbot():
    #         await ctx.author.send("Success!")
    #     else:
    #         await ctx.author.send("Failed to start the bot. Get help!")

    @commands.Cog.listener("on_message")
    async def chatgpt(self, message):
        query = message.content.strip()
        if not query or query.startswith("."):
            return

        user_keys = [i["user"] for i in self.listening_to]

        if message.author in user_keys:
            current_time = datetime.now()
            user = None
            for i in self.listening_to:
                if i["user"] == message.author:
                    user = i
                    break

            if user is None:
                await message.channel.send("Something went wrong.")
                return

            # Do not respond if it's been greater than 5 minutes since the last message
            if (current_time - user["time"]).total_seconds() > 300:
                self.listening_to.remove(message.author)
                return
            # Do not respond if it's been less than min_chat_waittime seconds since the last message
            elif (
                current_time - user["time"]
            ).total_seconds() < self.min_chat_waittime and not user["first"]:
                await message.channel.send(
                    "Hey {}, my single brain cell is being overworked.\n\
For now, I'm only responding to one message every {}secs because it gets too exhausting.\n\
If you want to end the chat session, type `.stopchat`.".format(
                        message.author.mention, self.min_chat_waittime
                    )
                )
                return
            else:
                user["time"] = current_time

            if not query:
                await message.channel.send("Please provide a query.")
                return

            try:
                response = get_chatgpt(query, self.chatbot, test=False)
                user["first"] = False
                await message.channel.send(response)
            except Exception as e:
                await message.channel.send("Something went wrong: {}".format(e))
