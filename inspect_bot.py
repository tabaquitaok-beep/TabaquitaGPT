import os
import sys
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from bot import bot
print('PREFIXES:', bot.command_prefix)
print('COMMANDS:', sorted(c.name for c in bot.commands))
