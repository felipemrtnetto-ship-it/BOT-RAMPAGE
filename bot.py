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

CANAL_ID = 1570446068490043442  # ID oficial do canal de alerta
TIMEZONE = pytz.timezone("America/Sao_Paulo")
ARQUIVO_ESTADO = "estado.json"

intents = discord.Intents.default()
bot = discord.Client(intents=intents)

lock = asyncio.Lock()
ultimo_minuto_processado = None

# ===============================
# BOSSES (TABELA OFICIAL)
# ===============================

BOSSES = [
    ("Blood Wizard", "18:10", None, "Devias ou /pvp2 (159,39)"),
    ("Crusher Skeleton", "19:05", None, "Aleatório em Lorencia"),
    ("Necromancer", "19:40", None, "Elbeland 2 ou /devias4 (30,39)"),
    ("Selupan", "20:10", None, "Raklion ou /pvp4 (174,200)"),
    ("Galia Black", "20:30", None, "Lost Tower (165, 76)"),
    ("Skull Reaper", "20:50", None, "Dungeon (91,236)"),
    ("Gwyn, o Senhor das Cinzas", "22:10", None, "Dungeon 3 (25,72)"),
    ("Hellmaine", "22:30", None, "Aida 2 (119,107)"),
    ("Balgass", "23:00", [2, 5], "Crywolf / Local do Evento"), # Apenas Quarta (2) e Sábado (5)
    ("Yhorm", "23:40", None, "/lorencia1 (22,46)"),
    ("Zorlak", "01:10", None, "Aleatório em Lorencia"),
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
# EMBEDS COM CONTAGEM REGRESSIVA DINÂMICA
# ===============================

def criar_embed_pre_alerta(nome, local, hora, timestamp_unix):
    return discord.Embed(
        title=f"⚠️ PRÉ-ALERTA: {nome}",
        description=(
            f"⏰ **Horário:** {hora}\n"
            f"⏳ **Inicia:** <t:{timestamp_unix}:R>\n"
            f"📍 **Local:** {local}\n\n"
            "*Preparem-se, o boss vai nascer em breve!*"
        ),
        color=0x3498db
    )

def criar_embed_alerta(nome, local, hora, timestamp_unix):
    return discord.Embed(
        title=f"🔥 BOSS {nome} NASCENDO! 🔥",
        description=(
            f"⏰ **Horário:** {hora}\n"
            f"⏳ **Tempo Restante:** <t:{timestamp_unix}:R>\n"
            f"📍 **Local:** {local}\n\n"
            "*Corram para o local!*"
        ),
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

        canal = bot.get_channel(CANAL_ID)
        if not canal:
            try:
                canal = await bot.fetch_channel(CANAL_ID)
            except discord.DiscordException:
                return

        for evento in BOSSES:
            nome, horario, dias, local = evento

            # Valida se o boss acontece no dia da semana atual
            if dias is not None and agora.weekday() not in dias:
                continue

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
            data_str = agora.strftime('%Y-%m-%d')
            timestamp_unix = int(hora_boss.timestamp())

            # 1. PRÉ-ALERTA DE 30 MINUTOS (entre 1740 e 1800 segundos)
            chave_30 = f"{nome}_{horario}_{data_str}_30"
            if 1740 <= diferenca <= 1800:
                if not estado.get(chave_30):
                    embed = criar_embed_pre_alerta(nome, local, horario, timestamp_unix)
                    await canal.send(embed=embed)
                    estado[chave_30] = True
                    salvar_estado(estado)

            # 2. ALERTA PRINCIPAL DE 10 MINUTOS (entre 0 e 600 segundos)
            chave_10 = f"{nome}_{horario}_{data_str}_10"
            if 0 < diferenca <= 600:
                if not estado.get(chave_10):
                    embed = criar_embed_alerta(nome, local, horario, timestamp_unix)
                    await canal.send(
                        content="@everyone",
                        embed=embed,
                        allowed_mentions=discord.AllowedMentions(everyone=True)
                    )
                    estado[chave_10] = True
                    salvar_estado(estado)

# ===============================
# READY
# ===============================

@bot.event
async def on_ready():
    print(f"🛡️ Bot de Alertas online como {bot.user}")
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
