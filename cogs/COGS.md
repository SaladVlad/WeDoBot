# WeDoSoftware Bot — Cog Development Guide

Cogs are Python modules that add commands to the bot without requiring a redeployment.
You write a `.py` file, upload it to Discord, and the commands are live immediately.

---

## How to Upload a Cog

1. Write your cog file (see structure below).
2. In any Discord channel, type `/uploadcog` and **attach your `.py` file** to the message.
3. The bot saves the file, loads it, and syncs the slash commands instantly.
4. To update an existing cog, upload a file with the **same filename** — it auto-reloads.

### Other cog management commands

| Command | Description |
|---|---|
| `/uploadcog` | Upload and load a cog (attach `.py` file) |
| `/loadcog <name>` | Load a cog by filename (without `.py`) |
| `/unloadcog <name>` | Unload a cog without deleting it |
| `/reloadcog <name>` | Reload a cog after editing it manually |
| `/listcogs` | List all currently loaded cogs |

---

## Cog File Structure

Every cog follows the same structure. Copy this template as a starting point.

```python
import discord
from discord.ext import commands


class MyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="commandname", description="What this command does.")
    async def commandname(self, ctx):
        await ctx.send("Hello!")


# Required — Discord.py calls this to register your cog
async def setup(bot):
    await bot.add_cog(MyCog(bot))
```

**Rules:**
- The class can be named anything, but must extend `commands.Cog`.
- The `setup(bot)` function at the bottom is required — do not leave it out.
- Use `hybrid_command` so the command works as both `/command` and `!command`.
- Each command name must be unique across all loaded cogs.

---

## Command Types

### Basic command — no arguments

```python
@commands.hybrid_command(name="hello", description="Say hello.")
async def hello(self, ctx):
    await ctx.send(f"Hello, {ctx.author.mention}!")
```

### Command with arguments

```python
@commands.hybrid_command(name="greet", description="Greet a user.")
async def greet(self, ctx, member: discord.Member):
    await ctx.send(f"Hey {member.mention}!")
```

### Command with an optional argument

```python
@commands.hybrid_command(name="greet", description="Greet a user.")
async def greet(self, ctx, member: discord.Member = None):
    target = member or ctx.author
    await ctx.send(f"Hey {target.mention}!")
```

### Command with a text argument (catches multiple words)

```python
@commands.hybrid_command(name="say", description="Make the bot say something.")
async def say(self, ctx, *, message: str):
    await ctx.send(message)
```

### Command that requires a permission

```python
@commands.hybrid_command(name="cleanup", description="Delete messages.")
@commands.has_permissions(manage_messages=True)
async def cleanup(self, ctx):
    await ctx.channel.purge(limit=10)
    await ctx.send("Done.", ephemeral=True)
```

Common permissions: `administrator`, `manage_messages`, `manage_roles`, `kick_members`, `ban_members`.

---

## Sending Responses

### Plain message

```python
await ctx.send("Hello!")
```

### Ephemeral (only visible to the user who ran the command)

```python
await ctx.send("Only you can see this.", ephemeral=True)
```

### Embed

```python
embed = discord.Embed(
    title="My Embed",
    description="Some text here.",
    color=discord.Color.blurple()
)
embed.add_field(name="Field", value="Value", inline=False)
embed.set_footer(text="Footer text")
await ctx.send(embed=embed)
```

### With a button

```python
class MyView(discord.ui.View):
    @discord.ui.button(label="Click me", style=discord.ButtonStyle.primary)
    async def click(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("You clicked!", ephemeral=True)

await ctx.send("Here is a button:", view=MyView())
```

---

## Using Bot State

You can access the bot and guild from within any command:

```python
guild   = ctx.guild                          # the server
channel = ctx.channel                        # current channel
author  = ctx.author                         # who ran the command
bot     = self.bot                           # the bot instance

# Find a channel by name
ch = discord.utils.get(guild.text_channels, name="general")

# Find a role by name
role = discord.utils.get(guild.roles, name="Admin")

# Find a member by ID
member = guild.get_member(123456789)
```

---

## Background Tasks

If your cog needs to run something on a schedule (e.g. every 10 minutes):

```python
from discord.ext import commands, tasks


class MyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.my_task.start()  # start the task when the cog loads

    def cog_unload(self):
        self.my_task.cancel()  # stop the task when the cog unloads

    @tasks.loop(minutes=10)
    async def my_task(self):
        channel = self.bot.get_channel(YOUR_CHANNEL_ID_HERE)
        if channel:
            await channel.send("10 minutes have passed.")


async def setup(bot):
    await bot.add_cog(MyCog(bot))
```

---

## Restricting Cog Commands to Specific Roles

After uploading a cog, use the permission system to restrict who can run its commands:

```
/permit <command_name> @Role
```

Example — only allow Admins to use `/cleanup`:
```
/permit cleanup @Admin
```

To remove the restriction:
```
/unpermit cleanup @Admin
```

To see all current restrictions:
```
/permissions
```

---

## Full Example Cog

```python
"""
Poll Cog — creates a simple yes/no poll with buttons.
Upload via: /uploadcog
"""

import discord
from discord.ext import commands


class PollView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.votes = {"yes": 0, "no": 0}

    @discord.ui.button(label="Yes 0", style=discord.ButtonStyle.success, emoji="✅")
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.votes["yes"] += 1
        button.label = f"Yes {self.votes['yes']}"
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="No 0", style=discord.ButtonStyle.danger, emoji="❌")
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.votes["no"] += 1
        button.label = f"No {self.votes['no']}"
        await interaction.response.edit_message(view=self)


class PollCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="poll", description="Create a yes/no poll.")
    async def poll(self, ctx, *, question: str):
        embed = discord.Embed(
            title="Poll",
            description=question,
            color=discord.Color.blurple()
        )
        embed.set_footer(text=f"Asked by {ctx.author.display_name}")
        await ctx.send(embed=embed, view=PollView())


async def setup(bot):
    await bot.add_cog(PollCog(bot))
```

---

## Common Mistakes

**Missing `async def setup(bot)`** — the bot will fail to load the cog with no useful error.

**Command name already taken** — if another loaded cog uses the same command name, loading will fail. Use `/listcogs` and `/unloadcog` to remove the conflicting one first.

**Forgetting `self`** — all methods inside a Cog class must have `self` as the first parameter before `ctx`.

**Using `ctx.send` inside a button callback** — inside `discord.ui.Button` callbacks you receive an `interaction`, not a `ctx`. Use `interaction.response.send_message(...)` instead.
