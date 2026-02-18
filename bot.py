const {
    default: makeWASocket,
    useMultiFileAuthState,
    fetchLatestBaileysVersion,
    DisconnectReason
} = require("@whiskeysockets/baileys");

const { Boom } = require("@hapi/boom");
const pino = require("pino");
const fs = require("fs");
const moment = require("moment-timezone");
const qrcode = require("qrcode-terminal");
const QRCode = require("qrcode");

// ===============================
// CONFIGURAÇÕES
// ===============================

const TIMEZONE = "America/Sao_Paulo";
const GRUPOS_FILE = "./grupos.json";

// ✅ GRUPO RAMPAGE
const GRUPO_PERMITIDO = "120363404442428979@g.us";

let grupos = {};

if (fs.existsSync(GRUPOS_FILE)) {
    grupos = JSON.parse(fs.readFileSync(GRUPOS_FILE));
}

function salvarGrupos() {
    fs.writeFileSync(GRUPOS_FILE, JSON.stringify(grupos, null, 2));
}

// ===============================
// 👑 BOSSES COM EMOJI
// ===============================

const BOSSES = [
  { nome: "Galia Black", emoji: "🗡️", hora: 10, minuto: 0, local: "Devias (190x30)" },
  { nome: "Kundun", emoji: "🐲", hora: 13, minuto: 10, local: "Kalima 6 (120x88)" },
  { nome: "Blood Wizard", emoji: "🧙‍♂️", hora: 14, minuto: 0, local: "Dungeon (45x150)" },
  { nome: "Crusher Skeleton", emoji: "💀", hora: 14, minuto: 40, local: "Lost Tower (100x120)" },
  { nome: "Necromancer", emoji: "☠️", hora: 15, minuto: 0, local: "Aida (85x60)" },
  { nome: "Selupan", emoji: "🦂", hora: 15, minuto: 30, local: "Raklion (45x210)" },
  { nome: "Skull Reaper", emoji: "👻", hora: 16, minuto: 0, local: "Tarkan (120x90)" },
  { nome: "Gywen", emoji: "🐺", hora: 17, minuto: 0, local: "Atlans (150x50)" },
  { nome: "HellMaine", emoji: "👿", hora: 18, minuto: 0, local: "Noria (200x120)" },
  { nome: "Yorm", emoji: "🐗", hora: 19, minuto: 0, local: "Icarus (80x80)" },
  { nome: "Zorlak", emoji: "🐉", hora: 19, minuto: 40, local: "Kanturu (110x90)" },
  { nome: "Balgass", emoji: "😈", hora: 20, minuto: 0, local: "Crywolf (Boss Zone)" }
];

let enviadosHoje = new Set();

function agora() {
  return moment().tz(TIMEZONE);
}

function formatarAlerta(boss) {
  return `${boss.emoji} HORA DO BOSS! ${boss.emoji}

╔════════════════════════════╗
║   ${boss.emoji} ${boss.nome.toUpperCase()}
╠════════════════════════════╣
║ ⚠️ COMEÇA EM 10 MINUTOS
║ 🕒 ${String(boss.hora).padStart(2, "0")}:${String(boss.minuto).padStart(2, "0")}
║ 📍 ${boss.local}
╠════════════════════════════╣
║ ⚔️ BUFF em /Arena6
║ 👥 Entre na PT!
╚════════════════════════════╝`;
}

// ===============================
// 🚀 INICIAR BOT
// ===============================

async function startBot() {
  try {
    const { state, saveCreds } = await useMultiFileAuthState("auth");
    const { version } = await fetchLatestBaileysVersion();

    const sock = makeWASocket({
      version,
      logger: pino({ level: "silent" }),
      auth: state,
      markOnlineOnConnect: true,
      syncFullHistory: false
    });

    sock.ev.on("creds.update", saveCreds);

    // ===============================
    // 🔄 CONEXÃO + QR
    // ===============================

    sock.ev.on("connection.update", async (update) => {
      const { connection, lastDisconnect, qr } = update;

      if (qr) {
        console.log("📱 Escaneie o QR abaixo:");
        qrcode.generate(qr, { small: true });

        try {
          const qrBase64 = await QRCode.toDataURL(qr);
          console.log("\n==============================");
          console.log("🔗 LINK DO QR CODE:");
          console.log(qrBase64);
          console.log("==============================\n");
        } catch (err) {
          console.log("Erro ao gerar QR em link:", err.message);
        }
      }

      if (connection === "open") {
        console.log("✅ Bot conectado com sucesso!");
      }

      if (connection === "close") {
        const shouldReconnect =
          new Boom(lastDisconnect?.error)?.output?.statusCode !== DisconnectReason.loggedOut;

        if (shouldReconnect) {
          console.log("🔄 Reconectando em 5 segundos...");
          setTimeout(startBot, 5000);
        } else {
          console.log("❌ Sessão encerrada. Apague a pasta 'auth' e gere novo QR.");
        }
      }
    });

    // ===============================
    // 📩 MENSAGENS
    // ===============================

    sock.ev.on("messages.upsert", async ({ messages }) => {
      try {
        const msg = messages[0];
        if (!msg.message || msg.key.fromMe) return;

        const chatId = msg.key.remoteJid;
        if (chatId !== GRUPO_PERMITIDO) return;

        const texto =
          msg.message.conversation ||
          msg.message.extendedTextMessage?.text ||
          "";

        if (texto.toLowerCase() === "/status") {
          await sock.sendMessage(chatId, {
            text: `🤖 BOT ONLINE

🕒 ${agora().format("DD/MM/YYYY HH:mm:ss")}
🔥 Sistema ativo`
          });
        }

        if (texto.toLowerCase().startsWith("/boss")) {
          const nome = texto.replace("/boss", "").trim().toLowerCase();

          const boss = BOSSES.find(
            b => b.nome.toLowerCase() === nome
          );

          if (!boss) {
            return sock.sendMessage(chatId, { text: "❌ Boss não encontrado." });
          }

          await sock.sendMessage(chatId, {
            text: formatarAlerta(boss)
          });
        }

      } catch (err) {
        console.log("Erro ao processar mensagem:", err.message);
      }
    });

    // ===============================
    // 🔔 ALERTA AUTOMÁTICO (CORRIGIDO)
    // ===============================

    setInterval(async () => {
      try {
        const agoraAtual = agora();

        for (const boss of BOSSES) {

          let horarioBoss = moment.tz(TIMEZONE)
            .set({
              hour: boss.hora,
              minute: boss.minuto,
              second: 0,
              millisecond: 0
            });

          if (horarioBoss.isBefore(agoraAtual)) {
            horarioBoss.add(1, "day");
          }

          const diferencaMin = horarioBoss.diff(agoraAtual, "minutes");

          const chave = `${boss.nome}-${horarioBoss.format("YYYY-MM-DD")}`;

          if (diferencaMin === 10 && !enviadosHoje.has(chave)) {

            enviadosHoje.add(chave);

            await sock.sendMessage(GRUPO_PERMITIDO, {
              text: formatarAlerta(boss)
            });

            console.log("🔔 Alerta enviado:", boss.nome);
          }
        }

        if (agoraAtual.format("HH:mm:ss") === "00:00:00") {
          enviadosHoje.clear();
          console.log("🔄 Reset diário executado");
        }

      } catch (err) {
        console.log("Erro no sistema automático:", err.message);
      }
    }, 30000);

  } catch (err) {
    console.log("Erro crítico:", err.message);
    setTimeout(startBot, 5000);
  }
}

startBot();
