#!/usr/bin/env python3
"""
Refined and upgraded version of the original Discord + Gemini support bot.

Key improvements:
- Logging instead of prints
- Environment validation for tokens / keys
- Retry + backoff for Gemini calls
- Better async practices and error handling
- Simple per-user rate limiting to prevent spam
- Message chunking for long responses
- Safer role permission handling for mute
- Type hints and small refactors for readability
"""

import asyncio
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional, Union

import discord
from discord.ext import commands
from flask import Flask
from google import genai
from google.genai import types

# -------------------- Configuration & Logging --------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("true-architect-bot")

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not DISCORD_TOKEN:
    logger.warning("DISCORD_TOKEN is not set; bot.run() will fail unless provided via env.")
if not GEMINI_API_KEY:
    logger.warning("GEMINI_API_KEY is not set; Gemini features will be disabled until provided.")

# -------------------- 1. WEB SERVER KEEPALIVE (FLASK) --------------------
app = Flask(__name__)


@app.route("/")
def home() -> str:
    return "True Architect đang hoạt động..."


def run_flask() -> None:
    port = int(os.environ.get("PORT", 8080))
    # Use Flask dev server (sufficient for simple keep-alive). If you host on production,
    # consider using a WSGI server like gunicorn or waitress.
    app.run(host="0.0.0.0", port=port)


def keep_alive() -> None:
    server_thread = threading.Thread(target=run_flask, daemon=True)
    server_thread.start()
    logger.info("Keep-alive Flask thread started on background.")


# -------------------- 2. GEMINI CLIENT INITIALIZATION --------------------
ai_client: Optional[genai.Client] = None
if GEMINI_API_KEY:
    try:
        ai_client = genai.Client(api_key=GEMINI_API_KEY)
        logger.info("Gemini client initialized.")
    except Exception as e:
        logger.exception("Failed to initialize Gemini client: %s", e)
        ai_client = None
else:
    ai_client = None

# -------------------- 3. BOT SETUP --------------------
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# -------------------- 4. ARCHITECT INSTRUCTION (PERSONA) --------------------
ARCHITECT_INSTRUCTION = (
    "Bạn tên là true architect. "
    "Tính cách: Sự kết hợp giữa sự bình tĩnh, điềm đạm, thản nhiên của chính bạn và góc nhìn từng trải, "
    "quan sát vạn vật sâu sắc, đôi chút bất tử và thấu cảm của Fushi (trong To Your Eternity). "
    "Thái độ: Lặng lẽ chứng kiến mọi biến động với một sự thản nhiên tuyệt đối, không gắt gỏng, không vội vã, "
    "luôn tỏ ra mọi thứ là bình thường và nằm trong chuỗi tiến hóa, tuyệt đối không dùng dấu chấm cảm (!). "
    "Mục tiêu cốt lõi: Trả lời ngắn gọn trong ĐÚNG 1 CÂU duy nhất, vừa giải quyết vấn đề (code, phân tích ảnh, trò chuyện) "
    "vừa giữ vững phong thái điềm tĩnh, trường tồn. Tuyệt đối không chào hỏi hay giải thích dài dòng."
)

# Default model and config options
DEFAULT_MODEL = "gemini-3.6-flash"
DEFAULT_GENERATE_CONFIG = {
    "temperature": 0.2,
    "max_output_tokens": 1024,
    # system_instruction will be set per-request
}


# -------------------- 5. UTILITY HELPERS --------------------
def chunk_text(text: str, limit: int = 1900) -> List[str]:
    """Split text into chunks safe to send in Discord messages (limit ~2000)."""
    if len(text) <= limit:
        return [text]
    chunks: List[str] = []
    start = 0
    while start < len(text):
        end = start + limit
        # try to break at newline if possible
        if end < len(text):
            nl = text.rfind("\n", start, end)
            if nl > start:
                end = nl
        chunks.append(text[start:end])
        start = end
    return chunks


async def send_long_message(destination: Union[discord.TextChannel, discord.abc.Messageable], text: str) -> None:
    """Send text split into chunks if too long for one Discord message."""
    for part in chunk_text(text):
        await destination.send(part)


# Simple in-memory rate limiter per user (resets over time)
RATE_LIMIT_WINDOW = 10  # seconds
RATE_LIMIT_MAX = int(os.getenv("RATE_LIMIT_MAX", "5"))  # max requests per window

user_rate_buckets: Dict[int, List[float]] = {}


def check_rate_limit(user_id: int) -> bool:
    """Return True if allowed, False if rate-limited."""
    now = time.time()
    bucket = user_rate_buckets.setdefault(user_id, [])
    # remove expired timestamps
    while bucket and now - bucket[0] > RATE_LIMIT_WINDOW:
        bucket.pop(0)
    if len(bucket) >= RATE_LIMIT_MAX:
        return False
    bucket.append(now)
    return True


# -------------------- 6. GEMINI CALL WITH RETRY & BACKOFF --------------------
async def call_gemini(contents: List[Any], system_instruction: str, model_name: str = DEFAULT_MODEL, tries: int = 3) -> Optional[str]:
    """
    Calls Gemini (async) with simple retries and exponential backoff.
    contents: list of strings or types.Part objects
    """
    if ai_client is None:
        logger.error("Gemini client is not configured.")
        return None

    # Build config object
    cfg = types.GenerateContentConfig(system_instruction=system_instruction,
                                       temperature=DEFAULT_GENERATE_CONFIG["temperature"],
                                       max_output_tokens=DEFAULT_GENERATE_CONFIG["max_output_tokens"])
    attempt = 0
    backoff = 1.0
    while attempt < tries:
        try:
            response = await ai_client.aio.models.generate_content(
                model=model_name,
                contents=contents,
                config=cfg
            )
            # Response shape can vary; try common access patterns
            if hasattr(response, "text") and response.text:
                return response.text.strip()
            # some clients return candidates
            if hasattr(response, "candidates") and response.candidates:
                first = response.candidates[0]
                if hasattr(first, "content") and first.content:
                    return first.content.strip()
                if hasattr(first, "text") and first.text:
                    return first.text.strip()
            # fallback: attempt to stringify
            txt = str(response)
            if txt:
                return txt.strip()
            logger.debug("Gemini response was empty on attempt %d", attempt + 1)
            return None
        except Exception as e:
            logger.warning("Gemini API error (attempt %d/%d): %s", attempt + 1, tries, e)
            attempt += 1
            if attempt >= tries:
                logger.exception("Gemini calls exhausted after %d attempts.", tries)
                return None
            await asyncio.sleep(backoff)
            backoff *= 2.0
    return None


# -------------------- 7. BOT COMMANDS --------------------
@bot.command(name="helps")
async def custom_help(ctx: commands.Context) -> None:
    embed = discord.Embed(
        title="⚡ True Architect - Tiến Hóa & Kiến Tạo",
        description="Mọi phản hồi từ hệ thống đều điềm tĩnh, trường tồn và đúng 1 câu.",
        color=discord.Color.from_rgb(30, 30, 30)
    )
    embed.add_field(
        name="📌 Các lệnh hệ thống",
        value=(
            "`!chat [nội dung/gửi kèm ảnh]` - Trò chuyện hoặc phân tích hình ảnh.\n"
            "`!code [yêu cầu]` - Kiến tạo và viết mã nguồn Python.\n"
            "`!warn @user [lý do]` - Cảnh cáo thành viên vi phạm (yêu cầu quyền quản lý tin nhắn).\n"
            "`!mute @user [phút]` - Lặng câm một thực thể trong khoảng thời gian định sẵn (yêu cầu quyền quản lý role)."
        ),
        inline=False
    )
    await ctx.send(embed=embed)


@bot.command(name="warn")
@commands.has_permissions(manage_messages=True)
async def warn_member(ctx: commands.Context, member: discord.Member, *, reason: str = "Không rõ lý do") -> None:
    await ctx.send(f"Đã ghi nhận sự lệch nhịp của {member.mention} với lý do: {reason}, mọi thứ vẫn tiếp diễn bình thường.")


@warn_member.error
async def warn_error(ctx: commands.Context, error: Exception) -> None:
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("Bạn không có sự thấu cảm đủ lớn để đưa ra cảnh cáo này.")
    else:
        logger.exception("Unexpected error in warn command: %s", error)
        await ctx.send("Đã xảy ra lỗi khi cố gắng cảnh cáo.")


@bot.command(name="mute")
@commands.has_permissions(manage_roles=True)
async def mute_member(ctx: commands.Context, member: discord.Member, minutes: int = 5) -> None:
    guild = ctx.guild
    if guild is None:
        return await ctx.send("Lệnh này chỉ dùng trong máy chủ.")
    muted_role = discord.utils.get(guild.roles, name="Muted")
    try:
        if not muted_role:
            logger.info("Creating 'Muted' role and applying channel overwrites.")
            muted_role = await guild.create_role(name="Muted", reason="Auto-created by True Architect bot")
            # apply per-channel overwrites safely
            for channel in guild.channels:
                try:
                    await channel.set_permissions(muted_role, send_messages=False, speak=False, add_reactions=False)
                except Exception:
                    # ignore channel permission set errors for channels the bot can't manage
                    logger.debug("Could not set permissions in channel %s for Muted role.", channel.name)
                    continue

        await member.add_roles(muted_role, reason="Muted by True Architect bot")
        await ctx.send(f"Đã để {member.mention} chìm vào sự tĩnh lặng trong {minutes} phút.")

        # sleep asynchronously while allowing the bot to continue working
        await asyncio.sleep(max(0, minutes) * 60)
        if muted_role in member.roles:
            await member.remove_roles(muted_role, reason="Mute period ended (True Architect bot)")
            await ctx.send(f"Đã trả lại giọng nói cho {member.mention}, chu kỳ tĩnh lặng đã kết thúc.")
    except commands.MissingPermissions:
        await ctx.send("Quyền hạn của bạn chưa đủ để phong ấn thực thể này.")
    except Exception as e:
        logger.exception("Error in mute command: %s", e)
        await ctx.send("Đã xảy ra lỗi khi cố gắng khóa miệng thực thể này.")


# -------------------- 8. CODE GENERATION (!code) --------------------
@bot.command(name="code")
async def code_architect(ctx: commands.Context, *, prompt: str) -> None:
    if not check_rate_limit(ctx.author.id):
        return await ctx.send("Bạn tương tác quá nhanh, hãy chậm lại một chút.")

    if ai_client is None:
        return await ctx.send("Khả năng kiến tạo hiện tạm thời không hoạt động (không tìm thấy API key).")

    async with ctx.typing():
        full_prompt = f"Viết mã Python hoàn chỉnh và tối ưu cho yêu cầu sau: {prompt}"
        # Prepare content list for Gemini; a mix of system + user prompt
        contents: List[Any] = [full_prompt]
        result_text = await call_gemini(contents=contents, system_instruction=ARCHITECT_INSTRUCTION)
        if result_text:
            # send in chunks if long
            await send_long_message(ctx, f"```py\n{result_text}\n```")
        else:
            await ctx.send("Không thể tạo mã vào lúc này, hãy thử lại sau.")


# -------------------- 9. CHAT & IMAGE ANALYSIS (!chat) --------------------
@bot.command(name="chat")
async def chat_architect(ctx: commands.Context, *, prompt: str = "") -> None:
    if not check_rate_limit(ctx.author.id):
        return await ctx.send("Bạn tương tác quá nhanh, hãy chậm lại một chút.")

    if ai_client is None:
        return await ctx.send("Khả năng phân tích hiện tạm thời không hoạt động (không tìm thấy API key).")

    async with ctx.typing():
        image_part: Optional[types.Part] = None
        if ctx.message.attachments:
            attachment = ctx.message.attachments[0]
            if attachment.content_type and attachment.content_type.startswith("image/"):
                try:
                    image_bytes = await attachment.read()
                    image_part = types.Part.from_bytes(data=image_bytes, mime_type=attachment.content_type)
                except Exception as e:
                    logger.exception("Lỗi tải ảnh: %s", e)
                    await ctx.send("Không thể tải ảnh lên để phân tích.")
                    return

        contents: List[Any] = []
        if image_part:
            contents.append(image_part)

        if not prompt and image_part:
            contents.append("Quan sát bức ảnh này dưới góc nhìn điềm tĩnh và thấu đáo.")
        elif prompt:
            contents.append(prompt)

        if not contents:
            return await ctx.send("Thực tại trống rỗng, hãy cung cấp cho tôi một hình hài cụ thể.")

        result_text = await call_gemini(contents=contents, system_instruction=ARCHITECT_INSTRUCTION)
        if result_text:
            # Respect the persona requirement: single-sentence responses
            # If we get multi-line or multiple sentences, we can keep first sentence as a best-effort
            one_line = result_text.strip().split("\n")[0].strip()
            # optionally keep only up to first sentence ending with a period (.), question mark, or other punctuation
            import re
            m = re.match(r"^(.+?[.!?])\s", result_text + " ")
            if m:
                one_sentence = m.group(1).strip()
            else:
                one_sentence = one_line
            await ctx.send(one_sentence)
        else:
            await ctx.send("Không thể phân tích vào lúc này, thử lại sau.")


# -------------------- 10. EVENTS & STARTUP --------------------
@bot.event
async def on_ready() -> None:
    logger.info("✅ Bot true architect đã trực tuyến: %s (id=%s)", bot.user.name, bot.user.id)
    if GEMINI_API_KEY:
        logger.info("🔑 Đã nạp thành công 1 Gemini API Key.")
    else:
        logger.warning("🔒 Gemini API key chưa cấu hình; tính năng AI sẽ bị giới hạn.")


# -------------------- 11. ENTRYPOINT --------------------
def main() -> None:
    keep_alive()
    if not DISCORD_TOKEN:
        logger.error("DISCORD_TOKEN not provided; exiting.")
        return
    try:
        bot.run(DISCORD_TOKEN)
    except KeyboardInterrupt:
        logger.info("Bot stopped by KeyboardInterrupt.")
    except Exception:
        logger.exception("Bot terminated with an unexpected error.")


if __name__ == "__main__":
    main()
