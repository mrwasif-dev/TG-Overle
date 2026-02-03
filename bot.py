import os
import logging
import asyncio
from pathlib import Path
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
from dotenv import load_dotenv

from video_processor import video_processor

# Load environment variables
load_dotenv()

# Bot Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN", "8393335004:AAFFMz05CTr-i6OtGGltSTUAbFb9gY9St64")
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", "500000000"))  # 500MB default
SUPPORTED_EXTENSIONS = {'.mp4', '.MP4', '.Mp4'}

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Store user tasks to prevent duplicate processing
user_tasks = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    user = update.effective_user
    welcome_text = """
🎬 *Welcome to Video Overlay Bot!*

I can add a custom overlay to the beginning of your videos.

*How to use:*
1️⃣ Send me any MP4 video file
2️⃣ I'll process it and add the overlay
3️⃣ Download the processed video

*Features:*
• Automatic overlay positioning
• Fast processing
• Preserves original quality after overlay
• Free to use!

*Note:* Only MP4 files up to 500MB are supported.
"""
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command handler"""
    help_text = """
*Available Commands:*
/start - Start the bot
/help - Show this help message
/status - Check bot status

*How to use:*
Just send me an MP4 video file and I'll process it automatically.

*Tips:*
• Make sure video is in MP4 format
• Max file size: 500MB
• Processing time depends on video length
"""
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Status command handler"""
    overlay_exists = video_processor.overlay_path.exists()
    overlay_status = "✅ Found" if overlay_exists else "❌ Not found"
    
    # Count files in output directory
    output_files = len(list(video_processor.output_dir.glob("*")))
    
    # Get FFmpeg status
    ffmpeg_status = "✅ Available"
    try:
        result = subprocess.run([video_processor.ffmpeg_path, '-version'], 
                              capture_output=True, text=True)
        if result.returncode != 0:
            ffmpeg_status = "❌ Not working"
    except:
        ffmpeg_status = "❌ Not found"
    
    status_text = f"""
*Bot Status:*
🤖 Bot: Online
{overlay_status} - Overlay file
🔧 {ffmpeg_status} - FFmpeg
📁 Processed videos: {output_files}
💾 Max file size: {MAX_FILE_SIZE//1024//1024}MB
🎥 Supported: MP4 files

*Instructions:*
Simply send any MP4 video to get started!
"""
    await update.message.reply_text(status_text, parse_mode=ParseMode.MARKDOWN)

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming video files"""
    user = update.effective_user
    user_id = user.id
    
    # Check if user already has a task in progress
    if user_id in user_tasks:
        await update.message.reply_text("⏳ You already have a video in progress. Please wait for it to complete.")
        return
    
    # Check if overlay exists
    if not video_processor.overlay_path.exists():
        await update.message.reply_text(
            "❌ *Overlay file not configured!*\n\n"
            "The overlay file is currently not available. "
            "Please try again later or contact support.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Get video file
    if update.message.video:
        video = update.message.video
        file_name = "video.mp4"
    elif update.message.document:
        video = update.message.document
        file_name = video.file_name or "video.mp4"
        
        # Check file extension
        file_ext = Path(file_name).suffix
        if file_ext not in SUPPORTED_EXTENSIONS:
            await update.message.reply_text(
                "❌ *Unsupported file format!*\n\n"
                "Please send only MP4 video files.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
    else:
        await update.message.reply_text("❌ Please send a video file.")
        return
    
    # Check file size
    if video.file_size > MAX_FILE_SIZE:
        await update.message.reply_text(
            f"❌ *File too large!*\n\n"
            f"Maximum file size: {MAX_FILE_SIZE//1024//1024}MB\n"
            f"Your file: {video.file_size//1024//1024}MB",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Send initial message
    processing_msg = await update.message.reply_text(
        "📥 *Downloading your video...*\n"
        "⏳ Please wait, this may take a moment.",
        parse_mode=ParseMode.MARKDOWN
    )
    
    try:
        # Mark user as processing
        user_tasks[user_id] = True
        
        # Download video
        input_path = video_processor.temp_dir / f"input_{user_id}_{video.file_id}.mp4"
        output_filename = f"processed_{Path(file_name).stem}.mp4"
        
        file = await context.bot.get_file(video.file_id)
        await file.download_to_drive(input_path)
        
        # Update status
        await processing_msg.edit_text(
            "⚙️ *Processing video...*\n"
            "Adding overlay to the beginning...\n"
            "⏱️ This may take a few minutes",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Process video
        output_path = video_processor.process_video(input_path, output_filename)
        
        if not output_path or not output_path.exists():
            await processing_msg.edit_text(
                "❌ *Processing failed!*\n\n"
                "There was an error processing your video. "
                "This could be due to:\n"
                "• Video format not supported\n"
                "• File too large\n"
                "• Server resources busy\n\n"
                "Please try again with a different video.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Get file size
        file_size = output_path.stat().st_size
        size_mb = file_size / (1024 * 1024)
        
        # Update status
        await processing_msg.edit_text(
            f"📤 *Uploading processed video...*\n"
            f"Size: {size_mb:.1f}MB\n"
            f"This may take a minute",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Send processed video
        with open(output_path, 'rb') as video_file:
            await context.bot.send_video(
                chat_id=update.effective_chat.id,
                video=video_file,
                caption=f"✅ *Video Processed Successfully!*\n\n"
                       f"• Original: {file_name}\n"
                       f"• Size: {size_mb:.1f}MB\n"
                       f"• Overlay added to beginning\n\n"
                       f"Thank you for using the bot! 🎬",
                parse_mode=ParseMode.MARKDOWN,
                supports_streaming=True,
                read_timeout=120,
                write_timeout=120,
                connect_timeout=120,
                pool_timeout=120
            )
        
        # Cleanup
        await processing_msg.delete()
        
        # Delete temporary files
        if input_path.exists():
            input_path.unlink()
        
        # Optionally delete output file after sending
        if output_path.exists():
            output_path.unlink()
        
        logger.info(f"Successfully processed video for user {user_id}")
        
    except asyncio.TimeoutError:
        await update.message.reply_text(
            "⏳ *Processing timeout!*\n\n"
            "The video took too long to process. "
            "Please try a shorter video or try again later.",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Error processing video for user {user_id}: {e}")
        await update.message.reply_text(
            "❌ *An error occurred!*\n\n"
            "Please try again or contact support if the problem persists.",
            parse_mode=ParseMode.MARKDOWN
        )
    finally:
        # Remove user from processing list
        user_tasks.pop(user_id, None)
        
        # Cleanup any remaining temp files
        video_processor.clean_temp_files()

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages"""
    text = update.message.text
    
    if text.startswith('/'):
        # Ignore unknown commands
        await update.message.reply_text(
            "❓ *Unknown command!*\n\n"
            "Use /help to see available commands.\n"
            "Or just send me an MP4 video to process! 🎬",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(
            "🎬 *Send me a video!*\n\n"
            "I'm a video processing bot. Just send me an MP4 video file "
            "and I'll add an overlay to the beginning.\n\n"
            "Use /help for more information.",
            parse_mode=ParseMode.MARKDOWN
        )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.error(f"Update {update} caused error {context.error}")
    
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ *An unexpected error occurred!*\n\n"
                "Please try again or send a different video.",
                parse_mode=ParseMode.MARKDOWN
            )
        except:
            pass

def main():
    """Start the bot"""
    try:
        # Check if bot token is available
        if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
            logger.error("Bot token not configured!")
            print("❌ ERROR: Bot token not configured!")
            print("Please set BOT_TOKEN in .env file or environment variables")
            return
        
        # Create application
        app = Application.builder().token(BOT_TOKEN).build()
        
        # Add handlers
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("status", status_command))
        
        # Handle videos and documents
        app.add_handler(MessageHandler(filters.VIDEO, handle_video))
        app.add_handler(MessageHandler(filters.Document.ALL, handle_video))
        
        # Handle text messages
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
        
        # Add error handler
        app.add_error_handler(error_handler)
        
        # Start bot
        logger.info("Starting bot...")
        print("\n" + "="*50)
        print("🎬 TELEGRAM VIDEO OVERLAY BOT")
        print("="*50)
        print(f"🤖 Bot Token: {BOT_TOKEN[:10]}...")
        print(f"🌐 Platform: Heroku")
        
        # Check overlay file
        if video_processor.overlay_path.exists():
            print(f"✅ Overlay found: {video_processor.overlay_path.name}")
        else:
            print(f"⚠️  Overlay NOT found: {video_processor.overlay_path}")
            print("   Place 'Family Home.mp4' in downloads/overlay/ folder")
        
        print(f"🔧 FFmpeg: {video_processor.ffmpeg_path}")
        print(f"💾 Max file size: {MAX_FILE_SIZE//1024//1024}MB")
        print("="*50)
        print("✅ Bot is starting on Heroku...")
        print("="*50 + "\n")
        
        # Heroku specific settings
        port = int(os.environ.get('PORT', 8443))
        app.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        print(f"\n❌ Error: {e}")
        print("Check your bot token and environment variables.")

if __name__ == '__main__':
    main()
