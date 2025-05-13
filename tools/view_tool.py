# video_editing_agent/tools/view_tool.py

import os
import logging
from typing import Dict, List, Any, Optional

from utils.ffmpeg_utils import extract_frames, extract_audio_segment, get_video_metadata

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DEFAULT_NUM_FRAMES = 3

def parse_time_to_seconds(time_str: str) -> Optional[float]:
    """
    Parses a time string (HH:MM:SS or HH:MM:SS.mmm, MM:SS, SS) into total seconds.
    """
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
            logger.warning(f"Invalid time string format: {time_str}")
            return None
    except ValueError:
        logger.warning(f"ValueError parsing time string: {time_str}")
        return None

def view_video_segment_impl(
    video_directory_path: str,
    file_name: str,
    start_time: str,
    end_time: str,
    num_frames: Optional[int] = None
) -> Dict[str, Any]:
    """
    Implements the logic for the 'view_video_segment' tool.
    Extracts frames and a single corresponding audio segment from a video.
    """
    if num_frames is None or num_frames <= 0:
        num_frames_to_extract = DEFAULT_NUM_FRAMES
        logger.info(f"num_frames not provided or invalid, defaulting to {DEFAULT_NUM_FRAMES}")
    else:
        num_frames_to_extract = num_frames

    full_video_path = os.path.join(video_directory_path, file_name)

    result: Dict[str, Any] = {
        "status_json": {},
        "images": [],
        "audios": [] # Will contain at most one audio segment
    }

    if not os.path.exists(full_video_path):
        error_msg = f"Video file '{file_name}' not found in directory '{video_directory_path}'."
        logger.error(error_msg)
        result["status_json"] = {"status": "error", "message": error_msg}
        return result

    start_time_sec = parse_time_to_seconds(start_time)
    end_time_sec = parse_time_to_seconds(end_time)

    if start_time_sec is None or end_time_sec is None:
        error_msg = f"Invalid time format for start_time ('{start_time}') or end_time ('{end_time}'). Use HH:MM:SS or similar."
        logger.error(error_msg)
        result["status_json"] = {"status": "error", "message": error_msg}
        return result
    
    if start_time_sec < 0 or end_time_sec < 0:
        error_msg = "Start and end times must be non-negative."
        logger.error(error_msg)
        result["status_json"] = {"status": "error", "message": error_msg}
        return result

    if end_time_sec < start_time_sec:
        error_msg = f"End time '{end_time}' cannot be before start time '{start_time}'."
        logger.error(error_msg)
        result["status_json"] = {"status": "error", "message": error_msg}
        return result

    video_metadata = get_video_metadata(full_video_path)
    if not video_metadata:
        error_msg = f"Could not retrieve metadata for video '{file_name}'. It might be corrupted or not a valid video."
        logger.error(error_msg)
        result["status_json"] = {"status": "error", "message": error_msg}
        return result

    video_duration_sec = video_metadata.get("duration_seconds", 0.0)
    if start_time_sec > video_duration_sec:
        error_msg = (f"Start time '{start_time}' ({start_time_sec:.2f}s) is beyond the video duration "
                     f"({video_duration_sec:.2f}s).")
        logger.error(error_msg)
        result["status_json"] = {"status": "error", "message": error_msg}
        return result
    
    effective_end_time_sec = min(end_time_sec, video_duration_sec)
    if end_time_sec > video_duration_sec:
        logger.warning(f"Requested end time {end_time_sec:.2f}s exceeds video duration {video_duration_sec:.2f}s. "
                        f"Will process up to video end ({effective_end_time_sec:.2f}s).")

    # --- Frame Extraction ---
    logger.info(f"Attempting to extract {num_frames_to_extract} frames for '{file_name}' "
                 f"from {start_time_sec:.2f}s to {effective_end_time_sec:.2f}s.")
    extracted_image_bytes = extract_frames(
        full_video_path,
        start_time_sec,
        effective_end_time_sec,
        num_frames_to_extract
    )
    result["images"] = extracted_image_bytes
    if not extracted_image_bytes:
        logger.warning(f"No frames were extracted for '{file_name}'.")

    # --- Audio Segment Extraction (Single Segment for the Requested Time Range) ---
    requested_segment_duration_sec = effective_end_time_sec - start_time_sec # Use effective times for actual extraction
    
    if requested_segment_duration_sec > 0.001 and video_metadata.get("has_audio"):
        logger.info(f"Extracting single audio segment for '{file_name}' "
                     f"from {start_time_sec:.2f}s to {effective_end_time_sec:.2f}s.")
        audio_bytes = extract_audio_segment(
            full_video_path,
            start_time_sec,
            effective_end_time_sec # Use the same range as frames
        )
        if audio_bytes:
            result["audios"].append(audio_bytes) # Append the single segment
        else:
            logger.warning(f"Failed to extract audio segment for '{file_name}'.")
    elif not video_metadata.get("has_audio"):
        logger.info(f"Video '{file_name}' does not have an audio track. No audio will be extracted.")
    else:
        logger.info(f"Segment duration is zero or invalid for audio extraction. No audio will be extracted.")

    # --- Final Status ---
    num_images_extracted = len(result["images"])
    num_audios_extracted = len(result["audios"]) # Will be 0 or 1

    if num_images_extracted > 0 or num_audios_extracted > 0:
        # --- DRASTICALLY SIMPLIFIED MESSAGE ---
        status_message = (
            "Media has been extracted. Please analyze the provided image and audio parts and describe their content."
        )
        result["status_json"] = {"status": "success", "message": status_message}
        logger.info(f"View tool success for {file_name}: {num_images_extracted} frames, {num_audios_extracted} audio.")
    elif "error" not in result["status_json"]:
        # --- SIMPLIFIED MESSAGE ---
        status_message = (
            "No media was extracted for the requested segment (it might be too short, empty, or have no audio track). "
            "There is nothing to describe from this segment."
        )
        result["status_json"] = {"status": "partial_success", "message": status_message}
        logger.warning(status_message)

    return result

if __name__ == '__main__':
    # --- Example Usage (requires a test video file and ffmpeg_utils.py) ---
    test_video_dir = "." 
    test_video_name = "test_video.mp4"

    if not os.path.exists(os.path.join(test_video_dir, test_video_name)):
        print(f"Test video '{test_video_name}' not found in '{test_video_dir}'. Skipping examples.")
    else:
        print(f"\n--- Testing view_video_segment_impl with: {test_video_name} ---")

        print("\nTest 1: Valid segment (3 frames, 0s to 5s)")
        output1 = view_video_segment_impl(
            video_directory_path=test_video_dir,
            file_name=test_video_name,
            start_time="00:00:00",
            end_time="00:00:05",
            num_frames=3
        )
        print(f"Status: {output1['status_json']}")
        print(f"Images extracted: {len(output1['images'])}")
        print(f"Audios extracted: {len(output1['audios'])} (should be 0 or 1)")
        if output1['images']:
            with open("view_tool_test_frame_0.png", "wb") as f:
                f.write(output1['images'][0])
            print("Saved first extracted frame as view_tool_test_frame_0.png")
        if output1['audios']:
            with open("view_tool_test_audio_segment.wav", "wb") as f:
                f.write(output1['audios'][0])
            print("Saved extracted audio segment as view_tool_test_audio_segment.wav")

        print("\nTest 2: Zero duration segment (start_time == end_time)")
        output2 = view_video_segment_impl(
            video_directory_path=test_video_dir,
            file_name=test_video_name,
            start_time="00:00:02",
            end_time="00:00:02",
            num_frames=1
        )
        print(f"Status: {output2['status_json']}")
        print(f"Images extracted: {len(output2['images'])}") # Should be 1
        print(f"Audios extracted: {len(output2['audios'])}") # Should be 0