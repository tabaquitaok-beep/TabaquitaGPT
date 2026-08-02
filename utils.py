from datetime import datetime, timezone
import discord

from config import ROLE_LEVELS, HIGH_COMMAND_ROLE_ID, HIGH_RANK_ROLE_ID


def get_member_role_level(member: discord.Member | None) -> int:
    if member is None:
        return 0
    level = 0
    for role in member.roles:
        level = max(level, ROLE_LEVELS.get(role.id, 0))
    return level


def has_min_role(member: discord.Member, minimum_level: int) -> bool:
    return get_member_role_level(member) >= minimum_level


def get_role_name(role_id: int) -> str:
    names = {
        1516095262903242831: "Wait",
        1492155946842198086: "Bot",
        1516093644720046150: "Miembro externo",
        1494162106725961849: "Low Rank",
        1495959303113412750: "Middle Rank",
        1495961100053778434: "High Rank",
        1496612684345512119: "High Command",
    }
    return names.get(role_id, "Sin rango")


def build_progress_bar(current: float, target: float) -> str:
    if target <= 0:
        return "████████"
    filled = min(8, max(0, int((current / target) * 8)))
    return "█" * filled + "▒" * (8 - filled)


def format_progress_line(current: float, target: float, label: str) -> str:
    bar = build_progress_bar(current, target)
    return f"`{label}` {bar} {int(current)}/{int(target)}"


def parse_amount(text: str) -> float | None:
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def is_high_command(member: discord.Member) -> bool:
    return member.guild_permissions.administrator or any(r.id == HIGH_COMMAND_ROLE_ID for r in member.roles)


def can_manage_xp(member: discord.Member) -> bool:
    return member.guild_permissions.administrator or any(r.id in {HIGH_RANK_ROLE_ID, HIGH_COMMAND_ROLE_ID} for r in member.roles)


def utcnow_str() -> str:
    return datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M:%S UTC")
