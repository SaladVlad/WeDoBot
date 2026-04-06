"""
Example Cog — WeDoSoftware Bot
================================
This is a template for writing new commands without redeploying.

How to use:
1. Write your commands in this file following the pattern below.
2. In Discord, attach this file to a message and run: !uploadcog
3. Commands are available instantly. No restart needed.
4. To update: edit the file and run !uploadcog again — it auto-reloads.

You can restrict who uses these commands with:
    !permit <command_name> @Role
"""

import discord
from discord.ext import commands


class ExampleCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Basic hybrid command (works as both !hello and /hello)
    @commands.hybrid_command(name="hello", description="Say hello.")
    async def hello(self, ctx):
        await ctx.send(f"Hello, {ctx.author.mention}!")

    # Command with an argument
    @commands.hybrid_command(name="say", description="Make the bot say something.")
    @commands.has_permissions(manage_messages=True)
    async def say(self, ctx, *, message: str):
        await ctx.message.delete()
        await ctx.send(message)

    # Command with an embed response
    @commands.hybrid_command(name="info", description="Show some custom info.")
    async def info(self, ctx):
        embed = discord.Embed(
            title="Custom Info",
            description="This command was loaded from a cog.",
            color=discord.Color.green()
        )
        embed.add_field(name="Cog", value="example_cog")
        await ctx.send(embed=embed)


# This function is required — Discord.py calls it to load the cog
async def setup(bot):
    await bot.add_cog(ExampleCog(bot))
