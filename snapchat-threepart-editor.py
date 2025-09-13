#!/usr/bin/env python3
"""
Snapchat Style 3-Image Video Editor with Google Sheets Integration and Random Audio
Creates 15-second videos by combining 3 individual 5-second videos with overlay text
Automatically selects overlay text from Google Sheets based on order (1,2,3) and image type
Each segment is 5 seconds with black text overlay bars at random vertical positions
Automatically crops images to 9:16 aspect ratio
Processes sets of 3 images in order and combines them into single 15-second videos
Adds random .mp3 audio from tiktok-audio folder, trimmed to 15 seconds
"""

import os
import sys
import subprocess
import shutil
import textwrap
import random
import re
from pathlib import Path
import tempfile

# Google Sheets imports
try:
    import gspread
    from google.oauth2.service_account import Credentials
    GOOGLE_SHEETS_AVAILABLE = True
except ImportError:
    GOOGLE_SHEETS_AVAILABLE = False

class SnapchatEditor:
    def __init__(self):
        self.script_dir = Path(__file__).parent
        self.input_dir = self.script_dir / "input-images"
        self.output_dir = self.script_dir / "output-video"
        self.temp_dir = self.script_dir / "temp-videos"  # For individual 5s videos
        self.audio_dir = self.script_dir / "tiktok-audio"
        self.credentials_path = self.script_dir / "assets" / "credentials.json"
        
        # Google Sheets configuration
        self.sheet_id = "11o5V4Esk--KfUeBAEVa_gBZtzWfSRK3zCrifxNWdva4"  # Default sheet ID
        self.worksheet_name = "SnapchatThreePart"
        self.gc = None
        self.worksheet = None
        
        # Video settings
        self.segment_duration = 3.0  # Each segment: 5 seconds
        self.total_duration = 9.0   # Total video: 15 seconds (3 segments)
        self.fps = 30
        
        # Supported file types
        self.image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp'}
        self.audio_extensions = {'.mp3'}
        
        # Text overlay settings
        self.font_size = 20
        self.text_padding = 10
        self.bar_opacity = 0.7
        
        # Random position settings
        self.min_position_percent = 45
        self.max_position_percent = 70
        
        # Updated headers for new format with order
        self.expected_headers = ['used?', 'mentions toffee?', 'type', 'order', 'overlay text']
        
        # Valid types mapping (filename -> sheet format)
        self.valid_types = {
            'crying': 'Crying',
            'confused': 'Confused', 
            'shocked': 'Shocked',
            'tongue': 'Tongue',
            'goofy': 'Goofy'
        }
    
    def find_audio_files(self):
        """Find all audio files in the audio directory"""
        if not self.audio_dir.exists():
            return []
            
        audio_files = []
        for file_path in self.audio_dir.iterdir():
            if file_path.suffix.lower() in self.audio_extensions:
                audio_files.append(file_path)
        
        return audio_files
    
    def select_random_audio(self):
        """Select a random audio file from the audio directory"""
        audio_files = self.find_audio_files()
        
        if not audio_files:
            print(f"⚠️  No audio files found in {self.audio_dir}")
            return None
        
        selected_audio = random.choice(audio_files)
        print(f"🎵 Selected random audio: {selected_audio.name}")
        return selected_audio
    
    def find_image_by_type(self, image_type):
        """Find an image file that matches the specified type"""
        if not self.input_dir.exists():
            return None
            
        # Convert sheet type back to filename format
        type_mapping = {v: k for k, v in self.valid_types.items()}
        filename_type = type_mapping.get(image_type)
        
        if not filename_type:
            print(f"❌ Unknown image type: {image_type}")
            return None
        
        # Look for files containing the type in their name
        for file_path in self.input_dir.iterdir():
            if (file_path.suffix.lower() in self.image_extensions and 
                filename_type.lower() in file_path.name.lower()):
                print(f"✅ Found image for type '{image_type}': {file_path.name}")
                return file_path
        
        print(f"❌ No image found for type '{image_type}' (looking for '{filename_type}' in filename)")
        return None
    
    def check_dependencies(self):
        """Check if FFmpeg and Google Sheets libraries are installed"""
        # Check FFmpeg
        if not shutil.which('ffmpeg'):
            print("❌ FFmpeg is not installed!")
            print("Please install FFmpeg:")
            print("  Mac: brew install ffmpeg")
            print("  Linux: sudo apt-get install ffmpeg") 
            print("  Windows: Download from ffmpeg.org")
            return False
        print("✅ FFmpeg found")
        
        # Check Google Sheets libraries
        if not GOOGLE_SHEETS_AVAILABLE:
            print("❌ Google Sheets libraries not installed!")
            print("Please install required packages:")
            print("  pip install gspread google-auth")
            return False
        print("✅ Google Sheets libraries found")
        
        return True
    
    def setup_google_sheets(self):
        """Set up Google Sheets connection"""
        if not self.credentials_path.exists():
            print(f"❌ Credentials file not found: {self.credentials_path}")
            print("Please:")
            print("1. Go to Google Cloud Console")
            print("2. Create a service account")
            print("3. Download the JSON credentials file")
            print("4. Save it as 'credentials.json' in the assets folder")
            return False
        
        try:
            scopes = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
            
            credentials = Credentials.from_service_account_file(
                str(self.credentials_path), 
                scopes=scopes
            )
            
            self.gc = gspread.authorize(credentials)
            print("✅ Google Sheets authentication successful")
            return True
            
        except Exception as e:
            print(f"❌ Error setting up Google Sheets: {str(e)}")
            return False
    
    def connect_to_sheet(self):
        """Connect to the specific Google Sheet"""
        try:
            spreadsheet = self.gc.open_by_key(self.sheet_id)
            print(f"✅ Connected to spreadsheet: {spreadsheet.title}")
            
            try:
                self.worksheet = spreadsheet.worksheet(self.worksheet_name)
            except:
                self.worksheet = spreadsheet.get_worksheet(0)
                self.worksheet_name = self.worksheet.title
            
            print(f"✅ Using worksheet: {self.worksheet_name}")
            return True
            
        except Exception as e:
            print(f"❌ Error connecting to Google Sheet: {str(e)}")
            return False
    
    def check_sheet_format(self):
        """Check if Google Sheet has correct format"""
        try:
            records = self.worksheet.get_all_records()
            
            if not records:
                print("❌ Google Sheet is empty or has no data rows")
                return False
            
            headers = list(records[0].keys())
            normalized_headers = [h.strip().lower() for h in headers]
            expected_normalized = [h.strip().lower() for h in self.expected_headers]
            
            if set(normalized_headers) != set(expected_normalized):
                print(f"❌ Google Sheet headers incorrect.")
                print(f"Expected: {self.expected_headers}")
                print(f"Found: {headers}")
                return False
            
            print("✅ Google Sheet format validated")
            print(f"📊 Found {len(records)} data rows")
            return True
            
        except Exception as e:
            print(f"❌ Error checking sheet format: {str(e)}")
            return False
    
    def get_next_video_sequence_from_sheet(self):
        """Get next unused sequence of 3 videos (orders 1, 2, 3) from Google Sheets"""
        try:
            records = self.worksheet.get_all_records()
            
            # Group unused records by a sequence identifier
            # We need to find sets of 3 consecutive unused records with orders 1, 2, 3
            unused_records = []
            for i, record in enumerate(records):
                record_used = str(record.get('used?', '')).strip().upper()
                if record_used == 'FALSE':
                    unused_records.append({
                        'row_index': i,
                        'row_number': i + 2,  # Sheet row (1-indexed + header)
                        'order': str(record.get('order', '')).strip(),
                        'type': str(record.get('type', '')).strip(),
                        'overlay_text': str(record.get('overlay text', '')).strip(),
                        'mentions_toffee': str(record.get('mentions toffee?', '')).strip()
                    })
            
            print(f"📊 Found {len(unused_records)} unused records total")
            
            # Look for a complete sequence (orders 1, 2, 3)
            # We'll take the first available set of consecutive unused records
            for start_idx in range(len(unused_records) - 2):
                sequence = unused_records[start_idx:start_idx + 3]
                
                # Check if we have orders 1, 2, 3
                orders = [record['order'] for record in sequence]
                if set(orders) == {'1', '2', '3'}:
                    # Sort by order to ensure correct sequence
                    sequence.sort(key=lambda x: int(x['order']))
                    
                    print(f"✅ Found complete video sequence:")
                    for i, record in enumerate(sequence, 1):
                        print(f"  {i}. Order {record['order']}: {record['type']} - \"{record['overlay_text'][:50]}{'...' if len(record['overlay_text']) > 50 else ''}\"")
                    
                    return sequence
            
            print("❌ No complete unused sequence (orders 1, 2, 3) found in Google Sheets")
            return None
            
        except Exception as e:
            print(f"❌ Error accessing Google Sheets data: {str(e)}")
            return None
    
    def mark_sequence_as_used(self, sequence):
        """Mark a sequence of 3 records as used in Google Sheets"""
        try:
            for record in sequence:
                row_number = record['row_number']
                self.worksheet.update_cell(row_number, 1, 'TRUE')  # Column 1 is 'used?'
                print(f"📋 Marked row {row_number} as used (Order {record['order']}: {record['type']})")
            
            print("✅ All 3 records marked as used in Google Sheets")
            return True
            
        except Exception as e:
            print(f"❌ Error updating Google Sheets: {str(e)}")
            return False
    
    def get_system_font_path(self):
        """Get a suitable font path, preferring custom font first"""
        custom_font_path = self.script_dir / "assets" / "HelveticaNeueRoman.otf"
        if custom_font_path.exists():
            return str(custom_font_path)
        
        import platform
        system = platform.system()
        
        if system == "Darwin":  # macOS
            font_paths = [
                "/System/Library/Fonts/Helvetica.ttc",
                "/System/Library/Fonts/Avenir.ttc",
                "/Library/Fonts/Arial.ttf"
            ]
        elif system == "Windows":
            font_paths = [
                "C:/Windows/Fonts/arial.ttf",
                "C:/Windows/Fonts/Arial.ttf",
                "C:/Windows/Fonts/calibri.ttf"
            ]
        else:  # Linux
            font_paths = [
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
            ]
        
        for font in font_paths:
            if Path(font).exists():
                return font
        return None
    
    def get_image_dimensions(self, image_path):
        """Get image dimensions using FFprobe"""
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height',
            '-of', 'csv=s=x:p=0',
            str(image_path)
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            width, height = map(int, result.stdout.strip().split('x'))
            return width, height
        except:
            return 1920, 1080  # Default fallback
    
    def calculate_crop_for_9_16(self, img_width, img_height):
        """Calculate crop parameters for 9:16 aspect ratio"""
        target_aspect = 9.0 / 16.0  # 0.5625
        current_aspect = img_width / img_height
        
        if current_aspect > target_aspect:
            # Image is too wide, crop width
            new_width = int(img_height * target_aspect)
            new_height = img_height
            crop_x = (img_width - new_width) // 2
            crop_y = 0
        else:
            # Image is too tall, crop height
            new_width = img_width
            new_height = int(img_width / target_aspect)
            crop_x = 0
            crop_y = (img_height - new_height) // 2
        
        return new_width, new_height, crop_x, crop_y
    
    def calculate_random_bar_position(self, video_height, bar_height):
        """Calculate random vertical position for the bar"""
        min_y = int(video_height * (self.min_position_percent / 100))
        max_y = int(video_height * (self.max_position_percent / 100))
        
        max_y = min(max_y, video_height - bar_height)
        min_y = max(min_y, 0)
        
        if min_y > max_y:
            min_y = max_y
        
        random_y = random.randint(min_y, max_y)
        return random_y
    
    def wrap_text_for_width(self, text, image_width):
        """Wrap text to fit within the image width"""
        available_width = image_width - 10
        char_width = self.font_size * 0.6
        chars_per_line = max(30, int(available_width / char_width))
        
        wrapped = textwrap.fill(text, width=chars_per_line, break_long_words=False, break_on_hyphens=False)
        line_count = len(wrapped.split('\n'))
        
        return wrapped, line_count
    
    def create_single_video_segment(self, image_path, overlay_text, output_path, segment_number):
        """Create a single 5-second video segment without audio"""
        print(f"🎬 Creating segment {segment_number}: {output_path.name}")
        
        # Get original image dimensions
        orig_width, orig_height = self.get_image_dimensions(image_path)
        print(f"📐 Original image dimensions: {orig_width}x{orig_height}")
        
        # Calculate crop for 9:16 aspect ratio
        crop_width, crop_height, crop_x, crop_y = self.calculate_crop_for_9_16(orig_width, orig_height)
        print(f"📐 Cropped dimensions: {crop_width}x{crop_height}")
        
        # Wrap text and calculate bar dimensions
        wrapped_text, line_count = self.wrap_text_for_width(overlay_text, crop_width)
        text_height = line_count * self.font_size
        bar_height = text_height + (self.text_padding * 2)
        
        # Calculate random bar position
        bar_y_position = self.calculate_random_bar_position(crop_height, bar_height)
        position_percent = (bar_y_position / crop_height) * 100
        print(f"🎲 Random bar position: {bar_y_position}px ({position_percent:.1f}%)")
        
        # Create temporary text file
        text_file = self.temp_dir / f"overlay_text_segment_{segment_number}.txt"
        with open(text_file, 'w', encoding='utf-8') as f:
            f.write(wrapped_text)
        
        # Get font
        font_param = ''
        system_font = self.get_system_font_path()
        if system_font:
            font_param = f":fontfile='{system_font}'"
        
        # Create filter for black overlay with cropping (NO AUDIO)
        filter_complex = (
            f"[0:v]crop={crop_width}:{crop_height}:{crop_x}:{crop_y}[cropped];"
            f"[cropped]drawbox="
            f"x=0:y={bar_y_position}:w={crop_width}:h={bar_height}:"
            f"color=black@{self.bar_opacity}:t=fill[with_bar];"
            f"[with_bar]drawtext="
            f"textfile='{str(text_file)}'"
            f"{font_param}"
            f":fontsize={self.font_size}"
            f":fontcolor=white"
            f":x=(w-text_w)/2"
            f":y={bar_y_position}+({bar_height}-text_h)/2"
            f":text_align=C"
        )
        
        cmd = [
            'ffmpeg',
            '-loop', '1',
            '-i', str(image_path),
            '-filter_complex', filter_complex,
            '-t', str(self.segment_duration),  # 5 seconds
            '-r', str(self.fps),
            '-c:v', 'libx264',
            '-preset', 'medium',
            '-crf', '23',
            '-pix_fmt', 'yuv420p',
            '-y',
            str(output_path)
        ]
        
        try:
            print(f"🔄 Processing segment {segment_number} ({self.segment_duration}s)...")
            
            process = subprocess.run(cmd, capture_output=True, text=True)
            
            # Clean up text file
            if text_file.exists():
                text_file.unlink()
            
            if process.returncode == 0:
                print(f"✅ Segment {segment_number} created successfully")
                return True
            else:
                print(f"❌ FFmpeg error for segment {segment_number}")
                print("Error details:")
                for line in process.stderr.split('\n')[-5:]:
                    if line.strip():
                        print(f"  {line.strip()}")
                return False
                
        except Exception as e:
            print(f"❌ Error creating segment {segment_number}: {str(e)}")
            if text_file.exists():
                text_file.unlink()
            return False
    
    def concatenate_videos_with_audio(self, video_paths, output_path, audio_file=None):
        """Concatenate 3 videos and add audio to create final 15-second video"""
        print(f"🔗 Concatenating {len(video_paths)} videos into final 15-second video...")
        
        # Create concat file for FFmpeg
        concat_file = self.temp_dir / "concat_list.txt"
        with open(concat_file, 'w') as f:
            for video_path in video_paths:
                f.write(f"file '{video_path.absolute()}'\n")
        
        cmd = [
            'ffmpeg',
            '-f', 'concat',
            '-safe', '0',
            '-i', str(concat_file),
        ]
        
        # Add audio input if available
        if audio_file:
            cmd.extend(['-i', str(audio_file)])
            print(f"🎵 Adding audio: {audio_file.name}")
        
        # Video processing
        cmd.extend([
            '-c:v', 'copy',  # Copy video without re-encoding for speed
        ])
        
        # Audio processing if available
        if audio_file:
            cmd.extend([
                '-af', f'volume=-10dB',  # Reduce volume
                '-c:a', 'aac',
                '-b:a', '128k',
                '-ac', '2',
                '-ar', '44100',
                '-t', str(self.total_duration),  # Trim audio to 15 seconds
            ])
        
        cmd.extend([
            '-movflags', '+faststart',
            '-y',
            str(output_path)
        ])
        
        try:
            print(f"🔄 Concatenating videos and adding audio...")
            
            process = subprocess.run(cmd, capture_output=True, text=True)
            
            # Clean up concat file
            if concat_file.exists():
                concat_file.unlink()
            
            if process.returncode == 0:
                print(f"✅ Final video created successfully: {output_path.name}")
                print(f"📹 Duration: {self.total_duration}s ({len(video_paths)} segments of {self.segment_duration}s each)")
                if audio_file:
                    print(f"🎵 Audio: {audio_file.name} (trimmed to {self.total_duration}s)")
                return True
            else:
                print(f"❌ FFmpeg concatenation error")
                print("Error details:")
                for line in process.stderr.split('\n')[-10:]:
                    if line.strip():
                        print(f"  {line.strip()}")
                return False
                
        except Exception as e:
            print(f"❌ Error concatenating videos: {str(e)}")
            if concat_file.exists():
                concat_file.unlink()
            return False
    
    def generate_output_filename(self, sequence_number):
        """Generate output filename for the sequence"""
        return self.output_dir / f"sequence-{sequence_number:03d}-video.mp4"
    
    def run(self):
        """Main execution function"""
        print("📱 Snapchat Style 3-Image Video Editor with Google Sheets Integration")
        print("=" * 80)
        
        # Check dependencies
        if not self.check_dependencies():
            return False
        
        # Set up Google Sheets connection
        if not self.setup_google_sheets():
            return False
        
        if not self.connect_to_sheet():
            return False
        
        if not self.check_sheet_format():
            return False
        
        # Ensure directories exist
        self.input_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        (self.script_dir / "assets").mkdir(parents=True, exist_ok=True)
        
        print(f"✅ Using Google Sheet: {self.worksheet.spreadsheet.title}")
        print(f"📄 Worksheet: {self.worksheet_name}")
        
        # Check for audio files
        audio_files = self.find_audio_files()
        if audio_files:
            print(f"✅ Found {len(audio_files)} audio file(s)")
        else:
            print(f"⚠️  No audio files found - videos will be created without audio")
        
        # Check for image files
        print(f"\n🏷️  Valid image types: {', '.join(self.valid_types.keys())}")
        missing_types = []
        for filename_type, sheet_type in self.valid_types.items():
            if not self.find_image_by_type(sheet_type):
                missing_types.append(filename_type)
        
        if missing_types:
            print(f"❌ Missing image types: {', '.join(missing_types)}")
            print("Please ensure you have images for all types in the input-images folder")
            return False
        
        print(f"\n⚙️  Video Settings:")
        print(f"   • Segment duration: {self.segment_duration}s (3 segments)")
        print(f"   • Total duration: {self.total_duration}s")
        print(f"   • Frame rate: {self.fps} fps")
        print(f"   • Aspect ratio: 9:16 (cropped)")
        print(f"   • Text source: Google Sheets (orders 1, 2, 3)")
        print(f"   • Audio source: {'Random from tiktok-audio' if audio_files else 'None'}")
        
        # Process video sequences
        successful_videos = 0
        failed_videos = 0
        sequence_number = 1
        
        while True:
            print(f"\n" + "="*80)
            print(f"🔄 Processing Video Sequence #{sequence_number}")
            print("="*80)
            
            # Get next sequence from Google Sheets
            sequence = self.get_next_video_sequence_from_sheet()
            if not sequence:
                print(f"⏹️  No more complete sequences available. Stopping.")
                break
            
            # Generate output filename
            final_output_path = self.generate_output_filename(sequence_number)
            print(f"📁 Final output: {final_output_path.name}")
            
            # Create individual segments
            segment_paths = []
            all_segments_created = True
            
            for i, record in enumerate(sequence, 1):
                print(f"\n📸 Creating segment {i}/3 (Order {record['order']}):")
                print(f"   Type: {record['type']}")
                print(f"   Text: {record['overlay_text'][:80]}{'...' if len(record['overlay_text']) > 80 else ''}")
                
                # Find corresponding image
                image_path = self.find_image_by_type(record['type'])
                if not image_path:
                    print(f"❌ No image found for type: {record['type']}")
                    all_segments_created = False
                    break
                
                # Create segment output path
                segment_output = self.temp_dir / f"segment_{sequence_number}_{i}.mp4"
                
                # Create the segment
                if self.create_single_video_segment(image_path, record['overlay_text'], segment_output, i):
                    segment_paths.append(segment_output)
                else:
                    print(f"❌ Failed to create segment {i}")
                    all_segments_created = False
                    break
            
            if not all_segments_created:
                print(f"❌ Failed to create complete sequence #{sequence_number}")
                # Clean up any created segments
                for path in segment_paths:
                    if path.exists():
                        path.unlink()
                failed_videos += 1
                sequence_number += 1
                continue
            
            # Select random audio for final video
            audio_file = self.select_random_audio() if audio_files else None
            
            # Concatenate segments and add audio
            if self.concatenate_videos_with_audio(segment_paths, final_output_path, audio_file):
                # Mark sequence as used in Google Sheets
                if self.mark_sequence_as_used(sequence):
                    print(f"\n🎉 SUCCESS for sequence #{sequence_number}!")
                    print(f"✅ Final video: {final_output_path.name}")
                    print(f"✨ Features applied:")
                    print(f"   • 3 segments of {self.segment_duration}s each")
                    print(f"   • Total duration: {self.total_duration}s")
                    print(f"   • Each segment cropped to 9:16 aspect ratio")
                    print(f"   • Black bar overlays at random positions")
                    print(f"   • White centered text from Google Sheets")
                    if audio_file:
                        print(f"   • Random TikTok audio (trimmed to {self.total_duration}s)")
                    print(f"   • Google Sheets automatically updated (3 rows marked as used)")
                    successful_videos += 1
                else:
                    print(f"⚠️  Video created but failed to update Google Sheets")
                    successful_videos += 1
            else:
                print(f"❌ Failed to create final video for sequence #{sequence_number}")
                failed_videos += 1
            
            # Clean up temporary segment files
            for path in segment_paths:
                if path.exists():
                    path.unlink()
            
            sequence_number += 1
            
            # Safety limit to prevent infinite loops
            if sequence_number > 100:
                print("⚠️  Reached safety limit of 100 sequences")
                break
        
        # Summary
        print(f"\n" + "="*80)
        print(f"📊 PROCESSING SUMMARY")
        print(f"=" * 80)
        print(f"✅ Successful videos: {successful_videos}")
        print(f"❌ Failed videos: {failed_videos}")
        print(f"📁 Total sequences processed: {successful_videos + failed_videos}")
        
        if successful_videos > 0:
            print(f"\n🎉 {successful_videos} video(s) created successfully in {self.output_dir}/")
            print(f"📹 Each video contains 3 segments ({self.segment_duration}s each) for {self.total_duration}s total")
            if audio_files:
                print(f"🎵 Random audio added to each video")
            print(f"📋 Google Sheets updated with used entries")
        
        return successful_videos > 0

def main():
    """Entry point"""
    print("Setting up 3-Image Snapchat Video Editor...")
    
    if not GOOGLE_SHEETS_AVAILABLE:
        print("\n❌ Google Sheets packages not installed!")
        print("This script requires Google Sheets integration.")
        print("Please install: pip install gspread google-auth")
        return False
    
    editor = SnapchatEditor()
    success = editor.run()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()