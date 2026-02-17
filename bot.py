import discord
from discord.ext import commands, tasks
import os
from datetime import datetime, timedelta
import pytz
import json
import asyncio

TOKEN = os.getenv("TOKEN")

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
# SISTEMA DE SALVAMENTO
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
# LISTA DE BOSSES
# ===============================

bosses = [
    ("10:45", "Galia Black", "Lost Tower (165, 76)"),
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
# EMBED PROFISSIONAL
# ===============================

def criar_embed(nome, local, horario, status, tempo=None):
    cores = {
        "NASCEU": 0xff0000,
        "EM 5 MINUTOS": 0xffa500,
        "PRÓXIMO": 0x00bfff
    }

    embed = discord.Embed(
        title=f"🔥 **BOSS {nome} {status}!** 🔥",
        color=cores.get(status, 0xffffff)
    )

    embed.add_field(name="🕒 **Horário**", value=f"**{horario}**", inline=False)
    embed.add_field(name="📍 **Local**", value=f"**{local}**", inline=False)

    if tempo:
        embed.add_field(name="⏳ **Tempo Restante**", value=f"**{tempo}**", inline=False)

    embed.set_footer(text="Sistema Automático PRO • MU Online")
    return embed

# ===============================
# CALCULAR PRÓXIMO BOSS
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
# EVENTO READY
# ===============================

@bot.event
async def on_ready():
    print(f"Bot DEFINITIVO online como {bot.user}")
    verificar_boss.start()
    atualizar_painel.start()

# ===============================
# VERIFICAR BOSSES (ANTI DUPLICAÇÃO)
# ===============================

@tasks.loop(seconds=30)
async def verificar_boss():
    global ultimo_minuto_processado

    async with lock_envio:

        agora = datetime.now(FUSO)
        minuto_atual = agora.strftime("%Y-%m-%d %H:%M")

        # Impede rodar duas vezes no mesmo minuto
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

            # Aviso 5 minutos antes
            if hora_menos5 == horario and f"5_{horario}" not in avisados:
                embed = criar_embed(nome, local, horario, "EM 5 MINUTOS")
                await canal.send("@everyone", embed=embed)
                avisados.add(f"5_{horario}")
                salvar_estado()
                return

            # Aviso exato
            if hora_atual == horario and f"0_{horario}" not in avisados:
                embed = criar_embed(nome, local, horario, "NASCEU")
                await canal.send("@everyone", embed=embed)
                avisados.add(f"0_{horario}")
                salvar_estado()
                return

        # Balgass especial
        if hora_atual == "23:00" and dia_semana in [2, 5] and "balgass" not in avisados:
            embed = criar_embed("Balgass", "Crywolf (112,80)", "23:00", "NASCEU")
            await canal.send("@everyone", embed=embed)
            avisados.add("balgass")
            salvar_estado()
            return

        # Reset diário às 03:00
        if hora_atual == "03:00":
            avisados.clear()
            salvar_estado()

# ===============================
# PAINEL CONTAGEM REGRESSIVA
# ===============================

@tasks.loop(minutes=1)
async def atualizar_painel():
    global mensagem_fixa

    canal = discord.utils.get(bot.get_all_channels(), name=CANAL_NOME)
    if not canal:
        return

    diferenca, nome, local, hora_boss = calcular_proximo_boss()

    horas, resto = divmod(int(diferenca.total_seconds()), 3600)
    minutos, segundos = divmod(resto, 60)
    tempo_formatado = f"{horas:02d}h {minutos:02d}m {segundos:02d}s"

    embed = criar_embed(
        nome,
        local,
        hora_boss.strftime("%H:%M"),
        "PRÓXIMO",
        tempo_formatado
    )

    if mensagem_fixa is None:
        mensagem_fixa = await canal.send(embed=embed)
    else:
        await mensagem_fixa.edit(embed=embed)

bot.run(TOKEN)
