import os
import discord
from discord import app_commands, ButtonStyle, SelectOption, Permissions, TextStyle
from discord.ext import commands, tasks
from discord.ui import Button, View, Select, Modal, TextInput
from dotenv import load_dotenv
import datetime
import asyncio
import json
import aiohttp
import random
import string
import pytz
from typing import Optional, Dict, List
import io
import logging
import sys
from datetime import datetime, timedelta
from keep_alive import keep_alive

# إعداد نظام التسجيل
def setup_logging():
    """إعداد نظام التسجيل مع دعم اليونيكود"""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # إزالة جميع المعالجات القديمة
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # إضافة معالج جديد يدعم اليونيكود
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    
    # تنسيق رسائل التسجيل
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', 
                                datefmt='%Y-%m-%d %H:%M:%S')
    handler.setFormatter(formatter)
    
    # إضافة معالج ملف للتسجيل
    file_handler = logging.FileHandler('bot.log', encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    
    logger.addHandler(handler)
    logger.addHandler(file_handler)
    
    return logger

# تهيئة نظام التسجيل
logger = setup_logging()

# تحميل المتغيرات البيئية
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# إعداد المنطقة الزمنية
timezone = pytz.timezone('Asia/Riyadh')

# تكوين البوت
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix='/', intents=intents)

# إعدادات البوت
DEFAULT_CONFIG = {
    'version': '7.0.0',
    'status_type': discord.ActivityType.watching,
    'status_text': 'نظام تذكرة | /مساعدة'
}

DEFAULT_CHANNELS = {
    'logs_channel': None,
    'archive_channel': None,
    'tickets_category': None,
    'feedback_channel': None
}

DEFAULT_PRIORITIES = {
    'critical': {
        'emoji': '⚡',
        'label': 'حرج',
        'response_time': '30 دقيقة',
        'color': 0xFF0000,
        'role': None
    },
    'urgent': {
        'emoji': '🔴',
        'label': 'عاجل',
        'response_time': 'ساعتين',
        'color': 0xFFA500,
        'role': None
    },
    'normal': {
        'emoji': '🟢',
        'label': 'عادي',
        'response_time': '24 ساعة',
        'color': 0x00FF00,
        'role': None
    }
}

DEFAULT_CATEGORIES = [
    discord.SelectOption(label='مشكلة تقنية', value='technical', emoji='🔧'),
    discord.SelectOption(label='استفسار عام', value='general', emoji='❓'),
    discord.SelectOption(label='اقتراح', value='suggestion', emoji='💡'),
    discord.SelectOption(label='شكوى', value='complaint', emoji='⚠️'),
    discord.SelectOption(label='طلب مساعدة', value='help', emoji='🆘')
]

# المتغيرات العامة
bot_config = DEFAULT_CONFIG.copy()
channel_config = DEFAULT_CHANNELS.copy()
priority_config = DEFAULT_PRIORITIES.copy()
ticket_categories = DEFAULT_CATEGORIES.copy()
active_tickets = {}
ticket_stats = {
    'total_tickets': 0,
    'open_tickets': 0,
    'closed_tickets': 0,
    'categories': {},
    'ratings': {}
}

# تحسين إعدادات التذاكر
ticket_settings = {
    'max_open_tickets': 10,  # تعديل العدد الأقصى للتذاكر المفتوحة
    'cooldown_minutes': 5,
    'auto_close_minutes': 10,  # إضافة وقت الإغلاق التلقائي
    'warning_hours': 24,
    'transcript_enabled': True,
    'rating_required': True,
    'anonymous_feedback': False
}

# إضافة متغيرات لتتبع نشاط التذاكر
ticket_activity = {}

# قائمة الردود التلقائية
auto_responses = {
    "مرحبا": "وعليكم السلام! كيف يمكنني مساعدتك؟",
    "شكرا": "العفو! نحن هنا لخدمتك 😊",
    "باي": "مع السلامة! نتمنى أن نكون قد قدمنا لك الخدمة المطلوبة 👋"
}

# إضافة متغيرات للتذكيرات
reminders = {}
REMINDER_CHECK_INTERVAL = 60  # التحقق كل دقيقة

# إضافة المتغيرات الجديدة
group_tickets = {}
ticket_solutions = {}

class TicketReminder:
    def __init__(self, channel_id: int, ticket_id: str, priority: str, created_at: datetime.datetime):
        self.channel_id = channel_id
        self.ticket_id = ticket_id
        self.priority = priority
        self.created_at = created_at
        self.last_reminder = None
        self.warning_sent = False
        
    def should_send_reminder(self) -> bool:
        if not self.last_reminder:
            response_times = {
                'critical': 30,    # 30 دقيقة
                'urgent': 120,     # ساعتين
                'normal': 1440     # 24 ساعة
            }
            time_passed = (datetime.datetime.now(timezone) - self.created_at).total_seconds() / 60
            return time_passed >= response_times[self.priority]
        else:
            # إرسال تذكير كل ساعتين بعد التذكير الأول
            time_since_last = (datetime.datetime.now(timezone) - self.last_reminder).total_seconds() / 60
            return time_since_last >= 120

@tasks.loop(minutes=1)
async def check_reminders():
    """التحقق من التذكيرات وإرسالها"""
    try:
        current_time = datetime.datetime.now(timezone)
        
        for ticket_id, reminder in reminders.copy().items():
            if reminder.should_send_reminder():
                channel = bot.get_channel(reminder.channel_id)
                if channel:
                    # التحقق من حالة التذكرة
                    if str(channel.id) not in active_tickets.values():
                        del reminders[ticket_id]
                        continue
                        
                    # إنشاء رسالة التذكير
                    embed = discord.Embed(
                        title="⏰ تذكير بتذكرة معلقة",
                        description=f"التذكرة {reminder.ticket_id} تحتاج إلى متابعة",
                        color=discord.Color.orange()
                    )
                    
                    time_passed = (current_time - reminder.created_at).total_seconds() / 3600
                    embed.add_field(
                        name="الوقت المنقضي",
                        value=f"{time_passed:.1f} ساعة",
                        inline=True
                    )
                    
                    embed.add_field(
                        name="الأولوية",
                        value=f"{priority_config[reminder.priority]['emoji']} {priority_config[reminder.priority]['label']}",
                        inline=True
                    )
                    
                    # إضافة منشن للرتبة المسؤولة
                    role_mention = f"<@&{priority_config[reminder.priority]['role']}>" if priority_config[reminder.priority]['role'] else ""
                    
                    await channel.send(
                        content=role_mention,
                        embed=embed
                    )
                    
                    reminder.last_reminder = current_time
                    
                    # إرسال تحذير للإدارة إذا تجاوزت التذكرة وقت الاستجابة بكثير
                    if not reminder.warning_sent and time_passed > 24:
                        logs_channel = bot.get_channel(channel_config['logs_channel'])
                        if logs_channel:
                            warning_embed = discord.Embed(
                                title="⚠️ تحذير: تذكرة متأخرة",
                                description=f"التذكرة {reminder.ticket_id} تجاوزت 24 ساعة بدون استجابة",
                                color=discord.Color.red()
                            )
                            warning_embed.add_field(
                                name="القناة",
                                value=channel.mention,
                                inline=True
                            )
                            warning_embed.add_field(
                                name="الأولوية",
                                value=f"{priority_config[reminder.priority]['emoji']} {priority_config[reminder.priority]['label']}",
                                inline=True
                            )
                            await logs_channel.send(embed=warning_embed)
                            reminder.warning_sent = True
                            
    except Exception as e:
        logger.error(f"خطأ في نظام التذكيرات: {str(e)}")

@tasks.loop(minutes=1)
async def check_ticket_activity():
    """التحقق من نشاط التذاكر وإغلاق غير النشطة"""
    try:
        current_time = datetime.datetime.now(timezone)
        
        for user_id, channel_id in active_tickets.copy().items():
            if str(channel_id) not in ticket_activity:
                continue
                
            last_activity = ticket_activity[str(channel_id)]
            inactive_minutes = (current_time - last_activity).total_seconds() / 60
            
            if inactive_minutes >= ticket_settings['auto_close_minutes']:
                channel = bot.get_channel(channel_id)
                if channel:
                    # إرسال رسالة الإغلاق
                    embed = discord.Embed(
                        title="🔒 إغلاق تلقائي للتذكرة",
                        description=f"تم إغلاق التذكرة تلقائياً بسبب عدم النشاط لمدة {ticket_settings['auto_close_minutes']} دقائق",
                        color=discord.Color.orange()
                    )
                    await channel.send(embed=embed)
                    
                    try:
                        # حذف التذكرة من نظام التذكيرات
                        ticket_id = None
                        for tid, reminder in reminders.copy().items():
                            if reminder.channel_id == channel_id:
                                ticket_id = tid
                                break
                        if ticket_id:
                            del reminders[ticket_id]
                        
                        # حفظ نسخة من المحادثة
                        if ticket_settings["transcript_enabled"]:
                            messages = []
                            async for message in channel.history(limit=None, oldest_first=True):
                                if message.content:
                                    messages.append(f"[{message.created_at.strftime('%Y-%m-%d %H:%M')}] {message.author}: {message.content}")
                                if message.embeds:
                                    for embed in message.embeds:
                                        if embed.title:
                                            messages.append(f"[{message.created_at.strftime('%Y-%m-%d %H:%M')}] {message.author}: [Embed] {embed.title}")
                            
                            transcript_text = "\n".join(messages)
                            
                            # حفظ في قناة الأرشيف
                            archive_channel = bot.get_channel(channel_config['archive_channel'])
                            if archive_channel:
                                file = discord.File(
                                    io.StringIO(transcript_text),
                                    filename=f"transcript-{channel.name}.txt"
                                )
                                await archive_channel.send(
                                    embed=discord.Embed(
                                        title=f"📜 نسخة من التذكرة {channel.name}",
                                        color=discord.Color.blue()
                                    ),
                                    file=file
                                )
                        
                        # تحديث الإحصائيات
                        ticket_stats["closed_tickets"] += 1
                        ticket_stats["open_tickets"] -= 1
                        await save_settings()
                        
                        # حذف القناة
                        await asyncio.sleep(5)
                        await channel.delete()
                        
                        # حذف من قائمة التذاكر النشطة
                        if user_id in active_tickets:
                            del active_tickets[user_id]
                        
                        # حذف من قائمة النشاط
                        if str(channel_id) in ticket_activity:
                            del ticket_activity[str(channel_id)]
                            
                    except Exception as e:
                        logger.error(f"خطأ في إغلاق التذكرة: {str(e)}")

    except Exception as e:
        logger.error(f"خطأ في فحص نشاط التذاكر: {str(e)}")

@bot.event
async def on_message(message):
    """تحديث وقت النشاط عند إرسال رسالة"""
    if message.channel.id in [int(channel_id) for channel_id in active_tickets.values()]:
        ticket_activity[str(message.channel.id)] = datetime.datetime.now(timezone)
    await bot.process_commands(message)

async def load_settings():
    """تحميل إعدادات البوت من الملف"""
    try:
        if os.path.exists('settings.json'):
            with open('settings.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict):  # التحقق من أن البيانات صالحة
                    bot_config.update(data.get('bot_config', {}))
                    channel_config.update(data.get('channel_config', {}))
                    priority_config.update(data.get('priority_config', {}))
                    ticket_stats.update(data.get('ticket_stats', {}))
                    logger.info("تم تحميل الإعدادات بنجاح")
                else:
                    logger.warning("تم العثور على بيانات غير صالحة في الملف")
                    await save_settings()  # إعادة إنشاء الملف بالإعدادات الافتراضية
        else:
            await save_settings()
            logger.info("تم إنشاء ملف إعدادات جديد")
    except Exception as e:
        logger.error(f"خطأ في تحميل الإعدادات: {str(e)}")
        await save_settings()  # محاولة إصلاح الملف

async def save_settings():
    """حفظ إعدادات البوت في الملف"""
    try:
        data = {
            'bot_config': bot_config,
            'channel_config': channel_config,
            'priority_config': priority_config,
            'ticket_stats': ticket_stats
        }
        with open('settings.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        logger.info("تم حفظ الإعدادات بنجاح")
    except Exception as e:
        logger.error(f"خطأ في حفظ الإعدادات: {str(e)}")

class TicketManager:
    """مدير نظام التذاكر"""
    
    @staticmethod
    async def handle_error(interaction: discord.Interaction, action: str, error: Exception):
        """معالجة الأخطاء وإرسال رسائل مناسبة"""
        error_msg = str(error)
        logger.error(f"خطأ في {action}: {error_msg}")
        
        # إنشاء رسالة الخطأ
        embed = discord.Embed(
            title="❌ حدث خطأ",
            description=f"عذراً، حدث خطأ أثناء {action}.",
            color=discord.Color.red()
        )
        
        # إضافة تفاصيل الخطأ للمشرفين فقط
        if interaction.user.guild_permissions.administrator:
            embed.add_field(
                name="تفاصيل الخطأ",
                value=f"```{error_msg}```",
                inline=False
            )
        
        # إرسال الرسالة
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)
        except:
            try:
                await interaction.channel.send(embed=embed)
            except:
                logger.error("فشل في إرسال رسالة الخطأ")

    @staticmethod
    async def create_ticket(interaction: discord.Interaction, category: str, priority: str, subject: str, description: str):
        """إنشاء تذكرة جديدة"""
        try:
            # التحقق من القنوات
            if not channel_config.get('tickets_category'):
                raise ValueError("لم يتم إعداد تصنيف التذاكر. الرجاء استخدام الأمر /اعداد_القنوات أولاً")
            
            # التحقق من وجود التصنيف وأنه من النوع الصحيح
            try:
                category_id = int(channel_config['tickets_category'])
                category_channel = interaction.guild.get_channel(category_id)
                
                if not category_channel:
                    # محاولة إنشاء تصنيف جديد
                    category_channel = await interaction.guild.create_category(
                        name="🎫 التذاكر",
                        reason="إنشاء تصنيف تلقائياً لنظام التذاكر"
                    )
                    channel_config['tickets_category'] = category_channel.id
                    await save_settings()
                    logger.info(f"تم إنشاء تصنيف جديد للتذاكر: {category_channel.name}")
                
                if not isinstance(category_channel, discord.CategoryChannel):
                    raise ValueError(f"القناة المحددة ({category_id}) ليست تصنيفاً. الرجاء استخدام الأمر /اعداد_القنوات لإعداد التصنيف الصحيح")
                
            except (ValueError, TypeError):
                raise ValueError("معرف التصنيف غير صالح. الرجاء استخدام الأمر /اعداد_القنوات لإعادة إعداد القنوات")
            
            # التحقق من صلاحيات البوت
            bot_member = interaction.guild.get_member(bot.user.id)
            required_permissions = discord.Permissions(
                manage_channels=True,
                read_messages=True,
                send_messages=True,
                manage_messages=True,
                embed_links=True,
                attach_files=True,
                read_message_history=True,
                manage_roles=True
            )
            
            if not category_channel.permissions_for(bot_member).is_superset(required_permissions):
                missing_perms = [perm[0] for perm in required_permissions if not getattr(category_channel.permissions_for(bot_member), perm[0])]
                raise ValueError(f"البوت يفتقد للصلاحيات التالية: {', '.join(missing_perms)}")
            
            # إنشاء اسم القناة
            ticket_number = ticket_stats['total_tickets'] + 1
            channel_name = f"ticket-{ticket_number:04d}"
            
            # إنشاء القناة
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                bot_member: discord.PermissionOverwrite(**{perm[0]: True for perm in required_permissions})
            }
            
            # إضافة الرتبة المسؤولة إذا وجدت
            if priority_config[priority]['role']:
                role = interaction.guild.get_role(priority_config[priority]['role'])
                if role:
                    overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
            
            # إنشاء القناة مع الأذونات
            ticket_channel = await interaction.guild.create_text_channel(
                name=channel_name,
                category=category_channel,
                topic=f"تذكرة {subject} | بواسطة {interaction.user.name}",
                overwrites=overwrites
            )
            
            # تحديث الإحصائيات
            ticket_stats['total_tickets'] += 1
            ticket_stats['open_tickets'] += 1
            ticket_stats['categories'][category] = ticket_stats['categories'].get(category, 0) + 1
            active_tickets[str(interaction.user.id)] = ticket_channel.id
            await save_settings()
            
            # إنشاء رسالة الترحيب
            embed = discord.Embed(
                title=f"تذكرة #{ticket_number:04d}",
                description=description,
                color=discord.Color(priority_config[priority]['color'])
            )
            embed.add_field(name="النوع", value=category, inline=True)
            embed.add_field(name="الأولوية", value=f"{priority_config[priority]['emoji']} {priority_config[priority]['label']}", inline=True)
            embed.add_field(name="وقت الاستجابة", value=priority_config[priority]['response_time'], inline=True)
            embed.set_footer(text=f"تم الإنشاء بواسطة {interaction.user.name}")
            
            # إضافة أزرار التحكم
            ticket_controls = TicketControlView()
            
            # إرسال رسالة الترحيب
            await ticket_channel.send(
                content=f"{interaction.user.mention} " + (f"<@&{priority_config[priority]['role']}> " if priority_config[priority]['role'] else ""),
                embed=embed,
                view=ticket_controls
            )
            
            # إرسال تأكيد للمستخدم
            await interaction.response.send_message(
                f"✅ تم إنشاء تذكرتك في {ticket_channel.mention}",
                ephemeral=True
            )
            
            # تسجيل الحدث
            logger.info(f"تم إنشاء تذكرة جديدة: {channel_name} بواسطة {interaction.user.name}")
            
            # إضافة التذكرة لنظام التذكيرات
            ticket_reminder = TicketReminder(
                channel_id=ticket_channel.id,
                ticket_id=f"#{ticket_number:04d}",
                priority=priority,
                created_at=datetime.datetime.now(timezone)
            )
            reminders[f"#{ticket_number:04d}"] = ticket_reminder
            
            # إضافة زر الدعم الجماعي
            ticket_controls = TicketControlView()
            group_support = GroupSupportView()
            
            # إرسال أزرار الدعم الجماعي
            await ticket_channel.send(view=group_support)
            
        except ValueError as e:
            await TicketManager.handle_error(interaction, "إنشاء التذكرة", e)
        except discord.Forbidden as e:
            await TicketManager.handle_error(interaction, "إنشاء التذكرة", "البوت لا يملك الصلاحيات الكافية")
        except Exception as e:
            await TicketManager.handle_error(interaction, "إنشاء التذكرة", e)

class TicketControlView(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(
        label="إغلاق التذكرة",
        style=ButtonStyle.danger,
        custom_id="close_ticket",
        emoji="🔒"
    )
    async def close_ticket(self, interaction: discord.Interaction, button: Button):
        await self.handle_close_ticket(interaction)
    
    @discord.ui.button(
        label="تحديث الحالة",
        style=ButtonStyle.primary,
        custom_id="update_status",
        emoji="🔄"
    )
    async def update_status(self, interaction: discord.Interaction, button: Button):
        await self.handle_status_update(interaction)
    
    @discord.ui.button(
        label="تعيين مشرف",
        style=ButtonStyle.success,
        custom_id="assign_staff",
        emoji="👤"
    )
    async def assign_staff(self, interaction: discord.Interaction, button: Button):
        await self.handle_staff_assignment(interaction)
    
    async def handle_close_ticket(self, interaction: discord.Interaction):
        try:
            if not interaction.user.guild_permissions.manage_channels and str(interaction.user.id) not in active_tickets:
                await interaction.response.send_message(
                    "❌ ليس لديك صلاحية لإغلاق هذه التذكرة!",
                    ephemeral=True
                )
                return

            await interaction.response.defer()
            
            # الحصول على معلومات التذكرة
            channel = interaction.channel
            guild_id = interaction.guild_id
            ticket_owner_id = None
            
            for user_id, ticket_channel_id in active_tickets.items():
                if ticket_channel_id == channel.id:
                    ticket_owner_id = int(user_id)
                    break
            
            if ticket_owner_id:
                try:
                    # محاولة إرسال نموذج التقييم في الخاص
                    ticket_owner = await bot.fetch_user(ticket_owner_id)
                    rating_view = RatingView(channel.name, guild_id)
                    
                    try:
                        await ticket_owner.send(
                            embed=discord.Embed(
                                title="📝 تقييم الخدمة",
                                description=f"شكراً لاستخدامك نظام التذاكر! نرجو تقييم الخدمة المقدمة في التذكرة {channel.name}:",
                                color=discord.Color.blue()
                            ),
                            view=rating_view
                        )
                        logger.info(f"تم إرسال نموذج التقييم في الخاص للمستخدم {ticket_owner.name}")
                    except discord.Forbidden:
                        logger.warning(f"تعذر إرسال رسالة خاصة للمستخدم {ticket_owner.name}")
                except Exception as e:
                    logger.error(f"خطأ في إرسال التقييم: {str(e)}")
            
            # إغلاق التذكرة
            await self.close_and_archive(interaction)
            
        except Exception as e:
            await ticket_manager.handle_error(interaction, "إغلاق التذكرة", e)
    
    async def handle_status_update(self, interaction: discord.Interaction):
        """تحديث حالة التذكرة"""
        try:
            # التحقق من الصلاحيات
            if not interaction.user.guild_permissions.manage_channels and str(interaction.user.id) not in active_tickets:
                await interaction.response.send_message(
                    "❌ ليس لديك صلاحية لتحديث حالة هذه التذكرة!",
                    ephemeral=True
                )
                return
            
            # إنشاء قائمة الحالات
            status_options = [
                discord.SelectOption(label="قيد المعالجة", value="in_progress", emoji="🔄"),
                discord.SelectOption(label="في انتظار الرد", value="waiting", emoji="⏳"),
                discord.SelectOption(label="تم الحل", value="resolved", emoji="✅"),
                discord.SelectOption(label="مؤجل", value="delayed", emoji="⏰"),
                discord.SelectOption(label="مرفوض", value="rejected", emoji="❌")
            ]
            
            class StatusSelect(discord.ui.Select):
                def __init__(self):
                    super().__init__(
                        placeholder="اختر الحالة الجديدة",
                        options=status_options,
                        custom_id="status_select"
                    )
                
                async def callback(self, interaction: discord.Interaction):
                    status_emojis = {
                        "in_progress": "🔄",
                        "waiting": "⏳",
                        "resolved": "✅",
                        "delayed": "⏰",
                        "rejected": "❌"
                    }
                    
                    status_names = {
                        "in_progress": "قيد المعالجة",
                        "waiting": "في انتظار الرد",
                        "resolved": "تم الحل",
                        "delayed": "مؤجل",
                        "rejected": "مرفوض"
                    }
                    
                    selected_status = self.values[0]
                    
                    # تحديث اسم القناة
                    channel = interaction.channel
                    new_name = f"{status_emojis[selected_status]}-{channel.name}"
                    await channel.edit(name=new_name)
                    
                    # إرسال رسالة تأكيد
                    embed = discord.Embed(
                        title="✅ تم تحديث الحالة",
                        description=f"تم تغيير حالة التذكرة إلى: {status_emojis[selected_status]} {status_names[selected_status]}",
                        color=discord.Color.green()
                    )
                    await interaction.response.send_message(embed=embed)
            
            # إنشاء وإرسال القائمة
            view = discord.ui.View()
            view.add_item(StatusSelect())
            await interaction.response.send_message(
                "اختر الحالة الجديدة للتذكرة:",
                view=view,
                ephemeral=True
            )
            
        except Exception as e:
            await ticket_manager.handle_error(interaction, "تحديث حالة التذكرة", e)
    
    async def handle_staff_assignment(self, interaction: discord.Interaction):
        """تعيين مشرف للتذكرة"""
        try:
            # التحقق من الصلاحيات
            if not interaction.user.guild_permissions.manage_channels:
                await interaction.response.send_message(
                    "❌ ليس لديك صلاحية لتعيين مشرف!",
                    ephemeral=True
                )
                return
            
            # الحصول على قائمة المشرفين
            staff_roles = [
                role for role in interaction.guild.roles
                if any(keyword in role.name.lower() for keyword in ['admin', 'mod', 'staff', 'مشرف', 'إدارة', 'ادارة'])
            ]
            
            if not staff_roles:
                await interaction.response.send_message(
                    "❌ لم يتم العثور على أي رتب إشرافية!",
                    ephemeral=True
                )
                return
            
            # إنشاء قائمة اختيار المشرفين
            staff_options = []
            for role in staff_roles:
                staff_options.append(
                    discord.SelectOption(
                        label=role.name,
                        value=str(role.id),
                        description=f"عدد الأعضاء: {len(role.members)}"
                    )
                )
            
            class StaffSelect(discord.ui.Select):
                def __init__(self):
                    super().__init__(
                        placeholder="اختر رتبة المشرف",
                        options=staff_options,
                        custom_id="staff_select"
                    )
                
                async def callback(self, interaction: discord.Interaction):
                    selected_role = interaction.guild.get_role(int(self.values[0]))
                    
                    # إضافة الرتبة للقناة
                    await interaction.channel.set_permissions(
                        selected_role,
                        read_messages=True,
                        send_messages=True
                    )
                    
                    # إرسال رسالة تأكيد
                    embed = discord.Embed(
                        title="✅ تم تعيين المشرف",
                        description=f"تم إضافة {selected_role.mention} للتذكرة",
                        color=discord.Color.green()
                    )
                    await interaction.response.send_message(embed=embed)
                    
                    # إرسال تنبيه في القناة
                    await interaction.channel.send(
                        f"{selected_role.mention} تم تعيينك لهذه التذكرة"
                    )
            
            # إنشاء وإرسال القائمة
            view = discord.ui.View()
            view.add_item(StaffSelect())
            await interaction.response.send_message(
                "اختر رتبة المشرف المسؤول عن هذه التذكرة:",
                view=view,
                ephemeral=True
            )
            
        except Exception as e:
            await ticket_manager.handle_error(interaction, "تعيين مشرف", e)
    
    async def send_rating_form(self, interaction: discord.Interaction):
        try:
            rating_view = RatingView(interaction.channel.name, interaction.guild_id)
            await interaction.followup.send(
                embed=discord.Embed(
                    title="📝 تقييم الخدمة",
                    description="يرجى تقييم مستوى الخدمة المقدمة قبل إغلاق التذكرة:",
                    color=discord.Color.blue()
                ),
                view=rating_view,
                ephemeral=True
            )
        except Exception as e:
            print(f"Error sending rating form: {e}")
    
    async def close_and_archive(self, interaction: discord.Interaction):
        try:
            channel = interaction.channel
            
            # حذف التذكرة من نظام التذكيرات
            ticket_id = None
            for tid, reminder in reminders.copy().items():
                if reminder.channel_id == channel.id:
                    ticket_id = tid
                    break
            if ticket_id:
                del reminders[ticket_id]
            
            # حفظ نسخة من المحادثة
            if ticket_settings["transcript_enabled"]:
                await self.save_transcript(channel)
            
            # إرسال رسالة الإغلاق
            await channel.send(
                embed=discord.Embed(
                    title="🔒 جاري إغلاق التذكرة",
                    description="سيتم إغلاق التذكرة خلال 5 ثواني...",
                    color=discord.Color.orange()
                )
            )
            
            # تحديث الإحصائيات
            ticket_stats["closed_tickets"] += 1
            ticket_stats["open_tickets"] -= 1
            
            # حذف القناة
            await asyncio.sleep(5)
            await channel.delete()
            
        except Exception as e:
            print(f"Error closing ticket: {e}")
    
    async def save_transcript(self, channel):
        try:
            messages = []
            async for message in channel.history(limit=None, oldest_first=True):
                if message.content:
                    messages.append(f"[{message.created_at.strftime('%Y-%m-%d %H:%M')}] {message.author}: {message.content}")
                if message.embeds:
                    for embed in message.embeds:
                        if embed.title:
                            messages.append(f"[{message.created_at.strftime('%Y-%m-%d %H:%M')}] {message.author}: [Embed] {embed.title}")
            
            transcript_text = "\n".join(messages)
            
            # حفظ في قناة الأرشيف
            archive_channel = channel.guild.get_channel(channel_config['archive_channel'])
            if archive_channel:
                file = discord.File(
                    io.StringIO(transcript_text),
                    filename=f"transcript-{channel.name}.txt"
                )
                await archive_channel.send(
                    embed=discord.Embed(
                        title=f"📜 نسخة من التذكرة {channel.name}",
                        color=discord.Color.blue()
                    ),
                    file=file
                )
        except Exception as e:
            print(f"Error saving transcript: {e}")

class RatingView(View):
    def __init__(self, ticket_name: str, guild_id: int):
        super().__init__(timeout=300.0)  # 5 minutes timeout
        self.ticket_name = ticket_name
        self.guild_id = guild_id
    
    @discord.ui.button(label="⭐", style=ButtonStyle.gray, custom_id="rate_1")
    async def rate_1(self, interaction: discord.Interaction, button: Button):
        await self.handle_rating(interaction, 1)
    
    @discord.ui.button(label="⭐⭐", style=ButtonStyle.gray, custom_id="rate_2")
    async def rate_2(self, interaction: discord.Interaction, button: Button):
        await self.handle_rating(interaction, 2)
    
    @discord.ui.button(label="⭐⭐⭐", style=ButtonStyle.gray, custom_id="rate_3")
    async def rate_3(self, interaction: discord.Interaction, button: Button):
        await self.handle_rating(interaction, 3)
    
    @discord.ui.button(label="⭐⭐⭐⭐", style=ButtonStyle.gray, custom_id="rate_4")
    async def rate_4(self, interaction: discord.Interaction, button: Button):
        await self.handle_rating(interaction, 4)
    
    @discord.ui.button(label="⭐⭐⭐⭐⭐", style=ButtonStyle.gray, custom_id="rate_5")
    async def rate_5(self, interaction: discord.Interaction, button: Button):
        await self.handle_rating(interaction, 5)
    
    async def handle_rating(self, interaction: discord.Interaction, rating: int):
        try:
            # تحديث الإحصائيات
            ticket_stats["ratings"][str(rating)] = ticket_stats["ratings"].get(str(rating), 0) + 1
            await save_settings()
            
            # إرسال نموذج الملاحظات
            feedback_modal = FeedbackModal(rating, self.ticket_name, self.guild_id)
            await interaction.response.send_modal(feedback_modal)
            
        except Exception as e:
            error_embed = discord.Embed(
                title="❌ خطأ",
                description="حدث خطأ أثناء معالجة التقييم. الرجاء المحاولة مرة أخرى لاحقاً.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=error_embed, ephemeral=True)
            logger.error(f"خطأ في معالجة التقييم: {str(e)}")

class FeedbackModal(Modal):
    def __init__(self, rating: int, ticket_name: str, guild_id: int):
        super().__init__(title="إضافة ملاحظات")
        self.rating = rating
        self.ticket_name = ticket_name
        self.guild_id = guild_id
        
        self.feedback = TextInput(
            label="ملاحظاتك (اختياري)",
            placeholder="اكتب ملاحظاتك حول الخدمة المقدمة...",
            required=False,
            style=discord.TextStyle.paragraph
        )
        
        self.add_item(self.feedback)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            # إنشاء رسالة التقييم
            embed = discord.Embed(
                title="✅ شكراً على تقييمك!",
                description=(
                    f"**التذكرة:** {self.ticket_name}\n"
                    f"**التقييم:** {'⭐' * self.rating}\n"
                    f"**الملاحظات:** {self.feedback.value or 'لا توجد ملاحظات'}"
                ),
                color=discord.Color.green(),
                timestamp=datetime.datetime.now(timezone)
            )
            
            # إرسال تأكيد للمستخدم
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
            try:
                # الحصول على السيرفر وقناة التقييمات
                guild = bot.get_guild(self.guild_id)
                if guild and channel_config.get('feedback_channel'):
                    feedback_channel = guild.get_channel(channel_config['feedback_channel'])
                    if feedback_channel:
                        feedback_embed = discord.Embed(
                            title="📊 تقييم جديد",
                            description=(
                                f"**التذكرة:** {self.ticket_name}\n"
                                f"**المستخدم:** {interaction.user.mention}\n"
                                f"**التقييم:** {'⭐' * self.rating}\n"
                                f"**الملاحظات:** {self.feedback.value or 'لا توجد ملاحظات'}"
                            ),
                            color=discord.Color.blue(),
                            timestamp=datetime.datetime.now(timezone)
                        )
                        await feedback_channel.send(embed=feedback_embed)
                        logger.info(f"تم إرسال تقييم جديد من المستخدم {interaction.user.name}")
            except Exception as e:
                logger.error(f"خطأ في إرسال التقييم لقناة التقييمات: {str(e)}")
            
        except Exception as e:
            error_embed = discord.Embed(
                title="❌ خطأ",
                description="حدث خطأ أثناء إرسال التقييم. الرجاء المحاولة مرة أخرى لاحقاً.",
                color=discord.Color.red()
            )
            
            try:
                await interaction.response.send_message(embed=error_embed, ephemeral=True)
            except:
                try:
                    await interaction.followup.send(embed=error_embed, ephemeral=True)
                except:
                    logger.error(f"فشل في إرسال رسالة الخطأ للمستخدم: {str(e)}")

class TicketModal(Modal):
    def __init__(self, category: str, priority: str):
        super().__init__(title="إنشاء تذكرة جديدة")
        
        self.category = category
        self.priority = priority
        
        self.subject = TextInput(
            label="عنوان المشكلة",
            placeholder="اكتب عنواناً مختصراً للمشكلة",
            required=True,
            max_length=100
        )
        
        self.description = TextInput(
            label="وصف المشكلة",
            placeholder="اشرح مشكلتك بالتفصيل",
            required=True,
            style=TextStyle.paragraph,
            max_length=1000
        )
        
        self.add_item(self.subject)
        self.add_item(self.description)
    
    async def on_submit(self, interaction: discord.Interaction):
        await TicketManager.create_ticket(
            interaction,
            self.category,  # النوع
            self.priority,  # الأولوية
            self.subject.value,
            self.description.value
        )

@bot.event
async def on_error(event, *args, **kwargs):
    """معالجة الأخطاء العامة"""
    try:
        error = sys.exc_info()[1]
        logger.error(f"خطأ في الحدث {event}: {str(error)}")
        
        # محاولة إعادة تشغيل المهام الدورية
        if not check_reminders.is_running():
            check_reminders.start()
        if not check_ticket_activity.is_running():
            check_ticket_activity.start()
            
    except Exception as e:
        logger.error(f"خطأ في معالجة الخطأ: {str(e)}")

@tasks.loop(minutes=1)
async def check_bot_health():
    """التحقق من صحة البوت وإعادة تشغيل المهام إذا لزم الأمر"""
    try:
        # التحقق من حالة المهام الدورية
        if not check_reminders.is_running():
            logger.warning("إعادة تشغيل مهمة التذكيرات")
            check_reminders.start()
            
        if not check_ticket_activity.is_running():
            logger.warning("إعادة تشغيل مهمة فحص نشاط التذاكر")
            check_ticket_activity.start()
            
        # التحقق من حالة البوت
        if not bot.is_ready():
            logger.warning("البوت غير متصل. محاولة إعادة الاتصال...")
            await bot.close()
            await bot.start(TOKEN)
            
    except Exception as e:
        logger.error(f"خطأ في فحص صحة البوت: {str(e)}")

@bot.event
async def on_ready():
    """يتم تنفيذه عند تشغيل البوت"""
    try:
        # تحميل الإعدادات
        load_settings()
        
        # مزامنة الأوامر
        await bot.tree.sync()
        
        # تعيين حالة البوت
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="Ticket | تذكرة"
            )
        )
        
        # بدء المهام الدورية
        check_reminders.start()
        check_ticket_activity.start()
        check_bot_health.start()
        
        # بدء نظام الحفاظ على التشغيل
        keep_alive()
        
        logger.info(f"تم تشغيل البوت {bot.user}")
        logger.info(f"إصدار {VERSION}")
        
    except Exception as e:
        logger.error(f"خطأ في بدء البوت: {e}")
        # محاولة إعادة تشغيل البوت
        await bot.close()
        await bot.start(TOKEN)

@bot.tree.command(name="انشاء_لوحة", description="إنشاء لوحة تذاكر تفاعلية")
@app_commands.default_permissions(administrator=True)
async def setup_ticket(interaction: discord.Interaction):
    """إنشاء لوحة تذاكر تفاعلية"""
    try:
        embed = discord.Embed(
            title="🎫 نظام التذاكر",
            description=(
                "مرحباً بك في نظام التذاكر!\n\n"
                "**خطوات إنشاء تذكرة:**\n"
                "1. اختر نوع التذكرة\n"
                "2. حدد مستوى الأولوية\n"
                "3. أكمل النموذج\n\n"
                "**مستويات الأولوية:**\n"
                "⚡ **حرج** - معالجة خلال 30 دقيقة\n"
                "🔴 **عاجل** - معالجة خلال ساعتين\n"
                "🟢 **عادي** - معالجة خلال 24 ساعة"
            ),
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"نظام تذاكر متطور | v{bot_config['version']}")
        
        # إنشاء زر التذكرة
        class TicketButton(Button):
            def __init__(self):
                super().__init__(
                    style=ButtonStyle.green,
                    label="إنشاء تذكرة",
                    emoji="🎫",
                    custom_id="create_ticket"
                )
            
            async def callback(self, interaction: discord.Interaction):
                # التحقق من التذاكر المفتوحة
                if str(interaction.user.id) in active_tickets:
                    embed = discord.Embed(
                        title="❌ خطأ",
                        description="لديك تذكرة مفتوحة بالفعل! يرجى إغلاق التذكرة الحالية أولاً.",
                        color=discord.Color.red()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                
                # إنشاء قائمة اختيار النوع
                class CategorySelect(Select):
                    def __init__(self):
                        super().__init__(
                            placeholder="اختر نوع التذكرة",
                            options=ticket_categories,
                            custom_id="category_select"
                        )
                    
                    async def callback(self, interaction: discord.Interaction):
                        # إنشاء قائمة اختيار الأولوية
                        priority_options = [
                            discord.SelectOption(
                                label=config['label'],
                                value=level,
                                emoji=config['emoji'],
                                description=f"وقت الاستجابة: {config['response_time']}"
                            )
                            for level, config in priority_config.items()
                        ]
                        
                        class PrioritySelect(Select):
                            def __init__(self):
                                super().__init__(
                                    placeholder="اختر مستوى الأولوية",
                                    options=priority_options,
                                    custom_id="priority_select"
                                )
                            
                            async def callback(self, interaction: discord.Interaction):
                                # تخزين القيم المحددة
                                selected_category = self.view.children[0].values[0]  # القيمة المحددة من قائمة النوع
                                selected_priority = self.values[0]  # القيمة المحددة من قائمة الأولوية
                                
                                # إنشاء نموذج التذكرة مع القيم الصحيحة
                                modal = TicketModal(selected_category, selected_priority)
                                await interaction.response.send_modal(modal)
                        
                        # إرسال قائمة الأولوية
                        view = View()
                        view.add_item(PrioritySelect())
                        await interaction.response.send_message(
                            "الرجاء اختيار مستوى الأولوية:",
                            view=view,
                            ephemeral=True
                        )
                
                # إرسال قائمة النوع
                view = View()
                view.add_item(CategorySelect())
                await interaction.response.send_message(
                    "الرجاء اختيار نوع التذكرة:",
                    view=view,
                    ephemeral=True
                )
        
        # إنشاء وإرسال اللوحة
        view = View()
        view.add_item(TicketButton())
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message("✅ تم إنشاء لوحة التذاكر بنجاح!", ephemeral=True)
        
    except Exception as e:
        await TicketManager.handle_error(interaction, "إنشاء لوحة التذاكر", e)

@bot.tree.command(name="احصائيات", description="عرض إحصائيات نظام التذاكر")
@app_commands.default_permissions(administrator=True)
async def show_stats(interaction: discord.Interaction):
    """عرض إحصائيات نظام التذاكر"""
    try:
        current_time = datetime.datetime.now(timezone)
        embed = discord.Embed(
            title="📊 إحصائيات نظام التذاكر",
            color=discord.Color.blue(),
            timestamp=current_time
        )
        
        # إحصائيات عامة
        embed.add_field(
            name="📈 إحصائيات عامة",
            value=(
                f"**إجمالي التذاكر:** {ticket_stats['total_tickets']}\n"
                f"**التذاكر المفتوحة:** {ticket_stats['open_tickets']}\n"
                f"**التذاكر المغلقة:** {ticket_stats['closed_tickets']}"
            ),
            inline=False
        )
        
        # إحصائيات التصنيفات
        categories_text = "\n".join([
            f"• {cat}: {count}" 
            for cat, count in ticket_stats["categories"].items()
        ]) or "لا توجد تذاكر"
        embed.add_field(name="📑 التصنيفات", value=categories_text, inline=False)
        
        # إحصائيات التقييمات
        ratings_text = "\n".join([
            f"{'⭐' * int(rating)}: {count}" 
            for rating, count in ticket_stats["ratings"].items()
            if count > 0
        ]) or "لا توجد تقييمات"
        embed.add_field(name="⭐ التقييمات", value=ratings_text, inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    except Exception as e:
        await TicketManager.handle_error(interaction, "عرض الإحصائيات", e)

@bot.tree.command(name="تعيين_رتب", description="إنشاء وتعيين الرتب للأولويات المختلفة")
@app_commands.default_permissions(administrator=True)
async def set_priority_roles(interaction: discord.Interaction):
    """إنشاء وتعيين الرتب للأولويات المختلفة"""
    try:
        # التحقق من صلاحيات البوت
        if not interaction.guild.me.guild_permissions.manage_roles:
            raise discord.Forbidden("البوت لا يملك صلاحية إدارة الرتب")

        # إنشاء الرتب تلقائياً
        roles_created = []
        for priority_level, config in priority_config.items():
            role_name = f"🎫 {config['label']}"
            
            # البحث عن الرتبة إذا كانت موجودة
            existing_role = discord.utils.get(interaction.guild.roles, name=role_name)
            
            if existing_role:
                role = existing_role
                logger.info(f"تم العثور على رتبة {role_name}")
            else:
                # إنشاء رتبة جديدة
                role = await interaction.guild.create_role(
                    name=role_name,
                    color=discord.Color(config['color']),
                    mentionable=True,
                    reason="إنشاء رتبة تلقائياً لنظام التذاكر"
                )
                logger.info(f"تم إنشاء رتبة جديدة: {role_name}")
            
            # تحديث الإعدادات
            config['role'] = role.id
            roles_created.append(role)
        
        # حفظ الإعدادات
        await save_settings()
        
        # إنشاء رسالة تأكيد
        embed = discord.Embed(
            title="✅ تم إنشاء وتعيين الرتب",
            description="تم إنشاء وتعيين الرتب التالية للتعامل مع التذاكر:",
            color=discord.Color.green()
        )
        
        for priority_level, config in priority_config.items():
            role = interaction.guild.get_role(config['role'])
            embed.add_field(
                name=f"{config['emoji']} {config['label']}",
                value=f"الرتبة: {role.mention}\nوقت الاستجابة: {config['response_time']}",
                inline=False
            )
        
        # إضافة نصائح للاستخدام
        embed.add_field(
            name="📝 ملاحظات",
            value=(
                "• يمكنك تعديل ألوان وأذونات الرتب يدوياً من إعدادات السيرفر\n"
                "• تأكد من وضع الرتب في المكان المناسب في قائمة الرتب\n"
                "• يمكنك إعادة تنفيذ هذا الأمر في أي وقت لإعادة ربط الرتب"
            ),
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    except discord.Forbidden as e:
        await interaction.response.send_message(
            "❌ خطأ: البوت لا يملك صلاحية إدارة الرتب",
            ephemeral=True
        )
    except Exception as e:
        await TicketManager.handle_error(interaction, "إنشاء وتعيين الرتب", e)

@bot.tree.command(name="اعداد_القنوات", description="إعداد قنوات النظام تلقائياً")
@app_commands.default_permissions(administrator=True)
async def setup_channels(interaction: discord.Interaction):
    """إعداد قنوات النظام تلقائياً"""
    try:
        # التحقق من صلاحيات البوت
        required_permissions = [
            "manage_channels",
            "manage_roles",
            "read_messages",
            "send_messages",
            "manage_messages",
            "embed_links",
            "attach_files",
            "read_message_history"
        ]
        
        missing_perms = []
        for perm in required_permissions:
            if not getattr(interaction.guild.me.guild_permissions, perm):
                missing_perms.append(perm)
        
        if missing_perms:
            raise discord.Forbidden(f"البوت يفتقد للصلاحيات التالية: {', '.join(missing_perms)}")

        await interaction.response.defer()

        # إنشاء تصنيف التذاكر
        category_name = "🎫 التذاكر"
        existing_category = discord.utils.get(interaction.guild.categories, name=category_name)
        
        if existing_category:
            category = existing_category
            logger.info(f"تم العثور على تصنيف {category_name}")
        else:
            try:
                category = await interaction.guild.create_category(
                    name=category_name,
                    reason="إنشاء تصنيف تلقائياً لنظام التذاكر"
                )
                logger.info(f"تم إنشاء تصنيف جديد: {category_name}")
            except Exception as e:
                raise Exception(f"فشل في إنشاء التصنيف: {str(e)}")

        # إعداد الأذونات الافتراضية للتصنيف
        try:
            await category.set_permissions(interaction.guild.default_role, read_messages=False)
            await category.set_permissions(interaction.guild.me, read_messages=True, send_messages=True, manage_channels=True)
        except Exception as e:
            logger.warning(f"فشل في إعداد أذونات التصنيف: {str(e)}")

        # إنشاء القنوات
        channels_to_create = {
            'logs_channel': ('📝-سجلات-التذاكر', 'قناة سجلات نظام التذاكر'),
            'archive_channel': ('📂-ارشيف-التذاكر', 'قناة أرشيف التذاكر المغلقة'),
            'feedback_channel': ('⭐-تقييمات-التذاكر', 'قناة تقييمات التذاكر')
        }

        created_channels = {}
        for channel_key, (channel_name, channel_topic) in channels_to_create.items():
            try:
                # البحث عن القناة إذا كانت موجودة
                existing_channel = discord.utils.get(category.text_channels, name=channel_name.replace('-', ''))
                
                if existing_channel:
                    channel = existing_channel
                    logger.info(f"تم العثور على قناة {channel_name}")
                else:
                    # إنشاء قناة جديدة
                    channel = await interaction.guild.create_text_channel(
                        name=channel_name,
                        category=category,
                        topic=channel_topic,
                        reason="إنشاء قناة تلقائياً لنظام التذاكر"
                    )
                    logger.info(f"تم إنشاء قناة جديدة: {channel_name}")

                # تحديث الإعدادات
                channel_config[channel_key] = channel.id
                created_channels[channel_key] = channel

            except Exception as e:
                logger.error(f"فشل في إنشاء قناة {channel_name}: {str(e)}")
                continue

        # تحديث معرف التصنيف
        channel_config['tickets_category'] = category.id

        # حفظ الإعدادات
        await save_settings()

        # إنشاء رسالة تأكيد
        embed = discord.Embed(
            title="✅ تم إنشاء وإعداد القنوات",
            description="تم إعداد القنوات التالية بنجاح:",
            color=discord.Color.green()
        )

        # إضافة حقول للقنوات التي تم إنشاؤها
        embed.add_field(
            name="📁 تصنيف التذاكر",
            value=category.mention,
            inline=False
        )

        for channel_key, channel in created_channels.items():
            embed.add_field(
                name={"logs_channel": "📝 قناة السجلات",
                     "archive_channel": "📂 قناة الأرشيف",
                     "feedback_channel": "⭐ قناة التقييمات"}[channel_key],
                value=channel.mention,
                inline=True
            )

        # إضافة نصائح للاستخدام
        embed.add_field(
            name="📝 ملاحظات",
            value=(
                "• تم إعداد الأذونات الأساسية للقنوات\n"
                "• يمكنك تعديل الأذونات يدوياً من إعدادات السيرفر\n"
                "• استخدم الأمر `/تعيين_رتب` لإعداد رتب الأولويات\n"
                "• استخدم الأمر `/انشاء_لوحة` لإنشاء لوحة التذاكر"
            ),
            inline=False
        )

        await interaction.followup.send(embed=embed, ephemeral=True)

    except discord.Forbidden as e:
        error_msg = str(e) if str(e) else "البوت لا يملك الصلاحيات الكافية لإنشاء القنوات"
        await interaction.response.send_message(
            f"❌ خطأ: {error_msg}",
            ephemeral=True
        )
    except Exception as e:
        await TicketManager.handle_error(interaction, "إعداد القنوات", e)

@bot.tree.command(name="مساعدة", description="عرض قائمة الأوامر المتاحة")
async def help_command(interaction: discord.Interaction):
    """عرض قائمة الأوامر المتاحة"""
    try:
        embed = discord.Embed(
            title="📚 قائمة الأوامر المتاحة",
            description="هذه قائمة بجميع الأوامر المتاحة في نظام التذاكر:",
            color=discord.Color.blue()
        )
        
        commands = {
            "🎫 /انشاء_لوحة": "إنشاء لوحة تذاكر تفاعلية (للمشرفين)",
            "📊 /احصائيات": "عرض إحصائيات نظام التذاكر (للمشرفين)",
            "👥 /تعيين_رتب": "تعيين الرتب للأولويات المختلفة (للمشرفين)",
            "⚙️ /اعداد_القنوات": "إعداد قنوات النظام (للمشرفين)",
            "❓ /مساعدة": "عرض هذه القائمة"
        }
        
        for command, description in commands.items():
            embed.add_field(name=command, value=description, inline=False)
        
        embed.set_footer(text=f"نظام تذاكر متطور | v{bot_config['version']}")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    except Exception as e:
        await TicketManager.handle_error(interaction, "عرض المساعدة", e)

# إنشاء مدير التذاكر
ticket_manager = TicketManager()

# إضافة الأوامر الإدارية
@bot.tree.command(name="طرد", description="طرد عضو من السيرفر")
@app_commands.describe(member="العضو المراد طرده", reason="سبب الطرد")
@app_commands.default_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = None):
    """طرد عضو من السيرفر"""
    try:
        # التحقق من الصلاحيات
        if not interaction.user.guild_permissions.kick_members:
            await interaction.response.send_message("❌ ليس لديك صلاحية طرد الأعضاء!", ephemeral=True)
            return
            
        if member.top_role >= interaction.user.top_role:
            await interaction.response.send_message("❌ لا يمكنك طرد عضو رتبته أعلى منك أو تساويك!", ephemeral=True)
            return
            
        # إنشاء رسالة التأكيد
        embed = discord.Embed(
            title="⚠️ تأكيد الطرد",
            description=f"هل أنت متأكد من طرد {member.mention}؟",
            color=discord.Color.yellow()
        )
        
        if reason:
            embed.add_field(name="السبب:", value=reason)
            
        # إنشاء أزرار التأكيد
        class KickConfirm(View):
            def __init__(self):
                super().__init__(timeout=60.0)
                
            @discord.ui.button(label="تأكيد", style=ButtonStyle.danger, emoji="⚠️")
            async def confirm(self, interaction: discord.Interaction, button: Button):
                try:
                    # تنفيذ الطرد
                    await member.kick(reason=f"بواسطة {interaction.user.name} - السبب: {reason if reason else 'لم يتم تحديد سبب'}")
                    
                    # إرسال رسالة نجاح
                    success_embed = discord.Embed(
                        title="✅ تم الطرد بنجاح",
                        description=f"تم طرد {member.mention} من السيرفر",
                        color=discord.Color.green()
                    )
                    if reason:
                        success_embed.add_field(name="السبب:", value=reason)
                    
                    await interaction.response.send_message(embed=success_embed)
                    
                    # تسجيل العملية
                    logger.info(f"تم طرد العضو {member.name} بواسطة {interaction.user.name}")
                    
                except Exception as e:
                    await interaction.response.send_message(f"❌ حدث خطأ أثناء الطرد: {str(e)}", ephemeral=True)
            
            @discord.ui.button(label="إلغاء", style=ButtonStyle.gray, emoji="✖️")
            async def cancel(self, interaction: discord.Interaction, button: Button):
                await interaction.response.send_message("تم إلغاء عملية الطرد", ephemeral=True)
        
        await interaction.response.send_message(embed=embed, view=KickConfirm(), ephemeral=True)
        
    except Exception as e:
        await interaction.response.send_message(f"❌ حدث خطأ: {str(e)}", ephemeral=True)

@bot.tree.command(name="حظر", description="حظر عضو من السيرفر")
@app_commands.describe(member="العضو المراد حظره", reason="سبب الحظر", delete_messages="عدد الأيام التي سيتم حذف رسائلها (0-7)")
@app_commands.default_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = None, delete_messages: int = 0):
    """حظر عضو من السيرفر"""
    try:
        # التحقق من الصلاحيات
        if not interaction.user.guild_permissions.ban_members:
            await interaction.response.send_message("❌ ليس لديك صلاحية حظر الأعضاء!", ephemeral=True)
            return
            
        if member.top_role >= interaction.user.top_role:
            await interaction.response.send_message("❌ لا يمكنك حظر عضو رتبته أعلى منك أو تساويك!", ephemeral=True)
            return
            
        # التحقق من عدد أيام حذف الرسائل
        delete_messages = max(0, min(7, delete_messages))
            
        # إنشاء رسالة التأكيد
        embed = discord.Embed(
            title="⚠️ تأكيد الحظر",
            description=f"هل أنت متأكد من حظر {member.mention}؟",
            color=discord.Color.red()
        )
        
        if reason:
            embed.add_field(name="السبب:", value=reason)
        embed.add_field(name="حذف الرسائل:", value=f"سيتم حذف رسائل آخر {delete_messages} يوم" if delete_messages > 0 else "لن يتم حذف الرسائل")
            
        # إنشاء أزرار التأكيد
        class BanConfirm(View):
            def __init__(self):
                super().__init__(timeout=60.0)
                
            @discord.ui.button(label="تأكيد", style=ButtonStyle.danger, emoji="⚠️")
            async def confirm(self, interaction: discord.Interaction, button: Button):
                try:
                    # تنفيذ الحظر
                    await member.ban(
                        reason=f"بواسطة {interaction.user.name} - السبب: {reason if reason else 'لم يتم تحديد سبب'}",
                        delete_message_days=delete_messages
                    )
                    
                    # إرسال رسالة نجاح
                    success_embed = discord.Embed(
                        title="✅ تم الحظر بنجاح",
                        description=f"تم حظر {member.mention} من السيرفر",
                        color=discord.Color.green()
                    )
                    if reason:
                        success_embed.add_field(name="السبب:", value=reason)
                    
                    await interaction.response.send_message(embed=success_embed)
                    
                    # تسجيل العملية
                    logger.info(f"تم حظر العضو {member.name} بواسطة {interaction.user.name}")
                    
                except Exception as e:
                    await interaction.response.send_message(f"❌ حدث خطأ أثناء الحظر: {str(e)}", ephemeral=True)
            
            @discord.ui.button(label="إلغاء", style=ButtonStyle.gray, emoji="✖️")
            async def cancel(self, interaction: discord.Interaction, button: Button):
                await interaction.response.send_message("تم إلغاء عملية الحظر", ephemeral=True)
        
        await interaction.response.send_message(embed=embed, view=BanConfirm(), ephemeral=True)
        
    except Exception as e:
        await interaction.response.send_message(f"❌ حدث خطأ: {str(e)}", ephemeral=True)

@bot.tree.command(name="تحذير", description="إعطاء تحذير لعضو")
@app_commands.describe(member="العضو المراد تحذيره", reason="سبب التحذير")
@app_commands.default_permissions(moderate_members=True)
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str):
    """إعطاء تحذير لعضو"""
    try:
        # التحقق من الصلاحيات
        if not interaction.user.guild_permissions.moderate_members:
            await interaction.response.send_message("❌ ليس لديك صلاحية تحذير الأعضاء!", ephemeral=True)
            return
            
        if member.top_role >= interaction.user.top_role:
            await interaction.response.send_message("❌ لا يمكنك تحذير عضو رتبته أعلى منك أو تساويك!", ephemeral=True)
            return
            
        # تحديث الإحصائيات
        if 'warnings' not in ticket_stats:
            ticket_stats['warnings'] = {}
            
        member_id = str(member.id)
        if member_id not in ticket_stats['warnings']:
            ticket_stats['warnings'][member_id] = []
            
        # إضافة التحذير
        warning = {
            'reason': reason,
            'by': interaction.user.name,
            'date': datetime.datetime.now(timezone).strftime('%Y-%m-%d %H:%M:%S')
        }
        
        ticket_stats['warnings'][member_id].append(warning)
        await save_settings()
        
        # إرسال رسالة التحذير
        embed = discord.Embed(
            title="⚠️ تحذير جديد",
            description=f"تم تحذير {member.mention}",
            color=discord.Color.orange()
        )
        embed.add_field(name="السبب:", value=reason)
        embed.add_field(name="بواسطة:", value=interaction.user.mention)
        embed.add_field(name="عدد التحذيرات:", value=str(len(ticket_stats['warnings'][member_id])))
        
        await interaction.response.send_message(embed=embed)
        
        try:
            # إرسال التحذير للعضو في الخاص
            user_embed = discord.Embed(
                title="⚠️ تحذير",
                description=f"لقد تلقيت تحذيراً في سيرفر {interaction.guild.name}",
                color=discord.Color.orange()
            )
            user_embed.add_field(name="السبب:", value=reason)
            await member.send(embed=user_embed)
        except:
            pass
            
        # تسجيل العملية
        logger.info(f"تم تحذير العضو {member.name} بواسطة {interaction.user.name}")
        
    except Exception as e:
        await interaction.response.send_message(f"❌ حدث خطأ: {str(e)}", ephemeral=True)

@bot.tree.command(name="مسح", description="مسح عدد معين من الرسائل")
@app_commands.describe(amount="عدد الرسائل المراد مسحها (1-100)")
@app_commands.default_permissions(manage_messages=True)
async def clear(interaction: discord.Interaction, amount: int):
    """مسح عدد معين من الرسائل"""
    try:
        # التحقق من الصلاحيات
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ ليس لديك صلاحية حذف الرسائل!", ephemeral=True)
            return
            
        # التحقق من العدد
        amount = max(1, min(100, amount))
        
        # تأجيل الرد
        await interaction.response.defer(ephemeral=True)
        
        # حذف الرسائل
        deleted = await interaction.channel.purge(limit=amount)
        
        # إرسال رسالة التأكيد
        await interaction.followup.send(f"✅ تم حذف {len(deleted)} رسالة", ephemeral=True)
        
        # تسجيل العملية
        logger.info(f"تم حذف {len(deleted)} رسالة بواسطة {interaction.user.name}")
        
    except Exception as e:
        await interaction.followup.send(f"❌ حدث خطأ: {str(e)}", ephemeral=True)

@bot.tree.command(name="ميوت", description="كتم عضو")
@app_commands.describe(member="العضو المراد كتمه", duration="مدة الكتم بالدقائق", reason="سبب الكتم")
@app_commands.default_permissions(moderate_members=True)
async def timeout(interaction: discord.Interaction, member: discord.Member, duration: int, reason: str = None):
    """كتم عضو"""
    try:
        # التحقق من الصلاحيات
        if not interaction.user.guild_permissions.moderate_members:
            await interaction.response.send_message("❌ ليس لديك صلاحية كتم الأعضاء!", ephemeral=True)
            return
            
        if member.top_role >= interaction.user.top_role:
            await interaction.response.send_message("❌ لا يمكنك كتم عضو رتبته أعلى منك أو تساويك!", ephemeral=True)
            return
            
        # تحويل المدة إلى ثواني
        duration_seconds = duration * 60
        
        # تنفيذ الكتم
        await member.timeout(
            datetime.timedelta(seconds=duration_seconds),
            reason=f"بواسطة {interaction.user.name} - السبب: {reason if reason else 'لم يتم تحديد سبب'}"
        )
        
        # إرسال رسالة التأكيد
        embed = discord.Embed(
            title="🔇 تم الكتم بنجاح",
            description=f"تم كتم {member.mention}",
            color=discord.Color.orange()
        )
        embed.add_field(name="المدة:", value=f"{duration} دقيقة")
        if reason:
            embed.add_field(name="السبب:", value=reason)
            
        await interaction.response.send_message(embed=embed)
        
        try:
            # إرسال إشعار للعضو في الخاص
            user_embed = discord.Embed(
                title="🔇 تم كتمك",
                description=f"تم كتمك في سيرفر {interaction.guild.name}",
                color=discord.Color.orange()
            )
            user_embed.add_field(name="المدة:", value=f"{duration} دقيقة")
            if reason:
                user_embed.add_field(name="السبب:", value=reason)
            await member.send(embed=user_embed)
        except:
            pass
            
        # تسجيل العملية
        logger.info(f"تم كتم العضو {member.name} لمدة {duration} دقيقة بواسطة {interaction.user.name}")
        
    except Exception as e:
        await interaction.response.send_message(f"❌ حدث خطأ: {str(e)}", ephemeral=True)

@bot.tree.command(name="تذكيرات", description="عرض التذكيرات النشطة")
@app_commands.default_permissions(administrator=True)
async def show_reminders(interaction: discord.Interaction):
    """عرض التذكيرات النشطة"""
    try:
        if not reminders:
            await interaction.response.send_message("لا توجد تذكيرات نشطة حالياً", ephemeral=True)
            return
            
        embed = discord.Embed(
            title="📋 التذكيرات النشطة",
            color=discord.Color.blue()
        )
        
        for ticket_id, reminder in reminders.items():
            channel = bot.get_channel(reminder.channel_id)
            if channel:
                time_passed = (datetime.datetime.now(timezone) - reminder.created_at).total_seconds() / 3600
                value = (
                    f"**القناة:** {channel.mention}\n"
                    f"**الأولوية:** {priority_config[reminder.priority]['emoji']} {priority_config[reminder.priority]['label']}\n"
                    f"**الوقت المنقضي:** {time_passed:.1f} ساعة"
                )
                embed.add_field(
                    name=f"تذكرة {ticket_id}",
                    value=value,
                    inline=False
                )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    except Exception as e:
        await TicketManager.handle_error(interaction, "عرض التذكيرات", e)

class GroupSupportView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        
    @discord.ui.button(label="تحويل إلى نقاش جماعي", style=discord.ButtonStyle.blurple, emoji="👥")
    async def convert_to_group(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            channel = interaction.channel
            
            # التحقق من أن القناة هي تذكرة
            if str(channel.id) not in active_tickets.values():
                await interaction.response.send_message("❌ هذه القناة ليست تذكرة نشطة!", ephemeral=True)
                return
            
            # التحقق من الصلاحيات
            if not interaction.user.guild_permissions.manage_channels:
                await interaction.response.send_message("❌ ليس لديك صلاحية تحويل التذكرة!", ephemeral=True)
                return
            
            # تحويل التذكرة إلى نقاش جماعي
            group_tickets[str(channel.id)] = {
                'solutions': [],
                'experts': set(),
                'votes': {}
            }
            
            # تعديل أذونات القناة
            await channel.edit(name=f"👥-{channel.name}")
            
            # إنشاء رسالة النقاش الجماعي
            embed = discord.Embed(
                title="🔄 تم تحويل التذكرة إلى نقاش جماعي",
                description=(
                    "يمكن للجميع المشاركة في حل هذه المشكلة!\n\n"
                    "**الميزات المتاحة:**\n"
                    "• إضافة حلول مقترحة\n"
                    "• دعوة خبراء للمساعدة\n"
                    "• التصويت على أفضل الحلول\n"
                    "• توثيق الحل النهائي"
                ),
                color=discord.Color.blue()
            )
            
            # إضافة أزرار التحكم
            group_controls = GroupControlsView()
            await interaction.response.send_message(embed=embed, view=group_controls)
            
        except Exception as e:
            await TicketManager.handle_error(interaction, "تحويل التذكرة", e)

class GroupControlsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        
    @discord.ui.button(label="إضافة حل", style=discord.ButtonStyle.green, emoji="💡")
    async def add_solution(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            # فتح نموذج إضافة حل
            solution_modal = AddSolutionModal()
            await interaction.response.send_modal(solution_modal)
            
        except Exception as e:
            await TicketManager.handle_error(interaction, "إضافة حل", e)
    
    @discord.ui.button(label="دعوة خبير", style=discord.ButtonStyle.blurple, emoji="📧")
    async def invite_expert(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            # فتح نموذج دعوة خبير
            invite_modal = InviteExpertModal()
            await interaction.response.send_modal(invite_modal)
            
        except Exception as e:
            await TicketManager.handle_error(interaction, "دعوة خبير", e)
    
    @discord.ui.button(label="توثيق الحل", style=discord.ButtonStyle.gray, emoji="📝")
    async def document_solution(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            channel = interaction.channel
            if str(channel.id) not in group_tickets:
                await interaction.response.send_message("❌ هذه ليست تذكرة جماعية!", ephemeral=True)
                return
            
            # التحقق من وجود حلول
            if not group_tickets[str(channel.id)]['solutions']:
                await interaction.response.send_message("❌ لا توجد حلول مقترحة بعد!", ephemeral=True)
                return
            
            # فرز الحلول حسب التصويت
            solutions = group_tickets[str(channel.id)]['solutions']
            votes = group_tickets[str(channel.id)]['votes']
            
            sorted_solutions = sorted(
                solutions,
                key=lambda x: sum(1 for v in votes.values() if v == solutions.index(x)),
                reverse=True
            )
            
            # إنشاء ملخص الحلول
            embed = discord.Embed(
                title="📋 ملخص الحلول المقترحة",
                color=discord.Color.green()
            )
            
            for i, solution in enumerate(sorted_solutions):
                vote_count = sum(1 for v in votes.values() if v == solutions.index(solution))
                embed.add_field(
                    name=f"الحل #{i+1} (👍 {vote_count})",
                    value=solution,
                    inline=False
                )
            
            # إضافة معلومات الخبراء
            experts = group_tickets[str(channel.id)]['experts']
            if experts:
                expert_mentions = [f"<@{expert_id}>" for expert_id in experts]
                embed.add_field(
                    name="👥 الخبراء المشاركون",
                    value="\n".join(expert_mentions),
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            await TicketManager.handle_error(interaction, "توثيق الحل", e)

class AddSolutionModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="إضافة حل مقترح")
        
        self.solution = discord.ui.TextInput(
            label="الحل المقترح",
            style=discord.TextStyle.paragraph,
            placeholder="اكتب الحل المقترح هنا...",
            required=True,
            max_length=1000
        )
        
        self.add_item(self.solution)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            channel = interaction.channel
            if str(channel.id) not in group_tickets:
                await interaction.response.send_message("❌ هذه ليست تذكرة جماعية!", ephemeral=True)
                return
            
            # إضافة الحل للقائمة
            solution_index = len(group_tickets[str(channel.id)]['solutions'])
            group_tickets[str(channel.id)]['solutions'].append(self.solution.value)
            
            # إنشاء رسالة الحل
            embed = discord.Embed(
                title=f"💡 حل مقترح #{solution_index + 1}",
                description=self.solution.value,
                color=discord.Color.green()
            )
            embed.set_footer(text=f"مقترح بواسطة {interaction.user.name}")
            
            # إضافة زر التصويت
            vote_view = VoteView(solution_index)
            await interaction.response.send_message(embed=embed, view=vote_view)
            
        except Exception as e:
            await TicketManager.handle_error(interaction, "إضافة حل", e)

class InviteExpertModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="دعوة خبير")
        
        self.expert = discord.ui.TextInput(
            label="معرف الخبير",
            placeholder="ضع معرف الخبير هنا...",
            required=True,
            max_length=100
        )
        
        self.reason = discord.ui.TextInput(
            label="سبب الدعوة",
            style=discord.TextStyle.paragraph,
            placeholder="اشرح سبب دعوة هذا الخبير...",
            required=True,
            max_length=500
        )
        
        self.add_item(self.expert)
        self.add_item(self.reason)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            channel = interaction.channel
            if str(channel.id) not in group_tickets:
                await interaction.response.send_message("❌ هذه ليست تذكرة جماعية!", ephemeral=True)
                return
            
            # معالجة معرف الخبير
            expert_id = ''.join(filter(str.isdigit, self.expert.value))
            if not expert_id:
                await interaction.response.send_message("❌ معرف الخبير غير صالح!", ephemeral=True)
                return
            
            try:
                expert = await interaction.guild.fetch_member(int(expert_id))
                if not expert:
                    await interaction.response.send_message("❌ لم يتم العثور على العضو!", ephemeral=True)
                    return
            except:
                await interaction.response.send_message("❌ لم يتم العثور على العضو!", ephemeral=True)
                return
            
            # إضافة الخبير للقناة
            await channel.set_permissions(expert, read_messages=True, send_messages=True)
            group_tickets[str(channel.id)]['experts'].add(expert.id)
            
            # إرسال رسالة الدعوة
            embed = discord.Embed(
                title="📧 دعوة للمساعدة",
                description=(
                    f"تمت دعوتك للمساعدة في حل مشكلة في {channel.mention}\n\n"
                    f"**السبب:** {self.reason.value}"
                ),
                color=discord.Color.blue()
            )
            
            try:
                await expert.send(embed=embed)
            except:
                pass
            
            # إرسال تأكيد في القناة
            await interaction.response.send_message(
                f"✅ تمت دعوة الخبير {expert.mention} للمساعدة!"
            )
            
        except Exception as e:
            await TicketManager.handle_error(interaction, "دعوة خبير", e)

class VoteView(discord.ui.View):
    def __init__(self, solution_index: int):
        super().__init__(timeout=None)
        self.solution_index = solution_index
        
    @discord.ui.button(label="تصويت", style=discord.ButtonStyle.green, emoji="👍")
    async def vote(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            channel = interaction.channel
            if str(channel.id) not in group_tickets:
                await interaction.response.send_message("❌ هذه ليست تذكرة جماعية!", ephemeral=True)
                return
            
            # تسجيل التصويت
            group_tickets[str(channel.id)]['votes'][str(interaction.user.id)] = self.solution_index
            
            # حساب عدد الأصوات
            vote_count = sum(1 for v in group_tickets[str(channel.id)]['votes'].values() if v == self.solution_index)
            
            await interaction.response.send_message(
                f"✅ تم تسجيل تصويتك! (إجمالي الأصوات: {vote_count})",
                ephemeral=True
            )
            
        except Exception as e:
            await TicketManager.handle_error(interaction, "التصويت", e)

# تعديل دالة إنشاء التذكرة لإضافة زر الدعم الجماعي
async def create_ticket(interaction: discord.Interaction, category: str, priority: str, subject: str, description: str):
    """إنشاء تذكرة جديدة"""
    try:
        # التحقق من عدد التذاكر المفتوحة للمستخدم
        user_tickets = sum(1 for user_id, _ in active_tickets.items() if user_id == str(interaction.user.id))
        if user_tickets >= ticket_settings['max_open_tickets']:
            raise ValueError(f"لديك {user_tickets} تذاكر مفتوحة بالفعل! الحد الأقصى المسموح به هو {ticket_settings['max_open_tickets']} تذاكر.")

        # التحقق من القنوات
        if not channel_config.get('tickets_category'):
            raise ValueError("لم يتم إعداد تصنيف التذاكر. الرجاء استخدام الأمر /اعداد_القنوات أولاً")
        
        # التحقق من وجود التصنيف وأنه من النوع الصحيح
        try:
            category_id = int(channel_config['tickets_category'])
            category_channel = interaction.guild.get_channel(category_id)
            
            if not category_channel:
                # محاولة إنشاء تصنيف جديد
                category_channel = await interaction.guild.create_category(
                    name="🎫 التذاكر",
                    reason="إنشاء تصنيف تلقائياً لنظام التذاكر"
                )
                channel_config['tickets_category'] = category_channel.id
                await save_settings()
                logger.info(f"تم إنشاء تصنيف جديد للتذاكر: {category_channel.name}")
            
            if not isinstance(category_channel, discord.CategoryChannel):
                raise ValueError(f"القناة المحددة ({category_id}) ليست تصنيفاً. الرجاء استخدام الأمر /اعداد_القنوات لإعداد التصنيف الصحيح")
            
        except (ValueError, TypeError):
            raise ValueError("معرف التصنيف غير صالح. الرجاء استخدام الأمر /اعداد_القنوات لإعادة إعداد القنوات")
        
        # التحقق من صلاحيات البوت
        bot_member = interaction.guild.get_member(bot.user.id)
        required_permissions = discord.Permissions(
            manage_channels=True,
            read_messages=True,
            send_messages=True,
            manage_messages=True,
            embed_links=True,
            attach_files=True,
            read_message_history=True,
            manage_roles=True
        )
        
        if not category_channel.permissions_for(bot_member).is_superset(required_permissions):
            missing_perms = [perm[0] for perm in required_permissions if not getattr(category_channel.permissions_for(bot_member), perm[0])]
            raise ValueError(f"البوت يفتقد للصلاحيات التالية: {', '.join(missing_perms)}")
        
        # إنشاء اسم القناة
        ticket_number = ticket_stats['total_tickets'] + 1
        channel_name = f"ticket-{ticket_number:04d}"
        
        # إنشاء القناة
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            bot_member: discord.PermissionOverwrite(**{perm[0]: True for perm in required_permissions})
        }
        
        # إضافة الرتبة المسؤولة إذا وجدت
        if priority_config[priority]['role']:
            role = interaction.guild.get_role(priority_config[priority]['role'])
            if role:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        
        # إنشاء القناة مع الأذونات
        ticket_channel = await interaction.guild.create_text_channel(
            name=channel_name,
            category=category_channel,
            topic=f"تذكرة {subject} | بواسطة {interaction.user.name}",
            overwrites=overwrites
        )
        
        # تحديث الإحصائيات
        ticket_stats['total_tickets'] += 1
        ticket_stats['open_tickets'] += 1
        ticket_stats['categories'][category] = ticket_stats['categories'].get(category, 0) + 1
        active_tickets[str(interaction.user.id)] = ticket_channel.id
        await save_settings()
        
        # إنشاء رسالة الترحيب
        embed = discord.Embed(
            title=f"تذكرة #{ticket_number:04d}",
            description=description,
            color=discord.Color(priority_config[priority]['color'])
        )
        embed.add_field(name="النوع", value=category, inline=True)
        embed.add_field(name="الأولوية", value=f"{priority_config[priority]['emoji']} {priority_config[priority]['label']}", inline=True)
        embed.add_field(name="وقت الاستجابة", value=priority_config[priority]['response_time'], inline=True)
        embed.set_footer(text=f"تم الإنشاء بواسطة {interaction.user.name}")
        
        # إضافة أزرار التحكم
        ticket_controls = TicketControlView()
        
        # إرسال رسالة الترحيب
        await ticket_channel.send(
            content=f"{interaction.user.mention} " + (f"<@&{priority_config[priority]['role']}> " if priority_config[priority]['role'] else ""),
            embed=embed,
            view=ticket_controls
        )
        
        # إرسال تأكيد للمستخدم
        await interaction.response.send_message(
            f"✅ تم إنشاء تذكرتك في {ticket_channel.mention}",
            ephemeral=True
        )
        
        # تسجيل الحدث
        logger.info(f"تم إنشاء تذكرة جديدة: {channel_name} بواسطة {interaction.user.name}")
        
        # إضافة التذكرة لنظام التذكيرات
        ticket_reminder = TicketReminder(
            channel_id=ticket_channel.id,
            ticket_id=f"#{ticket_number:04d}",
            priority=priority,
            created_at=datetime.datetime.now(timezone)
        )
        reminders[f"#{ticket_number:04d}"] = ticket_reminder
        
        # إضافة زر الدعم الجماعي
        ticket_controls = TicketControlView()
        group_support = GroupSupportView()
        
        # إرسال أزرار الدعم الجماعي
        await ticket_channel.send(view=group_support)
        
        # إضافة التذكرة لنظام تتبع النشاط
        ticket_activity[str(ticket_channel.id)] = datetime.datetime.now(timezone)
        
    except ValueError as e:
        await TicketManager.handle_error(interaction, "إنشاء التذكرة", e)
    except discord.Forbidden as e:
        await TicketManager.handle_error(interaction, "إنشاء التذكرة", "البوت لا يملك الصلاحيات الكافية")
    except Exception as e:
        await TicketManager.handle_error(interaction, "إنشاء التذكرة", e)

# تشغيل البوت
bot.run(TOKEN) 