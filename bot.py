import discord
from discord.ext import tasks
import asyncio
import pytz
from datetime import datetime, timedelta
import json
import os
import time

# ===============================
# CONFIG
# ===============================

TOKEN = os.getenv("TOKEN")

if not TOKEN:
    raise ValueError("❌ TOKEN não configurado na variável de ambiente.")

CANAL_NOME = "⚠️-alerta-dos-boss"
TIMEZONE = pytz.timezone("America/Sao_Paulo")
ARQUIVO_ESTADO = "estado.json"

intents = discord.Intents.default()
bot = discord.Client(intents=intents)

lock = asyncio.Lock()
ultimo_minuto_processado = None

# ===============================
# BOSSES
# ===============================

BOSSES = [
    ("Galia Black", "10:45", "Lost Tower (165, 76)"),
    ("Kundun", "13:10", "Kalima 6 - Lost Map +6"),
    ("Kundun", "15:10", "Kalima 6 - Lost Map +6"),
    ("Galia Black", "16:45", "Lost Tower (165, 76)"),
    ("Blood Wizard", "18:10", "Devias ou /pvp2 (159,39)"),
    ("Crusher Skeleton", "19:05", "Aleatório em Lorencia"),
    ("Necromancer", "19:40", "Elbeland 2 ou /devias4 (30,39)"),
    ("Selupan", "20:10", "Raklion ou /pvp4 (174,200)"),
    ("Skull Reaper", "20:50", "Dungeon (91,236)"),
    ("Gywen", "22:10", "Dungeon 3 (25,72)"),
    ("HellMaine", "22:30", "Aida 2 (119,107)"),
    ("Yorm", "23:40", "/lorencia1 (22,46)"),
    ("Zorlak", "01:10", "Aleatório em Lorencia"),
]

# ===============================
# ESTADO
# ===============================

def carregar_estado():
    if not os.path.exists(ARQUIVO_ESTADO):
        return {}
    with open(ARQUIVO_ESTADO, "r") as f:
        return json.load(f)

def salvar_estado(estado):
    with open(ARQUIVO_ESTADO, "w") as f:
        json.dump(estado, f)

estado = carregar_estado()

# ===============================
# EMBED
# ===============================

def criar_embed(nome, local, hora):
    return discord.Embed(
        title=f"🔥 BOSS {nome} EM 10 MINUTOS! 🔥",
        description=f"Horário - {hora}\nLocal - {local}",
        color=0xffa500
    )

# ===============================
# LOOP PRINCIPAL
# ===============================

@tasks.loop(seconds=30)
async def verificar_boss():
    global ultimo_minuto_processado
    async with lock:

        agora = datetime.now(TIMEZONE)
        minuto_atual = agora.strftime("%Y-%m-%d %H:%M")

        if minuto_atual == ultimo_minuto_processado:
            return

        ultimo_minuto_processado = minuto_atual

        # Reset diário às 03:00
        if agora.strftime("%H:%M") == "03:00":
            estado.clear()
            salvar_estado(estado)

        canal = discord.utils.get(bot.get_all_channels(), name=CANAL_NOME)
        if not canal:
            return

        for nome, horario, local in BOSSES:
            hora_boss = datetime.strptime(horario, "%H:%M")
            hora_boss = TIMEZONE.localize(
                datetime(
                    agora.year,
                    agora.month,
                    agora.day,
                    hora_boss.hour,
                    hora_boss.minute
                )
            )

            if hora_boss < agora:
                hora_boss += timedelta(days=1)

            diferenca = (hora_boss - agora).total_seconds()
            chave = f"{nome}_{horario}_10"

            if 0 < diferenca <= 600:
                if not estado.get(chave):

                    embed = criar_embed(nome, local, horario)

                    await canal.send(
                        content="@everyone",
                        embed=embed,
                        allowed_mentions=discord.AllowedMentions(everyone=True)
                    )

                    estado[chave] = True
                    salvar_estado(estado)

# ===============================
# READY
# ===============================

@bot.event
async def on_ready():
    print(f"🛡️ Bot online como {bot.user}")
    if not verificar_boss.is_running():
        verificar_boss.start()

# ===============================
# RECONEXÃO AUTOMÁTICA
# ===============================

if __name__ == "__main__":
    while True:
        try:
            bot.run(TOKEN)
        except Exception:
            print("⚠️ Reconectando em 10 segundos...")
            time.sleep(10)
