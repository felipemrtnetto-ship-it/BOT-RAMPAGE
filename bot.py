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
        with open(ARQUIVO_ESTADO, "w") as f:
            json.dump(estado, f)
    except Exception:
        pass

estado = carregar_estado()

# ===============================
# FUNÇÃO AUXILIAR: ENCONTRAR O PRÓXIMO BOSS
# ===============================

def obter_proximo_boss(agora):
    hoje_weekday = agora.weekday()
    candidatos = []

    # Olha os bosses de hoje e de amanhã para garantir que sempre ache o próximo
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

            # Se for do dia seguinte ou do dia de hoje que ainda vai acontecer
            if dt_boss > agora:
                candidatos.append((dt_boss, nome, horario, local))

    if not candidatos:
        return None

    # Ordena pelo mais próximo do momento atual
    candidatos.sort(key=lambda x: x[0])
    return candidatos[0] # Retorna (dt_boss, nome, horario, local)

# ===============================
# LOOP PRINCIPAL (ALERTAS + PAINEL DO PRÓXIMO BOSS)
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

        # --- 1. ATUALIZAÇÃO CONTÍNUA DO PRÓXIMO BOSS (A cada minuto) ---
        if minuto_atual != ultimo_minuto_processado:
            ultimo_minuto_processado = minuto_atual

            # Busca o próximo boss na fila
            proximo = obter_proximo_boss(agora)
            if proximo:
                dt_proximo, nome_prox, hora_prox, local_prox = proximo
                timestamp_prox = int(dt_proximo.timestamp())

                embed_painel = discord.Embed(
                    title="⏳ PRÓXIMO BOSS NA FILA",
                    description=(
                        f"🎯 **Boss:** `{nome_prox}`\n"
                        f"⏰ **Horário:** `{hora_prox}`\n"
                        f"⏳ **Começa:** <t:{timestamp_prox}:R>\n"
                        f"📍 **Local:** `{local_prox}`"
                    ),
                    color=0x9b59b6 # Cor roxa/azulada para o painel contínuo
                )
                embed_painel.set_footer(text="Atualizado automaticamente em tempo real")

                # ID da mensagem fixa do painel salva no estado (para o bot editar sempre a mesma mensagem e não poluir o chat)
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
                    # Se não existir mensagem salva, envia uma nova e salva o ID
                    nova_msg = await canal.send(embed=embed_painel)
                    estado["id_mensagem_painel"] = nova_msg.id
                    salvar_estado(estado)

        # Reset diário das travas de alerta às 03:00
        if agora.strftime("%H:%M") == "03:00":
            # Mantém apenas o ID da mensagem do painel para não perder a referência
            painel_id = estado.get("id_mensagem_painel")
            estado.clear()
            if painel_id:
                estado["id_mensagem_painel"] = painel_id
            salvar_estado(estado)

        # --- 2. DISPARO DOS ALERTAS DE 30 E 10 MINUTOS ---
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
# READY
# ===============================

@bot.event
async def on_ready():
    print(f"🛡️ Bot de Alertas com Painel Contínuo online como {bot.user}")
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
