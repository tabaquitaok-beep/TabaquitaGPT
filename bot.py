import os
import discord
from discord.ext import commands
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

# Cargar variables del archivo .env
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

# Conexión a MongoDB
db_client = AsyncIOMotorClient(MONGO_URI)
db = db_client["TabaquitaGPT"] # Nombre de tu base de datos

# Configuración del Bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"¡Conectado como {bot.user}!")
    # Prueba rápida de conexión a la base de datos
    try:
        await db_client.admin.command('ping')
        print("¡Conexión exitosa a MongoDB Atlas!")
    except Exception as e:
        print(f"Error al conectar a MongoDB: {e}")

@bot.command()
async def ping(ctx):
    await ctx.send("¡Pong! TabaquitaGPT está en línea y funcionando.")

# Ejecutar el bot
bot.run(TOKEN)