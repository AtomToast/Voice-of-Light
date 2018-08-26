import discord
from discord.ext import commands

import traceback
import sys
import logging
import asyncio
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

    elif isinstance(error, discord.errors.Forbidden):
        try:
            return await ctx.message.add_reaction("🔇")
        except Exception:
            pass

    print('Ignoring exception in command {}:'.format(ctx.command), file=sys.stderr)
    traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)


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
    try:
        await asyncio.wait_for(bot.pool.close(), 10.0)
    except asyncio.TimeoutError:
        await bot.pool.expire_connections()
        bot.pool.terminate()
    await bot.session.close()
    await bot.close()


@commands.is_owner()
@bot.command(hidden=True)
async def fetchguilds(ctx):
    async with bot.pool.acquire() as db:
        guilds_db = await db.fetch("SELECT ID FROM Guilds")
        guilds_bot = bot.guilds
        for g_bot in guilds_bot:
            for g_db in guilds_db:
                if g_db[0] == g_bot.id:
                    break
            else:
                await db.execute("INSERT INTO Guilds (ID, Name) VALUES ($1, $2)", g_bot.id, g_bot.name)
                print(f">> Joined {g_bot.name}")

    await ctx.send("Done fetching guilds!")


@commands.is_owner()
@bot.command(hidden=True)
async def announce(ctx, *, message):
    async with bot.pool.acquire() as db:
        guilds_db = await db.fetch("SELECT * FROM Guilds")
        for g in guilds_db:
            if g[2] is not None:
                channel = bot.get_channel(g[2])
            elif g[3] is not None:
                channel = bot.get_channel(g[3])
            elif g[4] is not None:
                channel = bot.get_channel(g[4])
            elif g[5] is not None:
                channel = bot.get_channel(g[5])
            else:
                guild = bot.get_guild(g[0])
                for ch in guild.text_channels:
                    bot_member = ctx.guild.get_member(bot.user.id)
                    permissions = ch.permissions_for(bot_member)
                    if permissions.send_messages:
                        await channel.send(message)
                        break

    await ctx.send("Announcement sent!")


if __name__ == "__main__":
    bot.pool = bot.loop.run_until_complete(asyncpg.create_pool(database="voiceoflightdb", loop=bot.loop, command_timeout=60))
    for ext in extensions:
        bot.load_extension(ext)
    bot.run(auth_token.discord)

# https://discordapp.com/api/oauth2/authorize?client_id=460410391290314752&scope=bot&permissions=19456
