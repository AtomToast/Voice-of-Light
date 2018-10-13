import discord
from discord.ext import commands

import auth_token
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

    @twitch.command()
    async def setchannel(self, ctx, channel=None):
        """Sets the channel to announce Twitch streams in"""
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

        async with self.bot.pool.acquire() as db:
            # add channel id for the guild to the database
            await db.execute("UPDATE Guilds SET TwitchNotifChannel=$1 WHERE ID=$2",
                             channel_obj.id, ctx.guild.id)

        await ctx.send("Successfully set Twitch notifications to " + channel_obj.mention)

    @twitch.command(aliases=["sub"])
    async def subscribe(self, ctx, *, channel=None):
        """Subscribes to a channel

        Its livestreams will be announced in the specified channel"""
        async with self.bot.pool.acquire() as db:
            # check if announcement channel is set up
            rows = await db.fetch("SELECT TwitchNotifChannel FROM Guilds WHERE ID=$1", ctx.guild.id)
            if len(rows) == 0 or rows[0][0] is None:
                await ctx.send("You need to set up a notifications channel before subscribing! \nUse either ;setchannel or ;surrenderat20 setchannel")
                return

        if channel is None:
            await ctx.send("You need to specify a channel to subscribe to")
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

        async with self.bot.pool.acquire() as db:
            # check if twitch channel is already in database
            # otherwise add it
            results = await db.fetch("SELECT 1 FROM TwitchChannels WHERE ID=$1", channel_id)
            if len(results) == 0:
                dt = datetime.datetime.min
                dt_aware = dt.replace(tzinfo=datetime.timezone.utc)
                await db.execute("INSERT INTO TwitchChannels (ID, Name, LastLive) VALUES ($1, $2, $3)",
                                 channel_id, channel_name, dt_aware)

            # insert subscription into database
            results = await db.fetch("SELECT 1 FROM TwitchSubscriptions WHERE TwitchChannel=$1 AND Guild=$2", channel_id, ctx.guild.id)
            if len(results) == 0:
                await db.execute("INSERT INTO TwitchSubscriptions (TwitchChannel, Guild) VALUES ($1, $2)", channel_id, ctx.guild.id)
            else:
                await ctx.send("You are already subscribed to this channel")
                return

        # send twitch subscription request
        parsingChannelUrl = "https://api.twitch.tv/helix/webhooks/hub"
        parsingChannelHeader = {'Client-ID': auth_token.twitch}
        parsingChannelQueryString = {"hub.mode": "subscribe", "hub.callback": auth_token.server_url + "/twitch",
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

        async with self.bot.pool.acquire() as db:
            # check if server is subscribed to channel
            # remove subscription
            results = await db.fetch("SELECT 1 FROM TwitchSubscriptions WHERE TwitchChannel=$1 AND Guild=$2", channel_id, ctx.guild.id)
            if len(results) == 1:
                await db.execute("DELETE FROM TwitchSubscriptions WHERE TwitchChannel=$1 AND Guild=$2", channel_id, ctx.guild.id)
            else:
                await ctx.send("You are not subscribed to this channel")
                return

            # remove channel from database if no server is subscribed to it anymore
            results = await db.fetch("SELECT 1 FROM TwitchSubscriptions WHERE TwitchChannel=$1", channel_id)
            if len(results) == 0:
                await db.execute("DELETE FROM TwitchChannels WHERE ID=$1", channel_id)

        # send unsubscribe request
        parsingChannelUrl = "https://api.twitch.tv/helix/webhooks/hub"
        parsingChannelHeader = {'Client-ID': auth_token.twitch}
        parsingChannelQueryString = {"hub.mode": "unsubscribe", "hub.callback": auth_token.server_url + "/twitch",
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
        async with self.bot.pool.acquire() as db:
            cursor = await db.fetch("SELECT TwitchChannels.Name \
                                       FROM TwitchSubscriptions INNER JOIN TwitchChannels \
                                       ON TwitchSubscriptions.TwitchChannel=TwitchChannels.ID \
                                       WHERE Guild=$1", ctx.guild.id)

            for row in cursor:
                names = names + row[0] + "\n"

        emb = discord.Embed(title="Twitch subscriptions", color=discord.Colour.purple(), description=names)
        await ctx.send(embed=emb)


def setup(bot):
    bot.add_cog(Twitch(bot))
