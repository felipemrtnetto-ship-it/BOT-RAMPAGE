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
ultimo_minuto_processado = None

# ===============================
# BOSSES (TABELA OFICIAL)
# Formato: (Nome, Horário, Dias [None = todos], Local)
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
    try:
        with open(ARQUIVO_ESTADO, "r") as f:
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
# FUNÇÕES AUXILIARES
# ===============================

def obter_proximo_boss(agora):
    weekday_atual = agora.weekday()
    candidatos = []

    for dia_offset in [0, 1]:
        dia_alvo = agora.date() + timedelta(days=dia_offset)
        weekday_alvo = dia_alvo.weekday()

        for nome, horario, dias, local in BOSSES:
            if dias is not None and weekday_alvo not in dias:
                continue

            hora, minuto = map(int, horario.split(":"))
            dt_boss = TIMEZONE.localize(
                datetime(dia_alvo.year, dia_alvo.month, dia_alvo.day, hora, minuto)
            )

            if dt_boss > agora:
                candidatos.append((dt_boss, nome, horario, local))

    if not candidatos:
        return None

    candidatos.sort(key=lambda x: x[0])
    return candidatos[0]

def gerar_embed_agenda_diaria(agora):
    weekday_atual = agora.weekday()
    embed = discord.Embed(
        title="📅 AGENDA DIÁRIA DE BOSSES",
        description="Lista completa dos bosses de hoje com contagem regressiva em tempo real:",
        color=0x2ecc71
    )

    encontrou = False
    for nome, horario, dias, local in BOSSES:
        if dias is not None and weekday_atual not in dias:
            continue

        hora, minuto = map(int, horario.split(":"))
        dt_boss = TIMEZONE.localize(
            datetime(agora.year, agora.month, agora.day, hora, minuto)
        )

        if dt_boss < agora:
            # Se já passou hoje, mostra como encerrado ou calcula para amanhã
            status = "✅ *Encerrado*"
        else:
            timestamp = int(dt_boss.timestamp())
            status = f"⏳ <t:{timestamp}:R> ({horario})"

        embed.add_field(
            name=f"🛡️ {nome}",
            value=f"Local: `{local}`\nStatus: {status}",
            inline=False
        )
        encontrou = True

    if not encontrou:
        embed.description = "Nenhum boss programado para hoje."

    embed.set_footer(text="Digite !bosses para atualizar a lista a qualquer momento.")
    return embed

# ===============================
# LOOP PRINCIPAL (PAINEL DO PRÓXIMO + ALERTAS)
# ===============================

@tasks.loop(seconds=30)
async def verificar_boss():
    global ultimo_minuto_processado
    async with lock:

        agora = datetime.now(TIMEZONE)
        minuto_atual = agora.strftime("%Y-%m-%d %H:%M")

        canal = bot.get_channel(CANAL_ID)
        if not canal:
            try:
                canal = await bot.fetch_channel(CANAL_ID)
            except discord.DiscordException:
                return

        # 1. ATUALIZAÇÃO DO PAINEL DO PRÓXIMO BOSS (A cada minuto)
        if minuto_atual != ultimo_minuto_processado:
            ultimo_minuto_processado = minuto_atual

            proximo = obter_proximo_boss(agora)
            if proximo:
                dt_proximo, nome_prox, hora_prox, local_prox = proximo
                timestamp_prox = int(dt_proximo.timestamp())

                embed_painel = discord.Embed(
                    title="⏳ PRÓXIMO BOSS NA FILA",
                    description=(
                        f"🎯 **Boss:** `{nome_prox}`\n"
                        f"⏰ **Horário:** `{hora_prox}`\n"
                        f"⏳ **Inicia:** <t:{timestamp_prox}:R>\n"
                        f"📍 **Local:** `{local_prox}`"
                    ),
                    color=0x9b59b6
                )
                embed_painel.set_footer(text="Painel atualizado automaticamente")

                msg_id = estado.get("id_mensagem_painel")
                mensagem_painel = None

                if msg_id:
                    try:
                        mensagem_painel = await canal.fetch_message(msg_id)
                    except discord.NotFound:
                        mensagem_painel = None

                if mensagem_painel:
                    try:
                        await mensagem_painel.edit(embed=embed_painel)
                    except discord.DiscordException:
                        pass
                else:
                    nova_msg = await canal.send(embed=embed_painel)
                    estado["id_mensagem_painel"] = nova_msg.id
                    salvar_estado(estado)

        # Reset diário às 03:00
        if agora.strftime("%H:%M") == "03:00":
            painel_id = estado.get("id_mensagem_painel")
            estado.clear()
            if painel_id:
                estado["id_mensagem_painel"] = painel_id
            salvar_estado(estado)

        # 2. DISPARO DOS ALERTAS DE 30 E 10 MINUTOS
        for evento in BOSSES:
            nome, horario, dias, local = evento

            if dias is not None and agora.weekday() not in dias:
                continue

            hora_boss = datetime.strptime(horario, "%H:%M")
            hora_boss = TIMEZONE.localize(
                datetime(agora.year, agora.month, agora.day, hora_boss.hour, hora_boss.minute)
            )

            if hora_boss < agora:
                hora_boss += timedelta(days=1)

            diferenca = (hora_boss - agora).total_seconds()
            data_str = agora.strftime('%Y-%m-%d')
            timestamp_unix = int(hora_boss.timestamp())

            # Pré-alerta de 30 minutos
            chave_30 = f"{nome}_{horario}_{data_str}_30"
            if 1740 <= diferenca <= 1800:
                if not estado.get(chave_30):
                    embed_30 = discord.Embed(
                        title=f"⚠️ PRÉ-ALERTA: {nome} em 30 minutos!",
                        description=f"⏰ **Horário:** {horario}\n⏳ **Inicia:** <t:{timestamp_unix}:R>\n📍 **Local:** {local}",
                        color=0x3498db
                    )
                    await canal.send(embed=embed_30)
                    estado[chave_30] = True
                    salvar_estado(estado)

            # Alerta principal de 10 minutos
            chave_10 = f"{nome}_{horario}_{data_str}_10"
            if 0 < diferenca <= 600:
                if not estado.get(chave_10):
                    embed_10 = discord.Embed(
                        title=f"🔥 BOSS {nome} NASCENDO EM BREVE! 🔥",
                        description=f"⏰ **Horário:** {horario}\n⏳ **Tempo Restante:** <t:{timestamp_unix}:R>\n📍 **Local:** {local}\n\n*Corram para o local!*",
                        color=0xffa500
                    )
                    await canal.send(
                        content="@everyone",
                        embed=embed_10,
                        allowed_mentions=discord.AllowedMentions(everyone=True)
                    )
                    estado[chave_10] = True
                    salvar_estado(estado)

# ===============================
# COMANDOS DE CHAT
# ===============================

@bot.event
async def on_ready():
    print(f"🛡️ Bot de Alertas e Agenda online como {bot.user}")
    if not verificar_boss.is_running():
        verificar_boss.start()

@bot.event
async def on_message(message):
    if message.author.bot or message.guild is None:
        return

    conteudo = message.content.strip().lower()

    # Comando para exibir a lista completa de todos os bosses com contagem regressiva
    if conteudo == "!bosses" or conteudo == "!agenda":
        agora = datetime.now(TIMEZONE)
        embed_agenda = gerar_embed_agenda_diaria(agora)
        await message.channel.send(embed=embed_agenda)
        try:
            await message.delete()
        except discord.DiscordException:
            pass

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
