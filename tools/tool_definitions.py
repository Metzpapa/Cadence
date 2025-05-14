# video_editing_agent/tools/tool_definitions.py

from google.genai import types # For FunctionDeclaration, Schema, Tool

# --- Tool Name Constants ---
FILE_DIRECTORY_TOOL_NAME = "list_directory_contents"
VIEW_TOOL_NAME = "view_video_segment"
SAVE_VIDEO_SEGMENT_TOOL_NAME = "save_video_segment" # New

# --- Function Declarations ---

# 1. File Directory Tool Declaration
FILE_DIRECTORY_TOOL_DECLARATION = types.FunctionDeclaration(
    name=FILE_DIRECTORY_TOOL_NAME,
    description=(
        "Lists video files and their basic metadata (like duration, resolution) "
        "from the pre-configured video directory. This tool does not take any parameters."
    ),
    parameters=types.Schema(
        type="OBJECT", # Corrected: Use string literal as per Pydantic validation and report
        properties={},
        required=[]
    )
)

# 2. View Video Segment Tool Declaration
VIEW_TOOL_DECLARATION = types.FunctionDeclaration(
    name=VIEW_TOOL_NAME,
    description=(
        "Extracts a specified number of visual frames and associated audio segments "
        "from a given video file within a defined time range. "
        "The tool will first return a status message. The actual image frames and audio snippets "
        "will then be provided for you to describe. You can specify a quality level for the extracted frames."
    ),
    parameters=types.Schema(
        type="OBJECT", # Corrected: Use string literal
        properties={
            "file_name": types.Schema(
                type="STRING", # Corrected: Use string literal
                description="The name of the video file (e.g., 'my_vacation.mp4') located in the configured directory."
            ),
            "start_time": types.Schema(
                type="STRING", # Corrected: Use string literal
                description="The start time of the segment to view, in HH:MM:SS or HH:MM:SS.mmm format (e.g., '00:01:30' or '00:01:30.500')."
            ),
            "end_time": types.Schema(
                type="STRING", # Corrected: Use string literal
                description="The end time of the segment to view, in HH:MM:SS or HH:MM:SS.mmm format (e.g., '00:02:00')."
            ),
            "num_frames": types.Schema(
                type="INTEGER", # Corrected: Use string literal
                description=(
                    "The number of frames to evenly sample from the specified time range. "
                    "This also influences how the total audio of the video is segmented and associated with these frames. "
                    "For example, if 3 frames are requested for the whole video, the audio will be split into 3 corresponding parts. "
                    "Default is 3 if not specified."
                )
            ),
            "quality": types.Schema( # New parameter
                type="STRING",
                description=(
                    "Optional. The desired quality (resolution) for the extracted frames. "
                    "Options: 'low' (~480p width), 'medium' (~720p width), 'high' (~1080p width, capped at original). "
                    "Defaults to 'low' if not specified."
                ),
                enum=["low", "medium", "high"] # Specify allowed values
            )
        },
        required=["file_name", "start_time", "end_time"] # num_frames and quality are optional
    )
)

# 3. Save Video Segment Tool Declaration (New)
SAVE_VIDEO_SEGMENT_TOOL_DECLARATION = types.FunctionDeclaration(
    name=SAVE_VIDEO_SEGMENT_TOOL_NAME,
    description=(
        "Trims a segment from a source video file based on start and end times and saves it as a new video file. "
        "The new file will be saved in a dedicated 'saved_clips' directory relative to where the agent is run. "
        "The tool re-encodes the segment to ensure frame accuracy and wide compatibility (MP4, H.264/AAC)."
    ),
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "source_file_name": types.Schema(
                type="STRING",
                description="The name of the original video file (e.g., 'GOPR0419.MP4') located in the configured video directory."
            ),
            "start_time": types.Schema(
                type="STRING",
                description="The start time of the segment to save, in HH:MM:SS or HH:MM:SS.mmm format (e.g., '00:01:30')."
            ),
            "end_time": types.Schema(
                type="STRING",
                description="The end time of the segment to save, in HH:MM:SS or HH:MM:SS.mmm format (e.g., '00:02:00')."
            ),
            "output_file_name": types.Schema(
                type="STRING",
                description="The desired name for the new trimmed video file (e.g., 'my_saved_clip.mp4'). Ensure it includes the .mp4 extension."
            )
        },
        required=["source_file_name", "start_time", "end_time", "output_file_name"]
    )
)

# --- Tool Configuration ---
TOOL_CONFIG = types.Tool(
    function_declarations=[
        FILE_DIRECTORY_TOOL_DECLARATION,
        VIEW_TOOL_DECLARATION,
        SAVE_VIDEO_SEGMENT_TOOL_DECLARATION, # New
    ]
)

if __name__ == '__main__':
    print("--- Tool Definitions ---")
    print(f"Tool Config: {TOOL_CONFIG}\n")
    print(f"File Directory Tool Name: {FILE_DIRECTORY_TOOL_NAME}")
    print(f"File Directory Tool Declaration: {FILE_DIRECTORY_TOOL_DECLARATION}\n")
    print(f"View Tool Name: {VIEW_TOOL_NAME}")
    print(f"View Tool Declaration: {VIEW_TOOL_DECLARATION}\n")
    print(f"Save Video Segment Tool Name: {SAVE_VIDEO_SEGMENT_TOOL_NAME}")
    print(f"Save Video Segment Tool Declaration: {SAVE_VIDEO_SEGMENT_TOOL_DECLARATION}\n")

    if VIEW_TOOL_DECLARATION.parameters:
        print("View Tool Parameters Schema:")
        if VIEW_TOOL_DECLARATION.parameters.properties:
            for prop_name, prop_schema in VIEW_TOOL_DECLARATION.parameters.properties.items():
                print(f"  - {prop_name}:")
                print(f"      Type: {prop_schema.type}")
                print(f"      Description: {prop_schema.description}")
        if VIEW_TOOL_DECLARATION.parameters.required:
            print(f"  Required: {VIEW_TOOL_DECLARATION.parameters.required}")

    if SAVE_VIDEO_SEGMENT_TOOL_DECLARATION.parameters:
        print("\nSave Video Segment Tool Parameters Schema:")
        if SAVE_VIDEO_SEGMENT_TOOL_DECLARATION.parameters.properties:
            for prop_name, prop_schema in SAVE_VIDEO_SEGMENT_TOOL_DECLARATION.parameters.properties.items():
                print(f"  - {prop_name}:")
                print(f"      Type: {prop_schema.type}")
                print(f"      Description: {prop_schema.description}")
        if SAVE_VIDEO_SEGMENT_TOOL_DECLARATION.parameters.required:
            print(f"  Required: {SAVE_VIDEO_SEGMENT_TOOL_DECLARATION.parameters.required}")