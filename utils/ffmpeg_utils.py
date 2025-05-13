 # video_editing_agent/utils/ffmpeg_utils.py

import ffmpeg # The ffmpeg-python library
import logging
import os
import tempfile
from typing import List, Dict, Any, Optional, Tuple

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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
        logging.error(f"Metadata check: Video file not found at {video_path}")
        return None
    try:
        logging.info(f"Probing video file: {video_path}")
        probe = ffmpeg.probe(video_path)

        video_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
        audio_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'audio'), None)

        if not video_stream:
            logging.warning(f"No video stream found in {video_path}")
            return None # Or handle as an audio-only file if desired

        # Duration
        duration_str = probe.get('format', {}).get('duration', None)
        duration = float(duration_str) if duration_str is not None else 0.0

        # Resolution
        width = int(video_stream.get('width', 0))
        height = int(video_stream.get('height', 0))

        # Frame rate
        fps_str = video_stream.get('avg_frame_rate', '0/1') # or 'r_frame_rate'
        if '/' in fps_str:
            num, den = map(int, fps_str.split('/'))
            fps = float(num / den) if den != 0 else 0.0
        else:
            fps = float(fps_str)

        metadata = {
            "duration_seconds": duration,
            "width": width,
            "height": height,
            "fps": fps,
            "has_audio": audio_stream is not None
        }
        logging.info(f"Metadata for {video_path}: {metadata}")
        return metadata

    except ffmpeg.Error as e:
        logging.error(f"ffmpeg error probing {video_path}: {e.stderr.decode('utf8') if e.stderr else str(e)}")
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred while probing {video_path}: {e}")
        return None


def extract_frames(
    video_path: str,
    start_time_sec: float,
    end_time_sec: float,
    num_frames: int = 3
) -> List[bytes]:
    """
    Extracts a specified number of evenly spaced frames from a video segment.

    Args:
        video_path: Path to the video file.
        start_time_sec: Start time of the segment in seconds.
        end_time_sec: End time of the segment in seconds.
        num_frames: Number of frames to extract.

    Returns:
        A list of byte strings, each representing a PNG image frame.
        Returns an empty list if an error occurs or no frames are extracted.
    """
    if not os.path.exists(video_path):
        logging.error(f"Frame extraction: Video file not found at {video_path}")
        return []
    if num_frames <= 0:
        logging.warning("Number of frames to extract must be positive.")
        return []
    if start_time_sec < 0 or end_time_sec < start_time_sec:
        logging.warning(f"Invalid time range for frame extraction: {start_time_sec}s to {end_time_sec}s")
        return []

    extracted_frames_bytes: List[bytes] = []

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            logging.info(f"Extracting {num_frames} frames from {video_path} "
                         f"({start_time_sec:.2f}s - {end_time_sec:.2f}s) into {temp_dir}")

            segment_duration = end_time_sec - start_time_sec
            if segment_duration < 0: segment_duration = 0 # Should be caught by earlier check

            input_stream = ffmpeg.input(video_path, ss=start_time_sec, to=end_time_sec if segment_duration > 0 else None)
            
            # If segment_duration is effectively zero (or very small), 'to' might cause issues with fps filter.
            # If 'to' is not specified, it processes until end of file from 'ss'.
            # If start_time_sec == end_time_sec, we want one frame at start_time_sec.

            if num_frames == 1 or segment_duration == 0:
                # Extract a single frame, typically at the start of the (potentially zero-duration) segment
                # The 'to' parameter might be problematic if segment_duration is 0, so we might omit it or set it carefully.
                # For a single frame, seeking to start_time_sec and taking 1 frame is robust.
                # We use a slightly modified input stream for single frame to avoid issues with 'to' if duration is 0.
                single_frame_input = ffmpeg.input(video_path, ss=start_time_sec)
                frame_filename = os.path.join(temp_dir, "frame_0001.png")
                
                process = (
                    single_frame_input
                    .output(frame_filename, vframes=1, format='image2', pix_fmt='rgb24') # rgb24 for PNG
                    .overwrite_output()
                    .run_async(pipe_stdout=True, pipe_stderr=True)
                )
                out, err = process.communicate()
                if process.returncode != 0:
                    logging.error(f"ffmpeg error extracting single frame: {err.decode('utf8')}")
                    return []
                
                if os.path.exists(frame_filename):
                    with open(frame_filename, 'rb') as f:
                        extracted_frames_bytes.append(f.read())
                    os.remove(frame_filename) # Clean up immediately

            else: # num_frames > 1 and segment_duration > 0
                # Calculate FPS for the filter to get num_frames over the segment_duration
                # Ensure fps_val is not zero if segment_duration is very small but positive
                fps_val = num_frames / segment_duration if segment_duration > 0.001 else num_frames 
                
                output_pattern = os.path.join(temp_dir, "frame_%04d.png")
                
                process = (
                    input_stream
                    .filter('fps', fps=fps_val)
                    .output(output_pattern, format='image2', pix_fmt='rgb24', start_number=0)
                    .overwrite_output()
                    .run_async(pipe_stdout=True, pipe_stderr=True)
                )
                out, err = process.communicate()

                if process.returncode != 0:
                    logging.error(f"ffmpeg error extracting multiple frames: {err.decode('utf8')}")
                    # Attempt to read any frames that might have been created before error
                
                # Read the generated frames
                for i in range(num_frames): # Check up to num_frames
                    frame_filename = os.path.join(temp_dir, f"frame_{i:04d}.png")
                    if os.path.exists(frame_filename):
                        with open(frame_filename, 'rb') as f:
                            extracted_frames_bytes.append(f.read())
                        # No need to os.remove here, TemporaryDirectory handles cleanup
                    else:
                        # If fewer frames were generated than requested (e.g., short segment or error)
                        break 
            
            if not extracted_frames_bytes:
                logging.warning(f"No frames were extracted for {video_path} in the given range.")

            logging.info(f"Successfully extracted {len(extracted_frames_bytes)} frames.")
            return extracted_frames_bytes

    except ffmpeg.Error as e:
        logging.error(f"ffmpeg error during frame extraction for {video_path}: {e.stderr.decode('utf8') if e.stderr else str(e)}")
        return []
    except Exception as e:
        logging.error(f"Unexpected error during frame extraction for {video_path}: {e}")
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
        Byte string of the WAV audio segment, or None if an error occurs.
    """
    if not os.path.exists(video_path):
        logging.error(f"Audio extraction: Video file not found at {video_path}")
        return None
    if start_time_sec < 0 or end_time_sec < start_time_sec:
        logging.warning(f"Invalid time range for audio extraction: {start_time_sec}s to {end_time_sec}s")
        return None

    segment_duration = end_time_sec - start_time_sec
    if segment_duration <= 0: # No audio to extract for zero or negative duration
        logging.info(f"Audio segment duration is zero or negative for {video_path}. Returning empty audio.")
        # Return a valid empty WAV header or None. For simplicity, let's return None.
        # Or, could return a minimal valid WAV byte string.
        return None


    temp_file_descriptor, temp_file_path = tempfile.mkstemp(suffix='.wav')
    os.close(temp_file_descriptor) # Close the descriptor, ffmpeg will open the file by path

    try:
        logging.info(f"Extracting audio from {video_path} "
                     f"({start_time_sec:.2f}s - {end_time_sec:.2f}s) into {temp_file_path}")

        input_stream = ffmpeg.input(video_path, ss=start_time_sec, to=end_time_sec)
        
        process = (
            input_stream
            .output(temp_file_path, acodec='pcm_s16le', ar=22050, ac=1) # WAV, 22.05kHz, mono
            .overwrite_output()
            .run_async(pipe_stdout=True, pipe_stderr=True)
        )
        out, err = process.communicate()

        if process.returncode != 0:
            logging.error(f"ffmpeg error extracting audio: {err.decode('utf8')}")
            return None

        if os.path.exists(temp_file_path) and os.path.getsize(temp_file_path) > 0:
            with open(temp_file_path, 'rb') as f:
                audio_bytes = f.read()
            logging.info(f"Successfully extracted audio segment to {len(audio_bytes)} bytes.")
            return audio_bytes
        else:
            logging.warning(f"No audio data extracted or temp file empty for {video_path}.")
            return None

    except ffmpeg.Error as e:
        logging.error(f"ffmpeg error during audio extraction for {video_path}: {e.stderr.decode('utf8') if e.stderr else str(e)}")
        return None
    except Exception as e:
        logging.error(f"Unexpected error during audio extraction for {video_path}: {e}")
        return None
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path) # Ensure cleanup

if __name__ == '__main__':
    # --- Example Usage (requires a test video file) ---
    # Create a dummy video file for testing if you don't have one.
    # For example, using ffmpeg CLI:
    # ffmpeg -f lavfi -i testsrc=duration=10:size=1280x720:rate=30 -f lavfi -i sine=frequency=1000:duration=10 -c:v libx264 -c:a aac -shortest test_video.mp4

    test_video = "test_video.mp4" # Replace with your test video path
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
                for i, frame_bytes in enumerate(frames):
                    with open(f"test_output_frame_{i}.png", "wb") as f_out:
                        f_out.write(frame_bytes)
                    print(f"  - Frame {i} size: {len(frame_bytes)} bytes (saved as test_output_frame_{i}.png)")
            else:
                print("Failed to extract frames or no frames found.")

            # Extract 1 frame
            print("\n--- Testing extract_frames (single frame) ---")
            single_frame_list = extract_frames(test_video, start_time_sec=2.0, end_time_sec=2.5, num_frames=1)
            if single_frame_list:
                print(f"Extracted {len(single_frame_list)} frame (single).")
                with open("test_output_single_frame.png", "wb") as f_out:
                    f_out.write(single_frame_list[0])
                print(f"  - Single frame size: {len(single_frame_list[0])} bytes (saved as test_output_single_frame.png)")

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
                with open("test_output_audio_segment.wav", "wb") as f_out:
                    f_out.write(audio)
                print("  - Audio segment saved as test_output_audio_segment.wav")
            else:
                print("Failed to extract audio segment.")
        else:
            print("Skipping audio extraction tests (video too short, no audio, or no metadata).")