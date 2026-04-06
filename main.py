"""
WeDoSoftware Discord Bot
========================
Install dependencies:
    pip install discord.py yt-dlp PyNaCl

Set env var before running:
    PowerShell: $env:DISCORD_TOKEN="your_token"
    Linux/Mac:  export DISCORD_TOKEN=your_token

Then: python main.py

Cogs go in the ./cogs/ folder. Upload via !uploadcog (attach .py file).
Slash commands sync automatically on startup.
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
import yt_dlp
import asyncio
import os
import shutil
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ============================================================
#  CONFIG
# ============================================================

TOKEN    = os.environ["DISCORD_TOKEN"]
GUILD_ID = 1490663487565992028
PREFIX   = "!"

CHANNELS = {
    "welcome":       "Welcome to WeDoSoftware!",
    "rules":         "Read before you chat.",
    "announcements": "Company-wide announcements.",
    "music":         "Use music commands here.",
    "bot-commands":  "Use bot commands here.",
}

CATEGORIES = {
    "INFO": ["welcome", "rules", "announcements"],
    "BOTS": ["music", "bot-commands"],
}

WELCOME_MESSAGE = (
    "Hey {user}, welcome to WeDoSoftware!\n"
    "Check out the rules in #rules and feel free to introduce yourself in #general."
)

RULES = [
    "Be respectful to all team members.",
    "Keep conversations in the appropriate channels.",
    "No spamming or unnecessary pings.",
    "No sharing of confidential project information outside designated channels.",
    "Follow Discord's Terms of Service.",
    "Listen to Admins and Project Managers.",
]

ROLES_TO_CREATE = [
    {"name": "Member", "color": discord.Color.light_grey(), "permissions": discord.Permissions.none()},
    {"name": "Muted",  "color": discord.Color.dark_gray(),  "permissions": discord.Permissions.none()},
]

AUTO_ROLE_NAME = "Member"

# ============================================================
#  PERMISSION SYSTEM
# Stores: command_name -> list of role IDs allowed to use it
# Empty list = everyone can use it
# ============================================================

PERMISSIONS_FILE = "permissions.json"

def load_permissions():
    if os.path.exists(PERMISSIONS_FILE):
        with open(PERMISSIONS_FILE) as f:
            return json.load(f)
    return {}

def save_permissions(data):
    with open(PERMISSIONS_FILE, "w") as f:
        json.dump(data, f, indent=2)

command_permissions = load_permissions()

def has_command_permission():
    async def predicate(ctx):
        cmd = ctx.command.name
        allowed_roles = command_permissions.get(cmd, [])
        if not allowed_roles:
            return True  # no restriction set, everyone can use it
        return any(str(r.id) in allowed_roles for r in ctx.author.roles)
    return commands.check(predicate)

# ============================================================
#  AUTO-DELETE SYSTEM
# Stores: channel_id -> seconds
# ============================================================

AUTODELETE_FILE = "autodelete.json"

def load_autodelete():
    if os.path.exists(AUTODELETE_FILE):
        with open(AUTODELETE_FILE) as f:
            return {int(k): v for k, v in json.load(f).items()}
    return {}

def save_autodelete(data):
    with open(AUTODELETE_FILE, "w") as f:
        json.dump({str(k): v for k, v in data.items()}, f, indent=2)

autodelete_channels = load_autodelete()

def parse_duration(s):
    """Parse duration string like 10m, 2h, 1d into seconds."""
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    if s[-1] in units:
        return int(s[:-1]) * units[s[-1]]
    raise ValueError(f"Invalid duration: {s}. Use format like 30m, 2h, 1d.")

# ============================================================
#  MUSIC
# ============================================================

music_queues  = {}
music_volumes = {}

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

def _find_ffmpeg():
    candidates = [
        shutil.which("ffmpeg"),
        "/usr/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
        "/nix/var/nix/profiles/default/bin/ffmpeg",
        "/run/current-system/sw/bin/ffmpeg",
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return "ffmpeg"

FFMPEG_EXECUTABLE = _find_ffmpeg()
print(f"FFmpeg resolved to: {FFMPEG_EXECUTABLE}")

AUDIO_SOURCES = [
    {
        "label": "YouTube (browser spoof)",
        "format": "bestaudio/best", "noplaylist": True, "quiet": True,
        "default_search": "ytsearch",
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        },
        "extractor_args": {"youtube": {"player_client": ["web"]}},
    },
    {
        "label": "YouTube (android)",
        "format": "bestaudio/best", "noplaylist": True, "quiet": True,
        "default_search": "ytsearch",
        "extractor_args": {"youtube": {"player_client": ["android"]}},
    },
    {
        "label": "YouTube (ios)",
        "format": "bestaudio/best", "noplaylist": True, "quiet": True,
        "default_search": "ytsearch",
        "extractor_args": {"youtube": {"player_client": ["ios"]}},
    },
    {
        "label": "YouTube (tv)",
        "format": "bestaudio/best", "noplaylist": True, "quiet": True,
        "default_search": "ytsearch",
        "extractor_args": {"youtube": {"player_client": ["tv_embedded"]}},
    },
    {
        "label": "SoundCloud",
        "format": "bestaudio/best", "noplaylist": True, "quiet": True,
        "default_search": "scsearch",
    },
    {
        "label": "Deezer",
        "format": "bestaudio/best", "noplaylist": True, "quiet": True,
        "default_search": "deezersearch",
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
#  BOT SETUP
# ============================================================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

GUILD_OBJ = discord.Object(id=GUILD_ID)

# ============================================================
#  STARTUP
# ============================================================

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")

    # Load all cogs from ./cogs/
    Path("cogs").mkdir(exist_ok=True)
    for cog_file in Path("cogs").glob("*.py"):
        try:
            await bot.load_extension(f"cogs.{cog_file.stem}")
            print(f"Loaded cog: {cog_file.stem}")
        except Exception as e:
            print(f"Failed to load cog {cog_file.stem}: {e}")

    # Sync slash commands to guild
    try:
        synced = await bot.tree.sync(guild=GUILD_OBJ)
        print(f"Synced {len(synced)} slash command(s)")
    except Exception as e:
        print(f"Slash sync failed: {e}")

    autodelete_task.start()
    print("Bot is ready.")

@bot.event
async def on_member_join(member):
    welcome_ch = discord.utils.get(member.guild.text_channels, name="welcome")
    if welcome_ch:
        await welcome_ch.send(WELCOME_MESSAGE.format(user=member.mention))
    role = discord.utils.get(member.guild.roles, name=AUTO_ROLE_NAME)
    if role:
        await member.add_roles(role)

# ============================================================
#  AUTO-DELETE BACKGROUND TASK
# ============================================================

@tasks.loop(minutes=5)
async def autodelete_task():
    for channel_id, max_age_seconds in list(autodelete_channels.items()):
        channel = bot.get_channel(channel_id)
        if not channel:
            continue
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)
        try:
            to_delete = []
            async for msg in channel.history(limit=200, before=cutoff):
                to_delete.append(msg)
            if to_delete:
                await channel.delete_messages(to_delete)
                print(f"Auto-deleted {len(to_delete)} messages in #{channel.name}")
        except Exception as e:
            print(f"Auto-delete error in {channel_id}: {e}")

# ============================================================
#  SETUP
# ============================================================

@bot.hybrid_command(name="setup", description="Create missing channels and roles. Run once.")
@commands.has_permissions(administrator=True)
@has_command_permission()
async def setup(ctx):
    guild = ctx.guild
    await ctx.send("Setting up server, please wait...")

    existing_roles = {r.name for r in guild.roles}
    for role_data in ROLES_TO_CREATE:
        if role_data["name"] not in existing_roles:
            await guild.create_role(
                name=role_data["name"],
                color=role_data["color"],
                permissions=role_data["permissions"],
            )

    muted_role = discord.utils.get(guild.roles, name="Muted")

    for category_name, channel_names in CATEGORIES.items():
        existing_cat = discord.utils.get(guild.categories, name=category_name)
        category = existing_cat or await guild.create_category(category_name)
        for ch_name in channel_names:
            if not discord.utils.get(guild.text_channels, name=ch_name):
                overwrites = {}
                if muted_role:
                    overwrites[muted_role] = discord.PermissionOverwrite(send_messages=False)
                if ch_name in ("welcome", "rules", "announcements"):
                    overwrites[guild.default_role] = discord.PermissionOverwrite(send_messages=False)
                await guild.create_text_channel(ch_name, category=category, topic=CHANNELS.get(ch_name, ""), overwrites=overwrites)

    rules_ch = discord.utils.get(guild.text_channels, name="rules")
    if rules_ch:
        rules_text = "**Server Rules**\n\n" + "\n".join(f"**{i+1}.** {r}" for i, r in enumerate(RULES))
        await rules_ch.purge(limit=10)
        await rules_ch.send(rules_text)

    await ctx.send("Server setup complete.")

# ============================================================
#  PERMISSION MANAGEMENT
# ============================================================

@bot.hybrid_command(name="permit", description="Allow a role to use a command.")
@commands.has_permissions(administrator=True)
async def permit(ctx, command_name: str, role: discord.Role):
    if command_name not in command_permissions:
        command_permissions[command_name] = []
    if str(role.id) not in command_permissions[command_name]:
        command_permissions[command_name].append(str(role.id))
        save_permissions(command_permissions)
    await ctx.send(f"Role **{role.name}** can now use `{PREFIX}{command_name}`.")

@bot.hybrid_command(name="unpermit", description="Remove a role's access to a command.")
@commands.has_permissions(administrator=True)
async def unpermit(ctx, command_name: str, role: discord.Role):
    if command_name in command_permissions and str(role.id) in command_permissions[command_name]:
        command_permissions[command_name].remove(str(role.id))
        save_permissions(command_permissions)
    await ctx.send(f"Role **{role.name}** can no longer use `{PREFIX}{command_name}`.")

@bot.hybrid_command(name="permissions", description="Show all command permission restrictions.")
@commands.has_permissions(administrator=True)
async def show_permissions(ctx):
    guild = ctx.guild
    if not command_permissions:
        await ctx.send("No command restrictions set. All commands are open to everyone.")
        return
    embed = discord.Embed(title="Command Permissions", color=discord.Color.blurple())
    for cmd, role_ids in command_permissions.items():
        if not role_ids:
            continue
        role_names = []
        for rid in role_ids:
            role = guild.get_role(int(rid))
            role_names.append(role.name if role else f"Unknown({rid})")
        embed.add_field(name=f"!{cmd}", value=", ".join(role_names), inline=False)
    await ctx.send(embed=embed)

# ============================================================
#  COG MANAGEMENT
# ============================================================

@bot.hybrid_command(name="uploadcog", description="Upload a .py cog file (attach it to the message).")
@has_command_permission()
async def uploadcog(ctx):
    if not ctx.message.attachments:
        await ctx.send("Attach a .py file to the message.")
        return
    attachment = ctx.message.attachments[0]
    if not attachment.filename.endswith(".py"):
        await ctx.send("Only .py files are accepted.")
        return

    Path("cogs").mkdir(exist_ok=True)
    path = Path("cogs") / attachment.filename
    await attachment.save(path)

    cog_name = f"cogs.{path.stem}"
    try:
        if cog_name in bot.extensions:
            await bot.reload_extension(cog_name)
            await ctx.send(f"Reloaded cog: `{attachment.filename}`")
        else:
            await bot.load_extension(cog_name)
            await ctx.send(f"Loaded cog: `{attachment.filename}`")
        await bot.tree.sync(guild=GUILD_OBJ)
    except Exception as e:
        await ctx.send(f"Failed to load cog: {e}")

@bot.hybrid_command(name="loadcog", description="Load a cog by name.")
@has_command_permission()
async def loadcog(ctx, name: str):
    try:
        await bot.load_extension(f"cogs.{name}")
        await bot.tree.sync(guild=GUILD_OBJ)
        await ctx.send(f"Loaded cog: `{name}`")
    except Exception as e:
        await ctx.send(f"Failed: {e}")

@bot.hybrid_command(name="unloadcog", description="Unload a cog by name.")
@has_command_permission()
async def unloadcog(ctx, name: str):
    try:
        await bot.unload_extension(f"cogs.{name}")
        await bot.tree.sync(guild=GUILD_OBJ)
        await ctx.send(f"Unloaded cog: `{name}`")
    except Exception as e:
        await ctx.send(f"Failed: {e}")

@bot.hybrid_command(name="reloadcog", description="Reload a cog by name.")
@has_command_permission()
async def reloadcog(ctx, name: str):
    try:
        await bot.reload_extension(f"cogs.{name}")
        await bot.tree.sync(guild=GUILD_OBJ)
        await ctx.send(f"Reloaded cog: `{name}`")
    except Exception as e:
        await ctx.send(f"Failed: {e}")

@bot.hybrid_command(name="listcogs", description="List all loaded cogs.")
@has_command_permission()
async def listcogs(ctx):
    loaded = list(bot.extensions.keys())
    if not loaded:
        await ctx.send("No cogs loaded.")
        return
    await ctx.send("Loaded cogs:\n" + "\n".join(f"- `{c}`" for c in loaded))

# ============================================================
#  AUTO-DELETE
# ============================================================

@bot.hybrid_command(name="autodelete", description="Auto-delete messages in a channel after a duration (e.g. 2h, 30m, 1d). Use 'off' to disable.")
@commands.has_permissions(manage_messages=True)
@has_command_permission()
async def autodelete(ctx, channel: discord.TextChannel, duration: str):
    if duration.lower() == "off":
        autodelete_channels.pop(channel.id, None)
        save_autodelete(autodelete_channels)
        await ctx.send(f"Auto-delete disabled for {channel.mention}.")
        return
    try:
        seconds = parse_duration(duration)
    except ValueError as e:
        await ctx.send(str(e))
        return
    autodelete_channels[channel.id] = seconds
    save_autodelete(autodelete_channels)
    await ctx.send(f"Auto-delete enabled for {channel.mention}. Messages older than **{duration}** will be deleted.")

@bot.hybrid_command(name="autodeletes", description="List all channels with auto-delete enabled.")
@commands.has_permissions(manage_messages=True)
async def autodeletes(ctx):
    if not autodelete_channels:
        await ctx.send("No auto-delete channels configured.")
        return
    lines = []
    for ch_id, seconds in autodelete_channels.items():
        ch = bot.get_channel(ch_id)
        name = ch.mention if ch else f"<#{ch_id}>"
        h, m = divmod(seconds // 60, 60)
        d, h = divmod(h, 24)
        dur = f"{d}d {h}h {m}m".strip()
        lines.append(f"{name} — {dur}")
    await ctx.send("Auto-delete channels:\n" + "\n".join(lines))

# ============================================================
#  MODERATION
# ============================================================

@bot.hybrid_command(name="kick", description="Kick a member.")
@commands.has_permissions(kick_members=True)
@has_command_permission()
async def kick(ctx, member: discord.Member, *, reason="No reason provided"):
    await member.kick(reason=reason)
    await ctx.send(f"{member} was kicked. Reason: {reason}")

@bot.hybrid_command(name="ban", description="Ban a member.")
@commands.has_permissions(ban_members=True)
@has_command_permission()
async def ban(ctx, member: discord.Member, *, reason="No reason provided"):
    await member.ban(reason=reason)
    await ctx.send(f"{member} was banned. Reason: {reason}")

@bot.hybrid_command(name="unban", description="Unban a user by username.")
@commands.has_permissions(ban_members=True)
@has_command_permission()
async def unban(ctx, *, username):
    bans = [entry async for entry in ctx.guild.bans()]
    for ban_entry in bans:
        if str(ban_entry.user) == username:
            await ctx.guild.unban(ban_entry.user)
            await ctx.send(f"Unbanned {ban_entry.user}.")
            return
    await ctx.send(f"No banned user found: {username}")

@bot.hybrid_command(name="mute", description="Mute a member.")
@commands.has_permissions(manage_roles=True)
@has_command_permission()
async def mute(ctx, member: discord.Member, *, reason="No reason provided"):
    muted_role = discord.utils.get(ctx.guild.roles, name="Muted")
    if not muted_role:
        await ctx.send('No "Muted" role found. Run !setup first.')
        return
    await member.add_roles(muted_role, reason=reason)
    await ctx.send(f"{member} has been muted. Reason: {reason}")

@bot.hybrid_command(name="unmute", description="Unmute a member.")
@commands.has_permissions(manage_roles=True)
@has_command_permission()
async def unmute(ctx, member: discord.Member):
    muted_role = discord.utils.get(ctx.guild.roles, name="Muted")
    if muted_role in member.roles:
        await member.remove_roles(muted_role)
        await ctx.send(f"{member} has been unmuted.")
    else:
        await ctx.send(f"{member} is not muted.")

@bot.hybrid_command(name="purge", description="Delete a number of messages (1-100).")
@commands.has_permissions(manage_messages=True)
@has_command_permission()
async def purge(ctx, amount: int):
    if not 1 <= amount <= 100:
        await ctx.send("Amount must be between 1 and 100.")
        return
    await ctx.channel.purge(limit=amount + 1)
    msg = await ctx.send(f"Deleted {amount} messages.")
    await asyncio.sleep(3)
    await msg.delete()

@bot.hybrid_command(name="addrole", description="Give a role to a member.")
@commands.has_permissions(manage_roles=True)
@has_command_permission()
async def addrole(ctx, member: discord.Member, *, role_name: str):
    role = discord.utils.get(ctx.guild.roles, name=role_name)
    if not role:
        await ctx.send(f'Role "{role_name}" not found.')
        return
    await member.add_roles(role)
    await ctx.send(f"Gave {role.name} to {member}.")

@bot.hybrid_command(name="removerole", description="Remove a role from a member.")
@commands.has_permissions(manage_roles=True)
@has_command_permission()
async def removerole(ctx, member: discord.Member, *, role_name: str):
    role = discord.utils.get(ctx.guild.roles, name=role_name)
    if not role:
        await ctx.send(f'Role "{role_name}" not found.')
        return
    await member.remove_roles(role)
    await ctx.send(f"Removed {role.name} from {member}.")

# ============================================================
#  INFO
# ============================================================

@bot.hybrid_command(name="userinfo", description="Show info about a user.")
@has_command_permission()
async def userinfo(ctx, member: discord.Member = None):
    member = member or ctx.author
    embed = discord.Embed(title=str(member), color=member.color)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="ID", value=member.id)
    embed.add_field(name="Joined Server", value=member.joined_at.strftime("%Y-%m-%d"))
    embed.add_field(name="Account Created", value=member.created_at.strftime("%Y-%m-%d"))
    roles = [r.name for r in member.roles if r.name != "@everyone"]
    embed.add_field(name="Roles", value=", ".join(roles) or "None", inline=False)
    await ctx.send(embed=embed)

@bot.hybrid_command(name="serverinfo", description="Show server info.")
@has_command_permission()
async def serverinfo(ctx):
    guild = ctx.guild
    embed = discord.Embed(title=guild.name, color=discord.Color.blurple())
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(name="Members", value=guild.member_count)
    embed.add_field(name="Channels", value=len(guild.text_channels))
    embed.add_field(name="Roles", value=len(guild.roles))
    embed.add_field(name="Created", value=guild.created_at.strftime("%Y-%m-%d"))
    await ctx.send(embed=embed)

@bot.hybrid_command(name="ping", description="Check bot latency.")
async def ping(ctx):
    await ctx.send(f"Pong! Latency: {round(bot.latency * 1000)}ms")

@bot.hybrid_command(name="announce", description="Post an announcement in #announcements.")
@commands.has_permissions(manage_messages=True)
@has_command_permission()
async def announce(ctx, *, message: str):
    ch = discord.utils.get(ctx.guild.text_channels, name="announcements")
    if not ch:
        await ctx.send("No #announcements channel found. Run !setup first.")
        return
    embed = discord.Embed(description=message, color=discord.Color.gold())
    embed.set_footer(text=f"Posted by {ctx.author}")
    await ch.send(embed=embed)
    if ctx.interaction is None:
        await ctx.message.delete()
    else:
        await ctx.send("Announced.", ephemeral=True)

@bot.hybrid_command(name="list", description="List all available commands.")
async def list_commands(ctx):
    embed = discord.Embed(title="WeDoSoftware Bot Commands", color=discord.Color.blurple())
    embed.add_field(name="Setup & Admin", value="`/setup` `/permit` `/unpermit` `/permissions`", inline=False)
    embed.add_field(name="Cogs", value="`/uploadcog` `/loadcog` `/unloadcog` `/reloadcog` `/listcogs`", inline=False)
    embed.add_field(name="Auto-Delete", value="`/autodelete #channel 2h` `/autodeletes`", inline=False)
    embed.add_field(name="Moderation", value="`/kick` `/ban` `/unban` `/mute` `/unmute` `/purge` `/addrole` `/removerole`", inline=False)
    embed.add_field(name="Info", value="`/userinfo` `/serverinfo` `/ping` `/announce`", inline=False)
    embed.add_field(name="Music", value="`/join` `/leave` `/play` `/skip` `/stop` `/pause` `/resume` `/volume` `/queue`", inline=False)
    await ctx.send(embed=embed)

# ============================================================
#  MUSIC
# ============================================================

@bot.hybrid_command(name="join", description="Join your voice channel.")
@has_command_permission()
async def join(ctx):
    if not ctx.author.voice:
        await ctx.send("You need to be in a voice channel first.")
        return
    vc = ctx.voice_client
    if vc:
        await vc.move_to(ctx.author.voice.channel)
    else:
        await ctx.author.voice.channel.connect()
    await ctx.send(f"Joined {ctx.author.voice.channel.name}.")

@bot.hybrid_command(name="leave", description="Leave the voice channel.")
@has_command_permission()
async def leave(ctx):
    if ctx.voice_client:
        get_queue(ctx.guild.id).clear()
        await ctx.voice_client.disconnect()
        await ctx.send("Disconnected.")
    else:
        await ctx.send("Not in a voice channel.")

@bot.hybrid_command(name="play", description="Play a song by name or URL.")
@has_command_permission()
async def play(ctx, *, query: str):
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

@bot.hybrid_command(name="skip", description="Skip the current song.")
@has_command_permission()
async def skip(ctx):
    vc = ctx.voice_client
    if vc and vc.is_playing():
        vc.stop()
        await ctx.send("Skipped.")
    else:
        await ctx.send("Nothing is playing.")

@bot.hybrid_command(name="stop", description="Stop music and clear the queue.")
@has_command_permission()
async def stop(ctx):
    vc = ctx.voice_client
    if vc:
        get_queue(ctx.guild.id).clear()
        vc.stop()
        await ctx.send("Stopped and queue cleared.")
    else:
        await ctx.send("Not playing anything.")

@bot.hybrid_command(name="pause", description="Pause the current song.")
@has_command_permission()
async def pause(ctx):
    vc = ctx.voice_client
    if vc and vc.is_playing():
        vc.pause()
        await ctx.send("Paused.")
    else:
        await ctx.send("Nothing is playing.")

@bot.hybrid_command(name="resume", description="Resume a paused song.")
@has_command_permission()
async def resume(ctx):
    vc = ctx.voice_client
    if vc and vc.is_paused():
        vc.resume()
        await ctx.send("Resumed.")
    else:
        await ctx.send("Nothing is paused.")

@bot.hybrid_command(name="volume", description="Set music volume (0-100).")
@has_command_permission()
async def volume(ctx, vol: int):
    if not 0 <= vol <= 100:
        await ctx.send("Volume must be between 0 and 100.")
        return
    music_volumes[ctx.guild.id] = vol / 100
    vc = ctx.voice_client
    if vc and vc.source:
        vc.source.volume = vol / 100
    await ctx.send(f"Volume set to {vol}%.")

@bot.hybrid_command(name="queue", description="Show the music queue.")
@has_command_permission()
async def show_queue(ctx):
    queue = get_queue(ctx.guild.id)
    vc = ctx.voice_client
    if not queue and (not vc or not vc.is_playing()):
        await ctx.send("Queue is empty.")
        return
    lines = [f"**{i+1}.** {title}" for i, (_, title) in enumerate(queue)]
    header = "**Now playing** (use /skip to skip)\n" if vc and vc.is_playing() else ""
    await ctx.send(header + "\n".join(lines) if lines else header + "No songs queued.")

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
        await ctx.send(f"Missing argument. Use `/list` to see usage.")
    elif isinstance(error, commands.CommandNotFound):
        pass
    elif isinstance(error, commands.CheckFailure):
        await ctx.send("You don't have the required role to use that command.")
    else:
        await ctx.send(f"An error occurred: {error}")
        raise error

# ============================================================
#  RUN
# ============================================================

bot.run(TOKEN)