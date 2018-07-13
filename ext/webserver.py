import discord

from aiohttp import web
import auth_token
import aiosqlite
import xmltodict
import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler


class Webserver:
    """A webserver for handling notifications"""
    def __init__(self, bot):
        self.bot = bot

        # create the application and add routes
        self.app = web.Application()
        self.app.add_routes([web.get("/GOOGLE DOMAIN VERIFICATION FILE", self.googleverification)])
        self.app.add_routes([web.post("/youtube", self.youtube)])
        self.app.add_routes([web.get("/youtube", self.youtubeverification)])
        self.app.add_routes([web.post("/twitch", self.twitch)])
        self.app.add_routes([web.get("/twitch", self.twitchverification)])

        # push notification run out after a specified time so I need to refresh them regularly
        self.scheduler = AsyncIOScheduler(event_loop=self.bot.loop)
        self.scheduler.add_job(self.refresh_subscriptions, "interval", days=5, id="refresher", replace_existing=True)
        self.scheduler.start()

    # run the webserver
    async def run(self):
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner)
        await self.site.start()

    # will be called by the scheduler above
    # goes through all twitch and youtube channels in the database
    # and refresh their subscription
    async def refresh_subscriptions(self):
        async with aiosqlite.connect("data.db") as db:
            cursor = await db.execute("SELECT DISTINCT TwitchChannel FROM TwitchSubscriptions")
            async for row in cursor:
                ID = row[0]
                parsingChannelUrl = "https://api.twitch.tv/helix/webhooks/hub"
                parsingChannelHeader = {'Client-ID': auth_token.twitch}
                parsingChannelQueryString = {"hub.mode": "subscribe", "hub.callback": "CALLBACK URL/twitch",
                                             "hub.topic": "https://api.twitch.tv/helix/streams?user_id=" + ID, "hub.lease_seconds": 864000}
                async with self.bot.session.post(parsingChannelUrl, headers=parsingChannelHeader, params=parsingChannelQueryString) as resp:
                    if resp.status != 202:
                        print(resp.text)
            await cursor.close()

            cursor = await db.execute("SELECT DISTINCT YoutubeChannel FROM YoutubeSubscriptions")
            async for row in cursor:
                ID = row[0]
                parsingChannelUrl = "https://pubsubhubbub.appspot.com/subscribe"
                parsingChannelHeader = {'Client-ID': auth_token.twitch}
                parsingChannelQueryString = {"hub.mode": "subscribe", "hub.callback": "CALLBACK URL/youtube",
                                             "hub.topic": "https://www.youtube.com/xml/feeds/videos.xml?channel_id=" + ID, "hub.lease_seconds": 864000}
                async with self.bot.session.post(parsingChannelUrl, headers=parsingChannelHeader, params=parsingChannelQueryString) as resp:
                    if resp.status != 202:
                        print(resp.text)
            await cursor.close()

        print("Refreshed Subscriptions")

    # handler for post requests to the /youtube route
    async def youtube(self, request):
        obj = xmltodict.parse(await request.text())
        # to check if the notification is about a video being deleted
        try:
            # if the request contains a "at:deleted-entry" parameter it is
            # otherwise a keyerror is raised which will be ignored to continue on normally
            obj["feed"]["at:deleted-entry"]
            parsingChannelUrl = "https://www.googleapis.com/youtube/v3/channels"
            parsingChannelQueryString = {"part": "statistics", "id": obj["feed"]["at:deleted-entry"]["at:by"]["uri"].split("/")[-1], "maxResults": "1",
                                         "key": auth_token.google}
            async with self.bot.session.get(parsingChannelUrl, params=parsingChannelQueryString) as resp:
                ch = await resp.json()
            async with aiosqlite.connect("data.db") as db:
                await db.execute("UPDATE YoutubeChannels SET VideoCount=? WHERE ID=?", (int(ch["items"][0]["statistics"]["videoCount"]), ch["items"][0]["id"]))
                await db.commit()
            return web.Response()
        except KeyError:
            pass

        # getting the video data
        parsingChannelUrl = "https://www.googleapis.com/youtube/v3/videos"
        parsingChannelQueryString = {"part": "snippet", "id": obj["feed"]["entry"]["yt:videoId"], "maxResults": "1",
                                     "key": auth_token.google}
        async with self.bot.session.get(parsingChannelUrl, params=parsingChannelQueryString) as resp:
            v = await resp.json()
        if len(v["items"]) == 0:
            # video not found, probably deleted already
            return web.Response()
        video = v["items"][0]["snippet"]

        # getting channel data
        parsingChannelUrl = "https://www.googleapis.com/youtube/v3/channels"
        parsingChannelQueryString = {"part": "snippet,statistics", "id": video["channelId"], "maxResults": "1",
                                     "key": auth_token.google}
        async with self.bot.session.get(parsingChannelUrl, params=parsingChannelQueryString) as resp:
            ch = await resp.json()
        channel_obj = ch["items"][0]

        # creating message embed
        emb = discord.Embed(title=video["title"],
                            description=video["channelTitle"],
                            url=obj["feed"]["entry"]["link"]["@href"],
                            color=discord.Colour.red())
        emb.timestamp = datetime.datetime.now()
        emb.set_image(url=video["thumbnails"]["default"]["url"])
        emb.set_footer(icon_url=channel_obj["snippet"]["thumbnails"]["default"]["url"], text="Youtube")

        # check if it's a video or a livestream
        # if it is neither it is a livestream announcement which will be ignored
        if video["liveBroadcastContent"] == "none":
            announcement = "New Video live!"
        elif video["liveBroadcastContent"] == "live":
            announcement = video["channelTitle"] + " is now live!"
        else:
            return web.Response()

        async with aiosqlite.connect("data.db") as db:
            # if it is a livestream the bot shouldn't announce a livestream more than once in an hour
            # to keep channels from getting spammed from stream restarts
            if video["liveBroadcastContent"] == "live":
                cursor = await db.execute("SELECT LastLive FROM YoutubeChannels WHERE ID=?", (obj["feed"]["entry"]["yt:channelId"],))
                dt = await cursor.fetchall()
                await cursor.close()
                dt_str = dt[0][0]
                while len(dt_str.split("-")[0]) < 4:
                    dt_str = "0" + dt_str
                if (datetime.datetime.now() - datetime.datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')).total_seconds() > 60 * 60:
                    await db.execute("UPDATE YoutubeChannels SET LastLive=? WHERE ID=?", (datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), obj["feed"]["entry"]["yt:channelId"]))
                    await db.commit()
                else:
                    # stream was restarted
                    return web.Response()
            else:
                # youtube does not tell if the notification is about a new video
                # or edits to an old one
                # so this checks if it's a new video or just an edit
                cursor = await db.execute("SELECT LastVideoID, VideoCount FROM YoutubeChannels WHERE ID=?", (obj["feed"]["entry"]["yt:channelId"],))
                r = await cursor.fetchall()
                stats = r[0]
                await cursor.close()
                if obj["feed"]["entry"]["yt:videoId"] != stats[0] and int(channel_obj["statistics"]["videoCount"]) > stats[1]:
                    await db.execute("UPDATE YoutubeChannels SET LastVideoID=?, VideoCount=? WHERE ID=?",
                                     (obj["feed"]["entry"]["yt:videoId"], int(channel_obj["statistics"]["videoCount"]), obj["feed"]["entry"]["yt:channelId"]))
                    await db.commit()
                else:
                    # A video has been edited
                    return web.Response()

            # send messages in all subscribed servers
            cursor = await db.execute("SELECT Guilds.AnnounceChannelID, YoutubeSubscriptions.OnlyStreams \
                                       FROM YoutubeSubscriptions INNER JOIN Guilds \
                                       ON YoutubeSubscriptions.Guild=Guilds.ID \
                                       WHERE YoutubeChannel=?", (obj["feed"]["entry"]["yt:channelId"],))

            async for row in cursor:
                # if the server set the subscription to "Only streams"
                # videos will not be announced
                if row[1] == 1 and video["liveBroadcastContent"] == "none":
                    continue
                announceChannel = self.bot.get_channel(row[0])
                await announceChannel.send(announcement, embed=emb)

            await cursor.close()
        return web.Response()

    # handler for posts to the /twitch route
    async def twitch(self, request):
        obj = await request.json()
        # check if it's a "stream down" notification, it does not contain any content
        if len(obj["data"]) == 0:
            # stream down
            return web.Response()

        data = obj["data"][0]

        # getting channel data
        parsingChannelUrl = "https://api.twitch.tv/helix/users"
        parsingChannelHeader = {'Client-ID': auth_token.twitch}
        parsingChannelQueryString = {"id": data["user_id"]}
        async with self.bot.session.get(parsingChannelUrl, headers=parsingChannelHeader, params=parsingChannelQueryString) as resp:
            channel_obj = await resp.json()
        ch = channel_obj["data"][0]

        # getting game data
        parsingChannelUrl = "https://api.twitch.tv/helix/games"
        parsingChannelHeader = {'Client-ID': auth_token.twitch}
        parsingChannelQueryString = {"id": data["game_id"]}
        async with self.bot.session.get(parsingChannelUrl, headers=parsingChannelHeader, params=parsingChannelQueryString) as resp:
            game_obj = await resp.json()

        # variables for game information
        # if no game is specified a default will be chosen
        if len(game_obj["data"]) == 0:
            game_url = ""
            game_name = "a game"
        else:
            ga = game_obj["data"][0]
            game_url = ga["box_art_url"].format(width=300, height=300)
            game_name = ga["name"]

        # creation of the message embed
        emb = discord.Embed(title=data["title"],
                            description=ch["display_name"],
                            url="https://www.twitch.tv/" + ch["login"],
                            color=discord.Colour.purple())
        emb.timestamp = datetime.datetime.now()
        emb.set_image(url=data["thumbnail_url"].format(width=320, height=180))
        emb.set_footer(icon_url=ch["profile_image_url"], text="Twitch")
        emb.set_thumbnail(url=game_url)

        async with aiosqlite.connect("data.db") as db:
            # streams should only be announced every hour
            # to keep channels from getting spammed with stream restarts
            cursor = await db.execute("SELECT LastLive FROM TwitchChannels WHERE ID=?", (ch["id"],))
            dt = await cursor.fetchall()
            await cursor.close()
            dt_str = dt[0][0]
            while len(dt_str.split("-")[0]) < 4:
                dt_str = "0" + dt_str
            if (datetime.datetime.now() - datetime.datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')).total_seconds() > 60 * 60:
                await db.execute("UPDATE TwitchChannels SET LastLive=? WHERE ID=?", (datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), ch["id"]))
                await db.commit()
            else:
                # stream was restarted
                return web.Response()

            # sending messages to all subscribed servers
            cursor = await db.execute("SELECT Guilds.AnnounceChannelID \
                                       FROM TwitchSubscriptions INNER JOIN Guilds \
                                       ON TwitchSubscriptions.Guild=Guilds.ID \
                                       WHERE TwitchChannel=?", (data["user_id"],))

            async for row in cursor:
                announceChannel = self.bot.get_channel(row[0])
                await announceChannel.send(ch["display_name"] + " is now live with " + game_name + " !", embed=emb)

            await cursor.close()
        return web.Response()

    # various verification endpoints
    # will verify the url as my own to google
    async def googleverification(self, request):
        return web.Response(text="google-site-verification: " + auth_token.google_callback_verification)

    # will verify youtube subscriptions
    async def youtubeverification(self, request):
        return web.Response(text=request.query["hub.challenge"])

    # will verify twitch subscriptions
    async def twitchverification(self, request):
        return web.Response(text=request.query["hub.challenge"])


def setup(bot):
    bot.add_cog(Webserver(bot))
