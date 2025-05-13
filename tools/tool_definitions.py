# video_editing_agent/tools/tool_definitions.py

from google.genai import types # For FunctionDeclaration, Schema, Tool

# --- Tool Name Constants ---
FILE_DIRECTORY_TOOL_NAME = "list_directory_contents"
VIEW_TOOL_NAME = "view_video_segment"

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
        "will then be provided for you to describe."
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
            )
        },
        required=["file_name", "start_time", "end_time"] # num_frames is optional
    )
)

# --- Tool Configuration ---
TOOL_CONFIG = types.Tool(
    function_declarations=[
        FILE_DIRECTORY_TOOL_DECLARATION,
        VIEW_TOOL_DECLARATION,
    ]
)

if __name__ == '__main__':
    print("--- Tool Definitions ---")
    print(f"Tool Config: {TOOL_CONFIG}\n")
    print(f"File Directory Tool Name: {FILE_DIRECTORY_TOOL_NAME}")
    print(f"File Directory Tool Declaration: {FILE_DIRECTORY_TOOL_DECLARATION}\n")
    print(f"View Tool Name: {VIEW_TOOL_NAME}")
    print(f"View Tool Declaration: {VIEW_TOOL_DECLARATION}\n")

    if VIEW_TOOL_DECLARATION.parameters:
        print("View Tool Parameters Schema:")
        if VIEW_TOOL_DECLARATION.parameters.properties:
            for prop_name, prop_schema in VIEW_TOOL_DECLARATION.parameters.properties.items():
                print(f"  - {prop_name}:")
                print(f"      Type: {prop_schema.type}") # This will now print the string literal
                print(f"      Description: {prop_schema.description}")
        if VIEW_TOOL_DECLARATION.parameters.required:
            print(f"  Required: {VIEW_TOOL_DECLARATION.parameters.required}")