import discord
from discord.ext import commands

import aiohttp
import aiosqlite
import datetime


class SurrenderNow:
    """Add or remove keywords to annouce from surrender@20 posts"""
    def __init__(self, bot):
        self.bot = bot

    async def start_websocket(self):
        # create a websocket to the api server
        self.session = aiohttp.ClientSession()
        async with self.session.ws_connect("ws://surrendernow.gg:3000/", timeout=40) as ws:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    obj = msg.json()
                    if obj["Type"] == "POST_RELEASED":
                        await self.handler(obj)
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    break
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    break
        print("Websocket connection closed")

    async def handler(self, obj):
        async with aiosqlite.connect("data.db") as db:
            cursor = await db.execute("SELECT * FROM Keywords")
            async for row in cursor:
                # check if keyword appears in post
                if obj["Data"]["cleanContent"].lower().count(row[0]) > 0:
                    extracts = []
                    # find paragraphs with keyword
                    for part in obj["Data"]["cleanContent"].split("\n \n"):
                        if row[0] in part.lower():
                            extracts.append(part.strip())

                    # create message embed and send it to the server
                    content = "\n\n".join(extracts)
                    if len(content) > 2000:
                        content = content[:2000] + "... `" + str(obj['Data']['cleanContent'].lower().count(row[0])) + "` mentions in total"

                    emb = discord.Embed(title=f"**{row[0]}** was mentioned in this post!",
                                        color=discord.Colour.orange(),
                                        description="\n\n".join(extracts),
                                        url=obj["Data"]["url"],
                                        timestamp=datetime.datetime.now())
                    emb.set_image(url=obj["Data"]["image"])
                    emb.set_author(name=obj["Data"]["title"])
                    emb.set_footer(text="Powered by surrendernow.gg")

                    channels = await db.execute("SELECT AnnounceChannelID FROM Guilds WHERE ID=?", (row[1],))
                    channel_id = await channels.fetchone()
                    channel = self.bot.get_channel(channel_id[0])
                    await channel.send(embed=emb)
            await cursor.close()

    # who and where the commands are permitted to use
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    @commands.group(aliases=["sn"])
    async def surrendernow(self, ctx):
        """Add and remove Keywords to search for in Surrender@20 posts.

        Found keywords will be posted with a short extract and a link to the post"""
        if ctx.invoked_subcommand is None:
            await ctx.send("You need to specify an action \n(use 'help surrendernow' for more information)")

    @surrendernow.command(aliases=["add"])
    async def add_keyword(self, ctx, *, keyword=None):
        """Adds a keyword to search for

        Results will be posted in the specified channel"""
        async with aiosqlite.connect("data.db") as db:
            # check if announcement channel is set up
            cursor = await db.execute("SELECT AnnounceChannelID FROM Guilds WHERE ID=?", (ctx.guild.id,))
            row = await cursor.fetchall()
            if len(row) == 0:
                await ctx.send("You need to set up a notifications channel before subscribing to any channels")
                return

        if keyword is None:
            await ctx.send("You need to spefify the keyword you want to add")
            return

        kw = keyword.lower()

        async with aiosqlite.connect("data.db") as db:
            # add keyword for the guild to database if it doesn't already exist
            cursor = await db.execute("SELECT * FROM Keywords WHERE Keyword=? AND Guild=?", (kw, ctx.guild.id))
            results = await cursor.fetchall()
            await cursor.close()

            if len(results) > 0:
                await ctx.send("This keyword already exists!")
                return

            await db.execute("INSERT INTO Keywords (Keyword, Guild) VALUES (?, ?)", (kw, ctx.guild.id))
            await db.commit()

        await ctx.send("Successfully added keyword '" + kw + "'")

    @surrendernow.command(aliases=["remove"])
    async def remove_keyword(self, ctx, *, keyword=None):
        """Removes a keyword

        Results will no longer be posted"""
        if keyword is None:
            await ctx.send("You need to spefify the keyword you want to remove")
            return

        kw = keyword.lower()

        async with aiosqlite.connect("data.db") as db:
            # remove keyword for guild from database
            cursor = await db.execute("SELECT * FROM Keywords WHERE Keyword=? AND Guild=?", (kw, ctx.guild.id))
            results = await cursor.fetchall()
            await cursor.close()

            if len(results) == 0:
                await ctx.send("This keyword does not exist!")
                return

            await db.execute("DELETE FROM Keywords WHERE Keyword=? AND Guild=?", (kw, ctx.guild.id))
            await db.commit()

        await ctx.send("Successfully removed keyword '" + kw + "'")

    @surrendernow.command(name="list")
    async def _list(self, ctx):
        """Displays a list of all Keywords"""
        names = ""
        async with aiosqlite.connect("data.db") as db:
            # get all keywords of the guild
            cursor = await db.execute("SELECT Keyword FROM Keywords WHERE Guild=?", (ctx.guild.id,))

            async for row in cursor:
                names = names + row[0] + "\n"
            await cursor.close()

        # create message embed and send it
        emb = discord.Embed(title="SurrenderNow keywords", color=discord.Colour.orange(), description=names)
        await ctx.send(embed=emb)


def setup(bot):
    bot.add_cog(SurrenderNow(bot))
