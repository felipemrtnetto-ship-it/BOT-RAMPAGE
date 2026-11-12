import discord
from discord.ext import tasks
import asyncio
import pytz
from datetime import datetime, timedelta
import json
import os
import time

print("🔄 A iniciar o script do bot...")

# ===============================
# CONFIG
# ===============================

TOKEN = os.getenv("TOKEN") or os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise ValueError("❌ TOKEN ou DISCORD_TOKEN não configurado na variável de ambiente.")

CANAL_PAINEL_ID = 1570446068490043442   # Canal do painel fixo
CANAL_ALERTAS_ID = 1570454121922822265  # Canal de alertas (@everyone)

TIMEZONE = pytz.timezone("America/Sao_Paulo")
ARQUIVO_ESTADO = "estado.json"

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
bot = discord.Client(intents=intents)

lock = asyncio.Lock()

# ===============================
# BOSSES (COM EMOJIS EXCLUSIVOS E DETALHES)
# ===============================

BOSSES = [
    ("Blood Wizard", "18:10", None, "Devias (/pvp2)", "159, 32", "🧙‍♂️"),
    ("Crusher Skeleton", "19:05", None, "Lorencia", "Spawn aleatório", "💀"),
    ("Necromancer", "19:40", None, "Elbeland 2 (/devias4)", "29, 39", "🔮"),
    ("Selupan", "20:10", None, "Raklion (após a ponte, /pvp4)", "174, 2027", "🕷️"),
    ("Galia Black", "20:30", None, "Lost Tower 1 (à esquerda do /move)", "166, 77", "🦇"),
    ("Skull Reaper", "20:50", None, "Dungeon 1 (à esquerda do /move)", "92, 237", "⚔️"),
    ("Gwyn, o Senhor das Cinzas", "22:10", None, "Dungeon 3", "25, 72", "🔥"),
    ("Hellmaine", "22:30", None, "Aida (/hellmaine)", "115, 100", "🐺"),
    ("Balgass", "23:00", [2, 5], "Crywolf Fortress", "112, 80 (Somente quartas e sábados)", "👑"),
    ("Yhorm", "23:40", None, "/lorencia1", "22, 46", "🛡️"),
    ("Zorlak", "01:10", None, "Lorencia", "Spawn aleatório", "⚡"),
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
# GERAR EMBED COM ESPAÇAMENTO E EMOJIS
# ===============================

def criar_embed_agenda_detalhada(agora):
    weekday_atual = agora.weekday()
    
    embed = discord.Embed(
        title="🛡️ HORÁRIOS DE BOSSES",
        description="━━━━━━━━━━━━━━━━━━━━",
        color=0x9b59b6
    )

    encontrou_algum = False

    for nome, horario, dias, mapa, coords, emoji in BOSSES:
        if dias is not None and weekday_atual not in dias:
            continue

        hora, minuto = map(int, horario.split(":"))
        dt_boss = TIMEZONE.localize(
            datetime(agora.year, agora.month, agora.day, hora, minuto)
        )

        if dt_boss < agora:
            dt_boss += timedelta(days=1)

        diferenca = (dt_boss - agora).total_seconds()
        tempo_formatado = formatar_tempo(diferenca)

        # Status visual de urgência
        if diferenca <= 600:
            status_icone = "🔥"
        elif diferenca <= 1800:
            status_icone = "⚠️"
        else:
            status_icone = "⏳"

        # Organização visual limpa e espaçada para cada boss
        texto_campo = (
            f"📍 **Mapa:** {mapa}\n"
            f"⏰ **Horário:** {horario}  |  📌 **Coords:** `{coords}`\n"
            f"{status_icone} **Faltam:** `{tempo_formatado}`\n"
            f"────────────────────────"  # Linha sutil de separação entre os bosses
        )

        embed.add_field(
            name=f"{emoji} {nome}",
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

@tasks.loop(seconds=5)
async def verificar_boss():
    async with lock:
        agora = datetime.now(TIMEZONE)

        # 1. ATUALIZAÇÃO DO PAINEL DE HORÁRIOS
        canal_painel = bot.get_channel(CANAL_PAINEL_ID)
        if not canal_painel:
            try:
                canal_painel = await bot.fetch_channel(CANAL_PAINEL_ID)
            except discord.DiscordException:
                canal_painel = None

        if canal_painel:
            embed_painel = criar_embed_agenda_detalhada(agora)

            msg_id = estado.get("id_mensagem_painel")
            if msg_id:
                try:
                    msg_antiga = await canal_painel.fetch_message(msg_id)
                    await msg_antiga.delete()
                except discord.NotFound:
                    pass
                except discord.DiscordException:
                    pass

            nova_msg = await canal_painel.send(embed=embed_painel)
            estado["id_mensagem_painel"] = nova_msg.id
            salvar_estado(estado)

        # 2. CANAL DE ALERTAS (@everyone)
        canal_alertas = bot.get_channel(CANAL_ALERTAS_ID)
        if not canal_alertas:
            try:
                canal_alertas = await bot.fetch_channel(CANAL_ALERTAS_ID)
            except discord.DiscordException:
                canal_alertas = None

        if canal_alertas:
            for evento in BOSSES:
                nome, horario, dias, mapa, coords, emoji = evento

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

                # Pré-alerta de 30 minutos
                chave_30 = f"{nome}_{horario}_{agorastr}_30"
                if 1795 <= diferenca <= 1800:
                    if not estado.get(chave_30):
                        embed_30 = discord.Embed(
                            title=f"⚠️ PRÉ-ALERTA: {emoji} {nome} em 30 minutos!",
                            description=f"⏰ **Horário:** {horario}\n📍 **Mapa:** {mapa} (`{coords}`)",
                            color=0x3498db
                        )
                        msg_alerta = await canal_alertas.send(embed=embed_30)
                        estado[chave_30] = True
                        salvar_estado(estado)
                        asyncio.create_task(apagar_mensagem_depois(msg_alerta, 900))

                # Alerta principal de 10 minutos
                chave_10 = f"{nome}_{horario}_{agorastr}_10"
                if 595 <= diferenca <= 600:
                    if not estado.get(chave_10):
                        embed_10 = discord.Embed(
                            title=f"🔥 BOSS {emoji} {nome} NASCENDO EM BREVE! 🔥",
                            description=f"⏰ **Horário:** {horario}\n📍 **Mapa:** {mapa} (`{coords}`)\n\n*Corram para o local!*",
                            color=0xffa500
                        )
                        msg_alerta = await canal_alertas.send(
                            content="@everyone",
                            embed=embed_10,
                            allowed_mentions=discord.AllowedMentions(everyone=True)
                        )
                        estado[chave_10] = True
                        salvar_estado(estado)
                        asyncio.create_task(apagar_mensagem_depois(msg_alerta, 900))

async def apagar_mensagem_depois(mensagem, segundos):
    await asyncio.sleep(segundos)
    try:
        await mensagem.delete()
    except discord.NotFound:
        pass
    except discord.DiscordException:
        pass

# ===============================
# READY
# ===============================

@bot.event
async def on_ready():
    print(f"🛡️ Bot conectado com sucesso como {bot.user}")
    if not verificar_boss.is_running():
        verificar_boss.start()
        print("🚀 Loop de verificação iniciado com sucesso!")

# ===============================
# EXECUÇÃO
# ===============================

if __name__ == "__main__":
    bot.run(TOKEN)
