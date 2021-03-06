import discord
from discord.ext import commands

import auth_token
import datetime
import re


class Youtube(commands.Cog):
    """Add or remove youtube channels to announce streams and videos of"""

    def __init__(self, bot):
        self.bot = bot

    # who and where the commands are permitted to use
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    @commands.group(aliases=["yt"])
    async def youtube(self, ctx):
        """(Un)Subscribe to channels to announce"""
        if ctx.invoked_subcommand is None:
            await ctx.send("You need to specify an action!\n(use 'help youtube' for more information)")

    @youtube.command()
    async def setchannel(self, ctx, channel=None):
        """Sets the channel to announce Youtube streams and videos in"""
        # get channel obj, depending on if it was mentioned or just the name was specified
        if len(ctx.message.channel_mentions) > 0:
            channel_obj = ctx.message.channel_mentions[0]
        elif channel is not None:
            channel_obj = discord.utils.get(
                ctx.guild.channels, name=channel.replace("#", ""))
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

        async with self.bot.pool.acquire() as db:
            # add channel id for the guild to the database
            await db.execute("UPDATE Guilds SET YoutubeNotifChannel=$1 WHERE ID=$2",
                             channel_obj.id, ctx.guild.id)

        await ctx.send("Successfully set Youtube notifications to " + channel_obj.mention)

    @youtube.command(aliases=["sub"])
    async def subscribe(self, ctx, *, channel=None):
        """Subscribes to a channel

        Its videos and livestreams will be announced in the specified channel

        Use "~onlystreams" in order to ignore videos of this channel"""
        async with self.bot.pool.acquire() as db:
            # check if announcement channel is set up
            rows = await db.fetch("SELECT YoutubeNotifChannel FROM Guilds WHERE ID=$1", ctx.guild.id)
            if len(rows) == 0 or rows[0][0] is None:
                await ctx.send("You need to set up a notifications channel before subscribing! \nUse either ;setchannel or ;surrenderat20 setchannel")
                return

        if channel is None:
            await ctx.send("You need to specify a channel to subscribe to")
            return

        # check if the subscription should be set to "only streams", ignoring videos
        if "~onlystreams" in channel.lower():
            channel = re.sub('(?i)' + re.escape('~onlystreams'), '', channel)
            onlystreams = True
        else:
            onlystreams = False

        # searching for the channel
        parsingChannelUrl = "https://www.googleapis.com/youtube/v3/search"
        parsingChannelQueryString = {"part": "snippet", "q": channel, "maxResults": "1",
                                     "key": auth_token.google, "type": "channel"}
        async with self.bot.session.get(parsingChannelUrl, params=parsingChannelQueryString) as resp:
            searchResult = await resp.json()

        # channel does not exist
        if len(searchResult["items"]) == 0:
            await ctx.send("Could not find a channel called " + channel)
            return

        # getting the channel data
        parsingChannelUrl = "https://www.googleapis.com/youtube/v3/channels"
        parsingChannelQueryString = {"part": "snippet,contentDetails,statistics", "id": searchResult["items"][0]["id"]["channelId"],
                                     "maxResults": "1", "key": auth_token.google}
        async with self.bot.session.get(parsingChannelUrl, params=parsingChannelQueryString) as resp:
            channel_obj = await resp.json()

        ch = channel_obj["items"][0]
        channel_id = ch["id"]
        channel_name = ch["snippet"]["title"]
        videoCount = int(ch["statistics"]["videoCount"])

        # getting last uploaded video
        parsingChannelUrl = "https://www.googleapis.com/youtube/v3/playlistItems"
        parsingChannelQueryString = {"part": "id", "playlistId": ch["contentDetails"]["relatedPlaylists"]["uploads"],
                                     "maxResults": "1", "key": auth_token.google}
        async with self.bot.session.get(parsingChannelUrl, params=parsingChannelQueryString) as resp:
            playlist_obj = await resp.json()

        videoID = playlist_obj["items"][0]["id"]

        async with self.bot.pool.acquire() as db:
            # check if youtube channel is already in database, otherwise add it
            results = await db.fetch("SELECT 1 FROM YoutubeChannels WHERE ID=$1", channel_id)
            if len(results) == 0:
                dt = datetime.datetime(
                    2018, 9, 12, 13, 33, 7, 593639, tzinfo=datetime.timezone.utc)
                await db.execute("INSERT INTO YoutubeChannels (ID, Name, LastLive, LastVideoID, VideoCount) VALUES ($1, $2, $3, $4, $5)",
                                 channel_id, channel_name, dt, videoID, videoCount)

            # insert subscription into the database
            results = await db.fetch("SELECT 1 FROM YoutubeSubscriptions WHERE YoutubeChannel=$1 AND Guild=$2", channel_id, ctx.guild.id)
            if len(results) == 0:
                await db.execute("INSERT INTO YoutubeSubscriptions (YoutubeChannel, Guild, OnlyStreams) VALUES ($1, $2, $3)",
                                 channel_id, ctx.guild.id, onlystreams)
            else:
                await ctx.send("You are already subscribed to this channel")
                return

        # send subscription request to youtube
        parsingChannelUrl = "https://pubsubhubbub.appspot.com/subscribe"
        parsingChannelQueryString = {"hub.mode": "subscribe", "hub.callback": auth_token.server_url + "/youtube",
                                     "hub.topic": "https://www.youtube.com/xml/feeds/videos.xml?channel_id=" + channel_id, "hub.lease_seconds": 864000}
        async with self.bot.session.post(parsingChannelUrl, params=parsingChannelQueryString) as resp:
            if resp.status != 202:
                print(resp.text)

        # create message embed and send it
        emb = discord.Embed(title="Successfully subscribed to " + channel_name,
                            description=ch["snippet"]["description"], color=discord.Colour.green())
        emb.set_thumbnail(url=ch["snippet"]["thumbnails"]["default"]["url"])
        emb.url = "https://www.youtube.com/channel/" + channel_id

        await ctx.send(embed=emb)

    @youtube.command(aliases=["unsub"])
    async def unsubscribe(self, ctx, *, channel=None):
        """Unsubscripes from a channel

        Its videos and livestreams will no longer be announced"""
        if channel is None:
            await ctx.send("You need to spefify the channel you want to unsubscribe from")
            return

        # searching for the channel
        parsingChannelUrl = "https://www.googleapis.com/youtube/v3/search"
        parsingChannelQueryString = {"part": "snippet", "q": channel, "maxResults": "1",
                                     "key": auth_token.google, "type": "channel"}
        async with self.bot.session.get(parsingChannelUrl, params=parsingChannelQueryString) as resp:
            channel_obj = await resp.json()

        if len(channel_obj["items"]) == 0:
            await ctx.send("Could not find a channel called " + channel)
            return

        ch = channel_obj["items"][0]
        channel_id = ch["id"]["channelId"]
        channel_name = ch["snippet"]["channelTitle"]

        async with self.bot.pool.acquire() as db:
            # check if server is already subscribed to the channel
            # remove subscrption from database
            results = await db.fetch("SELECT 1 FROM YoutubeSubscriptions WHERE YoutubeChannel=$1 AND Guild=$2", channel_id, ctx.guild.id)
            if len(results) == 1:
                await db.execute("DELETE FROM YoutubeSubscriptions WHERE YoutubeChannel=$1 AND Guild=$2", channel_id, ctx.guild.id)
            else:
                await ctx.send("You are not subscribed to this channel")
                return

            # remove channel from database if no server is subscribed to it anymore
            results = await db.fetch("SELECT 1 FROM YoutubeSubscriptions WHERE YoutubeChannel=$1", channel_id)
            if len(results) == 0:
                await db.execute("DELETE FROM YoutubeChannels WHERE ID=$1", channel_id)

        # send unsubscribe request
        parsingChannelUrl = "https://pubsubhubbub.appspot.com/subscribe"
        parsingChannelQueryString = {"hub.mode": "unsubscribe", "hub.callback": auth_token.server_url + "/youtube",
                                     "hub.topic": "https://www.youtube.com/xml/feeds/videos.xml?channel_id=" + channel_id}
        async with self.bot.session.post(parsingChannelUrl, params=parsingChannelQueryString) as resp:
            if resp.status != 202:
                print(resp.text)

        # create message embed and send it
        emb = discord.Embed(title="Successfully unsubscribed from " + channel_name,
                            description=ch["snippet"]["description"], color=discord.Colour.dark_red())
        emb.set_thumbnail(url=ch["snippet"]["thumbnails"]["default"]["url"])
        emb.url = "https://www.youtube.com/channel/" + channel_id

        await ctx.send(embed=emb)

    @youtube.command(name="list")
    async def _list(self, ctx):
        """Displays a list of all subscribed channels"""
        names = ""
        async with self.bot.pool.acquire() as db:
            # get all subscribed to channels of the guild
            cursor = await db.fetch("SELECT YoutubeChannels.Name, YoutubeSubscriptions.OnlyStreams \
                                       FROM YoutubeSubscriptions INNER JOIN YoutubeChannels \
                                       ON YoutubeSubscriptions.YoutubeChannel=YoutubeChannels.ID \
                                       WHERE Guild=$1", ctx.guild.id)
            for row in cursor:
                if row[1] == 1:
                    os = " (Only streams)"
                else:
                    os = ""
                names = names + row[0] + os + "\n"

        emb = discord.Embed(title="Youtube subscriptions",
                            color=discord.Colour.red(), description=names)
        await ctx.send(embed=emb)


def setup(bot):
    bot.add_cog(Youtube(bot))
