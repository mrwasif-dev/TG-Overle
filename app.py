import os
import logging
import asyncio
import traceback
from pathlib import Path
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode, ChatAction
from dotenv import load_dotenv

from video_processor import processor

# Load environment
load_dotenv()

# Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN", "8393335004:AAFFMz05CTr-i6OtGGltSTUAbFb9gY9St64")
MAX_SIZE = int(os.getenv("MAX_FILE_SIZE", "500000000"))  # 500MB

if not BOT_TOKEN:
    raise ValueError("Please set BOT_TOKEN in environment variables")

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# User session management
active_users = {}

# Commands
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 *Video Overlay Bot*\n\n"
        "Send me an MP4 video and I'll add an overlay to the beginning!\n\n"
        "*Commands:*\n"
        "/help - Show help\n"
        "/status - Bot status\n\n"
        "Max file size: 500MB",
        parse_mode=ParseMode.MARKDOWN
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Help*\n\n"
        "1. Send any MP4 video (max 500MB)\n"
        "2. Bot will process and add overlay\n"
        "3. Download processed video\n\n"
        "Processing time depends on video length.",
        parse_mode=ParseMode.MARKDOWN
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    overlay_status = "✅ Ready" if processor.overlay_path.exists() else "❌ Missing"
    
    await update.message.reply_text(
        f"📊 *Bot Status*\n\n"
        f"• Bot: ✅ Online\n"
        f"• Overlay: {overlay_status}\n"
        f"• Max Size: {MAX_SIZE//1024//1024}MB\n"
        f"• FFmpeg: ✅ Found\n"
        f"• Users: {len(active_users)}\n\n"
        f"Send a video to test!",
        parse_mode=ParseMode.MARKDOWN
    )

# Video handler
async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Check if user is already processing
    if user_id in active_users:
        await update.message.reply_text("⏳ Please wait, you already have a video in progress.")
        return
    
    # Check overlay
    if not processor.overlay_path.exists():
        await update.message.reply_text(
            "❌ *Overlay file missing!*\n\n"
            "Please contact the administrator.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Get video file
    if update.message.video:
        file_obj = update.message.video
        filename = "video.mp4"
    elif update.message.document:
        file_obj = update.message.document
        filename = file_obj.file_name or "video.mp4"
        
        # Check if MP4
        if not filename.lower().endswith('.mp4'):
            await update.message.reply_text("❌ Please send only MP4 files.")
            return
    else:
        return
    
    # Check size
    if file_obj.file_size > MAX_SIZE:
        await update.message.reply_text(f"❌ File too large! Max: {MAX_SIZE//1024//1024}MB")
        return
    
    # Mark user as active
    active_users[user_id] = True
    
    status_msg = None
    input_path = None
    
    try:
        # Send "typing" action
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action=ChatAction.TYPING
        )
        
        # Step 1: Download
        status_msg = await update.message.reply_text("📥 *Downloading video...*", parse_mode=ParseMode.MARKDOWN)
        
        input_path = processor.temp_dir / f"input_{user_id}_{file_obj.file_id}.mp4"
        output_filename = f"processed_{filename}"
        
        # Download file
        file = await context.bot.get_file(file_obj.file_id)
        await file.download_to_drive(input_path)
        
        # Step 2: Process
        await status_msg.edit_text("⚙️ *Processing video...*\nThis may take a moment.", parse_mode=ParseMode.MARKDOWN)
        
        output_path = processor.process_video(input_path, output_filename)
        
        if not output_path:
            await status_msg.edit_text(
                "❌ *Processing failed!*\n\n"
                "Please try a different video.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Step 3: Send back
        await status_msg.edit_text("📤 *Uploading processed video...*", parse_mode=ParseMode.MARKDOWN)
        
        # Get file size
        file_size = output_path.stat().st_size
        size_mb = file_size / (1024 * 1024)
        
        # Send video
        with open(output_path, 'rb') as f:
            await context.bot.send_video(
                chat_id=update.effective_chat.id,
                video=f,
                caption=f"✅ *Video Processed!*\nSize: {size_mb:.1f}MB",
                parse_mode=ParseMode.MARKDOWN,
                supports_streaming=True,
                read_timeout=120,
                write_timeout=120
            )
        
        # Cleanup
        await status_msg.delete()
        
        logger.info(f"Successfully processed video for user {user_id}")
        
    except asyncio.TimeoutError:
        logger.error(f"Timeout for user {user_id}")
        await update.message.reply_text(
            "⏳ *Processing timeout!*\n\n"
            "The video took too long to process.",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Error for user {user_id}: {e}")
        logger.error(traceback.format_exc())
        
        try:
            await update.message.reply_text(
                "❌ *An error occurred!*\n\n"
                "Please try again with a different video.",
                parse_mode=ParseMode.MARKDOWN
            )
        except:
            pass
    finally:
        # Cleanup
        active_users.pop(user_id, None)
        
        # Delete input file
        try:
            if input_path and input_path.exists():
                input_path.unlink()
        except:
            pass
        
        # Clean temp files
        try:
            processor.cleanup()
        except:
            pass

# Text handler
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if text.startswith('/'):
        await update.message.reply_text("❓ Unknown command. Use /help")
    else:
        await update.message.reply_text(
            "🎬 *Send me an MP4 video!*\n\n"
            "I'll add an overlay to the beginning of your video.",
            parse_mode=ParseMode.MARKDOWN
        )

# Error handler
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Bot error: {context.error}")
    logger.error(traceback.format_exc())

# Main function
def main():
    try:
        # Create application
        app = Application.builder().token(BOT_TOKEN).build()
        
        # Add handlers
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("help", help_cmd))
        app.add_handler(CommandHandler("status", status))
        
        # Media handlers
        app.add_handler(MessageHandler(filters.VIDEO, handle_video))
        app.add_handler(MessageHandler(filters.Document.ALL, handle_video))
        
        # Text handler
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
        
        # Error handler
        app.add_error_handler(error_handler)
        
        # Start bot
        logger.info("Starting bot...")
        print("="*50)
        print("🤖 TELEGRAM VIDEO OVERLAY BOT")
        print("="*50)
        print(f"Token: {BOT_TOKEN[:10]}...")
        print(f"Overlay: {'✅ Found' if processor.overlay_path.exists() else '❌ Missing'}")
        print(f"FFmpeg: {processor.ffmpeg_path}")
        print("="*50)
        print("Bot is running!")
        print("="*50)
        
        # Run polling
        app.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
            poll_interval=1.0,
            timeout=30
        )
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        print(f"❌ Error: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    main()
