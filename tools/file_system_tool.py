 # video_editing_agent/tools/file_system_tool.py

import os
import logging
from typing import List, Dict, Any, Optional
from utils.ffmpeg_utils import get_video_metadata # To get metadata for each video file

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Common video file extensions to look for
VIDEO_EXTENSIONS = ('.mp4', '.mov', '.avi', '.mkv', '.flv', '.wmv', '.webm')

def format_duration(seconds: float) -> str:
    """Helper function to format duration from seconds to HH:MM:SS."""
    if seconds is None or seconds < 0:
        return "N/A"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02}:{minutes:02}:{secs:02}"

def list_directory_contents_impl(video_directory_path: str) -> str:
    """
    Lists video files in the specified directory along with their metadata.

    Args:
        video_directory_path: The absolute path to the directory containing video files.

    Returns:
        A string listing the video files and their metadata, or a message
        if the directory is not found or no video files are present.
    """
    if not os.path.isdir(video_directory_path):
        logging.warning(f"Directory not found: {video_directory_path}")
        return f"Error: Directory '{video_directory_path}' not found."

    video_files_info: List[str] = []
    try:
        logging.info(f"Scanning directory: {video_directory_path}")
        for item_name in sorted(os.listdir(video_directory_path)):
            item_path = os.path.join(video_directory_path, item_name)
            if os.path.isfile(item_path) and item_name.lower().endswith(VIDEO_EXTENSIONS):
                logging.info(f"Processing video file: {item_name}")
                metadata = get_video_metadata(item_path)
                if metadata:
                    duration_formatted = format_duration(metadata.get("duration_seconds"))
                    resolution = f"{metadata.get('width', 'N/A')}x{metadata.get('height', 'N/A')}"
                    fps = f"{metadata.get('fps', 0.0):.2f}"
                    file_size_mb = f"{os.path.getsize(item_path) / (1024 * 1024):.2f} MB"

                    info_line = (
                        f"- {item_name}:\n"
                        f"    Duration: {duration_formatted}\n"
                        f"    Resolution: {resolution}\n"
                        f"    FPS: {fps}\n"
                        f"    Size: {file_size_mb}"
                    )
                    video_files_info.append(info_line)
                else:
                    video_files_info.append(
                        f"- {item_name}:\n"
                        f"    Metadata: Could not retrieve or not a valid video format."
                    )
            elif os.path.isfile(item_path):
                logging.debug(f"Skipping non-video file: {item_name}")
            elif os.path.isdir(item_path):
                logging.debug(f"Skipping sub-directory: {item_name}")


    except Exception as e:
        logging.error(f"Error accessing directory {video_directory_path}: {e}")
        return f"Error: Could not access directory contents. {str(e)}"

    if not video_files_info:
        return f"No video files found in directory '{video_directory_path}'."

    # We decided on a simple plaintext list for the LLM
    header = f"Video files in '{os.path.basename(video_directory_path)}':\n"
    return header + "\n\n".join(video_files_info)

if __name__ == '__main__':
    # Example usage:
    # Create a dummy directory and some dummy files for testing
    test_dir = "temp_video_test_dir"
    if not os.path.exists(test_dir):
        os.makedirs(test_dir)

    # Create dummy files (these won't have real metadata without ffmpeg creating them)
    # For a real test, you'd populate this with actual video files.
    dummy_files = ["video1.mp4", "clip.mov", "document.txt", "video2.avi"]
    for fname in dummy_files:
        with open(os.path.join(test_dir, fname), "w") as f:
            f.write("dummy content") # For size

    print(f"--- Testing list_directory_contents_impl with directory: {test_dir} ---")
    # To make this test more meaningful, get_video_metadata would need to handle
    # non-video files gracefully or you'd need actual videos.
    # For now, it will show "Could not retrieve" for these dummy files.
    
    # Mock get_video_metadata for a more controlled test if ffmpeg_utils is not fully ready
    # or if you don't want to depend on actual video files for this unit test.
    original_get_metadata = get_video_metadata
    def mock_get_video_metadata(video_path: str) -> Optional[Dict[str, Any]]:
        if "video1.mp4" in video_path:
            return {"duration_seconds": 125.5, "width": 1920, "height": 1080, "fps": 29.97}
        if "clip.mov" in video_path:
            return {"duration_seconds": 30.0, "width": 1280, "height": 720, "fps": 24.0}
        return None # For video2.avi and others

    # Apply the mock
    globals()['get_video_metadata'] = mock_get_video_metadata
    
    output_string = list_directory_contents_impl(test_dir)
    print("\nFormatted Output for LLM:")
    print(output_string)

    # Restore original function if needed elsewhere, or just let it be for this script run
    globals()['get_video_metadata'] = original_get_metadata

    # Clean up dummy directory and files
    # for fname in dummy_files:
    #     os.remove(os.path.join(test_dir, fname))
    # os.rmdir(test_dir)
    print(f"\nNote: Dummy files and directory '{test_dir}' were created for testing.")
    print("You may want to manually clean them up or add full cleanup code if desired.")