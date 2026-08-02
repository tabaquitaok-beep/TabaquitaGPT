import os
import asyncio
from aiohttp import web
import discord
from discord.ext import commands
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

# Jerarquía de roles: abajo menos permisos, arriba más permisos.
HIGH_COMMAND_ROLE_ID = 1496612684345512119
HIGH_RANK_ROLE_ID = 1495961100053778434
MIDDLE_RANK_ROLE_ID = 1495959303113412750
LOW_RANK_ROLE_ID = 1494162106725961849
MIEMBRO_EXTERNO_ROLE_ID = 1516093644720046150
BOT_ROLE_ID = 1492155946842198086
WAIT_ROLE_ID = 1516095262903242833

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


db_client = AsyncIOMotorClient(MONGO_URI)
db = db_client["TabaquitaGPT"]

intents = discord.Intents.default()
intents.message_content = True
# Usar solo el prefijo "!k" (acepta tanto "!kcmd" como "!k cmd")
bot = commands.Bot(command_prefix=["!k ", "!k"], intents=intents)

@bot.event
async def on_ready():
    print(f"¡Conectado como {bot.user}!")
    try:
        await db_client.admin.command('ping')
        print("¡Conexión exitosa a MongoDB Atlas!")
    except Exception as e:
        print(f"Error al conectar a MongoDB: {e}")

@bot.command()
async def ping(ctx):
    await ctx.send("¡Pong! TabaquitaGPT está en línea y funcionando.")

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
    embed.add_field(name="!ping", value="Comprueba que el bot está respondiendo.", inline=False)
    embed.add_field(name="!rank", value="Muestra tu rango y nivel de permisos.", inline=False)
    embed.add_field(name="!profile", value="Muestra información básica del usuario.", inline=False)
    embed.add_field(name="!loa", value="Marca tu estado como Leave of Absence.", inline=False)
    embed.add_field(name="!operativo", value="Vuelve a dejar tu estado operativo.", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="profile")
async def profile(ctx, target: discord.Member = None):
    member = target or ctx.author
    level = get_member_role_level(member)
    role_name = "Sin rango asignado"
    if level > 0:
        matching_roles = [role_id for role_id in ROLE_LEVELS if role_id in {role.id for role in member.roles}]
        highest_role_id = max(matching_roles, key=lambda role_id: ROLE_LEVELS[role_id], default=0)
        role_name = get_role_name(highest_role_id)

    embed = discord.Embed(title=f"📜 Perfil de {member.display_name}", color=discord.Color.blue())
    embed.add_field(name="Rango", value=role_name, inline=True)
    embed.add_field(name="Nivel", value=str(level), inline=True)
    embed.add_field(name="ID", value=str(member.id), inline=False)
    embed.add_field(name="Cuenta creada", value=member.created_at.strftime("%d/%m/%Y"), inline=True)
    embed.add_field(name="Entró al servidor", value=member.joined_at.strftime("%d/%m/%Y"), inline=True)
    await ctx.send(embed=embed)

@bot.command(name="loa")
async def loa(ctx):
    await ctx.send(f"✅ {ctx.author.mention} ha marcado su estado como Leave of Absence.")

@bot.command(name="operativo")
async def operativo(ctx):
    await ctx.send(f"✅ {ctx.author.mention} está ahora Operativo.")

@bot.command(name="accept")
@commands.has_any_role(HIGH_RANK_ROLE_ID, HIGH_COMMAND_ROLE_ID)
async def accept(ctx, member: discord.Member, *, note: str = None):
    await ctx.send(f"✅ {member.mention} ha sido aceptado por {ctx.author.mention}.")

@bot.command(name="meaccept")
@commands.has_role(HIGH_COMMAND_ROLE_ID)
async def meaccept(ctx, member: discord.Member):
    await ctx.send(f"✅ {member.mention} ha sido aceptado como miembro externo por {ctx.author.mention}.")

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