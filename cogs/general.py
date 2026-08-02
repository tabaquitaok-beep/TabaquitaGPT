import time
from datetime import datetime, timezone

import discord
from discord.ext import commands

from config import (
    OWNER_ID,
    STATUS_CHANNEL_ID,
    HIGH_COMMAND_ROLE_ID,
    HIGH_RANK_ROLE_ID,
    MIDDLE_RANK_ROLE_ID,
    LOW_RANK_ROLE_ID,
    WAIT_ROLE_ID,
    MIEMBRO_EXTERNO_ROLE_ID,
)
from stats import stats_store
from utils import (
    build_progress_bar,
    can_manage_xp,
    format_progress_line,
    get_member_role_level,
    get_role_name,
    is_high_command,
    parse_amount,
    utcnow_str,
)


def get_next_rank(current_rank: int | None) -> int | None:
    if current_rank == LOW_RANK_ROLE_ID:
        return MIDDLE_RANK_ROLE_ID
    if current_rank == MIDDLE_RANK_ROLE_ID:
        return HIGH_RANK_ROLE_ID
    if current_rank == HIGH_RANK_ROLE_ID:
        return HIGH_COMMAND_ROLE_ID
    return None


def get_requirement_text(next_rank: int | None) -> tuple[str, str, list[str]]:
    if next_rank == HIGH_RANK_ROLE_ID:
        return "High Rank", "Selección por un HC", ["AXP", "EXP"]
    if next_rank == HIGH_COMMAND_ROLE_ID:
        return "High Command", "Selección de Kenner", ["AXP", "EXP"]
    if next_rank == MIDDLE_RANK_ROLE_ID:
        return "Middle Rank", "", ["AXP", "EXP"]
    return "", "", ["AXP", "EXP"]


async def get_status_channel(bot: commands.Bot) -> discord.TextChannel | None:
    channel = bot.get_channel(STATUS_CHANNEL_ID)
    if channel is not None:
        return channel
    try:
        return await bot.fetch_channel(STATUS_CHANNEL_ID)
    except Exception:
        return None


async def send_status_embed(bot: commands.Bot, title: str, fields: list[tuple[str, str, bool]], color: discord.Color) -> None:
    channel = await get_status_channel(bot)
    if channel is None:
        return
    embed = discord.Embed(title=title, color=color, timestamp=datetime.now(timezone.utc))
    for name, value, inline in fields:
        embed.add_field(name=name, value=value, inline=inline)
    await channel.send(embed=embed)


async def send_owner_dm(bot: commands.Bot, embed: discord.Embed) -> None:
    try:
        owner = await bot.fetch_user(OWNER_ID)
        if owner is not None:
            await owner.send(embed=embed)
    except Exception as exc:
        print(f"[WARN] No se pudo enviar MD al owner: {exc}")


class GeneralCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.voice_start: dict[int, float] = {}

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"¡Conectado como {self.bot.user}!")
        db_status = "SQLite"
        if await stats_store.verify_mongo():
            db_status = "MongoDB"
            print("¡Conexión exitosa a MongoDB Atlas!")
        else:
            print("MongoDB no disponible, usando SQLite para persistencia.")

        embed = discord.Embed(
            title="🛡️ Sistema - Protocolo de Inicio",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Bot conectado como", value=f"`{self.bot.user}`", inline=True)
        embed.add_field(name="Base de datos", value=f"`{db_status}`", inline=True)
        embed.add_field(name="Hora de inicio", value=utcnow_str(), inline=False)
        embed.set_footer(text="TabaquitaGPT | Inicio exitoso")

        await send_owner_dm(self.bot, embed)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        await send_status_embed(
            self.bot,
            "Nuevo miembro",
            [
                ("Usuario", f"{member.mention} ({member.id})", False),
                ("Cuenta creada", member.created_at.strftime("%d/%m/%Y %H:%M:%S UTC"), False),
            ],
            discord.Color.green(),
        )

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return

        entered = before.channel is None and after.channel is not None
        left = before.channel is not None and after.channel is None
        switched = before.channel is not None and after.channel is not None and before.channel.id != after.channel.id

        if entered:
            self.voice_start[member.id] = time.time()
            await send_status_embed(
                self.bot,
                "Union a VC",
                [
                    ("Usuario", f"{member.mention} ({member.id})", False),
                    ("Ubicacion", after.channel.name, False),
                    ("Fecha y Hora", utcnow_str(), False),
                    ("Iniciando trackeo de VC", "", False),
                ],
                discord.Color.green(),
            )
            return

        if switched:
            start = self.voice_start.get(member.id)
            if start is None:
                self.voice_start[member.id] = time.time()
                return
            duration = time.time() - start
            gained = int(duration // 3600)
            if gained > 0:
                await stats_store.add_axp(str(member.id), float(gained))
            self.voice_start[member.id] = time.time()
            await send_status_embed(
                self.bot,
                "Cambio de VC",
                [
                    ("Usuario", f"{member.mention} ({member.id})", False),
                    ("VC Anterior", before.channel.name, False),
                    ("VC Nuevo", after.channel.name, False),
                    ("Tiempo en el VC", f"{int(duration // 3600):02d}:{int((duration % 3600) // 60):02d}:{int(duration % 60):02d}", False),
                    ("AXP Conseguida", str(gained), False),
                    ("Fecha y Hora", utcnow_str(), False),
                ],
                discord.Color.blue(),
            )
            return

        if left:
            start = self.voice_start.pop(member.id, None)
            if start is None:
                return
            duration = time.time() - start
            gained = int(duration // 3600)
            if gained > 0:
                await stats_store.add_axp(str(member.id), float(gained))
            await send_status_embed(
                self.bot,
                "Salida de VC",
                [
                    ("Usuario", f"{member.mention} ({member.id})", False),
                    ("Ubicacion", before.channel.name, False),
                    ("Fecha y Hora", utcnow_str(), False),
                    ("Estancia en el VC", f"{int(duration // 3600):02d}:{int((duration % 3600) // 60):02d}:{int(duration % 60):02d}", False),
                    ("AXP Conseguida", str(gained), False),
                ],
                discord.Color.red(),
            )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        if message.guild is not None:
            try:
                user_id = str(message.author.id)
                stats = await stats_store.get_user_stats(user_id)
                msgs = int(stats.get("messages", 0)) + 1
                award = 0.0
                if msgs >= 10:
                    award = 0.1 * (msgs // 10)
                    msgs = msgs % 10
                await stats_store.update_user_stats(user_id, {"messages": msgs})
                if award > 0:
                    await stats_store.add_axp(user_id, award)
            except Exception as exc:
                print(f"[LOG] on_message tracking error: {exc}")

        await self.bot.process_commands(message)

    @commands.command(name="ping")
    async def ping(self, ctx: commands.Context):
        await ctx.send("¡Pong! TabaquitaGPT está en línea y funcionando.")

    @commands.command(name="rank")
    async def rank(self, ctx: commands.Context, target: discord.Member | None = None):
        member = target or ctx.author
        level = get_member_role_level(member)
        if level <= 0:
            role_name = "Sin rango asignado"
        else:
            matching_roles = [role_id for role_id in ROLE_LEVELS if role_id in {role.id for role in member.roles}]
            current_rank = max(matching_roles, key=lambda role_id: ROLE_LEVELS[role_id], default=0)
            role_name = get_role_name(current_rank)
        await ctx.send(f"{member.mention} tiene nivel de rango {level} ({role_name}).")

    @commands.command(name="ayuda", aliases=["help"])
    async def help_command(self, ctx: commands.Context):
        embed = discord.Embed(title="📘 Ayuda básica", color=discord.Color.blue())
        embed.description = "Comandos disponibles en TabaquitaGPT. Usa `!k` como prefijo."
        embed.add_field(name="!kping", value="Comprueba que el bot está respondiendo.", inline=False)
        embed.add_field(name="!krank", value="Muestra tu rango y nivel de permisos.", inline=False)
        embed.add_field(name="!kprofile", value="Muestra tu información de perfil y progreso.", inline=False)
        embed.add_field(name="!kloa", value="Marca tu estado como Leave of Absence.", inline=False)
        embed.add_field(name="!koperativo", value="Vuelve a dejar tu estado operativo.", inline=False)
        embed.add_field(name="!kkgaxp <miembro> <cantidad>", value="Agrega AXP a un miembro.", inline=False)
        embed.add_field(name="!kkraxp <miembro> <cantidad>", value="Remueve AXP de un miembro.", inline=False)
        embed.add_field(name="!kkgexp <miembro> <cantidad>", value="Agrega EXP a un miembro.", inline=False)
        embed.add_field(name="!kkrexp <miembro> <cantidad>", value="Remueve EXP de un miembro.", inline=False)
        embed.add_field(name="!kkseaxp <miembro> <cantidad>", value="Fija AXP de un miembro (solo HC).", inline=False)
        embed.add_field(name="!kksexp <miembro> <cantidad>", value="Fija EXP de un miembro (solo HC).", inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="profile")
    async def profile(self, ctx: commands.Context, target: discord.Member | None = None):
        member = target or ctx.author
        level = get_member_role_level(member)
        current_rank = None
        role_name = "Sin rango asignado"
        if level > 0:
            matching_roles = [role_id for role_id in ROLE_LEVELS if role_id in {role.id for role in member.roles}]
            current_rank = max(matching_roles, key=lambda role_id: ROLE_LEVELS[role_id], default=None)
            role_name = get_role_name(current_rank)

        stats = await stats_store.get_user_stats(str(member.id))
        next_rank = get_next_rank(current_rank)
        next_rank_label, select_text, _ = get_requirement_text(next_rank)

        req_lines = []
        if next_rank is None:
            req_lines.append("Rango máximo alcanzado")
        else:
            reqs = {
                LOW_RANK_ROLE_ID: (0.0, 0.0),
                MIDDLE_RANK_ROLE_ID: (20.0, 10.0),
                HIGH_RANK_ROLE_ID: (50.0, 25.0),
                HIGH_COMMAND_ROLE_ID: (100.0, 50.0),
            }
            target_axp, target_exp = reqs.get(next_rank, (0.0, 0.0))
            req_lines.append(format_progress_line(stats.get("axp", 0.0), target_axp, "AXP"))
            req_lines.append(format_progress_line(stats.get("exp", 0.0), target_exp, "EXP"))
            if select_text:
                req_lines.append(select_text)

        status = stats.get("status", "Operativo")
        if status not in {"Operativo", "Leave of Absence"}:
            status = "Operativo"

        embed = discord.Embed(title=f"📜 Perfil de {member.display_name}", color=discord.Color.blue())
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Rango actual", value=role_name, inline=True)
        embed.add_field(name="Siguiente rango", value=next_rank_label or "Ninguno", inline=True)
        embed.add_field(name="Requisitos", value="\n".join(req_lines), inline=False)
        embed.add_field(name="AXP", value=f"{stats.get('axp', 0.0):.0f}", inline=True)
        embed.add_field(name="EXP", value=f"{stats.get('exp', 0.0):.0f}", inline=True)
        embed.add_field(name="Estado", value=status, inline=True)
        embed.add_field(name="Cuenta creada", value=member.created_at.strftime("%d/%m/%Y"), inline=True)
        embed.add_field(name="Ingreso al servidor", value=member.joined_at.strftime("%d/%m/%Y"), inline=True)
        embed.set_footer(text="Bot hecho por TabaquitaOk")
        await ctx.send(embed=embed)

    @commands.command(name="loa")
    async def loa(self, ctx: commands.Context):
        await stats_store.set_status(str(ctx.author.id), "LoA")
        await ctx.send(f"✅ {ctx.author.mention} ahora está en LoA.")

    @commands.command(name="operativo")
    async def operativo(self, ctx: commands.Context):
        await stats_store.set_status(str(ctx.author.id), "Operativo")
        await ctx.send(f"✅ {ctx.author.mention} ahora está Operativo.")

    @commands.command(name="accept")
    @commands.has_any_role(HIGH_RANK_ROLE_ID, HIGH_COMMAND_ROLE_ID)
    async def accept(self, ctx: commands.Context, member: discord.Member, *, note: str | None = None):
        await ctx.send(f"✅ {member.mention} ha sido aceptado por {ctx.author.mention}.")

    @commands.command(name="meaccept")
    @commands.has_role(HIGH_COMMAND_ROLE_ID)
    async def meaccept(self, ctx: commands.Context, member: discord.Member):
        await ctx.send(f"✅ {member.mention} ha sido aceptado como miembro externo por {ctx.author.mention}.")

    @commands.command(name="kgaxp")
    async def kgaxp(self, ctx: commands.Context, member: discord.Member, amount: str):
        if not can_manage_xp(ctx.author):
            await ctx.send("❌ No tienes permiso para dar AXP.")
            return
        val = parse_amount(amount)
        if val is None or val <= 0:
            await ctx.send("❌ Cantidad inválida.")
            return
        try:
            await stats_store.add_axp(str(member.id), val)
            await ctx.send(f"✅ Añadidos {val} AXP a {member.mention}.")
            print(f"[INFO] kgaxp success: {ctx.author} gave {val} AXP to {member}")
        except Exception as exc:
            print(f"[ERROR] kgaxp failed: {exc}")
            await ctx.send("❌ Error interno al agregar AXP. Revisa los logs.")

    @commands.command(name="kraxp")
    async def kraxp(self, ctx: commands.Context, member: discord.Member, amount: str):
        if not can_manage_xp(ctx.author):
            await ctx.send("❌ No tienes permiso para quitar AXP.")
            return
        val = parse_amount(amount)
        if val is None or val <= 0:
            await ctx.send("❌ Cantidad inválida.")
            return
        try:
            await stats_store.remove_axp(str(member.id), val)
            await ctx.send(f"✅ Quitados {val} AXP a {member.mention}.")
            print(f"[INFO] kraxp success: {ctx.author} removed {val} AXP from {member}")
        except Exception as exc:
            print(f"[ERROR] kraxp failed: {exc}")
            await ctx.send("❌ Error interno al remover AXP. Revisa los logs.")

    @commands.command(name="kgexp")
    async def kgexp(self, ctx: commands.Context, member: discord.Member, amount: str):
        if not can_manage_xp(ctx.author):
            await ctx.send("❌ No tienes permiso para dar EXP.")
            return
        val = parse_amount(amount)
        if val is None or val <= 0:
            await ctx.send("❌ Cantidad inválida.")
            return
        try:
            await stats_store.add_exp(str(member.id), val)
            await ctx.send(f"✅ Añadidos {val} EXP a {member.mention}.")
            print(f"[INFO] kgexp success: {ctx.author} gave {val} EXP to {member}")
        except Exception as exc:
            print(f"[ERROR] kgexp failed: {exc}")
            await ctx.send("❌ Error interno al agregar EXP. Revisa los logs.")

    @commands.command(name="krexp")
    async def krexp(self, ctx: commands.Context, member: discord.Member, amount: str):
        if not can_manage_xp(ctx.author):
            await ctx.send("❌ No tienes permiso para quitar EXP.")
            return
        val = parse_amount(amount)
        if val is None or val <= 0:
            await ctx.send("❌ Cantidad inválida.")
            return
        try:
            await stats_store.remove_exp(str(member.id), val)
            await ctx.send(f"✅ Quitados {val} EXP a {member.mention}.")
            print(f"[INFO] krexp success: {ctx.author} removed {val} EXP from {member}")
        except Exception as exc:
            print(f"[ERROR] krexp failed: {exc}")
            await ctx.send("❌ Error interno al remover EXP. Revisa los logs.")

    @commands.command(name="kseaxp")
    async def kseaxp(self, ctx: commands.Context, member: discord.Member, amount: str):
        if not is_high_command(ctx.author):
            await ctx.send("❌ Solo HC puede usar este comando.")
            return
        val = parse_amount(amount)
        if val is None or val < 0:
            await ctx.send("❌ Cantidad inválida.")
            return
        try:
            await stats_store.set_axp(str(member.id), val)
            await ctx.send(f"✅ AXP de {member.mention} fijada a {val}.")
        except Exception as exc:
            print(f"[ERROR] kseaxp failed: {exc}")
            await ctx.send("❌ Error interno al fijar AXP. Revisa los logs.")

    @commands.command(name="ksexp")
    async def ksexp(self, ctx: commands.Context, member: discord.Member, amount: str):
        if not is_high_command(ctx.author):
            await ctx.send("❌ Solo HC puede usar este comando.")
            return
        val = parse_amount(amount)
        if val is None or val < 0:
            await ctx.send("❌ Cantidad inválida.")
            return
        try:
            await stats_store.set_exp(str(member.id), val)
            await ctx.send(f"✅ EXP de {member.mention} fijada a {val}.")
        except Exception as exc:
            print(f"[ERROR] ksexp failed: {exc}")
            await ctx.send("❌ Error interno al fijar EXP. Revisa los logs.")


def setup(bot: commands.Bot):
    bot.add_cog(GeneralCog(bot))
