import discord
from discord.ext import commands

import aiosqlite
import datetime
import asyncio


def callback(result):
        print(result)
        print(result.exception())


class Reddit:
    """Add or remove subreddits to announce new posts of"""
    def __init__(self, bot):
        self.bot = bot

        # create polling background task
        self.reddit_poller = self.bot.loop.create_task(self.poll())
        self.reddit_poller.add_done_callback(callback)

    async def poll(self):
        await self.bot.wait_until_ready()

        async with aiosqlite.connect("data.db") as db:
            while not self.bot.is_closed():
                # loop through all subreddits and check if a new post is up
                subreddits = await db.execute("SELECT * FROM Subreddits")
                async for row in subreddits:
                    parsingChannelUrl = f"https://www.reddit.com/r/{row[1]}/new.json"
                    parsingChannelHeader = {'cache-control': "no-cache"}
                    parsingChannelQueryString = {"sort": "new", "limit": "1"}
                    async with self.bot.session.get(parsingChannelUrl, headers=parsingChannelHeader,
                                                    params=parsingChannelQueryString) as resp:
                        submissions_obj = await resp.json()

                    submission_data = submissions_obj["data"]["children"][0]["data"]

                    # new post found
                    if submission_data["id"] != row[2] and submission_data["created_utc"] > row[3]:
                        # update last post data in database
                        await db.execute("UPDATE Subreddits SET LastPostID=?, LastPostTime=? WHERE ID=?",
                                         (submission_data["id"], submission_data["created_utc"], row[0]))
                        await db.commit()

                        # create message embed
                        emb = discord.Embed(title=submission_data["title"],
                                            color=discord.Colour.dark_blue(),
                                            url="https://www.reddit.com" + submission_data["permalink"])
                        emb.timestamp = datetime.datetime.utcnow()
                        emb.set_author(name=submission_data["author"])

                        # if post content is very big, trim it
                        if len(submission_data["selftext"]) > 1900:
                            emb.description = submission_data["selftext"][:1900] + "... `click title to continue`"
                        else:
                            emb.description = submission_data["selftext"]

                        if submission_data["thumbnail"] != "self" and "_" not in submission_data["thumbnail"]:
                            emb.set_image(url=submission_data["thumbnail"])

                        # send notification to every subscribed server
                        channels = await db.execute("SELECT Guilds.AnnounceChannelID \
                                                     FROM SubredditSubscriptions INNER JOIN Guilds \
                                                     ON SubredditSubscriptions.Guild=Guilds.ID \
                                                     WHERE Subreddit=?", (row[0],))

                        async for ch in channels:
                            announceChannel = self.bot.get_channel(ch[0])
                            print("Reddit post channel: " + announceChannel.name + " - " + str(announceChannel.id))
                            await announceChannel.send("A new post in /r/" + row[1] + " !", embed=emb)

                        await channels.close()

                await subreddits.close()
                await asyncio.sleep(1)

    # who and where the commands are permitted to use
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    @commands.group(aliases=["rd"])
    async def reddit(self, ctx):
        """(Un)Subscribe to subreddits to announce"""
        if ctx.invoked_subcommand is None:
            await ctx.send("You need to specify an action \n(use 'help reddit' for more information)")

    @reddit.command(aliases=["sub"])
    async def subscribe(self, ctx, *, subreddit=None):
        """Subscribes to a subreddit

        Its new posts will be announced in the specified channel"""
        async with aiosqlite.connect("data.db") as db:
            # check if announcement channel is set up
            cursor = await db.execute("SELECT AnnounceChannelID FROM Guilds WHERE ID=?", (ctx.guild.id,))
            row = await cursor.fetchall()
            await cursor.close()
            if len(row) == 0:
                await ctx.send("You need to set up a notifications channel before subscribing to any subreddits")
                return

        if subreddit is None:
            await ctx.send("You need to spefify a subreddit to subscribe to")
            return

        sr = subreddit.replace("/r/", "").replace("r/", "")

        # search for specified subreddit
        parsingChannelUrl = f"https://www.reddit.com/subreddits/search.json?q={sr}"
        parsingChannelHeader = {'cache-control': "no-cache"}
        parsingChannelQueryString = {"limit": "1"}
        async with self.bot.session.get(parsingChannelUrl, headers=parsingChannelHeader,
                                        params=parsingChannelQueryString) as resp:
            subreddits_obj = await resp.json()

        if len(subreddits_obj["data"]["children"]) == 0:
            await ctx.send(f"Could not find a subreddit called {sr}")
            return

        subreddit_data = subreddits_obj["data"]["children"][0]["data"]

        if subreddit_data["display_name"].lower() != sr.lower():
            name = subreddit_data["display_name"]
            await ctx.send(f"Could not find subreddit called '{sr}'. \nDo you maybe mean '{name}'?")
            return

        # get last post data
        parsingChannelUrl = f"https://www.reddit.com/r/{sr}/new.json"
        parsingChannelHeader = {'cache-control': "no-cache"}
        parsingChannelQueryString = {"sort": "new", "limit": "1"}
        async with self.bot.session.get(parsingChannelUrl, headers=parsingChannelHeader,
                                        params=parsingChannelQueryString) as resp:
            submissions_obj = await resp.json()

        submission_data = submissions_obj["data"]["children"][0]["data"]

        async with aiosqlite.connect("data.db") as db:
            # if subreddit is not yet in database, add it
            n = await db.execute("SELECT 1 FROM Subreddits WHERE ID=?", (submission_data["subreddit_id"],))
            results = await n.fetchall()
            await n.close()
            if len(results) == 0:
                await db.execute("INSERT INTO Subreddits (ID, Name, LastPostID, LastPostTime) VALUES (?, ?, ?, ?)",
                                 (submission_data["subreddit_id"], submission_data["subreddit"],
                                  submission_data["id"], submission_data["created_utc"]))
                await db.commit()

            # add subscription to database
            n = await db.execute("SELECT 1 FROM SubredditSubscriptions WHERE Subreddit=? AND Guild=?",
                                 (submission_data["subreddit_id"], ctx.guild.id))
            results = await n.fetchall()
            await n.close()
            if len(results) == 0:
                await db.execute("INSERT INTO SubredditSubscriptions (Subreddit, Guild) VALUES (?, ?)",
                                 (submission_data["subreddit_id"], ctx.guild.id))
                await db.commit()
            else:
                await ctx.send("You are already subscribed to this Subreddit")
                return

        # create message embed and send it
        emb = discord.Embed(title="Successfully subscribed to " + submission_data["subreddit_name_prefixed"],
                            description=subreddit_data["public_description"], color=discord.Colour.green())
        emb.set_thumbnail(url=subreddit_data["icon_img"])
        emb.url = "https://www.reddit.com" + subreddit_data["url"]

        await ctx.send(embed=emb)

    @reddit.command(aliases=["unsub"])
    async def unsubscribe(self, ctx, *, subreddit=None):
        """Unsubscripes from a subreddit

        New posts will no longer be announced"""
        if subreddit is None:
            await ctx.send("You need to spefify a subreddit to subscribe to")
            return

        sr = subreddit.replace("/r/", "").replace("r/", "")

        # search subreddit
        parsingChannelUrl = f"https://www.reddit.com/subreddits/search.json?q={sr}"
        parsingChannelHeader = {'cache-control': "no-cache"}
        parsingChannelQueryString = {"limit": "1"}
        async with self.bot.session.get(parsingChannelUrl, headers=parsingChannelHeader,
                                        params=parsingChannelQueryString) as resp:
            subreddits_obj = await resp.json()

        if len(subreddits_obj["data"]["children"]) == 0:
            await ctx.send(f"Could not find a subreddit called {sr}")
            return

        subreddit_data = subreddits_obj["data"]["children"][0]["data"]

        if subreddit_data["display_name"].lower() != sr.lower():
            name = subreddit_data["display_name"]
            await ctx.send(f"Could not find subreddit called '{sr}'. \nDo you maybe mean '{name}'?")
            return

        # get latest post data
        parsingChannelUrl = f"https://www.reddit.com/r/{sr}/new.json"
        parsingChannelHeader = {'cache-control': "no-cache"}
        parsingChannelQueryString = {"sort": "new", "limit": "1"}
        async with self.bot.session.get(parsingChannelUrl, headers=parsingChannelHeader,
                                        params=parsingChannelQueryString) as resp:
            submissions_obj = await resp.json()

        submission_data = submissions_obj["data"]["children"][0]["data"]

        async with aiosqlite.connect("data.db") as db:
            # remove subscription from database
            n = await db.execute("SELECT 1 FROM SubredditSubscriptions WHERE Subreddit=? AND Guild=?",
                                 (submission_data["subreddit_id"], ctx.guild.id))
            results = await n.fetchall()
            await n.close()
            if len(results) == 1:
                await db.execute("DELETE FROM SubredditSubscriptions WHERE Subreddit=? AND Guild=?",
                                 (submission_data["subreddit_id"], ctx.guild.id))
                await db.commit()
            else:
                await ctx.send("You are not subscribed to this Subreddit")
                return

            # remove subreddit from database if no server is subscribed to it anymore
            n = await db.execute("SELECT 1 FROM SubredditSubscriptions WHERE Subreddit=?", (submission_data["subreddit_id"],))
            results = await n.fetchall()
            await n.close()
            if len(results) == 0:
                await db.execute("DELETE FROM Subreddits WHERE ID=?", (submission_data["subreddit_id"],))
                await db.commit()

        # create message embed and send it
        emb = discord.Embed(title="Successfully unsubscribed to " + submission_data["subreddit_name_prefixed"],
                            description=subreddit_data["public_description"], color=discord.Colour.dark_red())
        emb.set_thumbnail(url=subreddit_data["icon_img"])
        emb.url = "https://www.reddit.com" + subreddit_data["url"]

        await ctx.send(embed=emb)

    @reddit.command(name="list")
    async def _list(self, ctx):
        """Displays a list of all subscribed subreddits"""
        names = ""
        async with aiosqlite.connect("data.db") as db:
            # get all subreddits the server is subscribed to
            cursor = await db.execute("SELECT Subreddits.Name \
                                       FROM SubredditSubscriptions INNER JOIN Subreddits \
                                       ON SubredditSubscriptions.Subreddit=Subreddits.ID \
                                       WHERE Guild=?", (ctx.guild.id,))

            async for row in cursor:
                names = names + row[0] + "\n"
            await cursor.close()

        # create message embed and send it
        emb = discord.Embed(title="Subreddit subscriptions", color=discord.Colour.dark_blue(), description=names)
        await ctx.send(embed=emb)


def setup(bot):
    bot.add_cog(Reddit(bot))
