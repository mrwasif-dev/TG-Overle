import os
import subprocess
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class VideoProcessor:
    def __init__(self):
        # FFmpeg path for Heroku
        self.ffmpeg_path = self._get_ffmpeg_path()
        logger.info(f"Using FFmpeg at: {self.ffmpeg_path}")
        
        # Directories
        self.base_dir = Path(__file__).parent
        self.overlay_path = self.base_dir / "downloads" / "overlay" / "Family Home.mp4"
        self.output_dir = self.base_dir / "downloads" / "output"
        self.temp_dir = self.base_dir / "downloads" / "temp"
        
        # Create dirs
        for d in [self.output_dir, self.temp_dir]:
            d.mkdir(exist_ok=True)
    
    def _get_ffmpeg_path(self):
        """Get FFmpeg path for Heroku"""
        # Try Heroku buildpack path first
        heroku_path = "/app/vendor/ffmpeg/ffmpeg"
        if os.path.exists(heroku_path):
            return heroku_path
        
        # Try system FFmpeg
        try:
            subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
            return 'ffmpeg'
        except:
            # Last resort: try /usr/bin/ffmpeg
            return '/usr/bin/ffmpeg'
    
    def run_ffmpeg(self, cmd):
        """Run FFmpeg command"""
        # Replace ffmpeg with correct path
        if cmd[0] == 'ffmpeg':
            cmd[0] = self.ffmpeg_path
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )
            return result.returncode == 0, result.stdout, result.stderr
        except Exception as e:
            return False, "", str(e)
    
    def get_video_info(self, video_path):
        """Get video duration and dimensions"""
        try:
            # Duration
            cmd = [self.ffmpeg_path, '-v', 'error', 
                  '-show_entries', 'format=duration',
                  '-of', 'default=noprint_wrappers=1:nokey=1',
                  str(video_path)]
            
            success, stdout, stderr = self.run_ffmpeg(cmd)
            duration = float(stdout.strip()) if success else 0
            
            # Dimensions
            cmd = [self.ffmpeg_path, '-v', 'error',
                  '-select_streams', 'v:0',
                  '-show_entries', 'stream=width,height',
                  '-of', 'csv=p=0',
                  str(video_path)]
            
            success, stdout, stderr = self.run_ffmpeg(cmd)
            if success and stdout:
                width, height = map(int, stdout.strip().split(','))
            else:
                width, height = 1920, 1080
            
            return duration, width, height
        except Exception as e:
            logger.error(f"Video info error: {e}")
            return 0, 1920, 1080
    
    def process_video(self, input_path, output_filename):
        """Process video with overlay"""
        try:
            # Get overlay info
            overlay_dur, ov_width, ov_height = self.get_video_info(self.overlay_path)
            _, width, height = self.get_video_info(input_path)
            
            # Calculate bar height
            if height <= 360:
                bar_height = 30
            elif height <= 720:
                bar_height = 45
            else:
                bar_height = 60
            
            overlay_y = height - bar_height
            
            # Step 1: Process overlay part
            part1 = self.temp_dir / "part1.mp4"
            cmd1 = [
                self.ffmpeg_path, '-y',
                '-i', str(input_path),
                '-i', str(self.overlay_path),
                '-filter_complex',
                f'[1:v]scale={width}:{bar_height}[scaled];'
                f'[0:v][scaled]overlay=y={overlay_y}',
                '-t', str(overlay_dur),
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', '23',
                str(part1)
            ]
            
            logger.info("Processing overlay...")
            success, stdout, stderr = self.run_ffmpeg(cmd1)
            if not success:
                logger.error(f"Overlay failed: {stderr}")
                return None
            
            # Step 2: Remaining part
            part2 = self.temp_dir / "part2.mp4"
            cmd2 = [
                self.ffmpeg_path, '-y',
                '-i', str(input_path),
                '-ss', str(overlay_dur),
                '-c', 'copy',
                str(part2)
            ]
            
            logger.info("Getting remaining part...")
            success, stdout, stderr = self.run_ffmpeg(cmd2)
            if not success:
                logger.error(f"Copy failed: {stderr}")
                return None
            
            # Step 3: Concatenate
            list_file = self.temp_dir / "list.txt"
            with open(list_file, 'w') as f:
                f.write(f"file '{part1}'\n")
                f.write(f"file '{part2}'\n")
            
            output_path = self.output_dir / output_filename
            cmd3 = [
                self.ffmpeg_path, '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', str(list_file),
                '-c', 'copy',
                str(output_path)
            ]
            
            logger.info("Concatenating...")
            success, stdout, stderr = self.run_ffmpeg(cmd3)
            if not success:
                logger.error(f"Concat failed: {stderr}")
                return None
            
            # Cleanup temp files (keep part1, part2 for debugging)
            # list_file.unlink()
            
            return output_path
            
        except Exception as e:
            logger.error(f"Process error: {e}")
            return None

# Global instance
processor = VideoProcessor()
