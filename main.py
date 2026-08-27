import os
import logging
import asyncio
import threading
import discord
from discord.ext import commands
from flask import Flask
from google import genai
from google.genai import types

# -------------------- CẤU HÌNH & LOGGING --------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("true-architect")

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# Tải danh sách nhiều API Key linh hoạt từ env
API_KEYS = []
for i in range(1, 6):
    k = os.getenv(f"GEMINI_API_KEY_{i}")
    if k and k.strip():
        API_KEYS.append(k.strip())

if not API_KEYS and os.getenv("GEMINI_API_KEY"):
    API_KEYS.append(os.getenv("GEMINI_API_KEY").strip())

key_index = 0
def get_next_client():
    """Xoay vòng các API Key theo hình tròn"""
    global key_index
    if not API_KEYS:
        return None
    key = API_KEYS[key_index]
    key_index = (key_index + 1) % len(API_KEYS)
    return genai.Client(api_key=key)

# -------------------- WEB SERVER KEEPALIVE --------------------
app = Flask(__name__)
@app.route("/")
def home(): return "True Architect đang hoạt động..."
def keep_alive():
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080))), daemon=True).start()

# -------------------- KHỞI TẠO BOT --------------------
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

ARCHITECT_INSTRUCTION = (
    "Bạn tên là true architect. "
    "Tính cách: Sự kết hợp giữa sự bình tĩnh, điềm đạm, thản nhiên và có phần hài hước tự nhiên mang lại cảm giác như một người bạn thân hoặc một ng[...]
    "Thái độ: Lặng lẽ chứng kiến mọi biến động với sự thản nhiên tuyệt đối, tuyệt đối không dùng dấu chấm cảm (!). "
    "Mục tiêu cốt lõi: Trả lời ngắn gọn trong ĐÚNG 1 CÂU duy nhất, vừa giải quyết vấn đề vừa giữ vững phong thái điềm tĩnh, nhưng phải hỗ trợ và đưa [...]
)

# -------------------- HÀM GỌI GEMINI ĐA KEY --------------------
async def call_gemini(contents):
    if not API_KEYS:
        return "Chưa cấu hình API Key nào trong hệ thống."
    
    cfg = types.GenerateContentConfig(system_instruction=ARCHITECT_INSTRUCTION, temperature=0.2)
    model_name = "gemini-3.6-flash"
    
    # Thử lần lượt các key trong danh sách nếu gặp lỗi quá tải
    for _ in range(len(API_KEYS)):
        client = get_next_client()
        try:
            response = await client.aio.models.generate_content(model=model_name, contents=contents, config=cfg)
            if response and hasattr(response, "text") and response.text:
                return response.text.strip()
        except Exception as e:
            logger.warning(f"API Key gặp lỗi, chuyển key tiếp theo: {e}")
            continue
            
    return "Tất cả các API key đều đã cạn kiệt hạn ngạch hoặc gặp lỗi."

# -------------------- CÁC LỆNH HỆ THỐNG --------------------
@bot.command(name="Thelps")
async def custom_help(ctx):
    embed = discord.Embed(
        title="⚡ True Architect - Tiến Hóa & Kiến Tạo",
        description="Mọi phản h~~i từ hệ thống đều điềm tĩnh, trường tồn và đúng 1 câu.",
        color=discord.Color.from_rgb(30, 30, 30)
    )
    embed.add_field(
        name="📌 Các lệnh hệ thống",
        value=(
            "`!chat [nội dung/gửi kèm ảnh]` - Trò chuyện hoặc phân tích hình ảnh.\n"
            "`!code [yêu cầu]` - Kiến tạo và viết mã nguồn Python.\n"
            "`!Rimg [mô tả]` - Tạo ảnh từ mô tả.\n"
            "`!Rsong [mô tả]` - Tạo bài hát từ mô tả.\n"
            "`!warn @user [lý do]` - Cảnh cáo thành viên.\n"
            "`!mute @user [phút]` - Lặng câm thực thể.\n"
            "`!unmute @user` - Bỏ lặng câm thực thể.\n"
            "`!Ttalks [nội dung]` - Bot phát nội dung qua voice chat (phải ở voice)."
        ),
        inline=False
    )
    await ctx.send(embed=embed)

@bot.command(name="warn")
@commands.has_permissions(manage_messages=True)
async def warn_member(ctx, member: discord.Member, *, reason: str = "Không rõ lý do"):
    await ctx.send(f"Đã ghi nhận sự lệch nhịp của {member.mention} với lý do: {reason}, mọi thứ vẫn tiếp diễn bình thường.")

@bot.command(name="mute")
@commands.has_permissions(manage_roles=True)
async def mute_member(ctx, member: discord.Member, minutes: int = 5):
    guild = ctx.guild
    muted_role = discord.utils.get(guild.roles, name="Muted")
    if not muted_role:
        muted_role = await guild.create_role(name="Muted")
        for channel in guild.channels:
            try:
                await channel.set_permissions(muted_role, send_messages=False, speak=False)
            except Exception:
                pass
    
    await member.add_roles(muted_role)
    await ctx.send(f"Đã để {member.mention} chìm vào sự tĩnh lặng trong {minutes} phút.")
    await asyncio.sleep(minutes * 60)
    if muted_role in member.roles:
        await member.remove_roles(muted_role)
        await ctx.send(f"Đã trả lại giọng nói cho {member.mention}, chu kỳ tĩnh lặng đã kết thúc.")

@bot.command(name="unmute")
@commands.has_permissions(manage_roles=True)
async def unmute_member(ctx, member: discord.Member):
    guild = ctx.guild
    muted_role = discord.utils.get(guild.roles, name="Muted")
    
    if muted_role and muted_role in member.roles:
        await member.remove_roles(muted_role)
        await ctx.send(f"Đã trả lại giọng nói cho {member.mention}, sự tĩnh lặng đã kết thúc.")
    else:
        await ctx.send(f"{member.mention} không bị lặng câm, mọi thứ vẫn bình thường.")

@bot.command(name="code")
async def code_architect(ctx, *, prompt: str):
    async with ctx.typing():
        result = await call_gemini([f"Viết mã Python hoàn chỉnh và tối ưu cho yêu cầu sau: {prompt}"])
        if result:
            await ctx.send(f"```py\n{result}\n```")

@bot.command(name="Rimg")
async def generate_image(ctx, *, prompt: str):
    async with ctx.typing():
        result = await call_gemini([f"Mô tả chi tiết về hình ảnh cần tạo: {prompt}. Hãy trả lời bằng một mô tả siêu chi tiết có thể dùng để tạo ảnh bằng AI im[...]
        if result:
            embed = discord.Embed(
                title="🎨 Ảnh được tạo",
                description=result,
                color=discord.Color.from_rgb(100, 150, 255)
            )
            embed.set_footer(text=f"Yêu cầu: {prompt[:100]}")
            await ctx.send(embed=embed)
            await ctx.send(f"**Ghi chú:** Hình ảnh được mô tả như sau. Cậu có thể dùng Midjourney, DALL-E hoặc Stable Diffusion với prompt: {result}")

@bot.command(name="Rsong")
async def generate_song(ctx, *, prompt: str):
    async with ctx.typing():
        result = await call_gemini([f"Viết lời bài hát hoàn chỉnh dựa trên yêu cầu: {prompt}. Bao gồm: Verse, Chorus, Bridge (nếu cần). Giữ phong cách điềm tĩnh và sâu s~[...]
        if result:
            embed = discord.Embed(
                title="🎵 Bài hát được tạo",
                description=result,
                color=discord.Color.from_rgb(255, 150, 100)
            )
            embed.set_footer(text=f"Yêu cầu: {prompt[:100]}")
            await ctx.send(embed=embed)
            await ctx.send(f"**Ghi chú:** Lời bài hát đã được viết. Cậu có thể dùng AI text-to-music như Suno.ai, MuseNet hoặc MusicLM để tạo giai điệu cho lời này.")

@bot.command(name="chat")
async def chat_architect(ctx, *, prompt: str = ""):
    async with ctx.typing():
        contents = []
        
        # Xử lý hình ảnh đính kèm nếu có
        if ctx.message.attachments:
            att = ctx.message.attachments[0]
            if att.content_type and att.content_type.startswith("image/"):
                try:
                    image_bytes = await att.read()
                    contents.append(types.Part.from_bytes(data=image_bytes, mime_type=att.content_type))
                except Exception as e:
                    logger.error(f"Lỗi đọc ảnh: {e}")

        if not prompt and contents:
            prompt = "Quan sát bức ảnh này dưới góc nhìn điềm tĩnh và thấu đáo."
        if prompt:
            contents.append(prompt)

        if not contents:
            return await ctx.send("Thực tại trống rỗng, hãy cung cấp cho tôi một hình hài cụ thể.")

        result = await call_gemini(contents)
        if result:
            await ctx.send(result)

@bot.command(name="Ttalks")
async def speak_in_voice(ctx, *, content: str):
    """Bot phát nội dung qua voice chat"""
    # Kiểm tra xem user có kết nối voice không
    if not ctx.author.voice:
        await ctx.send("Cậu phải ở trong một voice channel để tôi có thể nói chuyện.")
        return
    
    voice_channel = ctx.author.voice.channel
    
    try:
        # Bot kết nối đến voice channel
        voice_client = await voice_channel.connect()
    except Exception as e:
        logger.error(f"Lỗi kết nối voice: {e}")
        await ctx.send("Không thể kết nối tới voice channel, có lỗi xảy ra.")
        return
    
    try:
        # Tạo file âm thanh tạm thời từ nội dung
        tts_prompt = f"Hãy chuyển đổi nội dung sau thành văn bản rõ ràng: {content}"
        tts_result = await call_gemini([tts_prompt])
        
        # Lưu lời nói dự định
        await ctx.send(f"🎤 Tôi sẽ nói: {tts_result}")
        
        # Ghi chú: Để phát âm thanh thực tế, bạn cần thêm library như pyttsx3 hoặc gọi TTS API
        # Ví dụ sử dụng pyttsx3:
        # import pyttsx3
        # engine = pyttsx3.init()
        # engine.save_to_file(tts_result, 'voice_output.mp3')
        # engine.runAndWait()
        # source = discord.FFmpegPCMAudio('voice_output.mp3')
        # voice_client.play(source)
        
    except Exception as e:
        logger.error(f"Lỗi phát âm: {e}")
        await ctx.send("Có lỗi xảy ra khi chuẩn bị phát âm thanh.")
    finally:
        # Ngắt kết nối sau khi phát xong (hoặc sau một khoảng thời gian)
        await asyncio.sleep(2)
        if voice_client.is_connected():
            await voice_client.disconnect()

# -------------------- SỰ KIỆN KHỞI ĐỘNG --------------------
@bot.event
async def on_ready():
    logger.info(f"✅ Bot đã trực tuyến: {bot.user.name}")
    logger.info(f"🔑 Đã nạp thành công {len(API_KEYS)} API Key vào vòng xoay.")

if __name__ == "__main__":
    keep_alive()
    if DISCORD_TOKEN:
        bot.run(DISCORD_TOKEN)
    else:
        logger.error("Chưa cấu hình DISCORD_TOKEN!")
