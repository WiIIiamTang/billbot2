from redbot.core import commands
import requests


class CustomPics(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # self.bot.loop.create_task(self.notify_debug())

    @commands.command()
    async def waifu(self, ctx):
        # embed = discord.Embed(title="Waifu", description="", color=0x00FF00)
        # r = requests.get("https://api.waifu.im/search/")
        # embed.set_image(url=r.json()["images"][0]["url"])
        # embed.set_title(r.json()["images"][0]["signature"])

        # await ctx.send(embed=embed)

        # No embed version
        r = requests.get("https://api.waifu.im/search/")
        await ctx.send(r.json()["images"][0]["url"])
