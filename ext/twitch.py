import discord
from discord.ext import commands

import auth_token
import aiosqlite
import datetime


class Twitch:
    """Add or remove twitch channels to announce streams of"""
    def __init__(self, bot):
        self.bot = bot

    # who and where the commands are permitted to use
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    @commands.group(aliases=["tw"])
    async def twitch(self, ctx):
        """(Un)Subscribe to channels to announce"""
        if ctx.invoked_subcommand is None:
            await ctx.send("You need to specify an action \n(use 'help twitch' for more information)")

    @twitch.command(aliases=["sub"])
    async def subscribe(self, ctx, *, channel=None):
        """Subscribes to a channel

        Its livestreams will be announced in the specified channel"""
        async with aiosqlite.connect("data.db") as db:
            # check if announcement channel is set up
            cursor = await db.execute("SELECT AnnounceChannelID FROM Guilds WHERE ID=?", (ctx.guild.id,))
            row = await cursor.fetchall()
            if len(row) == 0:
                await ctx.send("You need to set up a notifications channel before subscribing to any channels")
                return

        if channel is None:
            await ctx.send("You need to spefify a channel to subscribe to")
            return

        # trying to get channel data
        parsingChannelUrl = "https://api.twitch.tv/helix/users"
        parsingChannelHeader = {'Client-ID': auth_token.twitch}
        parsingChannelQueryString = {"login": channel}
        async with self.bot.session.get(parsingChannelUrl, headers=parsingChannelHeader, params=parsingChannelQueryString) as resp:
            channel_obj = await resp.json()

        if len(channel_obj["data"]) == 0:
            await ctx.send("Could not find a channel called " + channel)
            return

        ch = channel_obj["data"][0]
        channel_id = ch["id"]
        channel_name = ch["display_name"]

        async with aiosqlite.connect("data.db") as db:
            # check if twitch channel is already in database
            # otherwise add it
            n = await db.execute("SELECT 1 FROM TwitchChannels WHERE ID=?", (channel_id,))
            results = await n.fetchall()
            await n.close()
            if len(results) == 0:
                await db.execute("INSERT INTO TwitchChannels (ID, Name, LastLive) VALUES (?, ?, ?)",
                                 (channel_id, channel_name, datetime.datetime.min.strftime('%Y-%m-%d %H:%M:%S'),))
                await db.commit()

            # insert subscription into database
            n = await db.execute("SELECT 1 FROM TwitchSubscriptions WHERE TwitchChannel=? AND Guild=?", (channel_id, ctx.guild.id))
            results = await n.fetchall()
            await n.close()
            if len(results) == 0:
                await db.execute("INSERT INTO TwitchSubscriptions (TwitchChannel, Guild) VALUES (?, ?)", (channel_id, ctx.guild.id))
                await db.commit()
            else:
                await ctx.send("You are already subscribed to this channel")
                return

        # send twitch subscription request
        parsingChannelUrl = "https://api.twitch.tv/helix/webhooks/hub"
        parsingChannelHeader = {'Client-ID': auth_token.twitch}
        parsingChannelQueryString = {"hub.mode": "subscribe", "hub.callback": "CALLBACK URL/twitch",
                                     "hub.topic": "https://api.twitch.tv/helix/streams?user_id=" + channel_id, "hub.lease_seconds": 864000}
        async with self.bot.session.post(parsingChannelUrl, headers=parsingChannelHeader, params=parsingChannelQueryString) as resp:
            if resp.status != 202:
                print(resp.text)

        # create message embed and send it
        emb = discord.Embed(title="Successfully subscribed to " + channel_name,
                            description=ch["description"], color=discord.Colour.green())
        emb.set_thumbnail(url=ch["profile_image_url"])
        emb.url = "https://www.twitch.com/" + ch["login"]

        await ctx.send(embed=emb)

    @twitch.command(aliases=["unsub"])
    async def unsubscribe(self, ctx, *, channel=None):
        """Unsubscripes from a channel

        Its livestreams will no longer be announced"""
        if channel is None:
            await ctx.send("You need to spefify the channel you want to unsubscribe from")
            return

        # try to get channel data
        parsingChannelUrl = "https://api.twitch.tv/helix/users"
        parsingChannelHeader = {'Client-ID': auth_token.twitch}
        parsingChannelQueryString = {"login": channel}
        async with self.bot.session.get(parsingChannelUrl, headers=parsingChannelHeader, params=parsingChannelQueryString) as resp:
            channel_obj = await resp.json()

        if len(channel_obj["data"]) == 0:
            await ctx.send("Could not find a channel called " + channel)
            return

        ch = channel_obj["data"][0]
        channel_id = ch["id"]
        channel_name = ch["display_name"]

        async with aiosqlite.connect("data.db") as db:
            # check if server is subscribed to channel
            # remove subscription
            n = await db.execute("SELECT 1 FROM TwitchSubscriptions WHERE TwitchChannel=? AND Guild=?", (channel_id, ctx.guild.id))
            results = await n.fetchall()
            await n.close()
            if len(results) == 1:
                await db.execute("DELETE FROM TwitchSubscriptions WHERE TwitchChannel=? AND Guild=?", (channel_id, ctx.guild.id))
                await db.commit()
            else:
                await ctx.send("You are not subscribed to this channel")
                return

            # remove channel from database if no server is subscribed to it anymore
            n = await db.execute("SELECT 1 FROM TwitchSubscriptions WHERE TwitchChannel=?", (channel_id,))
            results = await n.fetchall()
            await n.close()
            if len(results) == 0:
                await db.execute("DELETE FROM TwitchChannels WHERE ID=?", (channel_id,))
                await db.commit()

        # send unsubscribe request
        parsingChannelUrl = "https://api.twitch.tv/helix/webhooks/hub"
        parsingChannelHeader = {'Client-ID': auth_token.twitch}
        parsingChannelQueryString = {"hub.mode": "unsubscribe", "hub.callback": "CALLBACK URL/twitch",
                                     "hub.topic": "https://api.twitch.tv/helix/streams?user_id=" + channel_id}
        async with self.bot.session.post(parsingChannelUrl, headers=parsingChannelHeader, params=parsingChannelQueryString) as resp:
            if resp.status != 202:
                print(resp.text)

        # create message embed and send it
        emb = discord.Embed(title="Successfully unsubscribed from " + channel_name,
                            description=ch["description"], color=discord.Colour.dark_red())
        emb.set_thumbnail(url=ch["profile_image_url"])
        emb.url = "https://www.twitch.com/" + ch["login"]

        await ctx.send(embed=emb)

    @twitch.command(name="list")
    async def _list(self, ctx):
        """Displays a list of all subscribed channels"""
        names = ""
        async with aiosqlite.connect("data.db") as db:
            cursor = await db.execute("SELECT TwitchChannels.Name \
                                       FROM TwitchSubscriptions INNER JOIN TwitchChannels \
                                       ON TwitchSubscriptions.TwitchChannel=TwitchChannels.ID \
                                       WHERE Guild=?", (ctx.guild.id,))

            async for row in cursor:
                names = names + row[0] + "\n"
            await cursor.close()

        emb = discord.Embed(title="Twitch subscriptions", color=discord.Colour.purple(), description=names)
        await ctx.send(embed=emb)


def setup(bot):
    bot.add_cog(Twitch(bot))
