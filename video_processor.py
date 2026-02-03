
import os
import subprocess
import logging
import tempfile
import shutil
from pathlib import Path

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class VideoProcessor:
    def __init__(self):
        # Use Heroku's ephemeral storage
        self.base_dir = Path("/tmp") if "HEROKU" in os.environ else Path(__file__).parent
        
        # Create directory structure
        self.overlay_path = self.base_dir / "downloads" / "overlay" / "Family Home.mp4"
        self.output_dir = self.base_dir / "downloads" / "output"
        self.temp_dir = self.base_dir / "downloads" / "temp"
        
        # Create directories
        for dir_path in [self.overlay_path.parent, self.output_dir, self.temp_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)
        
        # Check for overlay in app directory (for Heroku)
        if not self.overlay_path.exists():
            app_overlay = Path(__file__).parent / "downloads" / "overlay" / "Family Home.mp4"
            if app_overlay.exists():
                # Copy overlay to tmp directory
                shutil.copy2(app_overlay, self.overlay_path)
                logger.info(f"Copied overlay to {self.overlay_path}")
        
        logger.info(f"Overlay path: {self.overlay_path}")
        logger.info(f"Overlay exists: {self.overlay_path.exists()}")
    
    def run_command(self, cmd):
        """Run command with error handling"""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minutes timeout
            )
            return result.returncode == 0, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return False, "", "Command timeout"
        except Exception as e:
            return False, "", str(e)
    
    def get_video_info(self, video_path):
        """Get video duration and dimensions"""
        try:
            # Get duration
            duration_cmd = [
                'ffprobe', '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                str(video_path)
            ]
            
            success, stdout, stderr = self.run_command(duration_cmd)
            duration = float(stdout.strip()) if success and stdout else 0
            
            # Get dimensions
            dimensions_cmd = [
                'ffprobe', '-v', 'error',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=width,height',
                '-of', 'csv=p=0',
                str(video_path)
            ]
            
            success, stdout, stderr = self.run_command(dimensions_cmd)
            if success and stdout:
                width, height = map(int, stdout.strip().split(','))
            else:
                width, height = 1920, 1080  # Default
            
            return duration, width, height
        except Exception as e:
            logger.error(f"Error getting video info: {e}")
            return 0, 1920, 1080
    
    def cleanup(self):
        """Clean up temporary files"""
        try:
            if self.temp_dir.exists():
                for item in self.temp_dir.iterdir():
                    if item.is_file():
                        item.unlink()
        except Exception as e:
            logger.warning(f"Error cleaning temp files: {e}")
    
    def process_video(self, input_path, output_filename):
        """Main video processing function"""
        self.cleanup()  # Clean previous temp files
        
        try:
            # Get video info
            overlay_duration, width, height = self.get_video_info(self.overlay_path)
            _, video_width, video_height = self.get_video_info(input_path)
            
            # Use video dimensions
            width, height = video_width, video_height
            
            # Calculate overlay position
            if height <= 360:
                bar_height = 30
            elif height <= 720:
                bar_height = 45
            else:
                bar_height = 60
            
            overlay_y = height - bar_height
            
            # Step 1: Process first part with overlay
            part1 = self.temp_dir / "part1.mp4"
            cmd1 = [
                'ffmpeg', '-y',
                '-i', str(input_path),
                '-i', str(self.overlay_path),
                '-filter_complex',
                f'[1:v]scale={width}:{bar_height}[scaled];'
                f'[0:v][scaled]overlay=y={overlay_y}:enable=\'between(t,0,{overlay_duration})\'',
                '-t', str(overlay_duration),
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', '23',
                '-movflags', '+faststart',
                str(part1)
            ]
            
            logger.info("Processing overlay part...")
            success, stdout, stderr = self.run_command(cmd1)
            if not success:
                logger.error(f"Step 1 failed: {stderr}")
                return None
            
            # Step 2: Get remaining part
            part2 = self.temp_dir / "part2.mp4"
            cmd2 = [
                'ffmpeg', '-y',
                '-i', str(input_path),
                '-ss', str(overlay_duration),
                '-c', 'copy',
                '-movflags', '+faststart',
                str(part2)
            ]
            
            logger.info("Getting remaining part...")
            success, stdout, stderr = self.run_command(cmd2)
            if not success:
                logger.error(f"Step 2 failed: {stderr}")
                return None
            
            # Step 3: Concatenate
            concat_list = self.temp_dir / "list.txt"
            with open(concat_list, 'w') as f:
                f.write(f"file '{part1}'\n")
                f.write(f"file '{part2}'\n")
            
            output_path = self.output_dir / output_filename
            cmd3 = [
                'ffmpeg', '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', str(concat_list),
                '-c', 'copy',
                '-movflags', '+faststart',
                str(output_path)
            ]
            
            logger.info("Concatenating parts...")
            success, stdout, stderr = self.run_command(cmd3)
            if not success:
                logger.error(f"Step 3 failed: {stderr}")
                return None
            
            logger.info(f"Video processed: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Processing error: {e}")
            return None
        finally:
            # Don't clean temp files immediately (needed for upload)
            pass

# Global instance
processor = VideoProcessor()
