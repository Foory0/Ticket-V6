import discord
from discord.ext import commands
import os
from keep_alive import keep_alive
from dotenv import load_dotenv

# تحميل المتغيرات البيئية
load_dotenv()

# إعداد البوت
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='/', intents=intents)

@bot.event
async def on_ready():
    print(f'تم تسجيل الدخول كـ {bot.user}')
    try:
        synced = await bot.tree.sync()
        print(f'تم مزامنة {len(synced)} من الأوامر')
    except Exception as e:
        print(f'حدث خطأ في المزامنة: {e}')

@bot.tree.command(name="test", description="اختبار البوت")
async def test(interaction: discord.Interaction):
    await interaction.response.send_message("البوت يعمل! ✅")

# تشغيل خادم الويب للحفاظ على البوت نشطاً
keep_alive()

# تشغيل البوت
bot.run(os.getenv('DISCORD_TOKEN')) 