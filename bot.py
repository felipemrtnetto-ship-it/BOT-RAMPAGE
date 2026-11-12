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

TOKEN = os.getenv("TOKEN") or os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise ValueError("❌ TOKEN ou DISCORD_TOKEN não configurado na variável de ambiente.")

CANAL_ID = 1570446068490043442  # ID oficial do canal de alerta
TIMEZONE = pytz.timezone("America/Sao_Paulo")
ARQUIVO_ESTADO = "estado.json"

intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

lock = asyncio.Lock()

# ===============================
# BOSSES (TABELA DETALHADA)
# ===============================

BOSSES = [
    ("Blood Wizard", "18:10", None, "Devias (/pvp2)", "159, 32"),
    ("Crusher Skeleton", "19:05", None, "Lorencia", "Spawn aleatório"),
    ("Necromancer", "19:40", None, "Elbeland 2 (/devias4)", "29, 39"),
    ("Selupan", "20:10", None, "Raklion (após a ponte, /pvp4)", "174, 2027"),
    ("Galia Black", "20:30", None, "Lost Tower 1 (à esquerda do /move)", "166, 77"),
    ("Skull Reaper", "20:50", None, "Dungeon 1 (à esquerda do /move)", "92, 237"),
    ("Gwyn, o Senhor das Cinzas", "22:10", None, "Dungeon 3", "25, 72"),
    ("Hellmaine", "22:30", None, "Aida (/hellmaine)", "115, 100"),
    ("Balgass", "23:00", [2, 5], "Crywolf Fortress", "112, 80 (Somente quartas e sábados)"),
    ("Yhorm", "23:40", None, "/lorencia1", "22, 46"),
    ("Zorlak", "01:10", None, "Lorencia", "Spawn aleatório"),
]

# ===============================
# ESTADO
# ===============================

def carregar_estado():
    if not os.path.exists(ARQUIVO_ESTADO):
        return {}
    try:
        with open(ARQUIVO_ESTADO, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def salvar_estado(estado):
    try:
        with open(ARQUIVO_ESTADO, "w", encoding="utf-8") as f:
            json.dump(estado, f)
    except Exception:
        pass

estado = carregar_estado()

# ===============================
# FORMATAR TEMPO (HH:MM:SS)
# ===============================

def formatar_tempo(segundos_totais):
    if segundos_totais <= 0:
        return "🔴 Nascendo agora!"
    
    horas = int(segundos_totais // 3600)
    minutos = int((segundos_totais % 3600) // 60)
    segundos = int(segundos_totais % 60)
    
    return f"{horas:02d}:{minutos:02d}:{segundos:02d}"

# ===============================
# GERAR EMBED COM A AGENDA DETALHADA
# ===============================

def criar_embed_agenda_detalhada(agora):
    weekday_atual = agora.weekday()
    
    embed = discord.Embed(
        title="🛡️ HORÁRIOS DE BOSSES",
        description="━━━━━━━━━━━━━━━━━━━━",
        color=0x9b59b6
    )

    encontrou_algum = False

    for nome, horario, dias, mapa, coords in BOSSES:
        if dias is not None and weekday_atual not in dias:
            continue

        hora, minuto = map(int, horario.split(":"))
        dt_boss = TIMEZONE.localize(
            datetime(agora.year, agora.month, agora.day, hora, minuto)
        )

        if dt_boss < agora:
            dt_boss += timedelta(days=1)  # Se já passou hoje, calcula para amanhã

        diferenca = (dt_boss - agora).total_seconds()
        tempo_formatado = formatar_tempo(diferenca)

        # Status visual
        if diferenca <= 600:
            icone = "🔥"
        elif diferenca <= 1800:
            icone = "⚠️"
        else:
            icone = "⏳"

        texto_campo = (
            f"**Mapa:** {mapa}\n"
            f"**Horário:** {horario}\n"
            f"**Coordenadas:** {coords}\n"
            f"{icone} **Faltam:** `{tempo_formatado}`"
        )

        embed.add_field(
            name=f"⚔️ {nome}",
            value=texto_campo,
            inline=False
        )
        encontrou_algum = True

    if not encontrou_algum:
        embed.description = "Nenhum boss programado para hoje."

    embed.add_field(
        name="\u200b",
        value="━━━━━━━━━━━━━━━━━━━━\n*Fique atento aos horários e prepare-se para disputar os bosses!*",
        inline=False
    )
    
    return embed

# ===============================
# LOOP PRINCIPAL (PAINEL + ALERTAS)
# ===============================

@tasks.loop(seconds=5)  # Atualiza a cada 5 segundos para o relógio rodar fluido
async def verificar_boss():
    async with lock:
        agora = datetime.now(TIMEZONE)

        canal = bot.get_channel(CANAL_ID)
        if not canal:
            try:
                canal = await bot.fetch_channel(CANAL_ID)
            except discord.DiscordException:
                return

        # 1. ATUALIZAÇÃO DO PAINEL ÚNICO (Deleta o anterior e envia o novo atualizado)
        embed_painel = criar_embed_agenda_detalhada(agora)

        msg_id = estado.get("id_mensagem_painel")
        if msg_id:
            try:
                msg_antiga = await canal.fetch_message(msg_id)
                await msg_antiga.delete()
            except discord.NotFound:
                pass
            except discord.DiscordException:
                pass

        nova_msg = await canal.send(embed=embed_painel)
        estado["id_mensagem_painel"] = nova_msg.id
        salvar_estado(estado)

        # 2. DISPARO DOS ALERTAS DE 30 E 10 MINUTOS
        for evento in BOSSES:
            nome, horario, dias, mapa, coords = evento

            if dias is not None and agora.weekday() not in dias:
                continue

            hora_boss = datetime.strptime(horario, "%H:%M")
            hora_boss = TIMEZONE.localize(
                datetime(agora.year, agora.month, agora.day, hora_boss.hour, hora_boss.minute)
            )

            if hora_boss < agora:
                hora_boss += timedelta(days=1)

            diferenca = (hora_boss - agora).total_seconds()
            agorastr = agora.strftime('%Y-%m-%d')

            # Pré-alerta de 30 minutos (janela de 5 segundos)
            chave_30 = f"{nome}_{horario}_{agorastr}_30"
            if 1795 <= diferenca <= 1800:
                if not estado.get(chave_30):
                    embed_30 = discord.Embed(
                        title=f"⚠️ PRÉ-ALERTA: {nome} em 30 minutos!",
                        description=f"⏰ **Horário:** {horario}\n📍 **Mapa:** {mapa} ({coords})",
                        color=0x3498db
                    )
                    await canal.send(embed=embed_30)
                    estado[chave_30] = True
                    salvar_estado(estado)

            # Alerta principal de 10 minutos
            chave_10 = f"{nome}_{horario}_{agorastr}_10"
            if 595 <= diferenca <= 600:
                if not estado.get(chave_10):
                    embed_10 = discord.Embed(
                        title=f"🔥 BOSS {nome} NASCENDO EM BREVE! 🔥",
                        description=f"⏰ **Horário:** {horario}\n📍 **Mapa:** {mapa} ({coords})\n\n*Corram para o local!*",
                        color=0xffa500
                    )
                    await canal.send(
                        content="@everyone",
