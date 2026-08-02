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

db_client = AsyncIOMotorClient(MONGO_URI)
db = db_client["TabaquitaGPT"]

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=["!k", "!"], intents=intents)

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