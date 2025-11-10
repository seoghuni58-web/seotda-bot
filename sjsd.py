import logging
import random
import json
import os
from datetime import date
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from telegram.error import TimedOut
from telegram.request import HTTPXRequest

# =========================
# 설정
# =========================

TOKEN = "8057029622:AAFD8YF_RZDtjDpgGclSdKqTeqLMTljNQHQ"
USER_DATA_FILE = "users.json"
TURN_TIMEOUT = 45  # 본베팅 턴당 45초

# 관리자 유저네임 (앞에 @ 빼고)
ADMIN_USERNAMES = {"crst205", "burst_egg"}

# 프로필 카드 템플릿/폰트
PROFILE_TEMPLATE_PATH = "profile_template_600.png"  # 600x600 PNG 권장
PROFILE_FONT_PATH = "NotoSansKR-Black.ttf"

# 카드 코드 → 스티커 file_id
CARD_STICKERS = {
    "1K":  "CAACAgQAAyEFAATAFxUqAAIGSmkQtVeUPXxxq4WMvXwpYnnl-Mt4AAKpIwACOeKIUJT-o5Wh89PKNgQ",
    "1N":  "CAACAgQAAyEFAATAFxUqAAIGfWkQuDiDVW7DXostIbrF0gvX4JQSAAK7GQACpoaJUKRM7zQQpstjNgQ",
    "2A":  "CAACAgQAAyEFAATAFxUqAAIGf2kQuJPTQrVys81r2Xy0YFbEheugAAIsIgACk-qBUMSeOxZjBswWNgQ",
    "2B":  "CAACAgQAAyEFAATAFxUqAAIGgWkQuKTvrjl4AR-4GnXhPStw_2iVAAJ7GQACkQ2IUICl6-JB3eIJNgQ",
    "3K":  "CAACAgQAAyEFAATAFxUqAAIGg2kQuL4rzn5GQQgLdP96ovL9b7aAAAIUIAACc2qJUEmRFKZCTi0_NgQ",
    "3N":  "CAACAgQAAyEFAATAFxUqAAIGhWkQuNcFnWkjMP6fS1orJ5sJiLgvAAJuGwACG7SIUFUbF-M8hwWKNgQ",
    "4M":  "CAACAgQAAyEFAATAFxUqAAIGUWkQtZ0cVVU1A7SPmGgxxyrfQl--AAIKHQACKE-AUHdwsYqDrs75NgQ",
    "4N":  "CAACAgQAAyEFAATAFxUqAAIGiWkQuQwxLrG3LLkAAeK4b3uMffzARgACOx0AAq93gFDGnPYHzP6tHTYE",
    "5A":  "CAACAgQAAyEFAATAFxUqAAIGi2kQuR97NGtqhw17x_V7nSZARPzQAAIhHgACy42BUF5VB7MXy4-FNgQ",
    "5B":  "CAACAgQAAyEFAATAFxUqAAIGTWkQtXCQTcktvu537XmmFyoz6mZgAAJxHQACI56IUKCBMMwKC-PVNgQ",
    "6A":  "CAACAgQAAyEFAATAFxUqAAIGTGkQtW8navBkCyIC1am-x6v82anyAAIfHQACDGGJUAjXpCI8ObApNgQ",
    "6B":  "CAACAgQAAyEFAATAFxUqAAIGkWkQuXKrPNTJFwu4sp1QOSf9epUcAAJXHQAChnKAUFB3DH3K5I5tNgQ",
    "7M":  "CAACAgQAAyEFAATAFxUqAAIGk2kQuZdgvwJ_GapTymQehdc1Sv2yAAKfGgACzxKJUMOZTOp-U4fXNgQ",
    "7N":  "CAACAgQAAyEFAATAFxUqAAIGlWkQua88Jwlg8BlU8BBhPuplVJFIAALOHAACtrGIUG4acOa17EwPNgQ",
    "8K":  "CAACAgQAAyEFAATAFxUqAAIGl2kQufyk2B4YkaI_6eAv_t0Nga_oAAJWIgACi66IUCcweUTqRrtxNgQ",
    "8N":  "CAACAgQAAyEFAATAFxUqAAIGmWkQuhO4zUezB-E_qrP1OoWBl0zeAAKRIAACSu-JUEXglh_DniDrNgQ",
    "9N":  "CAACAgQAAyEFAATAFxUqAAIGm2kQujiM365BmuXLkP-hozWzz5d9AALzGgACdi6JUAABR-_wCD2KHjYE",
    "9M":  "CAACAgQAAyEFAATAFxUqAAIGnWkQul1YMpVrwT4_A_HbspM4HC9JAAK-HAACTx6AUOlaF8ETuoUTNgQ",
    "10A":"CAACAgQAAyEFAATAFxUqAAIGTmkQtXkIbvfsTyhK95Rn7i_VYZZEAAKZHgAChByJUBH5ZOzfuy83NgQ",
    "10B":"CAACAgQAAyEFAATAFxUqAAIGoWkQusC_2zAfEXGTCupT89fO33yUAALBHAACYbiAUFsYvPbyIASKNgQ",
}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

users: dict[int, dict] = {}
seotda_games: dict[int, dict] = {}

# 주머니 쿨타임
last_wallet_call = {}

# =========================
# 공통 유틸
# =========================

def load_users():
    global users
    if os.path.exists(USER_DATA_FILE):
        try:
            with open(USER_DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            users = {int(k): v for k, v in data.items()}
        except Exception as e:
            logger.warning(f"유저 데이터 로드 실패: {e}")
            users = {}
    else:
        users = {}

def save_users():
    try:
        data = {str(k): v for k, v in users.items()}
        with open(USER_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"유저 데이터 저장 실패: {e}")

def today_str() -> str:
    return date.today().isoformat()

def get_display_name(user) -> str:
    name = user.full_name or user.first_name or ""
    if user.username:
        return f"{name}(@{user.username})"
    return name

def get_user(user) -> dict:
    uid = user.id
    if uid not in users:
        users[uid] = {
            "name": get_display_name(user),
            "balance": 0,
            "joined": False,
            "freechips_date": "",
            "freechips_used": 0,
            "wins": 0,
            "losses": 0,
        }
    else:
        users[uid]["name"] = get_display_name(user)
        users[uid].setdefault("wins", 0)
        users[uid].setdefault("losses", 0)
    return users[uid]

async def get_name_by_id(context: ContextTypes.DEFAULT_TYPE, uid: int) -> str:
    if uid in users:
        return users[uid]["name"]
    try:
        u = await context.bot.get_chat(uid)
        return get_display_name(u)
    except Exception:
        return str(uid)

# =========================
# 프로필 카드
# =========================

async def create_profile_card(user, context) -> BytesIO:
    data = get_user(user)

    img = Image.open(PROFILE_TEMPLATE_PATH).convert("RGBA")
    draw = ImageDraw.Draw(img)

    try:
        font_title = ImageFont.truetype(PROFILE_FONT_PATH, 36)
        font_text = ImageFont.truetype(PROFILE_FONT_PATH, 24)
    except Exception:
        font_title = ImageFont.load_default()
        font_text = ImageFont.load_default()

    raw_name = data["name"]
    if user.username:
        name = raw_name.split(f"(@{user.username})")[0].strip()
    else:
        name = raw_name

    username = f"@{user.username}" if user.username else "-"
    balance_text = f"{data['balance']:,} 코인"
    wins = data.get("wins", 0)
    losses = data.get("losses", 0)
    record_text = f"{wins}승 {losses}패"

    cx, cy, r = 288, 150, 110

    try:
        photos = await context.bot.get_user_profile_photos(user.id, limit=1)
        if photos.total_count > 0:
            file_id = photos.photos[0][0].file_id
            file = await context.bot.get_file(file_id)

            buf = BytesIO()
            await file.download_to_memory(buf)
            buf.seek(0)

            avatar = Image.open(buf).convert("RGBA")

            w, h = avatar.size
            side = min(w, h)
            left = (w - side) // 2
            top = (h - side) // 2
            avatar = avatar.crop((left, top, left + side, top + side))
            avatar = avatar.resize((r * 2, r * 2), Image.LANCZOS)

            mask = Image.new("L", (r * 2, r * 2), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, r * 2, r * 2), fill=255)
            img.paste(avatar, (cx - r, cy - r), mask)
    except Exception:
        pass

    slots = [
        (310, 282, name),
        (320, 357, username),
        (326, 433, balance_text),
        (318, 506, record_text),
    ]

    for sx, sy, text in slots:
        bbox = draw.textbbox((0, 0), text, font=font_text)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = sx - tw / 2
        ty = sy - th / 2

        color = (0, 0, 0)
        if text == balance_text:
            color = (180, 40, 40)
        draw.text((tx, ty), text, fill=color, font=font_text)

    output = BytesIO()
    output.name = "profile_card.png"
    img.save(output, format="PNG", optimize=True)
    output.seek(0)
    return output

# =========================
# 덱 / 카드 표현
# =========================

def make_sutda_deck():
    deck = []
    # 1
    deck.append({"num": 1, "is_kwang": True, "code": "1K"})
    deck.append({"num": 1, "is_kwang": False, "code": "1N"})
    # 2
    deck.append({"num": 2, "is_kwang": False, "code": "2A"})
    deck.append({"num": 2, "is_kwang": False, "code": "2B"})
    # 3
    deck.append({"num": 3, "is_kwang": True, "code": "3K"})
    deck.append({"num": 3, "is_kwang": False, "code": "3N"})
    # 4
    deck.append({"num": 4, "is_kwang": False, "code": "4M"})  # 멍4
    deck.append({"num": 4, "is_kwang": False, "code": "4N"})
    # 5
    deck.append({"num": 5, "is_kwang": False, "code": "5A"})
    deck.append({"num": 5, "is_kwang": False, "code": "5B"})
    # 6
    deck.append({"num": 6, "is_kwang": False, "code": "6A"})
    deck.append({"num": 6, "is_kwang": False, "code": "6B"})
    # 7
    deck.append({"num": 7, "is_kwang": False, "code": "7M"})  # 멍7
    deck.append({"num": 7, "is_kwang": False, "code": "7N"})
    # 8
    deck.append({"num": 8, "is_kwang": True, "code": "8K"})
    deck.append({"num": 8, "is_kwang": False, "code": "8N"})
    # 9
    deck.append({"num": 9, "is_kwang": False, "code": "9M"})  # 멍9
    deck.append({"num": 9, "is_kwang": False, "code": "9N"})
    # 10
    deck.append({"num": 10, "is_kwang": False, "code": "10A"})
    deck.append({"num": 10, "is_kwang": False, "code": "10B"})

    random.shuffle(deck)
    return deck

def card_to_str(c: dict) -> str:
    num = c["num"]
    code = c["code"]
    if c["is_kwang"]:
        return f"{num}광"
    if code in ("4M", "7M", "9M"):
        return f"멍{num}"
    if num == 10:
        return "장"
    return str(num)

# =========================
# 특수 족보 체크
# =========================

def is_meong49(c1, c2):
    codes = {c1["code"], c2["code"]}
    return "4M" in codes and "9M" in codes

def is_49(c1, c2):
    nums = {c1["num"], c2["num"]}
    return nums == {4, 9}

def is_amsa(c1, c2):
    codes = {c1["code"], c2["code"]}
    return "4M" in codes and "7M" in codes

def is_ttaengjabi(c1, c2):
    codes = {c1["code"], c2["code"]}
    return "3K" in codes and "7M" in codes

# =========================
# 기본 족보 (광땡 랭크는 요청대로 기존 유지)
# =========================

def eval_standard(c1, c2):
    n1, n2 = c1["num"], c2["num"]
    k1, k2 = c1["is_kwang"], c2["is_kwang"]
    sset = {n1, n2}

    # 광땡
    if k1 and k2:
        codes = {c1["code"], c2["code"]}
        if codes == {"3K", "8K"}:
            return 1, "38광땡"
        if codes == {"1K", "3K"}:
            return 2, "13광땡"
        if codes == {"1K", "8K"}:
            return 2, "18광땡"  # (요청대로 수정하지 않음)

    # 땡
    if n1 == n2:
        name_map = {
            10: "장땡", 9: "9땡", 8: "8땡", 7: "7땡", 6: "6땡",
            5: "5땡", 4: "4땡", 3: "3땡", 2: "2땡", 1: "1땡",
        }
        rank_map = {10: 3, 9: 4, 8: 5, 7: 6, 6: 7, 5: 8, 4: 9, 3: 10, 2: 11, 1: 12}
        if n1 in name_map:
            return rank_map[n1], name_map[n1]

    # 알리~세륙
    if sset == {1, 2}:  return 13, "알리"
    if sset == {1, 4}:  return 14, "독사"
    if sset == {1, 9}:  return 15, "구삥"
    if sset == {1, 10}: return 16, "장삥"
    if sset == {4, 10}: return 17, "장사"
    if sset == {4, 6}:  return 18, "세륙"

    # 끗 / 망통
    s = (n1 + n2) % 10
    if s == 0:
        return 30, "망통"
    rank = 19 + (9 - s)  # 9끗 제일 쎔
    return rank, f"{s}끗"

# =========================
# /start / 가입 / 무료칩 / 주머니
# =========================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "섯다 봇입니다.\n"
        "그룹에서 `.가입` 후 `.섯다` 로 게임을 시작하세요. 🃏"
    )

async def cmd_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    data = get_user(user)

    dm_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(
        "패 확인용 DM 열기",
        url="https://t.me/koreacajino_bot?start=seotda"
    )]])

    if data["joined"]:
        await update.message.reply_text(
            "이미 가입되어 있습니다. 😊\n"
            "섯다 패를 DM으로 받으려면 봇과 1:1 채팅이 열려 있어야 합니다.\n"
            "아래 버튼을 눌러 봇에게 먼저 말을 걸어 주세요.",
            reply_markup=dm_keyboard,
        )
        return

    data["joined"] = True
    data["balance"] += 100000
    save_users()

    await update.message.reply_text(
        "가입 완료! 10만 코인 지급 💺\n"
        "섯다 게임에서 패를 DM으로 받으시려면\n"
        "아래 버튼을 눌러 봇에게 먼저 말을 걸어 주세요.",
        reply_markup=dm_keyboard,
    )

async def cmd_freechip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    data = get_user(user)
    today = today_str()
    if data["freechips_date"] != today:
        data["freechips_date"] = today
        data["freechips_used"] = 0

    if data["freechips_used"] >= 3:
        await update.message.reply_text("오늘 무료칩은 모두 받았습니다. ⚠️")
        return

    data["freechips_used"] += 1
    data["balance"] += 100000
    save_users()

    await update.message.reply_text(
        f"무료칩 10만 코인 지급 ({data['freechips_used']}/3) 💰\n"
        f"현재 보유: {data['balance']:,} 코인"
    )

async def cmd_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_wallet_call
    user = update.effective_user
    data = get_user(user)

    now = update.message.date.timestamp()
    last = last_wallet_call.get(user.id, 0)
    if now - last < 2:
        return
    last_wallet_call[user.id] = now

    try:
        card = await create_profile_card(user, context)
        card.seek(0)
        await update.message.reply_photo(photo=card)
    except TimedOut:
        name = get_display_name(user)
        username = f"@{user.username}" if user.username else "(없음)"
        await update.message.reply_text(
            f"👤 이름: {name}\n"
            f"🔹 사용자명: {username}\n"
            f"💰 보유 코인: {data['balance']:,}\n"
            f"📈 전적: {data.get('wins',0)}승 {data.get('losses',0)}패\n"
            f"(이미지 전송 지연으로 텍스트 안내)"
        )
    except Exception as e:
        name = get_display_name(user)
        username = f"@{user.username}" if user.username else "(없음)"
        await update.message.reply_text(
            f"👤 이름: {name}\n"
            f"🔹 사용자명: {username}\n"
            f"💰 보유 코인: {data['balance']:,}\n"
            f"📈 전적: {data.get('wins',0)}승 {data.get('losses',0)}패\n"
            f"(프로필 카드 생성 실패: {e})"
        )

async def cmd_help_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        ".가입 : 가입 + 10만 코인\n"
        ".무료칩 : 하루 최대 3번, 10만씩\n"
        ".주머니 / ?주머니 : 프로필 카드/잔액 확인\n"
        ".섯다 : 방 생성\n"
        ".시작 : 방 만든 사람이 게임 시작\n"
        ".개평 금액 (리플) : 개평 요청"
    )

# =========================
# 개평 기능 (.개평 금액, 리플 전용)
# =========================

async def cmd_tip_geapyung_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message

    if not msg.reply_to_message:
        await msg.reply_text("개평은 받을 사람의 메시지에 리플로\n`.개평 금액` 형식으로 사용하세요.")
        return

    text = msg.text.strip()
    parts = text.split()
    if len(parts) < 2:
        await msg.reply_text("형식: `.개평 금액`")
        return

    try:
        amount = int(parts[1])
    except ValueError:
        await msg.reply_text("금액은 숫자로 입력하세요.")
        return

    if amount <= 0:
        await msg.reply_text("0 이하 금액은 불가합니다.")
        return

    sender = msg.from_user
    receiver = msg.reply_to_message.from_user

    if not receiver or receiver.is_bot:
        await msg.reply_text("봇이나 잘못된 대상에게는 개평을 보낼 수 없습니다.")
        return
    if sender.id == receiver.id:
        await msg.reply_text("자기 자신에게는 개평을 보낼 수 없습니다.")
        return

    sender_data = get_user(sender)
    if sender_data["balance"] < amount:
        await msg.reply_text("코인이 부족합니다.")
        return

    fee = max(int(amount * 0.05), 1)
    send_amount = amount - fee

    from_name = get_display_name(sender)
    to_name = get_display_name(receiver)

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("네",   callback_data=f"TIPCONFIRM|{msg.chat_id}|{sender.id}|{receiver.id}|{amount}"),
        InlineKeyboardButton("아니오", callback_data=f"TIPCANCEL|{msg.chat_id}|{sender.id}"),
    ]])

    await msg.reply_text(
        f"{from_name} 님이 {to_name} 님께\n"
        f"개평 {amount:,} 코인을 보내시겠습니까?\n"
        f"(수수료 5%: {fee:,} / 실제 수령: {send_amount:,})",
        reply_markup=kb,
    )

async def cb_tip_geapyung_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data.split("|")
    action = data[0]

    if action not in ("TIPCONFIRM", "TIPCANCEL"):
        await query.answer("잘못된 요청입니다.", show_alert=True)
        return

    chat_id = int(data[1])
    sender_id = int(data[2])

    if query.from_user.id != sender_id:
        await query.answer("요청자만 누를 수 있습니다.", show_alert=True)
        return

    if action == "TIPCANCEL":
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await query.answer()
        await query.message.reply_text("개평이 취소되었습니다.")
        return

    if len(data) != 5:
        await query.answer("데이터 오류", show_alert=True)
        return

    receiver_id = int(data[3])
    try:
        amount = int(data[4])
    except ValueError:
        await query.answer("데이터 오류", show_alert=True)
        return

    sender_user = await context.bot.get_chat(sender_id)
    receiver_user = await context.bot.get_chat(receiver_id)

    sender_data = get_user(sender_user)
    receiver_data = get_user(receiver_user)

    if sender_data["balance"] < amount:
        await query.answer()
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await query.message.reply_text("코인이 부족하여 개평을 진행할 수 없습니다.")
        return

    fee = max(int(amount * 0.05), 1)
    send_amount = amount - fee
    if send_amount <= 0:
        await query.answer()
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await query.message.reply_text("수수료를 제외하면 보낼 금액이 없습니다.")
        return

    sender_data["balance"] -= amount
    receiver_data["balance"] += send_amount
    save_users()

    from_name = get_display_name(sender_user)
    to_name = get_display_name(receiver_user)

    try:
        await query.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await query.answer()
    await query.message.reply_text(
        f"개평 완료 ✅\n"
        f"{from_name} → {to_name}\n"
        f"보낸 금액: {amount:,} 코인\n"
        f"수수료: {fee:,} 코인\n"
        f"실제 수령: {send_amount:,} 코인\n"
        f"{from_name} 잔액: {sender_data['balance']:,} 코인\n"
        f"{to_name} 잔액: {receiver_data['balance']:,} 코인"
    )

# =========================
# 관리자 돈 생성 (리플 전용)
# =========================

async def cmd_admin_money_gen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    sender = msg.from_user

    if not sender or not sender.username or sender.username not in ADMIN_USERNAMES:
        return

    if not msg.reply_to_message:
        await msg.reply_text("지급할 유저의 메시지에 리플로 사용하세요.")
        return

    text = msg.text.strip()
    parts = text.split()

    if len(parts) < 2:
        await msg.reply_text("형식: @@돈생성 금액")
        return

    try:
        amount = int(parts[1])
    except ValueError:
        await msg.reply_text("금액은 숫자로 입력하세요.")
        return

    if amount <= 0:
        await msg.reply_text("0 이하 금액은 불가합니다.")
        return

    target_user = msg.reply_to_message.from_user
    if not target_user or target_user.is_bot:
        await msg.reply_text("봇이나 잘못된 대상에게는 지급할 수 없습니다.")
        return

    data = get_user(target_user)
    data["balance"] += amount
    save_users()

    await msg.reply_text(
        f"{get_display_name(target_user)} 님께 {amount:,} 코인 지급 완료.\n"
        f"현재 보유: {data['balance']:,} 코인"
    )

# =========================
# 게임 상태/도움 함수
# =========================

def new_game_state(chat_id: int, initiator_id: int) -> dict:
    return {
        "chat_id": chat_id,
        "initiator_id": initiator_id,
        "stake": None,
        "entry": 0,
        "unit": 0,
        "phase": "choose_stake",
        "participants": [initiator_id],
        "participant_info": {},
        "recruit_message_id": None,
        "deck": [],
        "cards": {},
        "pot": 0,
        "bets": {},
        "folded": set(),
        "half1_chosen": set(),
        "half1_halfers": set(),
        "bet_order": [],
        "turn_index": 0,
        "current_bet": 0,
        "raised": False,
        "turn_timeout_job": None,
        "is_regame": False,
        "regame_players": [],
        "regame_ready": set(),
        "start_deadline_job": None,
        "half1_jobs": {},        # 👉 이 줄 추가
    }

def get_game(chat_id: int):
    return seotda_games.get(chat_id)

def get_stake_config(stake: int):
    entry = stake // 10
    unit = (stake - entry) // 3
    max_total = entry + unit * 3
    return entry, unit, max_total

def cancel_turn_job(game: dict):
    job = game.get("turn_timeout_job")
    if job:
        try:
            job.schedule_removal()
        except Exception:
            pass
    game["turn_timeout_job"] = None

def cancel_start_deadline(game: dict):
    job = game.get("start_deadline_job")
    if job:
        try:
            job.schedule_removal()
        except Exception:
            pass
    game["start_deadline_job"] = None

# =========================
# 섯다 생성 / 인원 모집 / 시작 / 취소
# =========================

async def cancel_if_not_started(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.data["chat_id"]

    game = get_game(chat_id)
    if not game:
        return

    if game["phase"] in ("choose_stake", "recruit"):
        seotda_games.pop(chat_id, None)
        await context.bot.send_message(
            chat_id,
            "1분 동안 시작되지 않아 섯다 방이 자동 취소되었습니다. 🛑"
        )

async def cmd_seotda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text("섯다는 그룹방에서만 가능합니다. 📢")
        return

    if chat.id in seotda_games and seotda_games[chat.id]["phase"] != "finished":
        await update.message.reply_text("이미 진행 중인 게임이 있습니다. ⏳")
        return

    get_user(user)
    save_users()

    seotda_games[chat.id] = new_game_state(chat.id, user.id)
    name = get_display_name(user)

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("5만상",  callback_data=f"SEOTDA_STAKE|{chat.id}|50000"),
            InlineKeyboardButton("10만상", callback_data=f"SEOTDA_STAKE|{chat.id}|100000"),
            InlineKeyboardButton("30만상", callback_data=f"SEOTDA_STAKE|{chat.id}|300000"),
        ],
        [InlineKeyboardButton("취소", callback_data=f"SEOTDA_CANCEL|{chat.id}")]
    ])

    await update.message.reply_text(
        f"{name} 님이 섯다 게임을 만들었습니다. 🃏\n상금을 선택해주세요.",
        reply_markup=kb,
    )

async def cb_choose_stake(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user

    try:
        _, chat_id_str, stake_str = query.data.split("|")
        chat_id = int(chat_id_str)
        stake = int(stake_str)
    except Exception:
        await query.answer("잘못된 요청입니다.", show_alert=True)
        return

    game = get_game(chat_id)
    if not game or game["phase"] == "finished":
        await query.answer("이미 종료된 게임입니다.", show_alert=True)
        return

    if user.id != game["initiator_id"]:
        await query.answer("게임 생성자만 설정할 수 있습니다.", show_alert=True)
        return

    if stake not in (50000, 100000, 300000):
        await query.answer("잘못된 상금입니다.", show_alert=True)
        return

    entry, unit, max_total = get_stake_config(stake)
    if max_total != stake:
        await query.answer("상금 설정 오류입니다.", show_alert=True)
        return

    udata = get_user(user)
    if udata["balance"] < entry:
        await context.bot.send_message(chat_id, "시작자의 코인이 부족합니다. ❌")
        game["phase"] = "finished"
        await query.answer()
        return

    # 시작자 학교비
    udata["balance"] -= entry
    save_users()
    game["pot"] += entry
    game["bets"][user.id] = game["bets"].get(user.id, 0) + entry

    game["stake"] = stake
    game["entry"] = entry
    game["unit"] = unit
    game["phase"] = "recruit"

    label = f"{stake // 10000}만상"

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("참여", callback_data=f"SEOTDA_JOIN|{chat_id}")],
        [InlineKeyboardButton("취소", callback_data=f"SEOTDA_CANCEL|{chat_id}")]
    ])

    msg = await context.bot.send_message(
        chat_id,
        f"💰 {label} 섯다 인원 모집\n"
        f"참여 시 학교비 {entry:,} 코인 차감.\n"
        f"(최소 2명, 최대 7명)",
        reply_markup=kb,
    )
    game["recruit_message_id"] = msg.message_id

    try:
        await query.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    if game.get("start_deadline_job"):
        try:
            game["start_deadline_job"].schedule_removal()
        except Exception:
            pass
    job = context.application.job_queue.run_once(
        cancel_if_not_started,
        60,
        data={"chat_id": chat_id},
        name=f"start_deadline_{chat_id}",
    )
    game["start_deadline_job"] = job

    await query.answer("상금 설정 완료 ✅")

async def cb_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    uid = user.id

    try:
        _, chat_id_str = query.data.split("|")
        chat_id = int(chat_id_str)
    except Exception:
        await query.answer("잘못된 요청입니다.", show_alert=True)
        return

    game = get_game(chat_id)
    if not game or game["phase"] != "recruit":
        await query.answer("지금은 참여할 수 없습니다.", show_alert=True)
        return

    if uid in game["participants"]:
        await query.answer("이미 참여 중입니다.", show_alert=True)
        return

    if len(game["participants"]) >= 7:
        await query.answer("인원이 가득 찼습니다.", show_alert=True)
        return

    entry = game["entry"]
    udata = get_user(user)
    if udata["balance"] < entry:
        await query.answer("코인이 부족합니다.", show_alert=True)
        return

    udata["balance"] -= entry
    save_users()
    game["pot"] += entry
    game["bets"][uid] = game["bets"].get(uid, 0) + entry

    game["participants"].append(uid)
    game["participant_info"][uid] = {"name": get_display_name(user)}

    now_cnt = len(game["participants"])
    await query.answer("참여 완료 ✅")
    await context.bot.send_message(
        chat_id,
        f"{get_display_name(user)} 님 참가 ({now_cnt}/7) 💺"
    )

    if now_cnt == 7:
        await context.bot.send_message(
            chat_id,
            "방 인원이 가득 찼습니다. .시작 으로 게임을 시작하세요. 🎉"
        )

async def cb_cancel_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user

    try:
        _, chat_id_str = query.data.split("|")
        chat_id = int(chat_id_str)
    except Exception:
        await query.answer("잘못된 요청입니다.", show_alert=True)
        return

    game = get_game(chat_id)
    if not game:
        await query.answer("취소할 게임이 없습니다.", show_alert=True)
        return

    if user.id != game["initiator_id"]:
        await query.answer("게임 생성자만 취소할 수 있습니다.", show_alert=True)
        return

    if game["phase"] not in ("choose_stake", "recruit"):
        await query.answer("이미 게임이 진행 중입니다. 취소 불가.", show_alert=True)
        return

    cancel_start_deadline(game)
    seotda_games.pop(chat_id, None)
    await query.answer()
    await context.bot.send_message(chat_id, "게임이 취소되었습니다. 🛑")

# =========================
# .시작 → 1장 DM + 하프/다이
# =========================

async def cmd_start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    chat_id = chat.id

    game = get_game(chat_id)
    if not game or game["phase"] != "recruit":
        await update.message.reply_text("시작 가능한 게임이 없습니다.")
        return

    # 방 만든 사람만 시작
    if user.id != game["initiator_id"]:
        await update.message.reply_text("게임 생성자만 시작할 수 있습니다. 🔐")
        return

    if len(game["participants"]) < 2:
        await update.message.reply_text("최소 2명 이상이어야 합니다.")
        return

    await update.message.reply_text(
        f"섯다 게임 시작! 참여 인원 {len(game['participants'])}명 🃏\n"
        f"첫 번째 패가 DM으로 발송됩니다."
    )

    # 자동취소 타이머 해제 후 한 번만 시작
    cancel_start_deadline(game)
    await start_half_phase(context, game)

async def start_half_phase(context: ContextTypes.DEFAULT_TYPE, game: dict):
    chat_id = game["chat_id"]

    if game["phase"] != "recruit":
        return

    participants = game["participants"]
    if len(participants) < 2:
        await context.bot.send_message(chat_id, "인원이 부족하여 게임을 시작할 수 없습니다. ❌")
        game["phase"] = "finished"
        return

    # 초기화
    game["deck"] = make_sutda_deck()
    game["cards"] = {}
    game["folded"] = set()
    game["half1_chosen"] = set()
    game["half1_halfers"] = set()
    game["is_regame"] = False
    game["turn_timeout_job"] = None
    game["half1_jobs"] = {}   # 👉 타이머 dict 초기화

    game["phase"] = "half1"

    for uid in participants:
        c1 = game["deck"].pop()
        game["cards"][uid] = [c1, None]
        try:
            await send_cards_dm(context, uid, [c1], "[첫 번째 패] 🃏")
        except Exception as e:
            logger.warning(f"1장 DM 실패: {uid}, {e}")
            await context.bot.send_message(
                chat_id,
                f"{await get_name_by_id(context, uid)} 님께 DM을 보낼 수 없어 게임을 종료합니다. ❌"
            )
            game["phase"] = "finished"
            return

        # 👉 여기서 45초 타이머 걸기
        job = context.application.job_queue.run_once(
            half1_timeout,
            TURN_TIMEOUT,
            data={"chat_id": chat_id, "uid": uid},
            name=f"half1_timeout_{chat_id}_{uid}",
        )
        game["half1_jobs"][uid] = job

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("하프", callback_data=f"H1|{chat_id}|HALF"),
            InlineKeyboardButton("다이", callback_data=f"H1|{chat_id}|FOLD"),
        ],
        [
            InlineKeyboardButton(
                "패 확인하러가기",
                url=f"https://t.me/{(await context.bot.get_me()).username}"
            )
        ]
    ])

    await context.bot.send_message(
        chat_id,
        "2장을 받으려면 하프, 포기 시 다이를 선택해주세요.",
        reply_markup=kb,
    )


async def send_cards_dm(context: ContextTypes.DEFAULT_TYPE, uid: int, cards: list[dict], title: str):
    if len(cards) == 2:
        rank, name = eval_standard(cards[0], cards[1])
        text = f"[섯다] {title} 🃏\n" \
               f"{card_to_str(cards[0])} / {card_to_str(cards[1])}\n" \
               f"➡ {name}"
    else:
        text = f"[섯다] {title} 🃏\n" + " / ".join(card_to_str(c) for c in cards)

    await context.bot.send_message(uid, text)

    for c in cards:
        fid = CARD_STICKERS.get(c["code"])
        if fid:
            await context.bot.send_sticker(uid, fid)

async def cb_half1_or_die(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    uid = user.id

    try:
        _, chat_id_str, action = query.data.split("|")
        chat_id = int(chat_id_str)
    except Exception:
        await query.answer("잘못된 요청입니다.", show_alert=True)
        return

    game = get_game(chat_id)
    if not game or game["phase"] != "half1":
        await query.answer("지금은 선택할 수 없습니다.", show_alert=True)
        return

    if uid not in game["participants"]:
        await query.answer("참가자가 아닙니다.", show_alert=True)
        return

    if uid in game["half1_chosen"]:
        await query.answer("이미 선택했습니다.", show_alert=True)
        return

    unit = game["unit"]
    udata = get_user(user)

    if action == "HALF":
        if udata["balance"] < unit:
            await query.answer("코인 부족으로 하프 불가. 다이 처리됩니다.", show_alert=True)
            game["folded"].add(uid)
        else:
            udata["balance"] -= unit
            save_users()
            game["pot"] += unit
            game["bets"][uid] = game["bets"].get(uid, 0) + unit
            game["half1_halfers"].add(uid)
            await context.bot.send_message(
                chat_id,
                f"{await get_name_by_id(context, uid)} 님 하프 (2장 진행) 💰"
            )
    elif action == "FOLD":
        game["folded"].add(uid)
        await context.bot.send_message(
            chat_id,
            f"{await get_name_by_id(context, uid)} 님 다이 (학교비만 지불). ✋"
        )
    else:
        await query.answer("잘못된 선택입니다.", show_alert=True)
        return

    # ... 하프/다이 처리 로직 끝난 후 ...

    # 이 유저 타임아웃 취소
    job = game.get("half1_jobs", {}).pop(uid, None)
    if job:
        try:
            job.schedule_removal()
        except Exception:
            pass

    game["half1_chosen"].add(uid)
    await query.answer()

    if len(game["half1_chosen"]) == len(game["participants"]):
        await after_half1_complete(context, game)


async def after_half1_complete(context: ContextTypes.DEFAULT_TYPE, game: dict):
    chat_id = game["chat_id"]

    survivors = [uid for uid in game["half1_halfers"] if uid not in game["folded"]]

    if len(survivors) == 0:
        await finish_with_winners(context, game, [game["initiator_id"]], "모두 포기 → 시작자 승리 🏆")
        return

    if len(survivors) == 1:
        await finish_with_winners(context, game, survivors, "단독 하프 → 승리 🏆")
        return

    await start_bet2_phase(context, game, survivors)

# =========================
# 2단계: 2장 + 피망식 본베팅 + 45초
# =========================

def is_alive(game: dict, uid: int) -> bool:
    return uid not in game["folded"] and uid in game["half1_halfers"]

def get_alive_players(game: dict) -> list[int]:
    return [u for u in game.get("bet_order", []) if is_alive(game, u)]

async def start_bet2_phase(context: ContextTypes.DEFAULT_TYPE, game: dict, survivors: list[int]):
    chat_id = game["chat_id"]

    if game["phase"] != "half1":
        return

    for uid in survivors:
        if uid in game["folded"]:
            continue
        c2 = game["deck"].pop()
        game["cards"][uid][1] = c2
        c1 = game["cards"][uid][0]
        try:
            await send_cards_dm(context, uid, [c1, c2], "최종 패")
        except Exception as e:
            logger.warning(f"2장 DM 실패: {uid}, {e}")
            game["folded"].add(uid)

    alive = [u for u in survivors if is_alive(game, u)]

    if len(alive) == 0:
        await finish_with_winners(context, game, [game["initiator_id"]], "전원 탈락 → 시작자 승리 🏆")
        return
    if len(alive) == 1:
        await finish_with_winners(context, game, alive, "단독 생존 → 승리 🏆")
        return

    game["phase"] = "bet2"
    random.shuffle(alive)
    game["bet_order"] = alive
    game["turn_index"] = 0
    game["raised"] = False
    game["current_bet"] = max(game["bets"].get(u, 0) for u in alive)
    cancel_turn_job(game)

    bot_username = (await context.bot.get_me()).username
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("패 확인하러가기", url=f"https://t.me/{bot_username}")]])

    await context.bot.send_message(
        chat_id,
        "2장 패가 배부되었습니다. 본베팅 시작합니다. 🔁\n각 턴당 45초 안에 선택하지 않으면 자동 처리됩니다. ⏰",
        reply_markup=kb,
    )

    await prompt_bet2(context, game)

async def prompt_bet2(context: ContextTypes.DEFAULT_TYPE, game: dict):
    chat_id = game["chat_id"]
    alive = get_alive_players(game)

    if len(alive) <= 1:
        cancel_turn_job(game)
        if alive:
            await finish_with_winners(context, game, alive, "단독 생존 → 승리 🏆")
        else:
            await finish_with_winners(context, game, [game["initiator_id"]], "전원 포기 → 시작자 승리 🏆")
        return

    if game["turn_index"] >= len(game["bet_order"]):
        cancel_turn_job(game)
        await after_bet2_round(context, game)
        return

    uid = game["bet_order"][game["turn_index"]]

    if not is_alive(game, uid):
        game["turn_index"] += 1
        await prompt_bet2(context, game)
        return

    name = await get_name_by_id(context, uid)
    stake = game["stake"]
    pot = game["pot"]
    my_bet = game["bets"].get(uid, 0)
    current_bet = game["current_bet"]
    raised = game["raised"]

    udata = users.get(uid, {"balance": 0})
    balance = udata["balance"]

    remain_cap = max(stake - my_bet, 0)
    can_spend = min(remain_cap, balance)

    quarter = max(pot // 4, 1)
    half = max(pot // 2, quarter * 2)

    buttons = []

    if not raised:
        buttons.append(InlineKeyboardButton("체크", callback_data=f"B2|{chat_id}|{uid}|CHECK"))
        if can_spend >= quarter:
            buttons.append(InlineKeyboardButton(f"쿼터 {quarter:,}", callback_data=f"B2|{chat_id}|{uid}|QUARTER"))
        if can_spend >= half:
            buttons.append(InlineKeyboardButton(f"하프 {half:,}", callback_data=f"B2|{chat_id}|{uid}|HALF"))
        buttons.append(InlineKeyboardButton("다이", callback_data=f"B2|{chat_id}|{uid}|FOLD"))
    else:
        need = max(current_bet - my_bet, 0)
        if need > 0:
            if can_spend >= need:
                buttons.append(InlineKeyboardButton(f"콜 {need:,}", callback_data=f"B2|{chat_id}|{uid}|CALL"))
            if can_spend >= quarter:
                buttons.append(InlineKeyboardButton(f"쿼터 재인상 {quarter:,}", callback_data=f"B2|{chat_id}|{uid}|RQUARTER"))
            if can_spend >= half:
                buttons.append(InlineKeyboardButton(f"하프 재인상 {half:,}", callback_data=f"B2|{chat_id}|{uid}|RHALF"))
            buttons.append(InlineKeyboardButton("다이", callback_data=f"B2|{chat_id}|{uid}|FOLD"))
        else:
            buttons.append(InlineKeyboardButton("체크", callback_data=f"B2|{chat_id}|{uid}|CHECK"))
            if can_spend >= quarter:
                buttons.append(InlineKeyboardButton(f"쿼터 재인상 {quarter:,}", callback_data=f"B2|{chat_id}|{uid}|RQUARTER"))
            if can_spend >= half:
                buttons.append(InlineKeyboardButton(f"하프 재인상 {half:,}", callback_data=f"B2|{chat_id}|{uid}|RHALF"))

    if not buttons:
        game["folded"].add(uid)
        await context.bot.send_message(chat_id, f"{name} 님 코인 부족으로 자동 다이 처리됩니다. ✋")
        game["turn_index"] += 1
        await prompt_bet2(context, game)
        return

    cancel_turn_job(game)

    await context.bot.send_message(
        chat_id,
        f"{name} 님, 배팅하시겠습니까? (45초) 🎲",
        reply_markup=InlineKeyboardMarkup([buttons]),
    )

    job = context.application.job_queue.run_once(
        bet_timeout,
        TURN_TIMEOUT,
        data={"chat_id": chat_id, "uid": uid},
        name=f"bet_timeout_{chat_id}_{uid}",
    )
    game["turn_timeout_job"] = job

async def cb_bet2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    actor = query.from_user

    try:
        _, chat_id_str, uid_str, action = query.data.split("|")
        chat_id = int(chat_id_str)
        target_uid = int(uid_str)
    except Exception:
        await query.answer("잘못된 데이터입니다.", show_alert=True)
        return

    game = get_game(chat_id)
    if not game or game["phase"] != "bet2":
        await query.answer("잘못된 타이밍입니다.", show_alert=True)
        return

    if actor.id != target_uid:
        await query.answer("본인 차례만 가능합니다.", show_alert=True)
        return

    if not (game["turn_index"] < len(game["bet_order"]) and game["bet_order"][game["turn_index"]] == target_uid):
        await query.answer("지금은 당신의 차례가 아닙니다.", show_alert=True)
        return

    uid = actor.id
    name = await get_name_by_id(context, uid)
    stake = game["stake"]
    pot = game["pot"]
    my_bet = game["bets"].get(uid, 0)
    current_bet = game["current_bet"]
    raised = game["raised"]

    udata = get_user(actor)
    balance = udata["balance"]
    remain_cap = max(stake - my_bet, 0)
    can_spend = min(remain_cap, balance)

    quarter = max(pot // 4, 1)
    half = max(pot // 2, quarter * 2)

    msg = None

    def bet_more(amount: int) -> bool:
        nonlocal pot, my_bet
        if amount <= 0 or amount > can_spend:
            return False
        udata["balance"] -= amount
        my_bet += amount
        pot += amount
        game["bets"][uid] = my_bet
        game["pot"] = pot
        return True

    cancel_turn_job(game)

    if action == "CHECK":
        if raised and my_bet < current_bet:
            await query.answer("콜 또는 다이만 가능합니다.", show_alert=True)
            return
        msg = f"{name} 님 체크 ✅"

    elif action == "FOLD":
        game["folded"].add(uid)
        msg = f"{name} 님 다이. ✋"

    elif action == "QUARTER":
        if raised:
            await query.answer("재인상 버튼을 사용하세요.", show_alert=True)
            return
        if not bet_more(quarter):
            await query.answer("쿼터 불가.", show_alert=True)
            return
        game["raised"] = True
        game["current_bet"] = my_bet
        msg = f"{name} 님 쿼터 {quarter:,} 💰"

    elif action == "HALF":
        if raised:
            await query.answer("재인상 버튼을 사용하세요.", show_alert=True)
            return
        if not bet_more(half):
            await query.answer("하프 불가.", show_alert=True)
            return
        game["raised"] = True
        game["current_bet"] = my_bet
        msg = f"{name} 님 하프 {half:,} 💰"

    elif action == "CALL":
        if not raised:
            await query.answer("아직 인상된 베팅이 없습니다.", show_alert=True)
            return
        if my_bet >= current_bet:
            await query.answer("이미 콜 상태입니다.", show_alert=True)
            return
        need = current_bet - my_bet
        if need > can_spend:
            game["folded"].add(uid)
            msg = f"{name} 님 코인 부족으로 다이. ✋"
        else:
            bet_more(need)
            msg = f"{name} 님 콜 {need:,} ✅"

    elif action in ("RQUARTER", "RHALF"):
        if not raised:
            await query.answer("아직 인상 상태가 아닙니다.", show_alert=True)
            return
        base = quarter if action == "RQUARTER" else half
        if my_bet + base <= current_bet:
            await query.answer("재인상 금액이 부족합니다.", show_alert=True)
            return
        if not bet_more(base):
            await query.answer("재인상 불가.", show_alert=True)
            return
        game["current_bet"] = my_bet
        msg = f"{name} 님 베팅 인상 {base:,} 💣"

    else:
        await query.answer("잘못된 선택입니다.", show_alert=True)
        return

    save_users()
    await query.answer()
    if msg:
        await context.bot.send_message(chat_id, msg)

    game["turn_index"] += 1
    await prompt_bet2(context, game)

async def after_bet2_round(context: ContextTypes.DEFAULT_TYPE, game: dict):
    chat_id = game["chat_id"]
    alive = get_alive_players(game)

    if len(alive) <= 1:
        cancel_turn_job(game)
        if alive:
            await finish_with_winners(context, game, alive, "단독 생존 → 승리 🏆")
        else:
            await finish_with_winners(context, game, [game["initiator_id"]], "전원 포기 → 시작자 승리 🏆")
        return

    current_bet = max(game["bets"].get(u, 0) for u in alive)
    game["current_bet"] = current_bet

    if not game["raised"]:
        cancel_turn_job(game)
        await showdown(context, game, alive, allow_regame=True)
        return

    if all(game["bets"].get(u, 0) == current_bet for u in alive):
        cancel_turn_job(game)
        await showdown(context, game, alive, allow_regame=True)
        return

    game["turn_index"] = 0
    await context.bot.send_message(chat_id, "콜되지 않은 베팅이 있어 한 번 더 진행합니다. 🔁")
    await prompt_bet2(context, game)

# =========================
# 45초 타임아웃
# =========================

async def half1_timeout(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    data = job.data
    chat_id = data["chat_id"]
    uid = data["uid"]

    game = get_game(chat_id)
    if not game or game["phase"] != "half1":
        return

    # 이미 선택했으면 무시
    if uid in game.get("half1_chosen", set()):
        return

    name = await get_name_by_id(context, uid)

    # 자동 다이 처리
    game["folded"].add(uid)
    game.setdefault("half1_chosen", set()).add(uid)

    await context.bot.send_message(
        chat_id,
        f"{name} 님 45초 초과로 자동 다이 처리됩니다. ⏰✋"
    )

    # 이 유저 타이머 정리
    if "half1_jobs" in game:
        job_obj = game["half1_jobs"].pop(uid, None)
        if job_obj:
            try:
                job_obj.schedule_removal()
            except Exception:
                pass

    # 전원 결정 완료 시 다음 단계
    if len(game["half1_chosen"]) == len(game["participants"]):
        await after_half1_complete(context, game)


async def bet_timeout(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    data = job.data
    chat_id = data["chat_id"]
    uid = data["uid"]

    game = get_game(chat_id)
    if not game or game["phase"] != "bet2":
        return

    if job != game.get("turn_timeout_job"):
        return

    if not (game["turn_index"] < len(game["bet_order"]) and game["bet_order"][game["turn_index"]] == uid):
        return

    if not is_alive(game, uid):
        return

    name = await get_name_by_id(context, uid)
    my_bet = game["bets"].get(uid, 0)
    current_bet = game["current_bet"]

    game["turn_timeout_job"] = None

    if game["raised"] and my_bet < current_bet:
        game["folded"].add(uid)
        await context.bot.send_message(chat_id, f"{name} 님 45초 초과로 자동 다이 처리됩니다. ⏰✋")
    else:
        await context.bot.send_message(chat_id, f"{name} 님 45초 초과로 자동 체크 처리됩니다. ⏰✅")

    game["turn_index"] += 1
    await prompt_bet2(context, game)

# =========================
# 재경기 / 쇼다운 / 정산
# =========================

async def start_regame(context: ContextTypes.DEFAULT_TYPE, game: dict, players: list[int], reason: str):
    chat_id = game["chat_id"]
    cancel_turn_job(game)

    game["is_regame"] = True
    game["phase"] = "regame"
    game["regame_players"] = players
    game["regame_ready"] = set()
    game["deck"] = make_sutda_deck()
    game["cards"] = {}

    await context.bot.send_message(
        chat_id,
        f"{reason}\n재경기: 생존자 {len(players)}명, 기존 팟 그대로, 추가 베팅 없이 2장 쇼다운 진행. 🔁"
    )

    alive = []
    for uid in players:
        c1 = game["deck"].pop()
        c2 = game["deck"].pop()
        game["cards"][uid] = [c1, c2]
        try:
            await send_cards_dm(context, uid, [c1, c2], "[재경기 패]")
            alive.append(uid)
        except Exception as e:
            logger.warning(f"재경기 DM 실패: {uid}, {e}")

    game["regame_players"] = alive

    if len(alive) <= 1:
        if alive:
            await finish_with_winners(context, game, alive, "재경기 단독 생존 → 승리 🏆")
        else:
            await finish_with_winners(context, game, [game["initiator_id"]], "재경기 전원 탈락 → 시작자 승리 🏆")
        return

    kb = InlineKeyboardMarkup([[InlineKeyboardButton("쇼다운", callback_data=f"RG|{chat_id}|READY")]])

    await context.bot.send_message(
        chat_id,
        "재경기 참가자분들은 '쇼다운' 버튼을 눌러주세요.",
        reply_markup=kb,
    )

async def cb_regame_showdown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user

    _, chat_id_str, cmd = query.data.split("|")
    chat_id = int(chat_id_str)

    game = get_game(chat_id)
    if not game or game.get("phase") != "regame":
        await query.answer("재경기 상태가 아닙니다.", show_alert=True)
        return

    uid = user.id
    if uid not in game.get("regame_players", []):
        await query.answer("재경기 참가자가 아닙니다.", show_alert=True)
        return

    if cmd != "READY":
        await query.answer("잘못된 선택입니다.", show_alert=True)
        return

    if uid in game["regame_ready"]:
        await query.answer("이미 준비 완료입니다.", show_alert=True)
        return

    game["regame_ready"].add(uid)
    await query.answer()
    await context.bot.send_message(chat_id, f"{await get_name_by_id(context, uid)} 님 쇼다운 준비 완료 ✅")

    if len(game["regame_ready"]) == len(game["regame_players"]):
        await showdown(context, game, game["regame_players"], allow_regame=False)

async def showdown(context: ContextTypes.DEFAULT_TYPE, game: dict, survivors: list[int], allow_regame: bool):
    chat_id = game["chat_id"]
    pot = game["pot"]

    cancel_turn_job(game)

    hands = []
    for uid in survivors:
        c1, c2 = game["cards"][uid]
        std_rank, std_name = eval_standard(c1, c2)
        hands.append({
            "uid": uid,
            "name": await get_name_by_id(context, uid),
            "c1": c1, "c2": c2,
            "std_rank": std_rank, "std_name": std_name,
            "is_meong49": is_meong49(c1, c2),
            "is_49": is_49(c1, c2),
            "is_amsa": is_amsa(c1, c2),
            "is_tj": is_ttaengjabi(c1, c2),
        })

    if allow_regame:
        top_std = min(h["std_rank"] for h in hands)

        meong = [h for h in hands if h["is_meong49"]]
        if meong and top_std > 2:
            players = [h["uid"] for h in hands]
            await start_regame(context, game, players, "멍49 재경기 발동! 🔁")
            return

        g49 = [h for h in hands if h["is_49"]]
        if g49 and top_std >= 13:
            players = [h["uid"] for h in hands]
            await start_regame(context, game, players, "49 재경기 발동! 🔁")
            return

    amsa = [h for h in hands if h["is_amsa"]]
    has_38 = any(h["std_rank"] == 1 for h in hands)
    has_mid_gwang = any(h["std_rank"] == 2 for h in hands)  # 13/18
    if amsa:
        if not has_38 and has_mid_gwang:
            winners = [h["uid"] for h in amsa]
            await finish_with_winners(context, game, winners, "암행어사 발동! (13·18광땡 제압) 🕵️‍♂️")
            return

    tj = [h for h in hands if h["is_tj"]]
    if tj:
        top_std = min(h["std_rank"] for h in hands)
        if 4 <= top_std <= 12:
            winners = [h["uid"] for h in tj]
            await finish_with_winners(context, game, winners, "땡잡이 발동! (땡 제압) 🎯")
            return

    hands.sort(key=lambda x: x["std_rank"])
    best = hands[0]["std_rank"]
    win_list = [h for h in hands if h["std_rank"] == best]

    winner_ids = [w["uid"] for w in win_list]
    share = pot // len(win_list) if win_list else 0

    for uid in winner_ids:
        if uid in users:
            users[uid].setdefault("wins", 0)
            users[uid].setdefault("losses", 0)
            users[uid]["balance"] += share

    participants = game.get("participants", [])
    for uid in participants:
        if uid not in users:
            continue
        users[uid].setdefault("wins", 0)
        users[uid].setdefault("losses", 0)
        if uid in winner_ids:
            users[uid]["wins"] += 1
        else:
            users[uid]["losses"] += 1

    save_users()

    lines = ["[쇼다운 결과]"]
    for h in hands:
        lines.append(
            f"{h['name']}: {card_to_str(h['c1'])} / {card_to_str(h['c2'])} → {h['std_name']}"
        )

    if len(winner_ids) == 1:
        lines.append(f"\n🏆 승자: {win_list[0]['name']} (+{share:,} 코인)")
    else:
        wn = ", ".join(w["name"] for w in win_list)
        lines.append(f"\n🏆 공동 승자: {wn} (각 +{share:,} 코인)")

    lines.append(f"\n💰 총 팟: {pot:,} 코인")

    await context.bot.send_message(chat_id, "\n".join(lines))
    game["phase"] = "finished"

async def finish_with_winners(context: ContextTypes.DEFAULT_TYPE, game: dict, winner_ids: list[int], reason: str = ""):
    chat_id = game["chat_id"]
    pot = game["pot"]

    cancel_turn_job(game)

    share = pot // len(winner_ids) if winner_ids else 0
    names = []
    for uid in winner_ids:
        if uid in users:
            users[uid].setdefault("wins", 0)
            users[uid].setdefault("losses", 0)
            users[uid]["balance"] += share
        names.append(await get_name_by_id(context, uid))

    participants = game.get("participants", [])
    for uid in participants:
        if uid not in users:
            continue
        users[uid].setdefault("wins", 0)
        users[uid].setdefault("losses", 0)
        if uid in winner_ids:
            users[uid]["wins"] += 1
        else:
            users[uid]["losses"] += 1

    save_users()

    text = "[게임 종료]\n"
    if reason:
        text += reason + "\n"
    if winner_ids:
        if len(winner_ids) == 1:
            text += f"🏆 승자: {names[0]} (+{share:,} 코인)\n"
        else:
            text += f"🏆 공동 승자: {', '.join(names)} (각 +{share:,} 코인)\n"
    text += f"💰 총 팟: {pot:,} 코인"

    await context.bot.send_message(chat_id, text)
    game["phase"] = "finished"

# =========================
# main
# =========================

def main():
    load_users()

    request = HTTPXRequest(
        connect_timeout=30.0,
        read_timeout=60.0,
        write_timeout=60.0,
        pool_timeout=60.0,
    )

    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .request(request)
        .build()
    )

    # /start
    app.add_handler(CommandHandler("start", cmd_start))

    # 가입 / 무료칩 / 주머니
    app.add_handler(MessageHandler(filters.Regex(r"^\.가입$") & filters.TEXT, cmd_join))
    app.add_handler(MessageHandler(filters.Regex(r"^\.무료칩$") & filters.TEXT, cmd_freechip))
    app.add_handler(MessageHandler(filters.Regex(r"^[\.\?]주머니$") & filters.TEXT, cmd_wallet))
    app.add_handler(MessageHandler(filters.Regex(r"^\.설명$") & filters.TEXT, cmd_help_text))
    
    # 개평 (.개평 금액, 리플 전용)
    app.add_handler(
        MessageHandler(
            filters.Regex(r"^\.개평\s+\d+$") & filters.REPLY & filters.TEXT,
            cmd_tip_geapyung_request,
        )
    )
    app.add_handler(CallbackQueryHandler(cb_tip_geapyung_confirm, pattern=r"^TIPCONFIRM\|"))
    app.add_handler(CallbackQueryHandler(cb_tip_geapyung_confirm, pattern=r"^TIPCANCEL\|"))

    # 관리자 돈 생성 (리플에서 @@돈생성 금액)
    app.add_handler(
        MessageHandler(
            filters.Regex(r"^@@돈생성\s+\d+$") & filters.TEXT,
            cmd_admin_money_gen,
        )
    )

    # 섯다 생성 / 인원 모집 / 시작 / 취소
    app.add_handler(MessageHandler(filters.Regex(r"^\.섯다$") & filters.TEXT, cmd_seotda))
    app.add_handler(CallbackQueryHandler(cb_choose_stake, pattern=r"^SEOTDA_STAKE\|"))
    app.add_handler(CallbackQueryHandler(cb_join, pattern=r"^SEOTDA_JOIN\|"))
    app.add_handler(CallbackQueryHandler(cb_cancel_game, pattern=r"^SEOTDA_CANCEL\|"))
    app.add_handler(MessageHandler(filters.Regex(r"^\.시작$") & filters.TEXT, cmd_start_game))

    # 1단계 하프/다이
    app.add_handler(CallbackQueryHandler(cb_half1_or_die, pattern=r"^H1\|"))

    # 2단계 본베팅
    app.add_handler(CallbackQueryHandler(cb_bet2, pattern=r"^B2\|"))

    # 재경기 쇼다운
    app.add_handler(CallbackQueryHandler(cb_regame_showdown, pattern=r"^RG\|"))

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
