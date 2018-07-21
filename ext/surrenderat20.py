import discord
from discord.ext import commands

import aiosqlite
import auth_token
import datetime
import re


class SurrenderAt20:
    """Add or remove keywords to annouce from surrender@20 posts"""
    def __init__(self, bot):
        self.bot = bot
        self.cleanr = re.compile('<.*?>')

    # who and where the commands are permitted to use
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    @commands.group(aliases=["ff20"])
    async def surrenderat20(self, ctx):
        """Subscribe to Surrender@20 posts and search for keywords in posts."""
        if ctx.invoked_subcommand is None:
            await ctx.send("You need to specify an action \n(use 'help surrenderat20' for more information)")

    @surrenderat20.command()
    async def setchannel(self, ctx, channel=None):
        """Sets the channel to announce Surrender@20 posts in"""
        # get channel obj, depending on if it was mentioned or just the name was specified
        if len(ctx.message.channel_mentions) > 0:
            channel_obj = ctx.message.channel_mentions[0]
        elif channel is not None:
            channel_obj = discord.utils.get(ctx.guild.channels, name=channel.replace("#", ""))
            if channel_obj is None:
                await ctx.send(f"No channel named {channel}")
                return
        else:
            await ctx.send("Missing channel parameter")
            return

        bot_id = ctx.guild.get_member(self.bot.user.id)
        permissions = channel_obj.permissions_for(bot_id)
        if not permissions.send_messages or not permissions.embed_links:
            await ctx.send("Command failed, please make sure that the bot has both permissions for sending messages and using embeds in the specified channel!")
            return

        async with aiosqlite.connect("data.db") as db:
            # add channel id for the guild to the database
            await db.execute("UPDATE Guilds SET SurrenderAt20NotifChannel=? WHERE ID=?",
                             (channel_obj.id, ctx.guild.id))
            await db.commit()

        await ctx.send("Successfully set Surrender@20 notifications to " + channel_obj.mention)

    @surrenderat20.command(aliases=["sub"])
    async def subscribe(self, ctx, *, categories=None):
        """Subscribes to Surrender@20

        You can specify the categories you want to subscribe to or name none and subscribe to all.

        The possible categories are:
        - Red Posts
        - PBE
        - Rotations
        - Esports
        - Releases"""
        async with aiosqlite.connect("data.db") as db:
            # check if announcement channel is set up
            cursor = await db.execute("SELECT SurrenderAt20NotifChannel FROM Guilds WHERE ID=?", (ctx.guild.id,))
            row = await cursor.fetchall()
            await cursor.close()
            if len(row) == 0 or row[0][0] is None:
                await ctx.send("You need to set up a notifications channel before subscribing! \nUse either ;setchannel or ;surrenderat20 setchannel")
                return

            n = await db.execute("SELECT * FROM SurrenderAt20Subscriptions WHERE Guild=?", (ctx.guild.id,))
            results = await n.fetchall()
            await n.close()

            if len(results) == 1:
                if categories is None:
                    categories = "all categories"
                    redposts = True
                    pbe = True
                    rotations = True
                    esports = True
                    releases = True
                else:
                    categories = categories.lower()
                    # return error if no categories are no found but they are also not None
                    if "red posts" not in categories and "pbe" not in categories and "rotations" not in categories and "esports" not in categories and "releases" not in categories:
                        await ctx.send("No categories found, potentially check for typos")
                        return

                    result = results[0]
                    redposts, pbe, rotations, esports, releases = result[1:]
                    # looks for each category and update boolean variable for it
                    if "red posts" in categories:
                        redposts = 1
                    if "pbe" in categories:
                        pbe = 1
                    if "rotations" in categories:
                        rotations = 1
                    if "esports" in categories:
                        esports = 1
                    if "releases" in categories:
                        releases = 1

                # enter information into database
                await db.execute("UPDATE SurrenderAt20Subscriptions \
                                  SET RedPosts=?, PBE=?, Rotations=?, Esports=?, Releases=? \
                                  WHERE Guild=?",
                                 (redposts, pbe, rotations, esports, releases, ctx.guild.id))
                await db.commit()

            else:
                # if nothing is specified, subscribe to everything
                if categories is None:
                    categories = "all categories"
                    redposts = True
                    pbe = True
                    rotations = True
                    esports = True
                    releases = True
                else:
                    # looks for each category and sets a boolean variable for it
                    categories = categories.lower()
                    redposts = "red posts" in categories
                    pbe = "pbe" in categories
                    rotations = "rotations" in categories
                    esports = "esports" in categories
                    releases = "releases" in categories

                    # return error if no categories are no found but they are also not None
                    if not redposts and not pbe and not rotations and not esports and not releases:
                        await ctx.send("No categories found, potentially check for typos")
                        return

                # enter information into database
                await db.execute("INSERT INTO SurrenderAt20Subscriptions (Guild, RedPosts, PBE, Rotations, Esports, Releases) \
                                 VALUES (?, ?, ?, ?, ?, ?)",
                                 (ctx.guild.id, redposts, pbe, rotations, esports, releases))
                await db.commit()

        # create message embed and send response
        emb = discord.Embed(title="Successfully subscribed to " + categories.title(),
                            color=discord.Colour.green())
        emb.set_thumbnail(url="https://images-ext-2.discordapp.net/external/p4GLboECWMVLnDH-Orv6nkWm3OG8uLdI2reNRQ9RX74/http/3.bp.blogspot.com/-M_ecJWWc5CE/Uizpk6U3lwI/AAAAAAAACLo/xyh6eQNRzzs/s640/sitethumb.jpg")

        await ctx.send(embed=emb)

    @surrenderat20.command(aliases=["unsub"])
    async def unsubscribe(self, ctx, *, categories=None):
        """Unsubscribes from Surrender@20

        You can specify the categories you want to unsubscribe from or name none and unsubscribe from all.

        The possible categories are:
        - Red Posts
        - PBE
        - Rotations
        - Esports
        - Releases"""
        async with aiosqlite.connect("data.db") as db:
            n = await db.execute("SELECT * FROM SurrenderAt20Subscriptions WHERE Guild=?", (ctx.guild.id,))
            results = await n.fetchall()
            await n.close()
            if len(results) == 0:
                await ctx.send("You are not subscribed to any categories")
                return

            # if nothing is specified, unsubscribe from everything
            if categories is None:
                categories = "all categories"
                await db.execute("DELETE FROM SurrenderAt20Subscriptions WHERE Guild=?", (ctx.guild.id,))
                await db.commit()
            else:
                categories = categories.lower()
                # return error if no categories are no found but they are also not None
                if "red posts" not in categories and "pbe" not in categories and "rotations" not in categories and "esports" not in categories and "releases" not in categories:
                    await ctx.send("No categories found, potentially check for typos")
                    return

                result = results[0]
                redposts, pbe, rotations, esports, releases = result[1:]
                # looks for each category and update boolean variable for it
                if "red posts" in categories:
                    redposts = 0
                if "pbe" in categories:
                    pbe = 0
                if "rotations" in categories:
                    rotations = 0
                if "esports" in categories:
                    esports = 0
                if "releases" in categories:
                    releases = 0

                # enter information into database
                await db.execute("UPDATE SurrenderAt20Subscriptions \
                                  SET RedPosts=?, PBE=?, Rotations=?, Esports=?, Releases=? \
                                  WHERE Guild=?",
                                 (redposts, pbe, rotations, esports, releases, ctx.guild.id))
                await db.commit()

        # create message embed and send response
        emb = discord.Embed(title="Successfully unsubscribed from " + categories.title(),
                            color=discord.Colour.red())
        emb.set_thumbnail(url="https://images-ext-2.discordapp.net/external/p4GLboECWMVLnDH-Orv6nkWm3OG8uLdI2reNRQ9RX74/http/3.bp.blogspot.com/-M_ecJWWc5CE/Uizpk6U3lwI/AAAAAAAACLo/xyh6eQNRzzs/s640/sitethumb.jpg")

        await ctx.send(embed=emb)

    @surrenderat20.command(aliases=["add"])
    async def add_keyword(self, ctx, *, keyword=None):
        """Adds a keyword to search for"""
        async with aiosqlite.connect("data.db") as db:
            # check if announcement channel is set up
            cursor = await db.execute("SELECT AnnounceChannelID FROM Guilds WHERE ID=?", (ctx.guild.id,))
            row = await cursor.fetchall()
            await cursor.close()
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

    @surrenderat20.command(aliases=["remove"])
    async def remove_keyword(self, ctx, *, keyword=None):
        """Removes a keyword"""
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

    @surrenderat20.command(name="list")
    async def _list(self, ctx):
        """Displays a list of all Keywords"""
        keywords = ""
        categories = ""
        async with aiosqlite.connect("data.db") as db:
            # get all subscribed categories of the guild
            cursor = await db.execute("SELECT * FROM SurrenderAt20Subscriptions WHERE Guild=?", (ctx.guild.id,))
            subscriptions = await cursor.fetchone()
            await cursor.close()

            if subscriptions is None:
                categories = "-"
            else:
                if subscriptions[1] == 1:
                    categories = categories + "Red Posts\n"
                if subscriptions[2] == 1:
                    categories = categories + "PBE\n"
                if subscriptions[3] == 1:
                    categories = categories + "Rotations\n"
                if subscriptions[4] == 1:
                    categories = categories + "Esports\n"
                if subscriptions[5] == 1:
                    categories = categories + "Releases\n"

                if categories == "":
                    categories = "-"

            # get all keywords of the guild
            cursor = await db.execute("SELECT Keyword FROM Keywords WHERE Guild=?", (ctx.guild.id,))

            async for row in cursor:
                keywords = keywords + row[0] + "\n"
            await cursor.close()

            if keywords == "":
                keywords = "-"

        # create message embed and send it
        emb = discord.Embed(title="Surrender@20 subscriptions", color=discord.Colour.orange())
        emb.add_field(name="Categories", value=categories)
        emb.add_field(name="Keywords", value=keywords)
        await ctx.send(embed=emb)

    @surrenderat20.command()
    async def latest(self, ctx):
        """Sends the lastest Post"""
        parsingChannelUrl = "https://www.googleapis.com/blogger/v3/blogs/8141971962311514602/posts"
        parsingChannelQueryString = {"key": auth_token.google, "fields": "items"}
        async with self.bot.session.get(parsingChannelUrl, params=parsingChannelQueryString) as resp:
            posts = await resp.json()
        item = posts["items"][0]
        content = item["content"]

        emb = discord.Embed(title=item["title"],
                            color=discord.Colour.orange(),
                            description=" ".join(item["labels"]),
                            url=item["url"],
                            timestamp=datetime.datetime.utcnow())
        emb.set_thumbnail(url="https://images-ext-2.discordapp.net/external/p4GLboECWMVLnDH-Orv6nkWm3OG8uLdI2reNRQ9RX74/http/3.bp.blogspot.com/-M_ecJWWc5CE/Uizpk6U3lwI/AAAAAAAACLo/xyh6eQNRzzs/s640/sitethumb.jpg")
        if item["author"]["displayName"] == "Aznbeat":
            author_img = "https://images-ext-2.discordapp.net/external/HI8rRYejC0QYULMmoDBTcZgJ52U0Msvwj9JmUxd-JAI/https/disqus.com/api/users/avatars/Aznbeat.jpg"
        else:
            author_img = "https://images-ext-2.discordapp.net/external/t0bRQzNtKHoIDcFcj2X8R0O0UPqeeyKdvawNbVMoHXE/https/disqus.com/api/users/avatars/Moobeat.jpg"
        emb.set_author(name=item["author"]["displayName"], icon_url=author_img)

        startImgPos = content.find('<img', 0, len(content)) + 4
        if(startImgPos > -1):
            endImgPos = content.find('>', startImgPos, len(content))
            imageTag = content[startImgPos:endImgPos]
            startSrcPos = imageTag.find('src="', 0, len(content)) + 5
            endSrcPos = imageTag.find('"', startSrcPos, len(content))
            linkTag = imageTag[startSrcPos:endSrcPos]

            emb.set_image(url=linkTag)

        async with aiosqlite.connect("data.db") as db:
            keywords = await db.execute("SELECT Keyword FROM Keywords WHERE Guild=?", (ctx.guild.id,))
            async for keyword in keywords:
                kw = " " + keyword[0] + " "
                # check if keyword appears in post
                brokentext = content.replace("<br />", "\n")
                cleantext = re.sub(self.cleanr, '', brokentext).replace("&nbsp;", " ")
                if kw in cleantext.lower():
                    extracts = []
                    # find paragraphs with keyword
                    for part in cleantext.split("\n\n"):
                        if kw in part.lower():
                            extracts.append(part.strip())

                    # create message embed and send it to the server
                    exctrats_string = "\n\n".join(extracts)
                    if len(exctrats_string) > 950:
                        exctrats_string = exctrats_string[:950] + "... `" + str(cleantext.lower().count(kw)) + "` mentions in total"

                    emb.add_field(name=f"'{keyword[0]}' was mentioned in this post!", value=exctrats_string, inline=False)
            await keywords.close()

            channels = await db.execute("SELECT SurrenderAt20NotifChannel FROM Guilds WHERE ID=?", (ctx.guild.id,))
            channel_id = await channels.fetchone()
            channel = self.bot.get_channel(channel_id[0])
            await channel.send("New Surrender@20 post!", embed=emb)
        await ctx.send("Sent latest post into " + channel.mention)


def setup(bot):
    bot.add_cog(SurrenderAt20(bot))
