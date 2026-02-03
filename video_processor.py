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
        self.base_dir = Path(__file__).parent
        self.downloads_dir = self.base_dir / "downloads"
        self.overlay_path = self.downloads_dir / "overlay" / "Family Home.mp4"
        self.output_dir = self.downloads_dir / "output"
        self.temp_dir = self.downloads_dir / "temp"
        
        # Create directories
        self.overlay_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(exist_ok=True)
        self.temp_dir.mkdir(exist_ok=True)
        
        # Heroku compatible FFmpeg path
        self.ffmpeg_path = self.get_ffmpeg_path()
        
        logger.info(f"FFmpeg path: {self.ffmpeg_path}")
        logger.info(f"Overlay exists: {self.overlay_path.exists()}")
    
    def get_ffmpeg_path(self):
        """Get FFmpeg path for Heroku"""
        # Try system FFmpeg first
        try:
            subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
            return 'ffmpeg'
        except:
            # Heroku buildpack FFmpeg
            heroku_path = '/app/vendor/ffmpeg/ffmpeg'
            if os.path.exists(heroku_path):
                return heroku_path
            else:
                # Local FFmpeg
                return 'ffmpeg'
    
    def run_ffmpeg(self, cmd):
        """Run FFmpeg command with error handling"""
        # Replace 'ffmpeg' with actual path
        if cmd[0] == 'ffmpeg':
            cmd[0] = self.ffmpeg_path
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
                env={**os.environ, 'PATH': os.environ.get('PATH', '')}
            )
            
            if result.returncode != 0:
                logger.error(f"FFmpeg error: {result.stderr[:500]}")
                return False, result.stderr
            
            return True, result.stdout
        except subprocess.TimeoutExpired:
            logger.error("FFmpeg timeout")
            return False, "Processing timeout"
        except Exception as e:
            logger.error(f"FFmpeg exception: {e}")
            return False, str(e)
    
    def get_video_duration(self, video_path):
        """Get duration of video"""
        try:
            cmd = [self.ffmpeg_path, '-v', 'error', '-show_entries', 
                   'format=duration', '-of', 'csv=p=0', str(video_path)]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            duration = result.stdout.strip()
            return float(duration) if duration else 0
        except Exception as e:
            logger.error(f"Error getting duration: {e}")
            return 0
    
    def get_video_dimensions(self, video_path):
        """Get width and height of video"""
        try:
            width_cmd = [self.ffmpeg_path, '-v', 'error', '-select_streams', 'v:0',
                        '-show_entries', 'stream=width', '-of', 'csv=p=0', str(video_path)]
            height_cmd = [self.ffmpeg_path, '-v', 'error', '-select_streams', 'v:0',
                         '-show_entries', 'stream=height', '-of', 'csv=p=0', str(video_path)]
            
            width = int(subprocess.run(width_cmd, capture_output=True, text=True, timeout=30).stdout.strip())
            height = int(subprocess.run(height_cmd, capture_output=True, text=True, timeout=30).stdout.strip())
            
            return width, height
        except Exception as e:
            logger.error(f"Error getting dimensions: {e}")
            return 1920, 1080  # Default fallback
    
    def clean_temp_files(self):
        """Clean temporary files"""
        try:
            for file in self.temp_dir.glob("*"):
                if file.is_file():
                    file.unlink()
        except Exception as e:
            logger.error(f"Error cleaning temp files: {e}")
    
    def process_video(self, input_path, output_filename):
        """Process video with overlay"""
        try:
            # Check if overlay exists
            if not self.overlay_path.exists():
                logger.error("Overlay file not found!")
                return None
            
            # Get video info
            width, height = self.get_video_dimensions(input_path)
            overlay_duration = self.get_video_duration(self.overlay_path)
            
            # Determine bar height based on video height
            if height <= 360:
                bar_height = 30
            elif height <= 720:
                bar_height = 45
            else:
                bar_height = 60
            
            overlay_y = height - bar_height
            
            # Clean temp directory
            self.clean_temp_files()
            
            # Step 1: Process first part with overlay
            part1_path = self.temp_dir / "part1.mp4"
            ffmpeg_cmd1 = [
                self.ffmpeg_path, '-y',
                '-i', str(input_path),
                '-i', str(self.overlay_path),
                '-filter_complex',
                f'[1:v]scale={width}:{bar_height},format=rgba[ovr];'
                f'[0:v][ovr]overlay=y={overlay_y}',
                '-t', str(overlay_duration),
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', '23',
                '-movflags', '+faststart',
                str(part1_path)
            ]
            
            logger.info("Processing first part with overlay...")
            success1, error1 = self.run_ffmpeg(ffmpeg_cmd1)
            if not success1:
                logger.error(f"Failed to process part 1: {error1}")
                return None
            
            # Step 2: Copy remaining part
            part2_path = self.temp_dir / "part2.mp4"
            ffmpeg_cmd2 = [
                self.ffmpeg_path, '-y',
                '-i', str(input_path),
                '-ss', str(overlay_duration),
                '-c', 'copy',
                '-movflags', '+faststart',
                str(part2_path)
            ]
            
            logger.info("Copying remaining part...")
            success2, error2 = self.run_ffmpeg(ffmpeg_cmd2)
            if not success2:
                logger.error(f"Failed to copy part 2: {error2}")
                return None
            
            # Step 3: Concatenate parts
            list_file = self.temp_dir / "list.txt"
            with open(list_file, 'w') as f:
                f.write(f"file '{part1_path}'\n")
                f.write(f"file '{part2_path}'\n")
            
            output_path = self.output_dir / output_filename
            ffmpeg_cmd3 = [
                self.ffmpeg_path, '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', str(list_file),
                '-c', 'copy',
                '-movflags', '+faststart',
                str(output_path)
            ]
            
            logger.info("Concatenating parts...")
            success3, error3 = self.run_ffmpeg(ffmpeg_cmd3)
            if not success3:
                logger.error(f"Failed to concatenate: {error3}")
                return None
            
            # Cleanup temp files (keep output)
            self.clean_temp_files()
            
            logger.info(f"Video processed successfully: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Processing error: {e}")
            return None

# Create global instance
video_processor = VideoProcessor()
