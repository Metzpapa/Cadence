# video_editing_agent/main.py

import os
import readline # For better input experience
from dotenv import load_dotenv
import logging
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from google.genai import types

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
app_logger = logging.getLogger(__name__)

DEBUG_MODE_ENABLED = False
SDK_LOGGERS_TO_CONTROL = ["genai", "google.api_core", "google.auth", "httpx"]
APP_MODULE_LOGGERS_TO_CONTROL = [
    "llm_agent",
    "tools.file_system_tool",
    "tools.view_tool",
    "tools.save_video_segment_tool", # Added for new tool
    "utils.ffmpeg_utils"
]

def set_log_levels(is_debug_mode: bool):
    global DEBUG_MODE_ENABLED
    DEBUG_MODE_ENABLED = is_debug_mode
    sdk_level = logging.DEBUG if is_debug_mode else logging.WARNING
    app_module_level = logging.DEBUG if is_debug_mode else logging.INFO
    for sdk_logger_name in SDK_LOGGERS_TO_CONTROL:
        logging.getLogger(sdk_logger_name).setLevel(sdk_level)
    for app_module_logger_name in APP_MODULE_LOGGERS_TO_CONTROL:
        logging.getLogger(app_module_logger_name).setLevel(app_module_level)
    if is_debug_mode:
        app_logger.info("DEBUG logging ENABLED for SDKs and App Modules.")
    else:
        app_logger.info("Default logging levels set (SDKs at WARNING, App Modules at INFO).")

set_log_levels(DEBUG_MODE_ENABLED) # Initial call

from llm_agent import GeminiAgent

CONVERSATIONS_DIR = "conversations"
SAVED_CLIPS_DIR = "saved_clips" # Directory where clips will be saved by the new tool

def serialize_content_part(part: types.Part) -> Dict[str, Any]:
    serialized_part = {}
    if part.text:
        serialized_part["type"] = "text"
        serialized_part["text"] = part.text
    elif part.inline_data:
        serialized_part["type"] = "inline_data"
        serialized_part["mime_type"] = part.inline_data.mime_type
        # Avoid serializing full data for brevity in JSON log
        serialized_part["data_length_bytes"] = len(part.inline_data.data)
        serialized_part["data_preview"] = f"<Binary data: {part.inline_data.mime_type}, {len(part.inline_data.data)} bytes>"
    elif part.function_call:
        serialized_part["type"] = "function_call"
        serialized_part["function_call"] = {
            "name": part.function_call.name,
            "args": dict(part.function_call.args) # Ensure args are dict
        }
    elif part.function_response:
        serialized_part["type"] = "function_response"
        serialized_part["function_response"] = {
            "name": part.function_response.name,
            # Ensure response is dict, it should be JSON serializable
            "response": dict(part.function_response.response) if hasattr(part.function_response.response, 'items') else part.function_response.response
        }
    else:
        serialized_part["type"] = "unknown_part"
        serialized_part["content"] = str(part) # Fallback
    return serialized_part

def save_conversation_history(history: List[types.Content], base_dir: str = CONVERSATIONS_DIR):
    if not history:
        print("Conversation history is empty. Nothing to save.")
        app_logger.info("Attempted to save empty conversation history.")
        return

    os.makedirs(base_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(base_dir, f"conversation_{timestamp}.json")

    serialized_history = []
    for content_message in history:
        message_dict = {
            "role": content_message.role,
            "parts": [serialize_content_part(part) for part in content_message.parts]
        }
        serialized_history.append(message_dict)

    try:
        with open(filename, "w") as f:
            json.dump(serialized_history, f, indent=2)
        print(f"Conversation history saved to: {filename}")
        app_logger.info(f"Conversation history saved to: {filename}")
    except Exception as e:
        print(f"Error saving conversation history: {e}")
        app_logger.error(f"Error saving conversation history to {filename}: {e}", exc_info=True)

def main():
    app_logger.info("========================================")
    app_logger.info(" AI Video Editing Agent (Proof of Concept) ")
    app_logger.info("========================================")

    load_dotenv()
    api_key = os.getenv("GOOGLE_API_KEY")

    if not api_key:
        app_logger.error("GOOGLE_API_KEY not found.")
        print("\nERROR: GOOGLE_API_KEY not found in environment variables.")
        print("Please set it in a .env file or your system environment.")
        return

    while True:
        video_directory_path = input("\nEnter the path to your video files directory: ").strip()
        if os.path.isdir(video_directory_path):
            app_logger.info(f"Using video directory: {video_directory_path}")
            print(f"Using video directory: {video_directory_path}\n")
            break
        else:
            app_logger.error(f"Directory '{video_directory_path}' not found.")
            print(f"ERROR: Directory '{video_directory_path}' not found. Please try again.")

    # Ensure SAVED_CLIPS_DIR exists (or will be created by the tool)
    # For clarity, we can also ensure it here.
    try:
        os.makedirs(SAVED_CLIPS_DIR, exist_ok=True)
        app_logger.info(f"Ensured directory for saved clips exists: {os.path.abspath(SAVED_CLIPS_DIR)}")
        print(f"Note: Trimmed video clips will be saved in: ./{SAVED_CLIPS_DIR}/")
    except Exception as e:
        app_logger.error(f"Could not create directory '{SAVED_CLIPS_DIR}': {e}")
        print(f"Warning: Could not create directory '{SAVED_CLIPS_DIR}'. Saving clips might fail.")


    try:
        agent = GeminiAgent(api_key=api_key, video_directory_path=video_directory_path)
        app_logger.info("AI Agent initialized successfully by main.")
        print("AI Agent initialized successfully.")
        print("Type 'quit' or 'exit' to end the session.")
        print("Type '/save' to save the current conversation history.")
        print(f"Type '/debug' to toggle detailed logging (Currently: {'ON' if DEBUG_MODE_ENABLED else 'OFF'}).")
        print("----------------------------------------")
    except Exception as e:
        app_logger.error(f"Could not initialize AI Agent: {e}", exc_info=True)
        print(f"\nERROR: Could not initialize AI Agent: {e}")
        return

    conversation_history: List[types.Content] = []

    try:
        while True:
            user_prompt = input("\nPrompt> ").strip()

            if user_prompt.lower() in ["quit", "exit"]:
                app_logger.info("User requested to quit.")
                print("Exiting agent...")
                break
            
            if user_prompt.lower() == "/save":
                save_conversation_history(conversation_history)
                continue
            
            if user_prompt.lower() == "/debug":
                set_log_levels(not DEBUG_MODE_ENABLED)
                print(f"Detailed logging is now {'ON' if DEBUG_MODE_ENABLED else 'OFF'}.")
                continue

            if not user_prompt:
                continue

            app_logger.info("Agent processing started by main.")
            print("\n🤖 Agent is thinking...")
            try:
                assistant_response_text, updated_history = agent.process_prompt(
                    user_prompt_text=user_prompt,
                    conversation_history=conversation_history # Pass the current history
                )
                conversation_history = updated_history # Update history with the new state

                print("\nAssistant:")
                print(assistant_response_text)
                print("----------------------------------------")

            except Exception as e:
                app_logger.error(f"An error occurred while agent was processing prompt: {e}", exc_info=True)
                print(f"\nERROR: An error occurred while processing your prompt: {e}")

    except KeyboardInterrupt:
        app_logger.info("Exiting agent due to KeyboardInterrupt.")
        print("\nExiting agent due to KeyboardInterrupt...")
    finally:
        app_logger.info("========================================")
        app_logger.info("         Session Ended")
        app_logger.info("========================================")
        print("\n========================================")
        print("         Session Ended")
        print("========================================")

if __name__ == "__main__":
    main()