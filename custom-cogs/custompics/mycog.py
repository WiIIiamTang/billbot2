from redbot.core import commands
import requests
import booru
import discord


class CustomPics(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.gel = booru.Gelbooru()
        # self.bot.loop.create_task(self.notify_debug())

    @commands.command()
    async def waifu(self, ctx: commands.Context):
        r = requests.get("https://api.waifu.im/search/")
        await ctx.send(r.json()["images"][0]["url"])

    @commands.command()
    async def genshin(self, ctx: commands.Context, *, query: str):
        try:
            res = await self.gel.search(
                query=f"{query}_(genshin_impact) -rating:explicit,questionable",
                limit=1,
                random=True,
                gacha=True,
            )
            data = booru.resolve(res)
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
