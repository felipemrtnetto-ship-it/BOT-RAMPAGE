import discord
from discord.ext import commands, tasks
import os
from datetime import datetime, timedelta
import pytz
import json
import asyncio
import sys
import traceback

# ===============================
# TOKEN SEGURO
# ===============================

TOKEN = os.getenv("TOKEN")

if not TOKEN:
    raise ValueError("❌ TOKEN não configurado na variável de ambiente.")

# ===============================
# CONFIGURAÇÕES
# ===============================

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

CANAL_NOME = "⚠️-alerta-dos-boss"
FUSO = pytz.timezone("America/Sao_Paulo")
ARQUIVO_ESTADO = "estado.json"

lock_envio = asyncio.Lock()
ultimo_minuto_processado = None
mensagem_fixa = None

# ===============================
# LOG PROFISSIONAL
# ===============================

def log(msg):
    agora = datetime.now().strftime("%d/%m %H:%M:%S")
    print(f"[{agora}] {msg}")

# ===============================
# SALVAR ESTADO
# ===============================

def carregar_estado():
    if os.path.exists(ARQUIVO_ESTADO):
        with open(ARQUIVO_ESTADO, "r") as f:
            return set(json.load(f))
    return set()

def salvar_estado():
    with open(ARQUIVO_ESTADO, "w") as f:
        json.dump(list(avisados), f)

avisados = carregar_estado()

# ===============================
# BOSSES
# ===============================

bosses = [
    ("02:20", "Galia Black", "Lost Tower (165, 76)"),
    ("13:10", "Kundun", "Kalima 6 - Lost Map +6"),
    ("15:10", "Kundun", "Kalima 6 - Lost Map +6"),
    ("16:45", "Galia Black", "Lost Tower (165, 76)"),
    ("18:10", "Blood Wizard", "Devias ou /pvp2 (159,39)"),
    ("19:05", "Crusher Skeleton", "Aleatório em Lorencia"),
    ("19:40", "Necromancer", "Elbeland 2 ou /devias4 (30,39)"),
    ("20:10", "Selupan", "Raklion ou /pvp4 (174,200)"),
    ("20:50", "Skull Reaper", "Dungeon (91,236)"),
    ("22:10", "Gywen", "Dungeon 3 (25,72)"),
    ("22:30", "HellMaine", "Aida 2 (119,107)"),
    ("23:40", "Yorm", "/lorencia1 (22,46)"),
    ("01:10", "Zorlak", "Aleatório em Lorencia"),
]

# ===============================
# EMBED
# ===============================

def criar_embed(nome, local, horario, status, tempo=None):
    cores = {
        "NASCEU": 0xff0000,
        "EM 5 MINUTOS": 0xffa500,
        "PRÓXIMO": 0x00bfff
    }

    embed = discord.Embed(
        title=f"🔥 BOSS {nome} {status}! 🔥",
        color=cores.get(status, 0xffffff)
    )

    embed.add_field(name="🕒 Horário", value=f"**{horario}**", inline=False)
    embed.add_field(name="📍 Local", value=f"**{local}**", inline=False)

    if tempo:
        embed.add_field(name="⏳ Tempo Restante", value=f"**{tempo}**", inline=False)

    embed.set_footer(text="Sistema Automático ULTRA • MU Online")
    return embed

# ===============================
# CALCULAR PRÓXIMO
# ===============================

def calcular_proximo_boss():
    agora = datetime.now(FUSO)
    proximos = []

    for horario, nome, local in bosses:
        hora_boss = FUSO.localize(
            datetime.strptime(horario, "%H:%M").replace(
                year=agora.year, month=agora.month, day=agora.day
            )
        )

        if hora_boss < agora:
            hora_boss += timedelta(days=1)

        diferenca = hora_boss - agora
        proximos.append((diferenca, nome, local, hora_boss))

    proximos.sort(key=lambda x: x[0])
    return proximos[0]

# ===============================
# READY
# ===============================

@bot.event
async def on_ready():
    log(f"🛡️ Bot ULTRA online como {bot.user}")

    if not verificar_boss.is_running():
        verificar_boss.start()

    if not atualizar_painel.is_running():
        atualizar_painel.start()

# ===============================
# TRATAMENTO GLOBAL DE ERRO
# ===============================

@bot.event
async def on_error(event, *args, **kwargs):
    log(f"❌ ERRO GLOBAL no evento {event}")
    traceback.print_exc()

# ===============================
# SISTEMA DE AVISO
# ===============================

@tasks.loop(seconds=30)
async def verificar_boss():
    global ultimo_minuto_processado

    try:
        async with lock_envio:

            agora = datetime.now(FUSO)
            minuto_atual = agora.strftime("%Y-%m-%d %H:%M")

            if ultimo_minuto_processado == minuto_atual:
                return

            ultimo_minuto_processado = minuto_atual

            hora_atual = agora.strftime("%H:%M")
            hora_menos5 = (agora + timedelta(minutes=5)).strftime("%H:%M")
            dia_semana = agora.weekday()

            canal = discord.utils.get(bot.get_all_channels(), name=CANAL_NOME)
            if not canal:
                return

            for horario, nome, local in bosses:

                if hora_menos5 == horario and f"5_{horario}" not in avisados:
                    embed = criar_embed(nome, local, horario, "EM 5 MINUTOS")
                    await canal.send("**@everyone**", embed=embed)
                    avisados.add(f"5_{horario}")
                    salvar_estado()
                    log(f"⏰ Aviso 5 min enviado para {nome}")
                    return

                if hora_atual == horario and f"0_{horario}" not in avisados:
                    embed = criar_embed(nome, local, horario, "NASCEU")
                    await canal.send("**@everyone**", embed=embed)
                    avisados.add(f"0_{horario}")
                    salvar_estado()
                    log(f"🔥 Boss {nome} nasceu")
                    return

            if hora_atual == "03:00":
                avisados.clear()
                salvar_estado()
                log("♻️ Reset diário executado")

    except Exception as e:
        log("❌ Erro na task verificar_boss")
        traceback.print_exc()

# ===============================
# PAINEL
# ===============================

@tasks.loop(minutes=1)
async def atualizar_painel():
    global mensagem_fixa

    try:
        canal = discord.utils.get(bot.get_all_channels(), name=CANAL_NOME)
        if not canal:
            return

        diferenca, nome, local, hora_boss = calcular_proximo_boss()

        total = int(diferenca.total_seconds())
        horas, resto = divmod(total, 3600)
        minutos, segundos = divmod(resto, 60)
        tempo = f"{horas:02d}h {minutos:02d}m {segundos:02d}s"

        embed = criar_embed(
            nome,
            local,
            hora_boss.strftime("%H:%M"),
            "PRÓXIMO",
            tempo
        )

        if mensagem_fixa is None:
            mensagem_fixa = await canal.send(embed=embed)
        else:
            await mensagem_fixa.edit(embed=embed)

    except Exception:
        log("❌ Erro na task atualizar_painel")
        traceback.print_exc()

# ===============================
# RECONEXÃO AUTOMÁTICA INFINITA
# ===============================

async def iniciar_bot():
    while True:
        try:
            await bot.start(TOKEN)
        except Exception as e:
            log("⚠️ Conexão perdida. Tentando reconectar em 10 segundos...")
            await asyncio.sleep(10)

# ===============================
# START
# ===============================

asyncio.run(iniciar_bot())
