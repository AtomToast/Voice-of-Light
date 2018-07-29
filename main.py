import discord
from discord.ext import commands

import traceback
import sys
import logging
import asyncpg
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
extensions = ["ext.youtube", "ext.twitch", "ext.reddit", "ext.utils", "ext.webserver", "ext.surrenderat20"]

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
    async with bot.pool.acquire() as db:
        await db.execute("INSERT INTO Guilds (ID, Name) VALUES ($1, $2)", guild.id, guild.name)
    print(f">> Joined {guild.name}")


# remove guild data when leaving guilds
@bot.event
async def on_guild_remove(guild):
    async with bot.pool.acquire() as db:
        await db.execute("DELETE FROM Guilds WHERE ID=$1", guild.id)
        await db.execute("DELETE FROM YoutubeSubscriptions WHERE Guild=$1", guild.id)
        await db.execute("DELETE FROM TwitchSubscriptions WHERE Guild=$1", guild.id)
        await db.execute("DELETE FROM SubredditSubscriptions WHERE Guild=$1", guild.id)
        await db.execute("DELETE FROM Keywords WHERE Guild=$1", guild.id)
        await db.execute("DELETE FROM SurrenderAt20Subscriptions WHERE Guild=$1", guild.id)
    print(f"<< Left {guild.name}")


@bot.event
async def on_command_error(ctx, error):
    # This prevents any commands with local handlers being handled here in on_command_error.
    if hasattr(ctx.command, 'on_error'):
        return

    ignored = (commands.CommandNotFound, commands.UserInputError)

    # Allows us to check for original exceptions raised and sent to CommandInvokeError.
    # If nothing is found. We keep the exception passed to on_command_error.
    error = getattr(error, 'original', error)

    # Anything in ignored will return and prevent anything happening.
    if isinstance(error, ignored):
        return

    elif isinstance(error, commands.NoPrivateMessage):
        try:
            return await ctx.author.send(f'{ctx.command} can not be used in Private Messages.')
        except Exception:
            pass

    elif isinstance(error, commands.MissingPermissions):
        try:
            return await ctx.author.send('You lack permissions for this this command.')
        except Exception:
            pass

    elif isinstance(error, commands.BotMissingPermissions):
        try:
            return await ctx.author.send("The bot lacks the permissions: " + " ".join(error.missing_perms))
        except Exception:
            pass

    print('Ignoring exception in command {}:'.format(ctx.command), file=sys.stderr)
    traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)


# bot shutdown
@commands.is_owner()
@bot.command(hidden=True)
async def kill(ctx):
    await ctx.send(":(")
    await bot.pool.close()
    ws = bot.get_cog("Webserver")
    await ws.site.stop()
    await ws.runner.cleanup()
    rd = bot.get_cog("Reddit")
    rd.reddit_poller.cancel()
    await bot.session.close()
    await bot.close()


if __name__ == "__main__":
    bot.pool = bot.loop.run_until_complete(asyncpg.create_pool(database="voiceoflightdb", loop=bot.loop, command_timeout=60))
    for ext in extensions:
        bot.load_extension(ext)
    bot.run(auth_token.discord)

# https://discordapp.com/api/oauth2/authorize?client_id=460410391290314752&scope=bot&permissions=19456
