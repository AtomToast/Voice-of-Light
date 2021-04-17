import discord
from discord.ext import commands

from datetime import datetime
import asyncio


class Utils(commands.Cog):
    """Utility commands"""

    def __init__(self, bot):
        self.bot = bot

        # self.svan_sleep_reminder = self.bot.loop.create_task(
        #     self.sleep_reminder())

    # who and where the commands are permitted to use
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    @commands.command()
    async def setchannel(self, ctx, channel=None):
        """Sets the standard channel to announce all the notifications in

        Note that if you want certain things announced in unique channels you have to set them seperately for those!
        e.g. ;surrenderat20 setchannel #surrender20-feed"""
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
            await db.execute("UPDATE Guilds SET SurrenderAt20NotifChannel=$1, TwitchNotifChannel=$2, YoutubeNotifChannel=$3, RedditNotifChannel=$4 WHERE ID=$5",
                             channel_obj.id, channel_obj.id, channel_obj.id, channel_obj.id, ctx.guild.id)

        await ctx.send("Successfully set all notifications to " + channel_obj.mention)

    @commands.command()
    async def invite(self, ctx):
        """Get the link for adding the bot to your own server"""
        await ctx.send("https://discordapp.com/api/oauth2/authorize?client_id=460410391290314752&scope=bot&permissions=19456")

    @commands.command(aliases=["about"])
    async def support(self, ctx):
        """How to support the bot and the dev"""
        emb = discord.Embed(title="Support/About",
                            color=discord.Colour.dark_blue())
        emb.description = "Maintaining and updating the bot takes alot of time. So any help and support, as smol as it might be, is greatly appreciated!"
        emb.add_field(name="Support via PayPal",
                      value="https://www.paypal.me/atomtoast", inline=False)
        emb.add_field(name="Contribute to Voice of Light on GitHub",
                      value="https://github.com/AtomToast/Voice-of-Light")
        await ctx.send(embed=emb)

    async def sleep_reminder(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            guild = self.bot.get_guild(213881169844895744)  # get sol mains
            svan = guild.get_member(146498809772507136)  # get svan
            tyochi = guild.get_member(291641665033207809)  # get Tyochi
            time = datetime.now().time()
            if time.hour < 6 and svan.status != discord.Status.offline:
                await svan.send("It's past midnight. You should be sleeping!")
                # await tyochi.send("Tyo, stop being a weeb and go the fuck to sleep")
            if time.hour > 23 and svan.status != discord.Status.offline:
                await svan.send("Are you aware of the time? It's almost bed o'clock!")
            await asyncio.sleep(15 * 60)


def setup(bot):
    bot.add_cog(Utils(bot))
