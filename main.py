"""
Discord Server Bot — WeDoSoftware
===================================
Install dependencies first:
    pip install discord.py yt-dlp PyNaCl

You also need FFmpeg installed on your system:
    Windows: https://ffmpeg.org/download.html (add to PATH)
    Linux:   sudo apt install ffmpeg
    Mac:     brew install ffmpeg

Set your bot token as an environment variable before running:
    Windows CMD:        set DISCORD_TOKEN=your_token_here
    Windows PowerShell: $env:DISCORD_TOKEN="your_token_here"
    Linux/Mac:          export DISCORD_TOKEN=your_token_here

Then run:
    python bot.py

Running !setup will only ADD missing channels/roles — it will NOT
touch or delete anything that already exists on the server.
"""

import discord
from discord.ext import commands
import yt_dlp
import asyncio
import os

# ============================================================
#  CONFIG — edit everything here
# ============================================================

TOKEN = os.environ["DISCORD_TOKEN"]

# Your server (guild) ID
GUILD_ID = 1490663487565992028

# Command prefix (e.g. !kick, !play, !setup)
PREFIX = "!"

# New channels to add — existing channels are left untouched.
# "name": "topic"
# Channels already on the server (general, general-💬, important-links-🔗, Chill, General)
# will not be duplicated.
CHANNELS = {
    "welcome":       "Welcome to WeDoSoftware!",
    "rules":         "Read before you chat.",
    "announcements": "Company-wide announcements.",
    "music":         "Use music commands here.",
    "bot-commands":  "Use bot commands here.",
}

# New categories to create and which channels go inside them.
# Existing categories (Text Channels, Voice Channels, CAI) are left untouched.
CATEGORIES = {
    "INFO": ["welcome", "rules", "announcements"],
    "BOTS": ["music", "bot-commands"],
}

# Welcome message posted to #welcome when a new member joins.
# {user} = member mention
WELCOME_MESSAGE = """
Hey {user}, welcome to WeDoSoftware!
Check out the rules in #rules and feel free to introduce yourself in #general.
"""

# Rules posted to #rules during setup
RULES = [
    "Be respectful to all team members.",
    "Keep conversations in the appropriate channels.",
    "No spamming or unnecessary pings.",
    "No sharing of confidential project information outside designated channels.",
    "Follow Discord's Terms of Service.",
    "Listen to Admins and Project Managers.",
]

# Roles to create only if they do not already exist.
# Existing roles: @everyone, Devs, Admin, Project Manager, WeDoBot
# Only Muted and Member are missing — those will be created.
ROLES_TO_CREATE = [
    {
        "name": "Member",
        "color": discord.Color.light_grey(),
        "permissions": discord.Permissions.none(),
    },
    {
        "name": "Muted",
        "color": discord.Color.dark_gray(),
        "permissions": discord.Permissions.none(),
    },
]

# Role assigned automatically to new members on join
AUTO_ROLE_NAME = "Member"

# ============================================================
#  BOT SETUP
# ============================================================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# ============================================================
#  MUSIC — internal state per guild
# ============================================================

music_queues = {}  # guild_id -> list of (url, title)
music_volumes = {} # guild_id -> float (0.0 - 1.0)

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

# Resolve ffmpeg executable — checks common paths on Railway/Nix environments
import shutil
FFMPEG_EXECUTABLE = (
    shutil.which("ffmpeg")
    or "/usr/bin/ffmpeg"
    or "/nix/var/nix/profiles/default/bin/ffmpeg"
    or "ffmpeg"
)
print(f"FFmpeg path resolved to: {FFMPEG_EXECUTABLE}")

# Sources tried in order until one succeeds.
# Each entry is a dict of yt-dlp options with a "label" key for logging.
AUDIO_SOURCES = [
    {
        "label": "YouTube (browser spoof)",
        "format": "bestaudio/best",
        "noplaylist": True,
        "quiet": True,
        "default_search": "ytsearch",
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        },
        "extractor_args": {
            "youtube": {
                "player_client": ["web"],
            }
        },
    },
    {
        "label": "YouTube Music",
        "format": "bestaudio/best",
        "noplaylist": True,
        "quiet": True,
        "default_search": "https://music.youtube.com/search?q=",
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        },
    },
    {
        "label": "SoundCloud",
        "format": "bestaudio/best",
        "noplaylist": True,
        "quiet": True,
        "default_search": "scsearch",
    },
    {
        "label": "Bandcamp",
        "format": "bestaudio/best",
        "noplaylist": True,
        "quiet": True,
        "default_search": "ytsearch",  # fallback search, direct Bandcamp URLs work natively
    },
    {
        "label": "Deezer",
        "format": "bestaudio/best",
        "noplaylist": True,
        "quiet": True,
        "default_search": "deezersearch",
    },
    {
        "label": "YouTube (android client)",
        "format": "bestaudio/best",
        "noplaylist": True,
        "quiet": True,
        "default_search": "ytsearch",
        "extractor_args": {
            "youtube": {
                "player_client": ["android"],
            }
        },
    },
    {
        "label": "YouTube (ios client)",
        "format": "bestaudio/best",
        "noplaylist": True,
        "quiet": True,
        "default_search": "ytsearch",
        "extractor_args": {
            "youtube": {
                "player_client": ["ios"],
            }
        },
    },
    {
        "label": "YouTube (tv client)",
        "format": "bestaudio/best",
        "noplaylist": True,
        "quiet": True,
        "default_search": "ytsearch",
        "extractor_args": {
            "youtube": {
                "player_client": ["tv_embedded"],
            }
        },
    },
]


def get_queue(guild_id):
    if guild_id not in music_queues:
        music_queues[guild_id] = []
    return music_queues[guild_id]


async def fetch_audio(query):
    loop = asyncio.get_event_loop()
    last_error = None
    for source in AUDIO_SOURCES:
        label = source["label"]
        opts = {k: v for k, v in source.items() if k != "label"}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = await loop.run_in_executor(None, lambda: ydl.extract_info(query, download=False))
                if "entries" in info:
                    info = info["entries"][0]
                print(f"Audio fetched via: {label}")
                return info["url"], info.get("title", "Unknown")
        except Exception as e:
            print(f"Source [{label}] failed: {e}")
            last_error = e
            continue
    raise Exception(f"All sources failed. Last error: {last_error}")


def play_next(vc, guild_id):
    queue = get_queue(guild_id)
    if not queue:
        return
    url, title = queue.pop(0)
    volume = music_volumes.get(guild_id, 0.5)
    source = discord.PCMVolumeTransformer(
        discord.FFmpegPCMAudio(url, executable=FFMPEG_EXECUTABLE, **FFMPEG_OPTIONS),
        volume=volume,
    )
    vc.play(source, after=lambda e: play_next(vc, guild_id))


# ============================================================
#  EVENTS
# ============================================================

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print(f"Prefix: {PREFIX}")
    print("------")


@bot.event
async def on_member_join(member):
    guild = member.guild

    # Send welcome message
    welcome_ch = discord.utils.get(guild.text_channels, name="welcome")
    if welcome_ch:
        await welcome_ch.send(WELCOME_MESSAGE.format(user=member.mention))

    # Assign auto role
    role = discord.utils.get(guild.roles, name=AUTO_ROLE_NAME)
    if role:
        await member.add_roles(role)


# ============================================================
#  SETUP COMMAND — run once on a new server
# ============================================================

@bot.command(name="setup")
@commands.has_permissions(administrator=True)
async def setup(ctx):
    """Sets up channels, categories, roles, and posts rules. Run once."""
    guild = ctx.guild
    await ctx.send("Setting up server, please wait...")

    # Create roles
    existing_roles = {r.name for r in guild.roles}
    created_roles = {}
    for role_data in ROLES_TO_CREATE:
        if role_data["name"] not in existing_roles:
            r = await guild.create_role(
                name=role_data["name"],
                color=role_data["color"],
                permissions=role_data["permissions"],
            )
            created_roles[role_data["name"]] = r
            print(f"Created role: {role_data['name']}")

    # Deny send messages for Muted role in all channels
    muted_role = discord.utils.get(guild.roles, name="Muted") or created_roles.get("Muted")

    # Create categories and channels
    for category_name, channel_names in CATEGORIES.items():
        existing_cat = discord.utils.get(guild.categories, name=category_name)
        category = existing_cat or await guild.create_category(category_name)

        for ch_name in channel_names:
            existing_ch = discord.utils.get(guild.text_channels, name=ch_name)
            if not existing_ch:
                overwrites = {}
                if muted_role:
                    overwrites[muted_role] = discord.PermissionOverwrite(send_messages=False)

                # Make welcome/rules/announcements read-only for @everyone
                if ch_name in ("welcome", "rules", "announcements"):
                    overwrites[guild.default_role] = discord.PermissionOverwrite(send_messages=False)

                await guild.create_text_channel(
                    ch_name,
                    category=category,
                    topic=CHANNELS.get(ch_name, ""),
                    overwrites=overwrites,
                )
                print(f"Created channel: #{ch_name}")

    # Post rules
    rules_ch = discord.utils.get(guild.text_channels, name="rules")
    if rules_ch:
        rules_text = "**Server Rules**\n\n" + "\n".join(
            f"**{i+1}.** {rule}" for i, rule in enumerate(RULES)
        )
        await rules_ch.purge(limit=10)
        await rules_ch.send(rules_text)

    await ctx.send("Server setup complete.")


# ============================================================
#  MODERATION COMMANDS
# ============================================================

@bot.command(name="kick")
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="No reason provided"):
    """Kick a member. Usage: !kick @user reason"""
    await member.kick(reason=reason)
    await ctx.send(f"{member} was kicked. Reason: {reason}")


@bot.command(name="ban")
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="No reason provided"):
    """Ban a member. Usage: !ban @user reason"""
    await member.ban(reason=reason)
    await ctx.send(f"{member} was banned. Reason: {reason}")


@bot.command(name="unban")
@commands.has_permissions(ban_members=True)
async def unban(ctx, *, username):
    """Unban a user by username#discriminator. Usage: !unban user#1234"""
    bans = [entry async for entry in ctx.guild.bans()]
    for ban_entry in bans:
        if str(ban_entry.user) == username:
            await ctx.guild.unban(ban_entry.user)
            await ctx.send(f"Unbanned {ban_entry.user}.")
            return
    await ctx.send(f"No banned user found with name: {username}")


@bot.command(name="mute")
@commands.has_permissions(manage_roles=True)
async def mute(ctx, member: discord.Member, *, reason="No reason provided"):
    """Mute a member. Usage: !mute @user reason"""
    muted_role = discord.utils.get(ctx.guild.roles, name="Muted")
    if not muted_role:
        await ctx.send('No "Muted" role found. Run !setup first.')
        return
    await member.add_roles(muted_role, reason=reason)
    await ctx.send(f"{member} has been muted. Reason: {reason}")


@bot.command(name="unmute")
@commands.has_permissions(manage_roles=True)
async def unmute(ctx, member: discord.Member):
    """Unmute a member. Usage: !unmute @user"""
    muted_role = discord.utils.get(ctx.guild.roles, name="Muted")
    if muted_role in member.roles:
        await member.remove_roles(muted_role)
        await ctx.send(f"{member} has been unmuted.")
    else:
        await ctx.send(f"{member} is not muted.")


@bot.command(name="purge")
@commands.has_permissions(manage_messages=True)
async def purge(ctx, amount: int):
    """Delete a number of messages. Usage: !purge 10"""
    if amount < 1 or amount > 100:
        await ctx.send("Amount must be between 1 and 100.")
        return
    await ctx.channel.purge(limit=amount + 1)
    msg = await ctx.send(f"Deleted {amount} messages.")
    await asyncio.sleep(3)
    await msg.delete()


@bot.command(name="addrole")
@commands.has_permissions(manage_roles=True)
async def addrole(ctx, member: discord.Member, *, role_name):
    """Give a role to a member. Usage: !addrole @user RoleName"""
    role = discord.utils.get(ctx.guild.roles, name=role_name)
    if not role:
        await ctx.send(f'Role "{role_name}" not found.')
        return
    await member.add_roles(role)
    await ctx.send(f"Gave {role.name} to {member}.")


@bot.command(name="removerole")
@commands.has_permissions(manage_roles=True)
async def removerole(ctx, member: discord.Member, *, role_name):
    """Remove a role from a member. Usage: !removerole @user RoleName"""
    role = discord.utils.get(ctx.guild.roles, name=role_name)
    if not role:
        await ctx.send(f'Role "{role_name}" not found.')
        return
    await member.remove_roles(role)
    await ctx.send(f"Removed {role.name} from {member}.")


@bot.command(name="userinfo")
async def userinfo(ctx, member: discord.Member = None):
    """Show info about a user. Usage: !userinfo @user"""
    member = member or ctx.author
    embed = discord.Embed(title=str(member), color=member.color)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="ID", value=member.id)
    embed.add_field(name="Joined Server", value=member.joined_at.strftime("%Y-%m-%d"))
    embed.add_field(name="Account Created", value=member.created_at.strftime("%Y-%m-%d"))
    roles = [r.name for r in member.roles if r.name != "@everyone"]
    embed.add_field(name="Roles", value=", ".join(roles) or "None", inline=False)
    await ctx.send(embed=embed)


@bot.command(name="serverinfo")
async def serverinfo(ctx):
    """Show server info. Usage: !serverinfo"""
    guild = ctx.guild
    embed = discord.Embed(title=guild.name, color=discord.Color.blurple())
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(name="Members", value=guild.member_count)
    embed.add_field(name="Channels", value=len(guild.text_channels))
    embed.add_field(name="Roles", value=len(guild.roles))
    embed.add_field(name="Created", value=guild.created_at.strftime("%Y-%m-%d"))
    await ctx.send(embed=embed)


# ============================================================
#  MUSIC COMMANDS
# ============================================================

@bot.command(name="join")
async def join(ctx):
    """Join your voice channel. Usage: !join"""
    if not ctx.author.voice:
        await ctx.send("You need to be in a voice channel first.")
        return
    vc = ctx.voice_client
    if vc:
        await vc.move_to(ctx.author.voice.channel)
    else:
        await ctx.author.voice.channel.connect()
    await ctx.send(f"Joined {ctx.author.voice.channel.name}.")


@bot.command(name="leave")
async def leave(ctx):
    """Leave the voice channel. Usage: !leave"""
    if ctx.voice_client:
        get_queue(ctx.guild.id).clear()
        await ctx.voice_client.disconnect()
        await ctx.send("Disconnected.")
    else:
        await ctx.send("Not in a voice channel.")


@bot.command(name="play")
async def play(ctx, *, query):
    """Play a song by name or URL. Usage: !play never gonna give you up"""
    if not ctx.author.voice:
        await ctx.send("Join a voice channel first.")
        return

    vc = ctx.voice_client
    if not vc:
        vc = await ctx.author.voice.channel.connect()

    await ctx.send(f"Searching for: {query}")
    try:
        url, title = await fetch_audio(query)
    except Exception as e:
        await ctx.send(f"Could not find audio: {e}")
        return

    queue = get_queue(ctx.guild.id)

    if vc.is_playing() or vc.is_paused():
        queue.append((url, title))
        await ctx.send(f"Added to queue: **{title}** (position {len(queue)})")
    else:
        queue.append((url, title))
        play_next(vc, ctx.guild.id)
        await ctx.send(f"Now playing: **{title}**")


@bot.command(name="skip")
async def skip(ctx):
    """Skip the current song. Usage: !skip"""
    vc = ctx.voice_client
    if vc and vc.is_playing():
        vc.stop()
        await ctx.send("Skipped.")
    else:
        await ctx.send("Nothing is playing.")


@bot.command(name="stop")
async def stop(ctx):
    """Stop music and clear the queue. Usage: !stop"""
    vc = ctx.voice_client
    if vc:
        get_queue(ctx.guild.id).clear()
        vc.stop()
        await ctx.send("Stopped and queue cleared.")
    else:
        await ctx.send("Not playing anything.")


@bot.command(name="pause")
async def pause(ctx):
    """Pause the current song. Usage: !pause"""
    vc = ctx.voice_client
    if vc and vc.is_playing():
        vc.pause()
        await ctx.send("Paused.")
    else:
        await ctx.send("Nothing is playing.")


@bot.command(name="resume")
async def resume(ctx):
    """Resume a paused song. Usage: !resume"""
    vc = ctx.voice_client
    if vc and vc.is_paused():
        vc.resume()
        await ctx.send("Resumed.")
    else:
        await ctx.send("Nothing is paused.")


@bot.command(name="volume")
async def volume(ctx, vol: int):
    """Set music volume 0-100. Usage: !volume 50"""
    if not 0 <= vol <= 100:
        await ctx.send("Volume must be between 0 and 100.")
        return
    music_volumes[ctx.guild.id] = vol / 100
    vc = ctx.voice_client
    if vc and vc.source:
        vc.source.volume = vol / 100
    await ctx.send(f"Volume set to {vol}%.")


@bot.command(name="queue")
async def show_queue(ctx):
    """Show the music queue. Usage: !queue"""
    queue = get_queue(ctx.guild.id)
    vc = ctx.voice_client
    if not queue and (not vc or not vc.is_playing()):
        await ctx.send("Queue is empty.")
        return
    lines = [f"**{i+1}.** {title}" for i, (_, title) in enumerate(queue)]
    header = "**Now playing** (use !skip to skip)\n" if vc and vc.is_playing() else ""
    await ctx.send(header + "\n".join(lines) if lines else header + "No songs queued.")


# ============================================================
#  GENERAL COMMANDS
# ============================================================

@bot.command(name="ping")
async def ping(ctx):
    """Check bot latency. Usage: !ping"""
    await ctx.send(f"Pong! Latency: {round(bot.latency * 1000)}ms")


@bot.command(name="announce")
@commands.has_permissions(manage_messages=True)
async def announce(ctx, *, message):
    """Post an announcement in #announcements. Usage: !announce some message"""
    ch = discord.utils.get(ctx.guild.text_channels, name="announcements")
    if not ch:
        await ctx.send("No #announcements channel found. Run !setup first.")
        return
    embed = discord.Embed(description=message, color=discord.Color.gold())
    embed.set_footer(text=f"Posted by {ctx.author}")
    await ch.send(embed=embed)
    await ctx.message.delete()


@bot.command(name="commands")
async def list_commands(ctx):
    """List all available commands."""
    embed = discord.Embed(title="Bot Commands", color=discord.Color.blurple())
    embed.add_field(name="Setup", value="`!setup`", inline=False)
    embed.add_field(name="Moderation", value=(
        "`!kick @user [reason]`\n"
        "`!ban @user [reason]`\n"
        "`!unban user#1234`\n"
        "`!mute @user [reason]`\n"
        "`!unmute @user`\n"
        "`!purge <amount>`\n"
        "`!addrole @user RoleName`\n"
        "`!removerole @user RoleName`"
    ), inline=False)
    embed.add_field(name="Info", value=(
        "`!userinfo [@user]`\n"
        "`!serverinfo`\n"
        "`!ping`"
    ), inline=False)
    embed.add_field(name="Music", value=(
        "`!join`\n"
        "`!leave`\n"
        "`!play <name or URL>`\n"
        "`!skip`\n"
        "`!stop`\n"
        "`!pause`\n"
        "`!resume`\n"
        "`!volume <0-100>`\n"
        "`!queue`"
    ), inline=False)
    embed.add_field(name="Utility", value=(
        "`!announce <message>`\n"
        "`!commands`"
    ), inline=False)
    await ctx.send(embed=embed)


# ============================================================
#  ERROR HANDLING
# ============================================================

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You don't have permission to use that command.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("Member not found.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Missing argument. Use `{PREFIX}commands` to see usage.")
    elif isinstance(error, commands.CommandNotFound):
        pass  # Silently ignore unknown commands
    else:
        await ctx.send(f"An error occurred: {error}")
        raise error


# ============================================================
#  RUN
# ============================================================

bot.run(TOKEN)