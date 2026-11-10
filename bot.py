#!/usr/bin/env python3
"""Desteria's Outpost — standalone Railway Discord community bot.

One service, no local database. Only an administrator invoking /setup_all changes
setup channels or creates roles. Existing Friends/Faction structures are never edited.
"""
import logging
import os

import discord
from discord import app_commands

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("outpost")

GUILD_ID = 1240026480663199865
configured_id = os.getenv("DISCORD_GUILD_ID", str(GUILD_ID)).strip()
if configured_id != str(GUILD_ID):
    raise SystemExit(f"Wrong DISCORD_GUILD_ID; expected {GUILD_ID}. No Discord changes made.")
TOKEN = os.getenv("DISCORD_BOT_TOKEN", "").strip()
if not TOKEN:
    raise SystemExit("Missing DISCORD_BOT_TOKEN Railway variable")
GUILD = discord.Object(id=GUILD_ID)
COLOR = discord.Color(0x3A6658)

# Only these eight roles can be assigned by role buttons.
ROLE_GROUPS = {
    "games": [("MW4", "🔫"), ("Minecraft", "⛏️")],
    "platforms": [("PC", "💻"), ("PlayStation", "🎮"), ("Xbox", "🟩")],
    "style": [("Casual", "☕"), ("Competitive", "🏆"), ("Night Owl", "🌙")],
}

CHANNELS = {
    "welcome": ("👋・welcome", ["welcome"]),
    "roles": ("🎭・choose-roles", ["choose-roles", "pick-your-roles"]),
    "rules": ("📜・rules", ["rules"]),
    "announcements": ("📢・announcements", ["announcements"]),
    "commands": ("🤖・bot-commands", ["bot-commands"]),
}
WELCOME_CHANNEL_ORIGINAL_ID = 1240026480663199868


def embed(title: str, description: str, tag: str) -> discord.Embed:
    result = discord.Embed(title=title, description=description, colour=COLOR)
    result.set_footer(text=f"Desteria's Outpost · {tag}")
    return result


def existing_channel(guild: discord.Guild, key: str):
    if key == "welcome":
        ch = guild.get_channel(WELCOME_CHANNEL_ORIGINAL_ID)
        if isinstance(ch, discord.TextChannel):
            return ch
    exact, aliases = CHANNELS[key]
    found = [c for c in guild.text_channels if c.name == exact]
    if len(found) == 1:
        return found[0]
    if len(found) > 1:
        raise RuntimeError(f"Multiple channels named {exact}; resolve manually")
    # Avoid accidentally picking unrelated channels that only partly match a name.
    fallback = [c for c in guild.text_channels if c.name.lower().strip("# ") in aliases]
    if len(fallback) == 1:
        return fallback[0]
    if len(fallback) > 1:
        raise RuntimeError(f"Multiple possible {key} channels; resolve manually")
    return None


def member_role(guild: discord.Guild, name: str):
    return discord.utils.get(guild.roles, name=name)


def can_publish(guild: discord.Guild, channel: discord.TextChannel) -> bool:
    bot_member = guild.me
    if not bot_member or not channel:
        return False
    p = channel.permissions_for(bot_member)
    return p.view_channel and p.send_messages and p.embed_links and p.read_message_history


def welcome_embed(guild):
    ch = existing_channel(guild, "roles")
    target = ch.mention if ch else "#choose-roles"
    return embed(
        "🎮 Welcome to Desteria's Outpost ⛏️",
        "Welcome to our home base for **MW4**, **Minecraft**, and gaming with friends!\n\n"
        f"**🔓 TO UNLOCK GAME CHANNELS:** Open {target} and click **MW4** or **Minecraft** "
        "to get the corresponding game role. You can select both.\n\n"
        "📜 Read the rules · 💬 Hang out · 🔎 Find a squad · 🎵 Queue some music\n\n"
        "Squad up, survive, build, and have fun.",
        "welcome:v1",
    )


def rules_embed():
    e = embed("📜 Outpost Rules", "Keep it friendly. Everyone is here to enjoy gaming.", "rules:v1")
    rules = [
        ("1 · Respect people", "No harassment, discrimination, slurs, bullying or threats."),
        ("2 · Respect boundaries", "No unsolicited harassment in DMs, doxxing or sharing private messages/media without permission."),
        ("3 · No spam", "No scams, phishing, flooding, unwanted advertising or excessive mentions."),
        ("4 · Play fair", "No intentional griefing, cheating or spoiling others' gaming sessions."),
        ("5 · Keep it appropriate", "Use appropriate channels and comply with Discord's content and age-restriction rules."),
        ("6 · Keep voice chat pleasant", "No ear-rape audio, disruption, or talking over others to harass them."),
        ("7 · Follow Discord policies", "Report problems to admins; don't impersonate people or evade restrictions."),
    ]
    for name, value in rules:
        e.add_field(name=name, value=value, inline=False)
    return e


def guide_embed():
    return embed(
        "🤖 Bot Commands & How to Use Them",
        "**Everyone**\n"
        "• Role buttons in **#choose-roles** add/remove MW4, Minecraft, platform, and playstyle roles.\n"
        "• New members automatically receive the **Member** role and a welcome greeting.\n\n"
        "**Admins only**\n"
        "`/setup_all` — create missing public setup channels/roles and publish all panels.\n"
        "`/setup_roles` — create/refresh role selection panels.\n"
        "`/setup_welcome` — create/refresh permanent welcome message.\n"
        "`/setup_rules` — create/refresh server rules.\n"
        "`/setup_commands` — refresh this command guide.\n"
        "`/announcement` — post an announcement, optional @everyone.\n"
        "`/bot_status` — check bot, channels and role availability.\n\n"
        "**Music:** Use the separate music bot in #music-requests; this bot does not stream music.",
        "commands:v1",
    )


def panel_embed(group):
    title, text = {
        "games": ("🎮 Pick Your Games", "Select MW4 and/or Minecraft to access their sections."),
        "platforms": ("🕹️ Your Platform", "Show what you play on."),
        "style": ("🏆 Your Playstyle", "Find your people."),
    }[group]
    options = "\n".join(f"{emoji} **{name}**" for name, emoji in ROLE_GROUPS[group])
    return embed(title, f"{text}\n\n{options}\n\nClick once to add, again to remove.", f"roles:{group}:v1")


class ToggleButton(discord.ui.Button):
    def __init__(self, group: str, role_name: str, emoji: str):
        self.target_role = role_name
        super().__init__(label=role_name, emoji=emoji, style=discord.ButtonStyle.secondary,
                         custom_id=f"outpost:role:v1:{group}:{role_name.lower().replace(' ', '_')}")

    async def callback(self, interaction: discord.Interaction):
        if interaction.guild_id != GUILD_ID or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("This button is only for Outpost members.", ephemeral=True)
        role = member_role(interaction.guild, self.target_role)
        me = interaction.guild.me
        if role is None or me is None or not me.guild_permissions.manage_roles or role.managed or me.top_role <= role:
            return await interaction.response.send_message(
                "The role is missing or my bot role is too low. Please contact an admin.", ephemeral=True)
        try:
            if role in interaction.user.roles:
                await interaction.user.remove_roles(role, reason="Outpost self-selectable role")
                message = f"✅ Removed **{role.name}**."
            else:
                await interaction.user.add_roles(role, reason="Outpost self-selectable role")
                message = f"✅ Added **{role.name}**."
            await interaction.response.send_message(message, ephemeral=True)
        except discord.HTTPException:
            log.exception("Role toggle failed")
            if not interaction.response.is_done():
                await interaction.response.send_message("Discord couldn't change that role. Tell an admin.", ephemeral=True)


class RoleButtons(discord.ui.View):
    def __init__(self, group: str):
        super().__init__(timeout=None)
        for name, emoji in ROLE_GROUPS[group]:
            self.add_item(ToggleButton(group, name, emoji))


class OutpostBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(intents=intents, allowed_mentions=discord.AllowedMentions.none())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        for group in ROLE_GROUPS:
            self.add_view(RoleButtons(group))
        synced = await self.tree.sync(guild=GUILD)
        log.info("GUILD COMMANDS SYNCED: %s", ", ".join(c.name for c in synced))

bot = OutpostBot()


def admin_only():
    return app_commands.checks.has_permissions(manage_guild=True)


async def upsert(channel: discord.TextChannel, content: discord.Embed, view=None):
    """Stable ID via pinned messages: no Railway disk or volume needed."""
    tag = content.footer.text
    owned = []
    seen_ids = set()
    try:
        async for message in channel.pins(limit=100):
            owned.append(message)
            seen_ids.add(message.id)
    except discord.HTTPException:
        log.warning("Couldn't read pinned messages in #%s; checking recent history", channel.name)
    # Also find old unpinned panels (and allow recovery when pin permissions aren't set).
    async for item in channel.history(limit=500):
        if item.id not in seen_ids:
            owned.append(item)
            seen_ids.add(item.id)
    matches = [m for m in owned if m.author.id == bot.user.id and m.embeds and
               m.embeds[0].footer.text == tag]
    if len(matches) > 1:
        # Avoid making duplicates worse. An admin can clean up existing duplicates.
        raise RuntimeError(f"Found {len(matches)} duplicate {tag} panels; resolve manually")
    if matches:
        await matches[0].edit(embed=content, view=view)
        return f"Updated {matches[0].jump_url}"
    message = await channel.send(embed=content, view=view)
    try:
        await message.pin(reason="Permanent Outpost information panel")
    except (discord.Forbidden, discord.HTTPException):
        log.warning("Couldn't pin %s in #%s; grant Manage Messages for stronger duplicate protection", tag, channel.name)
    return f"Posted {message.jump_url}"


def start_category(guild):
    return next((c for c in guild.categories if c.name in ("📌 START HERE", "Welcome")), None)


async def ensure_channel(guild, key: str):
    channel = existing_channel(guild, key)
    if channel:
        return channel, False
    category = start_category(guild)
    if not category:
        raise RuntimeError("START HERE/Welcome category missing. Won't create channels in the wrong place.")
    me = guild.me
    if not me or not me.guild_permissions.manage_channels:
        raise RuntimeError("Bot needs Manage Channels to create missing information channels")
    # Only *new* channels get these overwrites. Existing channels are never edited.
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=True, send_messages=False,
                                                           read_message_history=True),
        me: discord.PermissionOverwrite(view_channel=True, send_messages=True, embed_links=True,
                                        read_message_history=True, manage_messages=True),
    }
    new = await guild.create_text_channel(CHANNELS[key][0], category=category, overwrites=overwrites,
                                          reason="Outpost admin /setup_all: missing information channel")
    log.info("Created new info channel #%s", new.name)
    return new, True


async def ensure_roles(guild):
    if not guild.me or not guild.me.guild_permissions.manage_roles:
        raise RuntimeError("Bot needs Manage Roles")
    names = ["Member"] + [name for entries in ROLE_GROUPS.values() for name, _ in entries]
    created = []
    for name in names:
        if not member_role(guild, name):
            role = await guild.create_role(name=name, colour=COLOR, reason="Outpost admin /setup_all: missing member/selection role")
            created.append(role.name)
    return created


async def post_channel(guild, key, value, view=None):
    ch = existing_channel(guild, key)
    if not ch:
        return f"⚠️ {key}: channel not found, run /setup_all"
    if not can_publish(guild, ch):
        return f"⚠️ {key}: bot needs View, Send, Embed Links, Read History. Existing permissions unchanged."
    try:
        return f"✅ {key}: {await upsert(ch, value, view)}"
    except (discord.HTTPException, RuntimeError):
        log.exception("Posting %s failed", key)
        return f"⚠️ {key}: could not post or duplicate panel detected. Check Railway logs."


async def post_roles(guild):
    me = guild.me
    missing = [name for group in ROLE_GROUPS.values() for name, _ in group if not member_role(guild, name)]
    if missing:
        return ["⚠️ Missing roles: " + ", ".join(missing) + "; run /setup_all"]
    if not me or not me.guild_permissions.manage_roles:
        return ["⚠️ Bot needs Manage Roles"]
    inaccessible = [name for group in ROLE_GROUPS.values() for name, _ in group if me.top_role <= member_role(guild, name)]
    if inaccessible:
        return ["⚠️ Move bot role above: " + ", ".join(inaccessible)]
    return [await post_channel(guild, "roles", panel_embed(group), RoleButtons(group)) for group in ROLE_GROUPS]


async def run_setup(guild, create=False):
    outcomes = []
    if create:
        created = await ensure_roles(guild)
        outcomes.append("Roles created: " + (", ".join(created) if created else "none (reused existing)"))
        for key in CHANNELS:
            _, was_created = await ensure_channel(guild, key)
            if was_created:
                outcomes.append(f"Created #{CHANNELS[key][0]}")
    outcomes.extend([
        await post_channel(guild, "welcome", welcome_embed(guild)),
        await post_channel(guild, "rules", rules_embed()),
        *(await post_roles(guild)),
        await post_channel(guild, "commands", guide_embed()),
    ])
    return outcomes


async def reply_setup(interaction, outcomes):
    body = "\n".join(outcomes)
    if len(body) > 1850:
        body = body[:1800] + "\n… see Railway logs"
    await interaction.followup.send(body, ephemeral=True)


@bot.tree.command(name="setup_all", description="Create missing info channels/roles and publish all Outpost embeds", guild=GUILD)
@app_commands.default_permissions(manage_guild=True)
@admin_only()
async def setup_all(i: discord.Interaction):
    await i.response.defer(ephemeral=True)
    try:
        await reply_setup(i, await run_setup(i.guild, create=True))
    except (discord.HTTPException, RuntimeError):
        log.exception("/setup_all failed")
        await i.followup.send("⚠️ Setup stopped. Read Railway logs for the cause. Existing private channels were not edited.", ephemeral=True)


@bot.tree.command(name="setup_roles", description="Refresh the three self-selectable role panels", guild=GUILD)
@app_commands.default_permissions(manage_guild=True)
@admin_only()
async def setup_roles(i: discord.Interaction):
    await i.response.defer(ephemeral=True)
    await reply_setup(i, await post_roles(i.guild))


@bot.tree.command(name="setup_welcome", description="Post or refresh permanent welcome embed", guild=GUILD)
@app_commands.default_permissions(manage_guild=True)
@admin_only()
async def setup_welcome(i: discord.Interaction):
    await i.response.defer(ephemeral=True)
    await reply_setup(i, [await post_channel(i.guild, "welcome", welcome_embed(i.guild))])


@bot.tree.command(name="setup_rules", description="Post or refresh rules embed", guild=GUILD)
@app_commands.default_permissions(manage_guild=True)
@admin_only()
async def setup_rules(i: discord.Interaction):
    await i.response.defer(ephemeral=True)
    await reply_setup(i, [await post_channel(i.guild, "rules", rules_embed())])


@bot.tree.command(name="setup_commands", description="Post or refresh the bot command guide", guild=GUILD)
@app_commands.default_permissions(manage_guild=True)
@admin_only()
async def setup_commands(i: discord.Interaction):
    await i.response.defer(ephemeral=True)
    await reply_setup(i, [await post_channel(i.guild, "commands", guide_embed())])


@bot.tree.command(name="announcement", description="Post an announcement to the dedicated channel", guild=GUILD)
@app_commands.default_permissions(manage_guild=True)
@admin_only()
@app_commands.describe(title="Announcement title", message="Announcement body", ping_everyone="Notify @everyone? Defaults to No")
async def announcement(i: discord.Interaction, title: str, message: str, ping_everyone: bool = False):
    if len(title) > 200 or len(message) > 3500 or not title.strip() or not message.strip():
        return await i.response.send_message("Use a title under 200 and message under 3500 characters.", ephemeral=True)
    channel = existing_channel(i.guild, "announcements")
    if not channel or not can_publish(i.guild, channel):
        return await i.response.send_message("Announcement channel missing or bot lacks permissions. Run /setup_all.", ephemeral=True)
    if ping_everyone and not channel.permissions_for(i.guild.me).mention_everyone:
        return await i.response.send_message("The bot needs Mention @everyone permission in announcements for that ping.", ephemeral=True)
    try:
        sent = await channel.send(content="@everyone" if ping_everyone else None,
                                  embed=embed("📢 " + title, message, "announcement"),
                                  allowed_mentions=discord.AllowedMentions(everyone=ping_everyone))
        await i.response.send_message(f"Posted: {sent.jump_url}", ephemeral=True)
    except discord.HTTPException:
        log.exception("announcement failed")
        await i.response.send_message("Discord rejected the announcement. Check Railway logs.", ephemeral=True)


@bot.tree.command(name="bot_status", description="Check Outpost bot role and channel setup", guild=GUILD)
@app_commands.default_permissions(manage_guild=True)
@admin_only()
async def bot_status(i: discord.Interaction):
    guild = i.guild
    lines = [f"Guild: {guild.name} ({guild.id})"]
    for key in CHANNELS:
        ch = existing_channel(guild, key)
        lines.append(f"{key}: " + ((ch.mention + (" ✅" if can_publish(guild, ch) else " ⚠️ no send")) if ch else "⚠️ missing"))
    for name in ["Member", "MW4", "Minecraft"]:
        lines.append(f"Role {name}: {'✅' if member_role(guild, name) else '⚠️ missing'}")
    lines.append(f"Member-join intent: {'✅' if bot.intents.members else '⚠️'}")
    await i.response.send_message("\n".join(lines), ephemeral=True)


@bot.event
async def on_ready():
    guild = bot.get_guild(GUILD_ID)
    log.info("CONNECTED: %s | SERVER: %s | guild_id=%s", bot.user, getattr(guild, "name", "NOT FOUND"), GUILD_ID)
    if guild and member_role(guild, "Member") is None:
        log.warning("Member role not found. Run /setup_all once.")


@bot.event
async def on_member_join(member: discord.Member):
    if member.guild.id != GUILD_ID:
        return
    role = member_role(member.guild, "Member")
    if role:
        try:
            await member.add_roles(role, reason="Outpost new member auto-role")
            log.info("Assigned Member to new user %s", member.id)
        except discord.HTTPException:
            log.exception("Could not auto-assign Member to %s", member.id)
    else:
        log.error("Member role absent. Run /setup_all")
    channel = existing_channel(member.guild, "welcome")
    if channel and can_publish(member.guild, channel):
        try:
            roles_channel = existing_channel(member.guild, "roles")
            target = roles_channel.mention if roles_channel else "#choose-roles"
            greeting = embed("👋 New player at the Outpost!", f"Welcome {member.mention}!\nHead to {target} to choose your game roles.", "new-member")
            await channel.send(embed=greeting, allowed_mentions=discord.AllowedMentions(users=[member]))
        except discord.HTTPException:
            log.exception("Could not post new-member greeting")


@bot.tree.error
async def on_error(i: discord.Interaction, error: app_commands.AppCommandError):
    log.error("Slash command failed: %r", error)
    text = "You need Manage Server permission." if isinstance(error, app_commands.MissingPermissions) else "Command failed; check Railway logs."
    try:
        if i.response.is_done():
            await i.followup.send(text, ephemeral=True)
        else:
            await i.response.send_message(text, ephemeral=True)
    except discord.HTTPException:
        pass


bot.run(TOKEN)
