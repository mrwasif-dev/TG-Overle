import os
import subprocess
import logging
import traceback
from pathlib import Path

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class VideoProcessor:
    def __init__(self):
        # Find FFmpeg
        self.ffmpeg_path = self._find_ffmpeg()
        logger.info(f"FFmpeg path: {self.ffmpeg_path}")
        
        # Directories
        self.base_dir = Path(__file__).parent
        self.overlay_path = self.base_dir / "downloads" / "overlay" / "Family Home.mp4"
        self.output_dir = self.base_dir / "downloads" / "output"
        self.temp_dir = self.base_dir / "downloads" / "temp"
        
        # Create directories
        for d in [self.output_dir, self.temp_dir]:
            d.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Overlay exists: {self.overlay_path.exists()}")
    
    def _find_ffmpeg(self):
        """Find FFmpeg in common locations"""
        paths = [
            "/app/vendor/ffmpeg/ffmpeg",      # Heroku buildpack
            "/usr/local/bin/ffmpeg",
            "/usr/bin/ffmpeg",
            "ffmpeg"
        ]
        
        for path in paths:
            try:
                result = subprocess.run(
                    [path, "-version"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    logger.info(f"Found FFmpeg at: {path}")
                    return path
            except:
                continue
        
        # Try 'which' command
        try:
            result = subprocess.run(
                ["which", "ffmpeg"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                found_path = result.stdout.strip()
                logger.info(f"Found via which: {found_path}")
                return found_path
        except:
            pass
        
        logger.error("FFmpeg not found!")
        return "ffmpeg"
    
    def cleanup(self):
        """Clean temporary files"""
        try:
            if self.temp_dir.exists():
                for item in self.temp_dir.glob("*"):
                    if item.is_file():
                        try:
                            item.unlink()
                        except:
                            pass
                logger.debug("Cleaned temp directory")
        except Exception as e:
            logger.warning(f"Cleanup error: {e}")
    
    def get_video_info(self, video_path):
        """Get video duration"""
        try:
            if not video_path.exists():
                logger.error(f"Video file not found: {video_path}")
                return 0
            
            cmd = [
                self.ffmpeg_path, '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                str(video_path)
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
            return 5.0  # Default 5 seconds
        except Exception as e:
            logger.error(f"Duration error: {e}")
            return 5.0
    
    def get_video_dimensions(self, video_path):
        """Get video width and height"""
        try:
            if not video_path.exists():
                return 1280, 720
            
            cmd = [
                self.ffmpeg_path, '-v', 'error',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=width,height',
                '-of', 'csv=p=0',
                str(video_path)
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0 and result.stdout.strip():
                width, height = map(int, result.stdout.strip().split(','))
                return width, height
            return 1280, 720
        except Exception as e:
            logger.error(f"Dimensions error: {e}")
            return 1280, 720
    
    def run_ffmpeg(self, cmd):
        """Run FFmpeg command with logging"""
        logger.info(f"Running: {' '.join(cmd[:6])}...")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minutes
            )
            
            if result.returncode != 0:
                logger.error(f"FFmpeg error (code {result.returncode}):")
                if result.stderr:
                    error_lines = result.stderr.split('\n')
                    for line in error_lines[-10:]:  # Last 10 error lines
                        if line.strip():
                            logger.error(f"  {line}")
                return False, result.stderr
            
            return True, result.stdout
            
        except subprocess.TimeoutExpired:
            logger.error("FFmpeg timeout expired")
            return False, "Timeout"
        except Exception as e:
            logger.error(f"FFmpeg exception: {e}")
            return False, str(e)
    
    def process_video(self, input_path, output_filename):
        """Process video with overlay - SIMPLIFIED VERSION"""
        try:
            # Clean old files
            self.cleanup()
            
            # Check if files exist
            if not input_path.exists():
                logger.error(f"Input file not found: {input_path}")
                return None
            
            if not self.overlay_path.exists():
                logger.error(f"Overlay file not found: {self.overlay_path}")
                return None
            
            # Get video info
            video_width, video_height = self.get_video_dimensions(input_path)
            overlay_duration = self.get_video_info(self.overlay_path)
            
            logger.info(f"Video dimensions: {video_width}x{video_height}")
            logger.info(f"Overlay duration: {overlay_duration}s")
            
            # Calculate overlay height (10% of video height, min 30px)
            overlay_height = max(30, video_height // 10)
            overlay_y = video_height - overlay_height
            
            # Output path
            output_path = self.output_dir / output_filename
            
            # SIMPLE ONE-STEP PROCESSING
            cmd = [
                self.ffmpeg_path, '-y',
                '-i', str(input_path),          # Main video
                '-i', str(self.overlay_path),   # Overlay video
                '-filter_complex',
                f'[1:v]scale={video_width}:{overlay_height}[ov];'
                f'[0:v][ov]overlay=y={overlay_y}:enable=\'lte(t,{overlay_duration})\'[vout]',
                '-map', '[vout]',              # Mapped video output
                '-map', '0:a?',                # Original audio (if exists)
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', '23',
                '-c:a', 'aac',                 # Audio codec
                '-b:a', '128k',
                '-movflags', '+faststart',
                '-pix_fmt', 'yuv420p',
                '-shortest',                   # End when shortest stream ends
                str(output_path)
            ]
            
            # Run FFmpeg
            success, error = self.run_ffmpeg(cmd)
            
            if not success:
                logger.error(f"Processing failed: {error}")
                return None
            
            # Verify output
            if output_path.exists():
                file_size = output_path.stat().st_size
                if file_size > 10240:  # At least 10KB
                    logger.info(f"Success! Output: {output_path} ({file_size//1024}KB)")
                    
                    # Also verify with ffprobe
                    verify_cmd = [
                        self.ffmpeg_path, '-v', 'error',
                        '-i', str(output_path),
                        '-f', 'null', '-'
                    ]
                    verify_result = subprocess.run(
                        verify_cmd,
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    
                    if verify_result.returncode == 0:
                        return output_path
                    else:
                        logger.error(f"Output verification failed: {verify_result.stderr}")
                        return None
                else:
                    logger.error(f"Output file too small: {file_size} bytes")
                    return None
            else:
                logger.error("Output file not created")
                return None
                
        except Exception as e:
            logger.error(f"Processing error: {e}")
            logger.error(traceback.format_exc())
            return None

# Global instance
processor = VideoProcessor()
