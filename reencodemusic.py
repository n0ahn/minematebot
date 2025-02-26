import os
import subprocess

music_dir = "music/"
output_dir = "music_reencoded/"

# Create the output directory if it doesn't exist
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# Loop through all MP3 files in the music directory
for filename in os.listdir(music_dir):
    if filename.endswith(".mp3"):
        input_path = os.path.join(music_dir, filename)
        output_path = os.path.join(output_dir, filename)
        
        # Run the FFmpeg command to re-encode the MP3 file
        command = [
            "ffmpeg",
            "-i", input_path,
            "-acodec", "libmp3lame",
            "-ar", "44100",  # 44.1 kHz
            "-ac", "2",  # Stereo
            output_path
        ]
        
        # Execute the command
        subprocess.run(command, check=True)
        print(f"Re-encoded: {filename}")

print("All MP3 files have been re-encoded!")
