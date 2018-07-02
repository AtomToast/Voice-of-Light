import discord
from discord.ext import commands

import aiosqlite


class Utils:
    """Utility commands"""
    def __init__(self, bot):
        self.bot = bot

    # who and where the commands are permitted to use
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    @commands.command()
    async def setchannel(self, ctx, channel=None):
        """Sets the channel to announce the notifications in"""
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

        async with aiosqlite.connect("data.db") as db:
            # add channel id for the guild to the database
            await db.execute("UPDATE Guilds SET AnnounceChannelID=? WHERE ID=?", (channel_obj.id, ctx.guild.id))
            await db.commit()

        await ctx.send("Successfully set notifications channel to " + channel_obj.mention)

    @commands.command()
    async def invite(self, ctx):
        """Get the link for adding the bot to your own server"""
        await ctx.send("https://discordapp.com/api/oauth2/authorize?client_id=460410391290314752&scope=bot&permissions=19456")


def setup(bot):
    bot.add_cog(Utils(bot))
