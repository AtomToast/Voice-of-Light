import discord
from discord.ext import commands

import logging
import aiosqlite
import auth_token
import aiohttp


# set up logging
logger = logging.getLogger('discord')
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(
    filename='discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter(
    '%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)


# setting up bot instance
description = "A bot that posts videos and streams.\n\nFor feedback and suggestions contact AtomToast#9642"
extensions = ["ext.youtube", "ext.twitch", "ext.reddit", "ext.utils", "ext.webserver", "ext.surrendernow"]

bot = commands.Bot(command_prefix=commands.when_mentioned_or(';'), description=description, activity=discord.Game(";help"))

bot.session = aiohttp.ClientSession(loop=bot.loop)


@bot.event
async def on_ready():
    print('Logged in as')
    print(bot.user.name)
    print(bot.user.id)
    print('------')


# add new guilds to database
@bot.event
async def on_guild_join(guild):
    async with aiosqlite.connect("data.db") as db:
        await db.execute("INSERT INTO Guilds (ID, Name) VALUES (?, ?)", (guild.id, guild.name))
        await db.commit()
    print(f">> Joined {guild.name}")


# remove guild data when leaving guilds
@bot.event
async def on_guild_remove(guild):
    async with aiosqlite.connect("data.db") as db:
        await db.execute("DELETE FROM Guilds WHERE ID=?", (guild.id,))
        await db.execute("DELETE FROM YoutubeSubscriptions WHERE Guild=?", (guild.id,))
        await db.execute("DELETE FROM TwitchSubscriptions WHERE Guild=?", (guild.id,))
        await db.execute("DELETE FROM SubredditSubscriptions WHERE Guild=?", (guild.id,))
        await db.execute("DELETE FROM Keywords WHERE Guild=?", (guild.id,))
        await db.commit()
    print(f"<< Left {guild.name}")


# bot shutdown
@commands.is_owner()
@bot.command(hidden=True)
async def kill(ctx):
    await ctx.send(":(")
    ws = bot.get_cog("Webserver")
    await ws.site.stop()
    await ws.runner.cleanup()
    rd = bot.get_cog("Reddit")
    rd.reddit_poller.cancel()
    await bot.session.close()
    await bot.close()


if __name__ == "__main__":
    for ext in extensions:
        bot.load_extension(ext)
    bot.run(auth_token.discord)

# https://discordapp.com/api/oauth2/authorize?client_id=460410391290314752&scope=bot&permissions=19456
