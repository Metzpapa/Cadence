# video_editing_agent/tools/save_video_segment_tool.py

import os
import logging
import ffmpeg # ffmpeg-python
from pathlib import Path
from typing import Dict, Any, Optional

# Attempt to import parse_time_to_seconds from view_tool
# This makes the tool dependent on view_tool.py being in the same directory or Python path.
# Alternatively, duplicate the function if you want this tool to be more standalone.
try:
    from .view_tool import parse_time_to_seconds
except ImportError:
    logger_fallback = logging.getLogger(__name__ + ".parse_time_fallback")
    def parse_time_to_seconds(time_str: str) -> Optional[float]:
        logger_fallback.warning("Using fallback parse_time_to_seconds in save_video_segment_tool.py. Consider ensuring view_tool.py is importable.")
        try:
            parts = time_str.split(':')
            if len(parts) == 3: # HH:MM:SS.mmm
                h = int(parts[0])
                m = int(parts[1])
                s_parts = parts[2].split('.')
                s = int(s_parts[0])
                ms = int(s_parts[1]) if len(s_parts) > 1 else 0
                return float(h * 3600 + m * 60 + s + ms / 1000.0)
            elif len(parts) == 2: # MM:SS.mmm
                m = int(parts[0])
                s_parts = parts[1].split('.')
                s = int(s_parts[0])
                ms = int(s_parts[1]) if len(s_parts) > 1 else 0
                return float(m * 60 + s + ms / 1000.0)
            elif len(parts) == 1: # SS.mmm
                s_parts = parts[0].split('.')
                s = int(s_parts[0])
                ms = int(s_parts[1]) if len(s_parts) > 1 else 0
                return float(s + ms / 1000.0)
            else:
                logger_fallback.warning(f"Invalid time string format: {time_str}")
                return None
        except ValueError:
            logger_fallback.warning(f"ValueError parsing time string: {time_str}")
            return None

from utils.ffmpeg_utils import get_video_metadata # Optional: for duration validation

logger = logging.getLogger(__name__)

SAVED_CLIPS_SUBDIR = "saved_clips" # Directory to save trimmed clips (relative to script execution)

def save_video_segment_impl(
    video_directory_path: str, # This is the source directory for videos
    source_file_name: str,
    start_time: str,
    end_time: str,
    output_file_name: str
) -> Dict[str, Any]:
    """
    Trims a video segment and saves it to a new file in the SAVED_CLIPS_SUBDIR.
    Re-encodes for accuracy using H.264/AAC in an MP4 container.
    """
    source_full_path = Path(video_directory_path) / source_file_name

    # Output directory is relative to where the script is run, not necessarily video_directory_path
    output_dir = Path(SAVED_CLIPS_SUBDIR)
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Ensured output directory exists: {output_dir.resolve()}")
    except Exception as e:
        error_msg = f"Could not create output directory '{output_dir.resolve()}': {e}"
        logger.error(error_msg)
        return {"status": "error", "message": error_msg}

    output_full_path = output_dir / output_file_name

    if not source_full_path.exists():
        error_msg = f"Source video file '{source_file_name}' not found at '{source_full_path}'."
        logger.error(error_msg)
        return {"status": "error", "message": error_msg}

    if not output_file_name.lower().endswith((".mp4", ".mov", ".avi", ".mkv")): # Allow common extensions
        logger.warning(f"Output file name '{output_file_name}' does not have a common video extension. Appending .mp4.")
        output_file_name += ".mp4"
        output_full_path = output_dir / output_file_name

    start_time_sec = parse_time_to_seconds(start_time)
    end_time_sec = parse_time_to_seconds(end_time)

    if start_time_sec is None or end_time_sec is None:
        error_msg = f"Invalid time format for start_time ('{start_time}') or end_time ('{end_time}'). Use HH:MM:SS or similar."
        logger.error(error_msg)
        return {"status": "error", "message": error_msg}

    if start_time_sec < 0 or end_time_sec < 0:
        error_msg = "Start and end times must be non-negative."
        logger.error(error_msg)
        return {"status": "error", "message": error_msg}

    if end_time_sec <= start_time_sec:
        error_msg = f"End time '{end_time}' ({end_time_sec:.2f}s) must be after start time '{start_time}' ({start_time_sec:.2f}s)."
        logger.error(error_msg)
        return {"status": "error", "message": error_msg}

    metadata = get_video_metadata(str(source_full_path))
    if metadata and metadata.get("duration_seconds") is not None:
        video_duration_sec = metadata["duration_seconds"]
        if start_time_sec >= video_duration_sec:
            error_msg = f"Start time '{start_time}' ({start_time_sec:.2f}s) is at or after video duration ({video_duration_sec:.2f}s)."
            logger.error(error_msg)
            return {"status": "error", "message": error_msg}
        if end_time_sec > video_duration_sec:
            logger.warning(f"Requested end time {end_time_sec:.2f}s exceeds video duration {video_duration_sec:.2f}s. "
                           f"Trimming up to video end ({video_duration_sec:.2f}s).")
            end_time_sec = video_duration_sec
            if end_time_sec <= start_time_sec: # Re-check after clamping
                error_msg = (f"Adjusted end time ({end_time_sec:.2f}s) is not after start time ({start_time_sec:.2f}s) "
                             f"after clamping to video duration. Original video might be shorter than requested start time.")
                logger.error(error_msg)
                return {"status": "error", "message": error_msg}
    elif metadata is None: # Could not get metadata
        logger.warning(f"Could not retrieve metadata for '{source_file_name}'. Proceeding without duration validation.")


    logger.info(f"Attempting to trim '{source_file_name}' from {start_time} ({start_time_sec:.2f}s) to {end_time} ({end_time_sec:.2f}s), "
                 f"saving as '{output_full_path}'.")

    try:
        # Using input seeking with -ss and -to for accuracy when re-encoding.
        # FFmpeg's -to is relative to the start of the input file, not relative to -ss.
        # So, we pass the original start_time and end_time strings.
        stream = ffmpeg.input(str(source_full_path), ss=start_time, to=end_time)
        stream = ffmpeg.output(
            stream,
            str(output_full_path),
            vcodec="libx264",
            acodec="aac",
            strict="-2" # For some ffmpeg versions needing experimental aac
        )
        stream = stream.overwrite_output()

        logger.debug(f"FFmpeg command: {' '.join(ffmpeg.compile(stream))}")
        # Set quiet=True to suppress ffmpeg's console output during normal operation
        # For debugging, set quiet=False or capture stderr explicitly
        out, err = stream.run(capture_stdout=True, capture_stderr=True, quiet=False) # Set quiet=False for more debug info

        # Log ffmpeg output, even on success, as it can contain useful info
        if out:
            logger.debug(f"FFmpeg stdout: {out.decode('utf-8', errors='ignore')}")
        if err: # FFmpeg often prints info to stderr even on success
             logger.info(f"FFmpeg stderr: {err.decode('utf-8', errors='ignore')}") # Use INFO for stderr as it's not always an error

        success_msg = f"Successfully trimmed segment and saved to '{output_full_path.resolve()}'."
        logger.info(success_msg)
        return {"status": "success", "message": success_msg, "output_path": str(output_full_path.resolve())}

    except ffmpeg.Error as e:
        error_details = e.stderr.decode('utf-8', errors='ignore') if e.stderr else "No stderr output from FFmpeg."
        # Check if the error is "File exists" and overwrite_output was not effective or if it's another error
        if "File exists" in error_details and ".overwrite_output()" not in " ".join(ffmpeg.compile(stream)): # A bit of a hacky check
            error_msg = f"Output file '{output_full_path}' already exists. FFmpeg will not overwrite without explicit instruction."
        else:
            error_msg = f"FFmpeg error while trimming '{source_file_name}': {error_details}"
        logger.error(error_msg, exc_info=True)
        return {"status": "error", "message": f"FFmpeg error: {error_details}"} # Return FFmpeg's direct error
    except Exception as e:
        error_msg = f"An unexpected error occurred while saving segment from '{source_file_name}': {e}"
        logger.error(error_msg, exc_info=True)
        return {"status": "error", "message": error_msg}

if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    # Create a dummy video for testing if you don't have one:
    # ffmpeg -y -f lavfi -i testsrc=duration=10:size=320x240:rate=10 -c:v libx264 -c:a aac -shortest dummy_video.mp4
    test_video_dir_main = "."
    test_source_video_main = "dummy_video.mp4" # Make sure this file exists in the current directory

    if not (Path(test_video_dir_main) / test_source_video_main).exists():
        print(f"Test video '{test_source_video_main}' not found in '{test_video_dir_main}'. "
              f"Please create it or update path. Skipping save_video_segment_impl test.")
    else:
        print(f"\n--- Testing save_video_segment_impl with: {test_source_video_main} ---")

        # Test 1: Valid trim
        result1 = save_video_segment_impl(
            video_directory_path=test_video_dir_main,
            source_file_name=test_source_video_main,
            start_time="00:00:02",
            end_time="00:00:05",
            output_file_name="trimmed_valid.mp4"
        )
        print(f"Test 1 Result: {result1}")

        # Test 2: End time exceeding duration (should clamp)
        result2 = save_video_segment_impl(
            video_directory_path=test_video_dir_main,
            source_file_name=test_source_video_main,
            start_time="00:00:08", # Assuming dummy_video.mp4 is 10s long
            end_time="00:00:15",   # Exceeds 10s duration
            output_file_name="trimmed_exceed_duration.mp4"
        )
        print(f"Test 2 Result (exceed duration): {result2}")

        # Test 3: Invalid time (end before start)
        result3 = save_video_segment_impl(
            video_directory_path=test_video_dir_main,
            source_file_name=test_source_video_main,
            start_time="00:00:05",
            end_time="00:00:02",
            output_file_name="trimmed_invalid_order.mp4"
        )
        print(f"Test 3 Result (invalid time order): {result3}")

        # Test 4: Source file not found
        result4 = save_video_segment_impl(
            video_directory_path=test_video_dir_main,
            source_file_name="non_existent_video.mp4",
            start_time="00:00:01",
            end_time="00:00:03",
            output_file_name="trimmed_no_source.mp4"
        )
        print(f"Test 4 Result (source not found): {result4}")

        # Test 5: Output filename without .mp4
        result5 = save_video_segment_impl(
            video_directory_path=test_video_dir_main,
            source_file_name=test_source_video_main,
            start_time="00:00:01",
            end_time="00:00:03",
            output_file_name="trimmed_no_extension" # No .mp4
        )
        print(f"Test 5 Result (no extension): {result5}")