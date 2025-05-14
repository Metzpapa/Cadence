# video_editing_agent/utils/ffmpeg_utils.py

import ffmpeg # The ffmpeg-python library
import logging
import os
import tempfile
from typing import List, Dict, Any, Optional, Tuple
import pathlib # Added for cross-platform path handling

logger = logging.getLogger(__name__)

QUALITY_TARGET_WIDTHS = {
    "low": 640,    # Approx 480p for 16:9 (640x360) or 4:3 (640x480)
    "medium": 1280, # Approx 720p (1280x720)
    "high": 1920,   # Approx 1080p (1920x1080)
}

def parse_time_to_seconds(time_str: str) -> Optional[float]:
    """
    Parses a time string (HH:MM:SS or HH:MM:SS.mmm, MM:SS, SS) into total seconds.
    Returns None if parsing fails.
    """
    if not isinstance(time_str, str):
        logger.warning(f"parse_time_to_seconds received non-string input: {time_str}")
        return None
        
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
    except Exception as e:
        logger.error(f"Unexpected error parsing time string '{time_str}': {e}", exc_info=True)
        return None


def get_video_metadata(video_path: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves metadata for a video file using ffprobe.

    Args:
        video_path: Path to the video file.

    Returns:
        A dictionary containing metadata like duration, width, height, fps,
        or None if an error occurs or the file is not a valid video.
    """
    if not os.path.exists(video_path):
        logger.error(f"Metadata check: Video file not found at {video_path}")
        return None
    try:
        logger.info(f"Probing video file: {video_path}")
        probe = ffmpeg.probe(video_path)

        video_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
        audio_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'audio'), None)

        # Duration
        duration_str = probe.get('format', {}).get('duration', None)
        duration = float(duration_str) if duration_str is not None else 0.0

        metadata = {
            "duration_seconds": duration,
            "has_audio": audio_stream is not None
        }
        
        # Add video stream specific metadata if available
        if video_stream:
             # Resolution
            width = int(video_stream.get('width', 0))
            height = int(video_stream.get('height', 0))
            # Frame rate
            fps_str = video_stream.get('avg_frame_rate', '0/1') # or 'r_frame_rate'
            if '/' in fps_str:
                num, den = map(int, fps_str.split('/'))
                fps = float(num / den) if den != 0 else 0.0
            else:
                try:
                    fps = float(fps_str)
                except ValueError:
                    fps = 0.0 # Handle cases where fps_str isn't a simple float

            metadata["width"] = width
            metadata["height"] = height
            metadata["fps"] = fps
        else:
             metadata["width"] = 0
             metadata["height"] = 0
             metadata["fps"] = 0.0
             logger.warning(f"No video stream found in {video_path}")


        logger.info(f"Metadata for {video_path}: {metadata}")
        return metadata

    except ffmpeg.Error as e:
        logger.error(f"ffmpeg error probing {video_path}: {e.stderr.decode('utf8') if e.stderr else str(e)}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred while probing {video_path}: {e}", exc_info=True)
        return None


def extract_frames(
    video_path: str,
    start_time_sec: float,
    end_time_sec: float,
    num_frames: int = 3,
    quality_level: str = "low" # New parameter with default
) -> List[bytes]:
    if not os.path.exists(video_path):
        logger.error(f"Frame extraction: Video file not found at {video_path}")
        return []
    if num_frames <= 0:
        logger.warning("Number of frames to extract must be positive.")
        return []
    # Allow start_time_sec == end_time_sec for single frame extraction
    if start_time_sec < 0 or end_time_sec < start_time_sec:
        logger.warning(f"Invalid time range for frame extraction: {start_time_sec}s to {end_time_sec}s")
        return []

    extracted_frames_bytes: List[bytes] = []
    original_metadata = get_video_metadata(video_path)
    original_width = original_metadata.get("width", 0) if original_metadata else 0

    target_width = QUALITY_TARGET_WIDTHS.get(quality_level, QUALITY_TARGET_WIDTHS["low"])

    # Determine if scaling is needed and what the scale filter should be
    scale_filter = None
    if original_width > 0 and original_width > target_width:
        # Scale down to target_width, maintain aspect ratio (-1 for height)
        scale_filter = f"scale={target_width}:-1"
        logger.info(f"Applying scale filter for quality '{quality_level}': {scale_filter} (original width: {original_width})")
    elif original_width > 0:
        logger.info(f"No downscaling needed for quality '{quality_level}'. Original width ({original_width}) <= target width ({target_width}).")
    else:
        logger.warning(f"Could not determine original video width. Proceeding without scaling for quality '{quality_level}'.")


    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            logger.info(f"Extracting {num_frames} frames from {video_path} "
                         f"({start_time_sec:.2f}s - {end_time_sec:.2f}s) at quality '{quality_level}' into {temp_dir}")

            segment_duration = end_time_sec - start_time_sec
            # Ensure segment_duration is not negative if start_time_sec == end_time_sec
            if segment_duration < 0: segment_duration = 0

            # Base input stream
            # For segment_duration == 0, 'to' might be problematic.
            # If start_time_sec == end_time_sec, we want one frame at start_time_sec.
            # ffmpeg handles ss=T, to=T by outputting one frame at T.
            input_stream_ffmpeg = ffmpeg.input(video_path, ss=start_time_sec, to=end_time_sec)

            if num_frames == 1:
                # For a single frame, we don't need the fps filter.
                # We just take 1 frame from the specified segment (which might be a point in time).
                stream_to_process = input_stream_ffmpeg
                if scale_filter:
                    stream_to_process = stream_to_process.filter('scale', *scale_filter.split('=')[1].split(':'))

                frame_filename = os.path.join(temp_dir, "frame_0001.png")
                process = (
                    stream_to_process
                    .output(frame_filename, vframes=1, format='image2', pix_fmt='rgb24')
                    .overwrite_output()
                    .run_async(pipe_stdout=True, pipe_stderr=True)
                )
                out, err = process.communicate()

                if process.returncode != 0:
                    logger.error(f"ffmpeg error extracting single frame: {err.decode('utf8', errors='ignore')}")
                    return []
                
                if os.path.exists(frame_filename):
                    with open(frame_filename, 'rb') as f:
                        extracted_frames_bytes.append(f.read())
            else: # num_frames > 1
                if segment_duration <= 0.001 and num_frames > 1: # Effectively a single point in time but multiple frames requested
                    logger.warning(f"Segment duration is near zero ({segment_duration:.3f}s) but {num_frames} frames requested. Will attempt to extract one frame.")
                    # Fallback to single frame logic for this edge case
                    stream_to_process = ffmpeg.input(video_path, ss=start_time_sec) # Re-input for single frame at point
                    if scale_filter:
                         stream_to_process = stream_to_process.filter('scale', *scale_filter.split('=')[1].split(':'))
                    frame_filename = os.path.join(temp_dir, "frame_0001.png")
                    process = (
                        stream_to_process
                        .output(frame_filename, vframes=1, format='image2', pix_fmt='rgb24')
                        .overwrite_output()
                        .run_async(pipe_stdout=True, pipe_stderr=True)
                    )
                    out, err = process.communicate()
                    if process.returncode == 0 and os.path.exists(frame_filename):
                        with open(frame_filename, 'rb') as f:
                            extracted_frames_bytes.append(f.read())
                    else:
                        logger.error(f"ffmpeg error extracting single frame fallback: {err.decode('utf8', errors='ignore')}")

                else: # Normal case: num_frames > 1 and segment_duration > 0
                    # Calculate FPS for the filter to get num_frames over the segment_duration
                    fps_val = num_frames / segment_duration if segment_duration > 0.001 else num_frames # Avoid division by zero
                    
                    stream_to_process = input_stream_ffmpeg.filter('fps', fps=fps_val)
                    if scale_filter:
                        stream_to_process = stream_to_process.filter('scale', *scale_filter.split('=')[1].split(':'))
                    
                    output_pattern = os.path.join(temp_dir, "frame_%04d.png")
                    process = (
                        stream_to_process
                        .output(output_pattern, format='image2', pix_fmt='rgb24', start_number=0)
                        .overwrite_output()
                        .run_async(pipe_stdout=True, pipe_stderr=True)
                    )
                    out, err = process.communicate()

                    if process.returncode != 0:
                        logger.error(f"ffmpeg error extracting multiple frames: {err.decode('utf8', errors='ignore')}")
                    
                    for i in range(num_frames):
                        frame_filename = os.path.join(temp_dir, f"frame_{i:04d}.png")
                        if os.path.exists(frame_filename):
                            with open(frame_filename, 'rb') as f:
                                extracted_frames_bytes.append(f.read())
                        else:
                            break 
            
            if not extracted_frames_bytes:
                logger.warning(f"No frames were extracted for {video_path} in the given range with quality '{quality_level}'.")

            logger.info(f"Successfully extracted {len(extracted_frames_bytes)} frames at quality '{quality_level}'.")
            return extracted_frames_bytes

    except ffmpeg.Error as e:
        logger.error(f"ffmpeg error during frame extraction for {video_path}: {e.stderr.decode('utf8', errors='ignore') if e.stderr else str(e)}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error during frame extraction for {video_path}: {e}", exc_info=True)
        return []


def extract_audio_segment(
    video_path: str,
    start_time_sec: float,
    end_time_sec: float
) -> Optional[bytes]:
    """
    Extracts an audio segment from a video file as WAV bytes.

    Args:
        video_path: Path to the video file.
        start_time_sec: Start time of the segment in seconds.
        end_time_sec: End time of the segment in seconds.

    Returns:
        Byte string of the WAV audio segment, or None if an error occurs or no audio.
    """
    if not os.path.exists(video_path):
        logger.error(f"Audio extraction: Video file not found at {video_path}")
        return None
    if start_time_sec < 0 or end_time_sec < start_time_sec:
        logger.warning(f"Invalid time range for audio extraction: {start_time_sec}s to {end_time_sec}s")
        return None

    segment_duration = end_time_sec - start_time_sec
    if segment_duration <= 0: # No audio to extract for zero or negative duration
        logger.info(f"Audio segment duration is zero or negative for {video_path}. Returning None.")
        return None

    # Use pathlib for robust path handling
    input_path_p = pathlib.Path(video_path)

    # Check if video has audio stream before attempting extraction
    metadata = get_video_metadata(video_path)
    if not metadata or not metadata.get("has_audio"):
        logger.info(f"Video '{os.path.basename(video_path)}' does not have an audio track or metadata could not be retrieved. No audio will be extracted.")
        return None

    temp_file_descriptor, temp_file_path = tempfile.mkstemp(suffix='.wav')
    os.close(temp_file_descriptor) # Close the descriptor, ffmpeg will open the file by path

    try:
        logger.info(f"Extracting audio from {video_path} "
                     f"({start_time_sec:.2f}s - {end_time_sec:.2f}s) into {temp_file_path}")

        # Use input seeking with 'to' for the audio segment
        input_stream = ffmpeg.input(str(input_path_p), ss=start_time_sec, to=end_time_sec)
        
        process = (
            input_stream
            .output(temp_file_path, acodec='pcm_s16le', ar=22050, ac=1) # WAV, 22.05kHz, mono
            .overwrite_output()
            .run_async(pipe_stdout=True, pipe_stderr=True)
        )
        out, err = process.communicate()

        if process.returncode != 0:
            logger.error(f"ffmpeg error extracting audio: {err.decode('utf8')}")
            return None

        if os.path.exists(temp_file_path) and os.path.getsize(temp_file_path) > 0:
            try:
                with open(temp_file_path, 'rb') as f:
                    audio_bytes = f.read()
                logger.info(f"Successfully extracted audio segment to {len(audio_bytes)} bytes.")
                return audio_bytes
            except Exception as read_e:
                 logger.error(f"Error reading extracted audio file {temp_file_path}: {read_e}")
                 return None
        else:
            logger.warning(f"No audio data extracted or temp file empty for {video_path}.")
            return None

    except ffmpeg.Error as e:
        logger.error(f"ffmpeg error during audio extraction for {video_path}: {e.stderr.decode('utf8') if e.stderr else str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error during audio extraction for {video_path}: {e}", exc_info=True)
        return None
    finally:
        if os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path) # Ensure cleanup
            except Exception as cleanup_e:
                logger.error(f"Error cleaning up temp audio file {temp_file_path}: {cleanup_e}")


def trim_and_save_segment(
    input_video_path: str,
    start_time_sec: float,
    end_time_sec: float,
    output_video_path: str
) -> bool:
    """
    Trims a video segment from start_time_sec to end_time_sec and saves it
    to output_video_path using ffmpeg-python, prioritizing accuracy via re-encoding.

    Args:
        input_video_path: Full path to the source video file.
        start_time_sec: Start time of the segment in seconds.
        end_time_sec: End time of the segment in seconds.
        output_video_path: Full path where the new video should be saved.

    Returns:
        True if the segment was successfully trimmed and saved, False otherwise.
    """
    logger.info(f"Attempting to trim '{input_video_path}' from {start_time_sec:.2f}s to {end_time_sec:.2f}s and save to '{output_video_path}'")

    if not os.path.exists(input_video_path):
        logger.error(f"Trim failed: Input video file not found at {input_video_path}")
        return False
    if start_time_sec < 0 or end_time_sec < start_time_sec:
        logger.error(f"Trim failed: Invalid time range: {start_time_sec}s to {end_time_sec}s")
        return False
    
    # Ensure output directory exists
    output_dir = os.path.dirname(output_video_path)
    if output_dir and not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir, exist_ok=True)
            logger.info(f"Created output directory: {output_dir}")
        except Exception as e:
            logger.error(f"Failed to create output directory {output_dir}: {e}", exc_info=True)
            return False

    try:
        # Use pathlib for robust path handling
        input_path_p = pathlib.Path(input_video_path)
        output_path_p = pathlib.Path(output_video_path)

        # Build the ffmpeg command using input seeking (-ss before -i)
        # and specifying the end time (-to) for accuracy with re-encoding.
        # Re-encode using H.264 video and AAC audio for broad compatibility.
        process = (
            ffmpeg
            .input(str(input_path_p), ss=start_time_sec, to=end_time_sec)
            .output(str(output_path_p), vcodec='libx264', acodec='aac')
            .overwrite_output() # Allow overwriting existing files
            .run_async(pipe_stdout=True, pipe_stderr=True) # Use async to capture output
        )
        out, err = process.communicate() # Wait for process to complete

        if process.returncode != 0:
            error_message = err.decode('utf8') if err else "Unknown FFmpeg error"
            logger.error(f"FFmpeg error during trim: {error_message}")
            return False

        # Check if the output file was actually created and is not empty
        if not os.path.exists(output_video_path) or os.path.getsize(output_video_path) == 0:
             logger.error(f"Trim failed: Output file was not created or is empty: {output_video_path}")
             return False

        logger.info(f"Successfully trimmed and saved segment to '{output_video_path}'.")
        return True

    except ffmpeg.Error as e:
        error_message = e.stderr.decode('utf8') if e.stderr else str(e)
        logger.error(f"ffmpeg error during trim for {input_video_path}: {error_message}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error during trim for {input_video_path}: {e}", exc_info=True)
        return False


if __name__ == '__main__':
    # --- Example Usage (requires a test video file) ---
    # Create a dummy video file for testing if you don't have one.
    # For example, using ffmpeg CLI:
    # ffmpeg -f lavfi -i testsrc=duration=10:size=1280x720:rate=30 -f lavfi -i sine=frequency=1000:duration=10 -c:v libx264 -c:a aac -shortest test_video.mp4

    test_video = "test_video.mp4" # Replace with your test video path
    test_output_dir = "temp_agent_outputs"
    test_output_video = os.path.join(test_output_dir, "trimmed_clip.mp4")

    # Ensure test output directory exists
    os.makedirs(test_output_dir, exist_ok=True)

    if not os.path.exists(test_video):
        print(f"Test video '{test_video}' not found. Skipping examples.")
    else:
        print(f"\n--- Testing with video: {test_video} ---")

        # Test metadata
        print("\n--- Testing get_video_metadata ---")
        metadata = get_video_metadata(test_video)
        if metadata:
            print(f"Metadata: {metadata}")
        else:
            print("Failed to get metadata.")

        # Test frame extraction
        print("\n--- Testing extract_frames ---")
        if metadata and metadata["duration_seconds"] >= 5:
            # Extract 3 frames from 1s to 4s
            frames = extract_frames(test_video, start_time_sec=1.0, end_time_sec=4.0, num_frames=3)
            if frames:
                print(f"Extracted {len(frames)} frames.")
                # Save first frame for inspection
                # with open(os.path.join(test_output_dir, "test_output_frame_0.png"), "wb") as f_out:
                #     f_out.write(frames[0])
                # print(f"  - First frame size: {len(frames[0])} bytes (saved to {test_output_dir})")
            else:
                print("Failed to extract frames or no frames found.")

            # Extract 1 frame
            print("\n--- Testing extract_frames (single frame) ---")
            single_frame_list = extract_frames(test_video, start_time_sec=2.0, end_time_sec=2.5, num_frames=1)
            if single_frame_list:
                print(f"Extracted {len(single_frame_list)} frame (single).")
                # Save single frame for inspection
                # with open(os.path.join(test_output_dir, "test_output_single_frame.png"), "wb") as f_out:
                #     f_out.write(single_frame_list[0])
                # print(f"  - Single frame size: {len(single_frame_list[0])} bytes (saved to {test_output_dir})")
            else:
                print("Failed to extract single frame.")
        else:
            print("Skipping frame extraction tests (video too short or no metadata).")


        # Test audio extraction
        print("\n--- Testing extract_audio_segment ---")
        if metadata and metadata["duration_seconds"] >= 5 and metadata["has_audio"]:
            # Extract audio from 1s to 3s
            audio = extract_audio_segment(test_video, start_time_sec=1.0, end_time_sec=3.0)
            if audio:
                print(f"Extracted audio segment: {len(audio)} bytes.")
                # Save audio for inspection
                # with open(os.path.join(test_output_dir, "test_output_audio_segment.wav"), "wb") as f_out:
                #     f_out.write(audio)
                # print(f"  - Audio segment saved to {test_output_dir}")
            else:
                print("Failed to extract audio segment.")
        else:
            print("Skipping audio extraction tests (video too short, no audio, or no metadata).")

        # Test trim and save segment
        print("\n--- Testing trim_and_save_segment ---")
        if metadata and metadata["duration_seconds"] >= 10: # Need a slightly longer video for a meaningful trim test
            start_trim = 2.0
            end_trim = 7.0
            print(f"Attempting to trim from {start_trim}s to {end_trim}s...")
            success = trim_and_save_segment(test_video, start_trim, end_trim, test_output_video)
            if success:
                print(f"Trim and save successful! Output: {test_output_video}")
                # Verify output file exists and has size
                if os.path.exists(test_output_video):
                    print(f"Output file size: {os.path.getsize(test_output_video)} bytes")
                else:
                    print("Output file does not exist after reported success!")
            else:
                print("Trim and save failed.")
        else:
             print("Skipping trim and save test (video too short or no metadata).")


    # --- Cleanup ---
    # Note: Manual cleanup of temp_agent_outputs directory and its contents might be needed after running this script.
    # For automated cleanup in a test script, you'd use shutil.rmtree(test_output_dir)
    print(f"\nNote: Test output directory '{test_output_dir}' and its contents were created for testing.")
    print("You may want to manually clean them up or add full cleanup code if desired.")