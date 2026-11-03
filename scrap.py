import os
import re
import asyncio
import unicodedata
from urllib.parse import unquote
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaWebPage
from telethon.errors import FloodWaitError

# =========================
# CONFIGURACIÓN
# =========================
API_ID = int(os.environ.get("TG_API_ID", 32708998))
API_HASH = os.environ.get("TG_API_HASH", "aac0df0f82992c2f4b22eaec5b7e5dfb")
TARGET = os.environ.get("TG_TARGET", "@timyscrappv2").strip()
STAR = os.environ.get("TG_STAR", "⭐️").strip()
SESSION_NAME = os.environ.get("TG_SESSION", "my_account_session").strip()
DEBUG = os.environ.get("TG_DEBUG", "1") == "1"
DEFAULT_IMAGE = "mi_logo.jpg"

# ⚠️ DELAY ENTRE MENSAJES (en segundos)
MESSAGE_DELAY = 3

keywords_raw = os.environ.get(
    "TG_KEYWORDS",
    "approved,approve,approving,approval,aprobado,aprobada,aprobados,aprobadas,aprobacion,aprobación",
)

# =========================
# UTILIDADES DE TEXTO
# =========================
def normalize(s: str) -> str:
    s = s.casefold()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s

def clean_text(s: str) -> str:
    if not s:
        return s
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Cf")
    s = s.replace("\u00a0", " ")
    s = s.replace("│", "|").replace("｜", "|").replace("⌁", "|")
    return s

def strip_leading_tag(line: str) -> str:
    line = line.strip()
    while True:
        new = re.sub(r"^\[[^]]+\]\s*", " ", line).strip()
        if new == line:
            break
        line = new
    line = re.sub(r"^[•·☇ヾ⌿⽷+*\s:-]+\s*", " ", line).strip()
    return line

def extract_value_after_markers(line: str) -> str | None:
    m = re.search(r"(?:»|-->|->|:|=|⇾|→|⌁)\s*(.+)$", line)
    return m.group(1).strip() if m else None

def letters_only(s: str) -> str:
    return "".join(ch for ch in normalize(s) if ch.isalpha())

# =========================
# EXTRACCIÓN TIMY EXTRAS
# =========================
def extract_timy_extras(text: str) -> list[str]:
    text_limpio = normalize(clean_text(text))
    patron = re.compile(r"(\d{12,16}x{4})\s*\|\s*(\d{2})\s*\|\s*(\d{2,4})\s*\|\s*(\w+)", re.IGNORECASE)
    resultados = []
    
    for m in patron.finditer(text_limpio):
        cc = m.group(1)
        mm = m.group(2)
        yy = m.group(3)
        if len(yy) == 2:
            yy = f"20{yy}"
        extra = m.group(4)
        resultados.append(f"{cc}|{mm}|{yy}|{extra}")
        
    return resultados

# =========================
# FILTRO DE ACTIVACIÓN
# =========================
KEYWORDS = [k.strip() for k in keywords_raw.split(",") if k.strip()]
KEYWORDS_N = [normalize(k) for k in KEYWORDS]
kw_pattern = re.compile(
    r"(?<![a-z0-9])(?:%s)(?![a-z0-9])" % "|".join(map(re.escape, KEYWORDS_N))
)

# =========================
# EXTRACCIÓN DE TARJETA
# =========================
code_in_url_pattern = re.compile(
    r"(\d{15,16})\s*(?:||%7C|│|｜)\s*(\d{2})\s*(?:||%7C|│|｜)\s*(\d{4})\s*(?:||%7C|│|｜)\s*(\d{3,4})",
    re.IGNORECASE,
)

def extract_code_from_text(text: str) -> str | None:
    text_limpio = clean_text(text)
    patron_tarjeta = re.compile(r"(\d{15,16})\s*[|/│｜-]\s*(\d{2})\s*[|/│｜-]\s*(\d{2,4})\s*[|/│｜-]\s*(\d{3,4})")
    for line in text_limpio.splitlines():
        m = patron_tarjeta.search(line)
        if m:
            ano = m.group(3)
            if len(ano) == 2:
                ano = f"20{ano}"
            return f"{m.group(1)}|{m.group(2)}|{ano}|{m.group(4)}"
    return None

def extract_code_from_buttons(buttons) -> str | None:
    if not buttons:
        return None
    for row in buttons:
        for b in row:
            url = getattr(b, "url", None)
            if not url:
                continue
            u = clean_text(unquote(url))
            m = code_in_url_pattern.search(u)
            if m:
                return f"{m.group(1)}|{m.group(2)}|{m.group(3)}|{m.group(4)}"
    return None

# =========================
# EXTRACCIÓN DE BANCO
# =========================
def extract_Bank_line(text: str) -> str | None:
    for raw in clean_text(text).splitlines():
        linea_normalizada = normalize(raw)
        if "bank" in linea_normalizada or "banco" in linea_normalizada:
            valor = extract_value_after_markers(raw)
            if valor and valor.strip():
                return f"Bank = {valor.strip()}"
            partes = re.split(r"(?:»|⇾|→|:|=|⌁|->|-->)", raw)
            if len(partes) > 1 and partes[-1].strip():
                return f"Bank = {partes[-1].strip()}"
            linea_limpia = strip_leading_tag(raw)
            if linea_limpia:
                return f"Bank = {linea_limpia}"
    return None

# =========================
# EXTRACCIÓN DE INFO
# =========================
def extract_Info_line(text: str) -> str | None:
    for raw in clean_text(text).splitlines():
        linea_normalizada = normalize(raw)
        if "info" in linea_normalizada or "type" in linea_normalizada or "tipo" in linea_normalizada:
            valor = extract_value_after_markers(raw)
            if valor and valor.strip():
                return valor.strip()
            valor_n = extract_value_after_markers(linea_normalizada)
            if valor_n and valor_n.strip():
                return valor_n.strip()
            linea_limpia = strip_leading_tag(raw)
            if linea_limpia:
                linea_limpia = re.sub(r"^(info|type|tipo)\s*", "", normalize(linea_limpia), flags=re.IGNORECASE).strip()
                return linea_limpia
    return None

# =========================
# EXTRACCIÓN DE PAÍS
# =========================
ALIASES_COUNTRY = {
    "philippines": "Filipinas", "malaysia": "Malasia", "netherlands": "Países Bajos",
    "united states": "Estados Unidos", "usa": "Estados Unidos", "us": "Estados Unidos",
    "spain": "España", "mexico": "México", "united kingdom": "Reino Unido", "uk": "Reino Unido"
}
COUNTRY_ISO = {
    "Países Bajos": "NL", "Estados Unidos": "US", "México": "MX", "Filipinas": "PH",
    "Malasia": "MY", "España": "ES", "El Salvador": "SV", "Reino Unido": "GB",
    "Alemania": "DE", "Francia": "FR", "Italia": "IT", "Japón": "JP", "China": "CN",
    "Corea del Sur": "KR", "Australia": "AU", "Canadá": "CA", "Brasil": "BR",
    "Argentina": "AR", "Chile": "CL", "Colombia": "CO", "Perú": "PE"
}

def country_to_flag(country: str) -> str:
    code = COUNTRY_ISO.get(country)
    if not code:
        return "🏳️"
    return "".join(chr(127397 + ord(c)) for c in code.upper())

def extract_country_and_flag(text: str) -> tuple[str, str]:
    text_normalizado = normalize(clean_text(text))
    country_line = None
    for raw in clean_text(text).splitlines():
        line = strip_leading_tag(raw).strip()
        key = letters_only(line)
        if "country" in key or "pais" in key:
            country_line = line
            break
            
    if country_line:
        mflag = re.search(r"[\U0001F1E6-\U0001F1FF]{2}", country_line)
        flag = mflag.group(0) if mflag else None
        value = extract_value_after_markers(country_line) or country_line
        value = re.sub(r"\[[^\]]*\]", "", value).strip()
        value = re.sub(r"[\U0001F1E6-\U0001F1FF]{2}", "", value).strip()
        raw_country = value.strip()
        raw_country = re.sub(r"^country\s*", "", raw_country, flags=re.IGNORECASE).strip()
        raw_country = re.sub(r"^pais\s*", "", raw_country, flags=re.IGNORECASE).strip()
        parts = re.split(r"(?:»|⇾|→|:|=|⌁|->|-->)", raw_country)
        raw_country = parts[-1].strip() if parts else raw_country.strip()
        raw_n = normalize(raw_country)
        country = ALIASES_COUNTRY.get(raw_n, raw_country.title() if raw_country.isupper() else raw_country)
        if not flag:
            flag = country_to_flag(country)
        return (country, flag)
        
    for pais_espanol, iso in COUNTRY_ISO.items():
        if normalize(pais_espanol) in text_normalizado:
            return (pais_espanol, country_to_flag(pais_espanol))
            
    for alias_ingles, pais_espanol in ALIASES_COUNTRY.items():
        if alias_ingles in text_normalizado:
            return (pais_espanol, country_to_flag(pais_espanol))
            
    return ("Desconocido", "🏳️")

# =========================
# PLANTILLAS DE DISEÑO PROFESIONAL
# =========================
def format_scam_message(uid6, flag, coco_line_value, country, banco_limpio, info_final):
    return "\n".join([
        "╔══════════════════════╗",
        f"   🐦‍🔥 𝗧𝗬𝗠𝗜 𝗦𝗖𝗥𝗔𝗣𝗣𝗘𝗥 🐦‍🔥",
        "╚══════════════════════╝",
        f"🎴 BIN: #{uid6}  {flag}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"💳 𝗧𝗮𝗿𝗷𝗲𝘁𝗮:",
        f"   {coco_line_value}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"✅ 𝗘𝘀𝘁𝗮𝗱𝗼: ¡𝗔𝗽𝗿𝗼𝗯𝗮𝗱𝗮!",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"🌍 𝗣𝗮í𝘀: {country.upper()} {flag}",
        f"🏦 𝗕𝗮𝗻𝗰𝗼: {banco_limpio.upper()} 🔖",
        f"📋 𝗜𝗻𝗳𝗼: {info_final} 📡",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "🪭 𝗣𝗿𝗲𝗺𝗶𝘂𝗺 𝗔𝗰𝘁𝗶𝘃𝗼 🪭"
    ]).strip()

def format_extras_message(uid6, flag, extra, country, banco_limpio, info_final):
    return "\n".join([
        "╔══════════════════════╗",
        f"   🍂 𝗧𝗬𝗠𝗜 𝗘𝗫𝗧𝗥𝗔𝗦 🍂",
        "╚══════════════════════╝",
        f"🎴 BIN: #{uid6}  {flag}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"💳 𝗧𝗮𝗿𝗷𝗲𝘁𝗮:",
        f"   {extra}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"🔓 𝗘𝘀𝘁𝗮𝗱𝗼: ¡𝗘𝘅𝘁𝗿𝗮í𝗱𝗼!",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"🌍 𝗣𝗮í𝘀: {country.upper()} 🔖",
        f"🏦 𝗕𝗮𝗻𝗰𝗼: {banco_limpio.upper()} {flag}",
        f"📋 𝗜𝗻𝗳𝗼: {info_final} 📡",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "🪭 𝗣𝗿𝗲𝗺𝗶𝘂𝗺 𝗔𝗰𝘁𝗶𝘃𝗼 🪭"
    ]).strip()

# =========================
# FUNCIÓN AUXILIAR PARA ENVIAR CON MANEJO DE FLOOD
# =========================
async def safe_send_with_logo(client, target, caption, buttons):
    """Envía mensaje con logo si existe, sino solo texto"""
    # Verificar si la imagen existe
    if os.path.exists(DEFAULT_IMAGE):
        try:
            await client.send_file(target, DEFAULT_IMAGE, caption=caption, buttons=buttons)
            return True
        except FloodWaitError as e:
            print(f"   ⚠️ FloodWait detectado: esperando {e.seconds} segundos...")
            await asyncio.sleep(e.seconds)
            try:
                await client.send_file(target, DEFAULT_IMAGE, caption=caption, buttons=buttons)
                return True
            except Exception as e2:
                print(f"   ❌ Error después de esperar: {e2}")
                return False
        except Exception as e:
            print(f"   ❌ Error al enviar con logo: {e}")
            # Si falla el envío con imagen, intentar sin imagen
            pass
    
    # Si no hay imagen o falló, enviar solo texto
    try:
        await client.send_message(target, caption, buttons=buttons)
        return True
    except FloodWaitError as e:
        print(f"   ⚠️ FloodWait detectado: esperando {e.seconds} segundos...")
        await asyncio.sleep(e.seconds)
        try:
            await client.send_message(target, caption, buttons=buttons)
            return True
        except Exception as e2:
            print(f"   ❌ Error después de esperar: {e2}")
            return False
    except Exception as e:
        print(f"   ❌ Error al enviar mensaje: {e}")
        return False

# =========================
# CLIENTE TELEGRAM
# =========================
client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

@client.on(events.NewMessage(incoming=True))
async def handler(event):
    msg = event.message
    text_original = msg.raw_text or ""
    
    if not text_original:
        return

    btns = msg.buttons
    
    # ==========================
    # MODO 1: TIMY EXTRAS
    # ==========================
    extras = extract_timy_extras(text_original)
    if extras:
        print(f"\n📨 [EXTRAS] Detectados {len(extras)} formato(s)")
        
        country, flag = extract_country_and_flag(text_original)
        bank_line = extract_Bank_line(text_original)
        if not bank_line or "none" in bank_line.lower() or len(bank_line) < 8:
            Bank_line = "Bank = (no encontrado)"
        else:
            Bank_line = bank_line
        
        info_raw = extract_Info_line(text_original)
        info_limpia = info_raw.upper() if info_raw else "(NO ENCONTRADO)"
        
        banco_limpio = Bank_line.replace("Bank = ", "").strip()
        
        for i, extra in enumerate(extras):
            uid6 = extra.split("|", 1)[0][:6]
            
            prefijo_bin = ""
            primer_digito = extra[0]
            if primer_digito == "3":
                prefijo_bin = "3- "
            elif primer_digito == "4":
                prefijo_bin = "4- "
            elif primer_digito == "5":
                prefijo_bin = "5- "
            
            info_final = f"{prefijo_bin}{info_limpia}"
            
            out_text = format_extras_message(uid6, flag, extra, country, banco_limpio, info_final)
            
            print(f"   📤 Enviando formato {i+1}/{len(extras)}: {extra}")
            
            # Esperar antes de enviar (excepto el primero)
            if i > 0:
                print(f"   ⏳ Esperando {MESSAGE_DELAY} segundos...")
                await asyncio.sleep(MESSAGE_DELAY)
            
            # Enviar con logo si existe, sino solo texto
            success = await safe_send_with_logo(client, TARGET, out_text, btns)
            if success:
                if os.path.exists(DEFAULT_IMAGE):
                    print(f"   ✅ Formato enviado con logo")
                else:
                    print(f"   ✅ Formato enviado (sin logo - archivo no encontrado)")

    # ==========================
    # MODO 2: TIMY SCAM
    # ==========================
    if kw_pattern.search(normalize(clean_text(text_original))):
        print(f"\n📨 [SCAM] Palabra clave detectada")
        
        # Esperar si ya enviamos extras
        if extras:
            print(f"   ⏳ Esperando {MESSAGE_DELAY} segundos antes de SCAM...")
            await asyncio.sleep(MESSAGE_DELAY)
        
        coco_code = extract_code_from_text(text_original)
        if coco_code is None:
            coco_code = extract_code_from_buttons(msg.buttons)
            
        country, flag = extract_country_and_flag(text_original)
        bank_line = extract_Bank_line(text_original)
        if not bank_line or "none" in bank_line.lower() or len(bank_line) < 8:
            Bank_line = "Bank = (no encontrado)"
        else:
            Bank_line = bank_line

        info_raw = extract_Info_line(text_original)
        info_limpia = info_raw.upper() if info_raw else "(NO ENCONTRADO)"

        prefijo_bin = ""
        if coco_code:
            primer_digito = coco_code[0]
            if primer_digito == "3":
                prefijo_bin = "3- "
            elif primer_digito == "4":
                prefijo_bin = "4- "
            elif primer_digito == "5":
                prefijo_bin = "5- "

        info_final = f"{prefijo_bin}{info_limpia}"

        uid6 = coco_code.split("|", 1)[0][:6] if coco_code else "------"
        coco_line_value = coco_code if coco_code else ("Pulsa el boton de abajo" if msg.buttons else "(no encontrado)")
        banco_limpio = Bank_line.replace("Bank = ", "").strip()

        out_text = format_scam_message(uid6, flag, coco_line_value, country, banco_limpio, info_final)
        
        print(f"   📤 Enviando mensaje SCAM")
        
        # Enviar con logo si existe, sino solo texto
        success = await safe_send_with_logo(client, TARGET, out_text, btns)
        if success:
            if os.path.exists(DEFAULT_IMAGE):
                print(f"   ✅ Mensaje SCAM enviado con logo")
            else:
                print(f"   ✅ Mensaje SCAM enviado (sin logo - archivo no encontrado)")

async def main():
    print("⚠️ INICIANDO SCRAPPER ⚠️ (build: flood-protection + logo-check)")
    print(f"   Target: {TARGET} | Debug: {DEBUG}")
    print(f"   Modos activos: EXTRAS + SCAM")
    print(f"   Delay entre mensajes: {MESSAGE_DELAY}s")
    
    # Verificar si existe el logo
    if os.path.exists(DEFAULT_IMAGE):
        print(f"   ✅ Logo encontrado: {DEFAULT_IMAGE}")
    else:
        print(f"   ⚠️ Logo NO encontrado: {DEFAULT_IMAGE}")
        print(f"   ℹ️ Los mensajes se enviarán SIN imagen")
    
    await client.start()
    print("✅ Conectado. Scrapper encendido... (Ctrl+C para salir)")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
