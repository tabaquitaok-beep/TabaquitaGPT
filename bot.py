import os
import asyncio
import sqlite3
import threading
import time
import datetime
import urllib.parse
from aiohttp import web
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
MONGO_URI = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI") or os.getenv("DATABASE_URL")


def _derive_mongo_db_name(uri: str | None) -> str | None:
    if not uri:
        return None
    try:
        parsed = urllib.parse.urlparse(uri)
        if parsed.path:
            name = parsed.path.lstrip('/')
            return name if name else None
    except Exception:
        pass
    return None

MONGO_DB_NAME = os.getenv("MONGO_DB_NAME") or _derive_mongo_db_name(MONGO_URI) or "TabaquitaGPT"
STATS_COLLECTION_NAME = "user_stats"

# Jerarquía de roles: abajo menos permisos, arriba más permisos.
HIGH_COMMAND_ROLE_ID = 1496612684345512119
HIGH_RANK_ROLE_ID = 1495961100053778434
MIDDLE_RANK_ROLE_ID = 1495959303113412750
LOW_RANK_ROLE_ID = 1494162106725961849
MIEMBRO_EXTERNO_ROLE_ID = 1516093644720046150
BOT_ROLE_ID = 1492155946842198086
WAIT_ROLE_ID = 1516095262903242833
STATUS_CHANNEL_ID = 1510791864566022154

ROLE_LEVELS = {
    WAIT_ROLE_ID: 0,
    BOT_ROLE_ID: 1,
    MIEMBRO_EXTERNO_ROLE_ID: 2,
    LOW_RANK_ROLE_ID: 3,
    MIDDLE_RANK_ROLE_ID: 4,
    HIGH_RANK_ROLE_ID: 5,
    HIGH_COMMAND_ROLE_ID: 6,
}


def get_member_role_level(member: discord.Member) -> int:
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
        WAIT_ROLE_ID: "Wait",
        BOT_ROLE_ID: "Bot",
        MIEMBRO_EXTERNO_ROLE_ID: "Miembro externo",
        LOW_RANK_ROLE_ID: "Low Rank",
        MIDDLE_RANK_ROLE_ID: "Middle Rank",
        HIGH_RANK_ROLE_ID: "High Rank",
        HIGH_COMMAND_ROLE_ID: "High Command",
    }
    return names.get(role_id, "Sin rango")


async def get_status_channel() -> discord.TextChannel | None:
    channel = bot.get_channel(STATUS_CHANNEL_ID)
    if channel is not None:
        return channel
    try:
        return await bot.fetch_channel(STATUS_CHANNEL_ID)
    except Exception:
        return None


async def send_status_embed(title: str, fields: list[tuple[str, str, bool]], color: discord.Color):
    channel = await get_status_channel()
    if channel is None:
        return
    embed = discord.Embed(title=title, color=color, timestamp=datetime.datetime.utcnow())
    for name, value, inline in fields:
        embed.add_field(name=name, value=value, inline=inline)
    await channel.send(embed=embed)


# --- Simple StatsStore usando SQLite (persistencia ligera) ---
class StatsStore:
    def __init__(self, path: str = "data/user_stats.db"):
        self.mongo_client = None
        self.db = None
        self.collection = None
        self.use_mongo = bool(MONGO_URI)

        if self.use_mongo:
            try:
                from motor.motor_asyncio import AsyncIOMotorClient

                self.mongo_client = AsyncIOMotorClient(
                    MONGO_URI,
                    serverSelectionTimeoutMS=5000,
                    connectTimeoutMS=5000,
                )
                self.db = self.mongo_client.get_database(MONGO_DB_NAME)
                self.collection = self.db[STATS_COLLECTION_NAME]
            except Exception:
                print("[WARN] No se pudo inicializar MongoDB; usando SQLite en su lugar.")
                self.use_mongo = False

        self.path = os.path.abspath(path)
        d = os.path.dirname(self.path)
        if d:
            os.makedirs(d, exist_ok=True)
        self._lock = threading.Lock()
        self._ensure_table()

    def _ensure_table(self):
        with self._lock:
            conn = sqlite3.connect(self.path)
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_stats (
                        _id TEXT PRIMARY KEY,
                        axp REAL NOT NULL,
                        exp REAL NOT NULL,
                        messages INTEGER NOT NULL,
                        status TEXT NOT NULL
                    )
                    """
                )
                conn.commit()
            finally:
                conn.close()

    def _get_sync(self, user_id: str) -> dict:
        with self._lock:
            conn = sqlite3.connect(self.path)
            try:
                cur = conn.execute("SELECT _id, axp, exp, messages, status FROM user_stats WHERE _id = ?", (user_id,))
                row = cur.fetchone()
                if not row:
                    return {"_id": user_id, "axp": 0.0, "exp": 0.0, "messages": 0, "status": "Operativo"}
                return {"_id": row[0], "axp": float(row[1]), "exp": float(row[2]), "messages": int(row[3]), "status": row[4]}
            finally:
                conn.close()

    def _upsert_sync(self, stats: dict):
        with self._lock:
            conn = sqlite3.connect(self.path)
            try:
                conn.execute(
                    """
                    INSERT INTO user_stats(_id, axp, exp, messages, status)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(_id) DO UPDATE SET
                        axp=excluded.axp,
                        exp=excluded.exp,
                        messages=excluded.messages,
                        status=excluded.status
                    """,
                    (
                        stats["_id"],
                        float(stats.get("axp", 0.0)),
                        float(stats.get("exp", 0.0)),
                        int(stats.get("messages", 0)),
                        stats.get("status", "Operativo"),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    async def get_user_stats(self, user_id: str) -> dict:
        if self.use_mongo and self.collection is not None:
            try:
                user_id = str(user_id)
                doc = await self.collection.find_one({"_id": user_id})
                if doc is None:
                    doc = {"_id": user_id, "axp": 0.0, "exp": 0.0, "messages": 0, "status": "Operativo"}
                    await self.collection.insert_one(doc)
                    return doc
                doc.setdefault("axp", 0.0)
                doc.setdefault("exp", 0.0)
                doc.setdefault("messages", 0)
                doc.setdefault("status", "Operativo")
                return doc
            except Exception as e:
                print(f"[WARN] Error Mongo get_user_stats: {e}; cayendo a SQLite.")
                self.use_mongo = False

        return await asyncio.to_thread(self._get_sync, user_id)

    async def update_user_stats(self, user_id: str, updates: dict):
        if self.use_mongo and self.collection is not None:
            try:
                user_id = str(user_id)
                default = {"_id": user_id, "axp": 0.0, "exp": 0.0, "messages": 0, "status": "Operativo"}
                update_data = {"$set": updates, "$setOnInsert": default}
                await self.collection.update_one({"_id": user_id}, update_data, upsert=True)
                return
            except Exception as e:
                print(f"[WARN] Error Mongo update_user_stats: {e}; cayendo a SQLite.")
                self.use_mongo = False

        current = await self.get_user_stats(user_id)
        current.update(updates)
        await asyncio.to_thread(self._upsert_sync, current)

    async def add_axp(self, user_id: str, amount: float):
        stats = await self.get_user_stats(user_id)
        stats["axp"] = float(stats.get("axp", 0.0)) + float(amount)
        await asyncio.to_thread(self._upsert_sync, stats)

    async def remove_axp(self, user_id: str, amount: float):
        stats = await self.get_user_stats(user_id)
        stats["axp"] = max(0.0, float(stats.get("axp", 0.0)) - float(amount))
        await asyncio.to_thread(self._upsert_sync, stats)

    async def add_exp(self, user_id: str, amount: float):
        stats = await self.get_user_stats(user_id)
        stats["exp"] = float(stats.get("exp", 0.0)) + float(amount)
        await asyncio.to_thread(self._upsert_sync, stats)

    async def remove_exp(self, user_id: str, amount: float):
        stats = await self.get_user_stats(user_id)
        stats["exp"] = max(0.0, float(stats.get("exp", 0.0)) - float(amount))
        await asyncio.to_thread(self._upsert_sync, stats)

    async def set_axp(self, user_id: str, amount: float):
        stats = await self.get_user_stats(user_id)
        stats["axp"] = float(amount)
        await asyncio.to_thread(self._upsert_sync, stats)

    async def set_exp(self, user_id: str, amount: float):
        stats = await self.get_user_stats(user_id)
        stats["exp"] = float(amount)
        await asyncio.to_thread(self._upsert_sync, stats)

    async def set_status(self, user_id: str, status: str):
        stats = await self.get_user_stats(user_id)
        stats["status"] = status
        await asyncio.to_thread(self._upsert_sync, stats)


# Instancia global
stats_store = StatsStore()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True
# Usar solo el prefijo "!k" (acepta tanto "!kcmd" como "!k cmd")
bot = commands.Bot(command_prefix=["!k ", "!k"], intents=intents)

# In-memory trackers
voice_start: dict[int, float] = {}


@bot.event
async def on_ready():
    print(f"¡Conectado como {bot.user}!")
    if stats_store.use_mongo and stats_store.mongo_client is not None:
        try:
            await stats_store.mongo_client.admin.command('ping')
            print("¡Conexión exitosa a MongoDB Atlas!")
        except Exception as e:
            print(f"Error al conectar a MongoDB: {e}; cayendo a SQLite.")
            stats_store.use_mongo = False
    else:
        print("MongoDB no configurado; usando SQLite para persistencia.")

@bot.command()
async def ping(ctx):
    await ctx.send("¡Pong! TabaquitaGPT está en línea y funcionando.")


@bot.event
async def on_member_join(member: discord.Member):
    if member.bot:
        return
    await send_status_embed(
        "Nuevo miembro",
        [
            ("Usuario", f"{member.mention} ({member.id})", False),
            ("Cuenta creada", member.created_at.strftime("%d/%m/%Y %H:%M:%S UTC"), False),
        ],
        discord.Color.green(),
    )

@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    if member.bot:
        return

    entered = before.channel is None and after.channel is not None
    left = before.channel is not None and after.channel is None
    switched = before.channel is not None and after.channel is not None and before.channel.id != after.channel.id

    if entered:
        voice_start[member.id] = time.time()
        await send_status_embed(
            "Union a VC",
            [
                ("Usuario", f"{member.mention} ({member.id})", False),
                ("Ubicacion", after.channel.name, False),
                ("Fecha y Hora", datetime.datetime.utcnow().strftime("%d/%m/%Y %H:%M:%S UTC"), False),
                ("Iniciando trackeo de VC", "", False),
            ],
            discord.Color.green(),
        )
        return

    if switched:
        start = voice_start.get(member.id)
        if start is None:
            voice_start[member.id] = time.time()
            return
        duration = time.time() - start
        gained = int(duration // 3600)
        if gained > 0:
            await stats_store.add_axp(str(member.id), float(gained))
        voice_start[member.id] = time.time()
        await send_status_embed(
            "Cambio de VC",
            [
                ("Usuario", f"{member.mention} ({member.id})", False),
                ("VC Anterior", before.channel.name, False),
                ("VC Nuevo", after.channel.name, False),
                ("Tiempo en el VC", f"{int(duration // 3600):02d}:{int((duration % 3600) // 60):02d}:{int(duration % 60):02d}", False),
                ("AXP Conseguida", str(gained), False),
                ("Resumiendo trackeo exitosamente", "", False),
            ],
            discord.Color.blue(),
        )
        return

    if left:
        start = voice_start.pop(member.id, None)
        if start is None:
            return
        duration = time.time() - start
        gained = int(duration // 3600)
        if gained > 0:
            await stats_store.add_axp(str(member.id), float(gained))
        await send_status_embed(
            "Salida de VC",
            [
                ("Usuario", f"{member.mention} ({member.id})", False),
                ("Ubicacion", before.channel.name, False),
                ("Fecha y Hora", datetime.datetime.utcnow().strftime("%d/%m/%Y %H:%M:%S UTC"), False),
                ("Estancia en el VC", f"{int(duration // 3600):02d}:{int((duration % 3600) // 60):02d}:{int(duration % 60):02d}", False),
                ("AXP Conseguida", str(gained), False),
            ],
            discord.Color.red(),
        )


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # Count messages for AXP per 10 messages -> 0.1 AXP
    if message.guild is not None:
        try:
            user_id = str(message.author.id)
            stats = await stats_store.get_user_stats(user_id)
            msgs = int(stats.get("messages", 0)) + 1
            award = 0.0
            if msgs >= 10:
                give_times = msgs // 10
                award = 0.1 * give_times
                msgs = msgs % 10

            await stats_store.update_user_stats(user_id, {"messages": msgs})
            if award > 0:
                await stats_store.add_axp(user_id, award)
        except Exception as e:
            try:
                print(f"[LOG] on_message tracking error: {e}")
            except Exception:
                pass

    await bot.process_commands(message)

@bot.command(name="rank")
async def rank(ctx, target: discord.Member = None):
    member = target or ctx.author
    level = get_member_role_level(member)

    if level <= 0:
        role_name = "Sin rango asignado"
    else:
        matching_roles = [role_id for role_id in ROLE_LEVELS if role_id in {role.id for role in member.roles}]
        highest_role_id = max(matching_roles, key=lambda role_id: ROLE_LEVELS[role_id], default=0)
        role_name = get_role_name(highest_role_id)

    await ctx.send(
        f"{member.mention} tiene nivel de rango {level} ({role_name})."
    )

@bot.command(name="ayuda")
async def help_command(ctx):
    embed = discord.Embed(title="📘 Ayuda básica", color=discord.Color.blue())
    embed.description = "Comandos disponibles en TabaquitaGPT."
    embed.add_field(name="!kping", value="Comprueba que el bot está respondiendo.", inline=False)
    embed.add_field(name="!krank", value="Muestra tu rango y nivel de permisos.", inline=False)
    embed.add_field(name="!kprofile", value="Muestra información básica del usuario.", inline=False)
    embed.add_field(name="!kloa", value="Marca tu estado como Leave of Absence.", inline=False)
    embed.add_field(name="!koperativo", value="Vuelve a dejar tu estado operativo.", inline=False)
    await ctx.send(embed=embed)

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


def build_progress_bar(current: float, target: float) -> str:
    if target <= 0:
        return "████████"
    filled = min(8, max(0, int((current / target) * 8)))
    return "█" * filled + "▒" * (8 - filled)


def format_progress_line(current: float, target: float, label: str) -> str:
    bar = build_progress_bar(current, target)
    return f"`{label}` {bar} {int(current)}/{int(target)}"


@bot.command(name="profile")
async def profile(ctx, target: discord.Member = None):
    member = target or ctx.author
    level = get_member_role_level(member)
    role_name = "Sin rango asignado"
    current_rank = None
    if level > 0:
        matching_roles = [role_id for role_id in ROLE_LEVELS if role_id in {role.id for role in member.roles}]
        current_rank = max(matching_roles, key=lambda role_id: ROLE_LEVELS[role_id], default=None)
        role_name = get_role_name(current_rank)

    stats = await stats_store.get_user_stats(str(member.id))
    next_rank = get_next_rank(current_rank)
    next_rank_label, select_text, fields_order = get_requirement_text(next_rank)

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

@bot.command(name="loa")
async def loa(ctx):
    await stats_store.set_status(str(ctx.author.id), "LoA")
    await ctx.send(f"✅ {ctx.author.mention} ahora está en LoA.")

@bot.command(name="operativo")
async def operativo(ctx):
    await stats_store.set_status(str(ctx.author.id), "Operativo")
    await ctx.send(f"✅ {ctx.author.mention} ahora está Operativo.")

@bot.command(name="accept")
@commands.has_any_role(HIGH_RANK_ROLE_ID, HIGH_COMMAND_ROLE_ID)
async def accept(ctx, member: discord.Member, *, note: str = None):
    await ctx.send(f"✅ {member.mention} ha sido aceptado por {ctx.author.mention}.")

@bot.command(name="meaccept")
@commands.has_role(HIGH_COMMAND_ROLE_ID)
async def meaccept(ctx, member: discord.Member):
    await ctx.send(f"✅ {member.mention} ha sido aceptado como miembro externo por {ctx.author.mention}.")


# ------------------ Comandos de gestión de AXP/EXP ------------------
def _parse_amount(text: str) -> float | None:
    try:
        return float(text.replace(',', '.'))
    except Exception:
        return None

def _can_manage_xp(author: discord.Member) -> bool:
    return author.guild_permissions.administrator or any(r.id in {HIGH_RANK_ROLE_ID, HIGH_COMMAND_ROLE_ID} for r in author.roles)

def _is_high_command(author: discord.Member) -> bool:
    return author.guild_permissions.administrator or any(r.id == HIGH_COMMAND_ROLE_ID for r in author.roles)


@bot.command(name="kgaxp")
async def kgaxp(ctx, member: discord.Member, amount: str):
    if not _can_manage_xp(ctx.author):
        await ctx.send("❌ No tienes permiso para dar AXP.")
        return
    val = _parse_amount(amount)
    if val is None or val <= 0:
        await ctx.send("❌ Cantidad inválida.")
        return
    await stats_store.add_axp(str(member.id), val)
    await ctx.send(f"✅ Añadidos {val} AXP a {member.mention}.")


@bot.command(name="kraxp")
async def kraxp(ctx, member: discord.Member, amount: str):
    if not _can_manage_xp(ctx.author):
        await ctx.send("❌ No tienes permiso para quitar AXP.")
        return
    val = _parse_amount(amount)
    if val is None or val <= 0:
        await ctx.send("❌ Cantidad inválida.")
        return
    await stats_store.remove_axp(str(member.id), val)
    await ctx.send(f"✅ Quitados {val} AXP a {member.mention}.")


@bot.command(name="kgexp")
async def kgexp(ctx, member: discord.Member, amount: str):
    if not _can_manage_xp(ctx.author):
        await ctx.send("❌ No tienes permiso para dar EXP.")
        return
    val = _parse_amount(amount)
    if val is None or val <= 0:
        await ctx.send("❌ Cantidad inválida.")
        return
    await stats_store.add_exp(str(member.id), val)
    await ctx.send(f"✅ Añadidos {val} EXP a {member.mention}.")


@bot.command(name="krexp")
async def krexp(ctx, member: discord.Member, amount: str):
    if not _can_manage_xp(ctx.author):
        await ctx.send("❌ No tienes permiso para quitar EXP.")
        return
    val = _parse_amount(amount)
    if val is None or val <= 0:
        await ctx.send("❌ Cantidad inválida.")
        return
    await stats_store.remove_exp(str(member.id), val)
    await ctx.send(f"✅ Quitados {val} EXP a {member.mention}.")


@bot.command(name="kseaxp")
async def kseaxp(ctx, member: discord.Member, amount: str):
    if not _is_high_command(ctx.author):
        await ctx.send("❌ Solo HC puede usar este comando.")
        return
    val = _parse_amount(amount)
    if val is None or val < 0:
        await ctx.send("❌ Cantidad inválida.")
        return
    await stats_store.set_axp(str(member.id), val)
    await ctx.send(f"✅ AXP de {member.mention} fijada a {val}.")


@bot.command(name="ksexp")
async def ksexp(ctx, member: discord.Member, amount: str):
    if not _is_high_command(ctx.author):
        await ctx.send("❌ Solo HC puede usar este comando.")
        return
    val = _parse_amount(amount)
    if val is None or val < 0:
        await ctx.send("❌ Cantidad inválida.")
        return
    await stats_store.set_exp(str(member.id), val)
    await ctx.send(f"✅ EXP de {member.mention} fijada a {val}.")

async def handle(request):
    return web.Response(text="¡TabaquitaGPT está activo y funcionando!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Servidor web falso corriendo en el puerto {port}")

async def main():
    await asyncio.gather(
        start_web_server(),
        bot.start(TOKEN)
    )

if __name__ == "__main__":
    asyncio.run(main())