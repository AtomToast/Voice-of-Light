import discord
from discord.ext import commands

import datetime
import asyncio
import auth_token
import traceback
import sys


class Reddit(commands.Cog):
    """Add or remove subreddits to announce new posts of"""
    def __init__(self, bot):
        self.bot = bot

        # create polling background task
        self.reddit_poller = self.bot.loop.create_task(self.poll())
        self.reddit_poller.add_done_callback(self.callback)

    def callback(self, result):
        ex = result.exception()
        print('Ignoring exception in Reddit.poll()', file=sys.stderr)
        traceback.print_exception(type(ex), ex, ex.__traceback__, file=sys.stderr)

        if ex == asyncio.CancelledError:
            self.reddit_poller = self.bot.loop.create_task(self.poll())
            self.reddit_poller.add_done_callback(self.callback)

    async def poll(self):
        await self.bot.wait_until_ready()

        async with self.bot.pool.acquire() as db:
            while not self.bot.is_closed():
                # loop through all subreddits and check if a new post is up
                subreddits = await db.fetch("SELECT * FROM Subreddits")
                for row in subreddits:
                    parsingChannelUrl = f"https://www.reddit.com/r/{row[1]}/new.json"
                    parsingChannelHeader = {'cache-control': "no-cache", "User-Agent": auth_token.user_agent}
                    parsingChannelQueryString = {"sort": "new", "limit": "1"}
                    async with self.bot.session.get(parsingChannelUrl, headers=parsingChannelHeader,
                                                    params=parsingChannelQueryString) as resp:
                        if resp.status > 400:
                            await asyncio.sleep(2)
                            continue

                        try:
                            submissions_obj = await resp.json()
                        except Exception as ex:
                            print(await resp.text())
                            print('Ignoring exception in Reddit.poll()', file=sys.stderr)
                            traceback.print_exception(type(ex), ex, ex.__traceback__, file=sys.stderr)
                            await asyncio.sleep(1)
                            continue

                    try:
                        submission_data = submissions_obj["data"]["children"][0]["data"]
                    except Exception:
                        await asyncio.sleep(1)
                        continue

                    # new post found
                    if submission_data["id"] != row[2] and submission_data["created_utc"] > row[3]:

                        # update last post data in database
                        await db.execute("UPDATE Subreddits SET LastPostID=$1, LastPostTime=$2 WHERE ID=$3",
                                         submission_data["id"], submission_data["created_utc"], row[0])

                        # create message embed
                        if len(submission_data["title"]) > 256:
                            title = submission_data["title"][:256]
                        else:
                            title = submission_data["title"]
                        emb = discord.Embed(title=title,
                                            color=discord.Colour.dark_blue(),
                                            url="https://www.reddit.com" + submission_data["permalink"])
                        emb.timestamp = datetime.datetime.utcnow()
                        emb.set_author(name=submission_data["author"])

                        post_content = submission_data["selftext"].replace("amp;", "").replace("&#x200B;", "").replace("&lt;", "<").replace("&gt;", ">")
                        # if post content is very big, trim it
                        if len(submission_data["selftext"]) > 1900:
                            emb.description = post_content[:1900] + "... `click title to continue`"
                        else:
                            emb.description = post_content

                        try:
                            emb.set_image(url=submission_data["preview"]["images"][0]["variants"]["gif"]["source"]["url"])
                        except KeyError:
                            try:
                                if submission_data["thumbnail"] not in ["self", "default", "spoiler", "nsfw"]:
                                    if submission_data["over_18"]:
                                        emb.set_image(url=submission_data["preview"]["images"][0]["source"]["url"])
                                    else:
                                        emb.set_image(url=submission_data["thumbnail"])
                                elif submission_data["over_18"] and submission_data["domain"] in ["i.imgur.com", "imgur.com", "i.redd.it", "gfycat.com"]:
                                    emb.set_image(url=submission_data["url"])
                            except KeyError:
                                pass

                        # send notification to every subscribed server
                        channels = await db.fetch("SELECT Guilds.RedditNotifChannel, Guilds.ID \
                                                     FROM SubredditSubscriptions INNER JOIN Guilds \
                                                     ON SubredditSubscriptions.Guild=Guilds.ID \
                                                     WHERE Subreddit=$1", row[0])

                        for ch in channels:
                            announceChannel = self.bot.get_channel(ch[0])
                            if submission_data["over_18"] and not announceChannel.is_nsfw():
                                try:
                                    emb.set_image(url=submission_data["preview"]["images"][0]["variants"]["nsfw"]["source"]["url"].replace("amp;", ""))
                                except KeyError:
                                    emb.set_image(url="https://www.digitaltrends.com/wp-content/uploads/2012/11/reddit.jpeg")
                                emb.set_footer(text="This is an NSFW post, to uncensor posts, please mark the notification channel as NSFW")
                            try:
                                await announceChannel.send("A new post in /r/" + row[1] + " !", embed=emb)
                            except AttributeError:
                                guild = self.bot.get_guild(ch[1])
                                if guild is None:
                                    await db.execute("DELETE FROM SubredditSubscriptions WHERE Subreddit=$1 AND Guild=$2", ch[0], ch[1])
                            except discord.errors.Forbidden:
                                pass

                await asyncio.sleep(1)

    # who and where the commands are permitted to use
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    @commands.group(aliases=["rd"])
    async def reddit(self, ctx):
        """(Un)Subscribe to subreddits to announce"""
        if ctx.invoked_subcommand is None:
            await ctx.send("You need to specify an action \n(use 'help reddit' for more information)")

    @reddit.command()
    async def setchannel(self, ctx, channel=None):
        """Sets the channel to announce Reddit posts in"""
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

        bot_member = ctx.guild.get_member(self.bot.user.id)
        permissions = channel_obj.permissions_for(bot_member)
        if not permissions.send_messages or not permissions.embed_links:
            await ctx.send("Command failed, please make sure that the bot has both permissions for sending messages and using embeds in the specified channel!")
            return

        async with self.bot.pool.acquire() as db:
            # add channel id for the guild to the database
            await db.execute("UPDATE Guilds SET RedditNotifChannel=$1 WHERE ID=$2",
                             channel_obj.id, ctx.guild.id)

        await ctx.send("Successfully set Reddit notifications to " + channel_obj.mention)

    @reddit.command(aliases=["sub"])
    async def subscribe(self, ctx, *, subreddit=None):
        """Subscribes to a subreddit

        Its new posts will be announced in the specified channel"""
        async with self.bot.pool.acquire() as db:
            # check if announcement channel is set up
            rows = await db.fetch("SELECT RedditNotifChannel FROM Guilds WHERE ID=$1", ctx.guild.id)
            if len(rows) == 0 or rows[0][0] is None:
                await ctx.send("You need to set up a notifications channel before subscribing! \nUse either ;setchannel or ;surrenderat20 setchannel")
                return

        if subreddit is None:
            await ctx.send("You need to specify a subreddit to subscribe to")
            return

        sr = subreddit.replace("/r/", "").replace("r/", "")

        # search for specified subreddit
        parsingChannelUrl = f"https://www.reddit.com/subreddits/search.json?q={sr}&include_over_18=on"
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

        announceChannel = self.bot.get_channel(rows[0][0])
        if subreddit_data["over18"] and not announceChannel.is_nsfw():
            await ctx.send("This subreddit is NSFW, to subscribe you need to set the announcement channel to NSFW")
            return

        # get last post data
        parsingChannelUrl = f"https://www.reddit.com/r/{sr}/new.json"
        parsingChannelHeader = {'cache-control': "no-cache"}
        parsingChannelQueryString = {"sort": "new", "limit": "1"}
        async with self.bot.session.get(parsingChannelUrl, headers=parsingChannelHeader,
                                        params=parsingChannelQueryString) as resp:
            submissions_obj = await resp.json()

        submission_data = submissions_obj["data"]["children"][0]["data"]

        async with self.bot.pool.acquire() as db:
            # if subreddit is not yet in database, add it
            results = await db.fetch("SELECT 1 FROM Subreddits WHERE ID=$1", submission_data["subreddit_id"])
            if len(results) == 0:
                await db.execute("INSERT INTO Subreddits (ID, Name, LastPostID, LastPostTime) VALUES ($1, $2, $3, $4)",
                                 submission_data["subreddit_id"], submission_data["subreddit"],
                                 submission_data["id"], submission_data["created_utc"])

            # add subscription to database
            results = await db.fetch("SELECT 1 FROM SubredditSubscriptions WHERE Subreddit=$1 AND Guild=$2",
                                     submission_data["subreddit_id"], ctx.guild.id)
            if len(results) == 0:
                await db.execute("INSERT INTO SubredditSubscriptions (Subreddit, Guild) VALUES ($1, $2)",
                                 submission_data["subreddit_id"], ctx.guild.id)
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
        parsingChannelUrl = f"https://www.reddit.com/subreddits/search.json?q={sr}&include_over_18=on"
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

        async with self.bot.pool.acquire() as db:
            # remove subscription from database
            results = await db.fetch("SELECT 1 FROM SubredditSubscriptions WHERE Subreddit=$1 AND Guild=$2",
                                     submission_data["subreddit_id"], ctx.guild.id)
            if len(results) == 1:
                await db.execute("DELETE FROM SubredditSubscriptions WHERE Subreddit=$1 AND Guild=$2",
                                 submission_data["subreddit_id"], ctx.guild.id)
            else:
                await ctx.send("You are not subscribed to this Subreddit")
                return

            # remove subreddit from database if no server is subscribed to it anymore
            results = await db.fetch("SELECT 1 FROM SubredditSubscriptions WHERE Subreddit=$1", submission_data["subreddit_id"])
            if len(results) == 0:
                await db.execute("DELETE FROM Subreddits WHERE ID=$1", submission_data["subreddit_id"])

        # create message embed and send it
        emb = discord.Embed(title="Successfully unsubscribed from " + submission_data["subreddit_name_prefixed"],
                            description=subreddit_data["public_description"], color=discord.Colour.dark_red())
        emb.set_thumbnail(url=subreddit_data["icon_img"])
        emb.url = "https://www.reddit.com" + subreddit_data["url"]

        await ctx.send(embed=emb)

    @reddit.command(name="list")
    async def _list(self, ctx):
        """Displays a list of all subscribed subreddits"""
        names = ""
        async with self.bot.pool.acquire() as db:
            # get all subreddits the server is subscribed to
            cursor = await db.fetch("SELECT Subreddits.Name \
                                       FROM SubredditSubscriptions INNER JOIN Subreddits \
                                       ON SubredditSubscriptions.Subreddit=Subreddits.ID \
                                       WHERE Guild=$1", ctx.guild.id)

            for row in cursor:
                names = names + row[0] + "\n"

        # create message embed and send it
        emb = discord.Embed(title="Subreddit subscriptions", color=discord.Colour.dark_blue(), description=names)
        await ctx.send(embed=emb)


def setup(bot):
    bot.add_cog(Reddit(bot))
