# video_editing_agent/main.py

import os
import readline
from dotenv import load_dotenv
import logging
import json # For saving conversation history
from datetime import datetime # For unique filenames
from typing import Dict, Any
from google.genai import types # To help with type checking for serialization

# --- Detailed SDK Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logging.getLogger("genai").setLevel(logging.DEBUG)
logging.getLogger("google.api_core").setLevel(logging.DEBUG)
logging.getLogger("google.auth").setLevel(logging.DEBUG)
logging.getLogger("httpx").setLevel(logging.DEBUG)

logger = logging.getLogger(__name__)

from llm_agent import GeminiAgent

CONVERSATIONS_DIR = "conversations" # Directory to save conversations

def serialize_content_part(part: types.Part) -> Dict[str, Any]:
    """
    Serializes a single types.Part object into a dictionary for JSON.
    For binary data, it indicates presence and type rather than embedding raw bytes.
    """
    serialized_part = {}
    if part.text:
        serialized_part["type"] = "text"
        serialized_part["text"] = part.text
    elif part.inline_data:
        serialized_part["type"] = "inline_data"
        serialized_part["mime_type"] = part.inline_data.mime_type
        serialized_part["data_length_bytes"] = len(part.inline_data.data)
        # To save actual data, you'd write part.inline_data.data to a separate file
        # and reference it here, or base64 encode it.
        # For this log, we'll just note its presence and size.
        serialized_part["data_preview"] = f"<Binary data: {part.inline_data.mime_type}, {len(part.inline_data.data)} bytes>"
    elif part.function_call:
        serialized_part["type"] = "function_call"
        serialized_part["function_call"] = {
            "name": part.function_call.name,
            "args": dict(part.function_call.args)
        }
    elif part.function_response:
        serialized_part["type"] = "function_response"
        serialized_part["function_response"] = {
            "name": part.function_response.name,
            "response": dict(part.function_response.response) # Assuming response is a Struct/dict
        }
    # Add other part types if necessary (e.g., file_data)
    else:
        serialized_part["type"] = "unknown_part"
        serialized_part["content"] = str(part) # Fallback
    return serialized_part

def save_conversation_history(history: list[types.Content], base_dir: str = CONVERSATIONS_DIR):
    """
    Saves the conversation history to a JSON file.
    """
    if not history:
        print("Conversation history is empty. Nothing to save.")
        logger.info("Attempted to save empty conversation history.")
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
        logger.info(f"Conversation history saved to: {filename}")
    except Exception as e:
        print(f"Error saving conversation history: {e}")
        logger.error(f"Error saving conversation history to {filename}: {e}", exc_info=True)


def main():
    logger.info("========================================")
    logger.info(" AI Video Editing Agent (Proof of Concept) ")
    logger.info("========================================")

    load_dotenv()
    api_key = os.getenv("GOOGLE_API_KEY")

    if not api_key:
        logger.error("GOOGLE_API_KEY not found.")
        # ... (rest of API key error handling) ...
        return

    # ... (video directory input) ...
    while True:
        video_directory_path = input("\nEnter the path to your video files directory: ").strip()
        if os.path.isdir(video_directory_path):
            logger.info(f"Using video directory: {video_directory_path}")
            print(f"Using video directory: {video_directory_path}\n")
            break
        else:
            logger.error(f"Directory '{video_directory_path}' not found.")
            print(f"ERROR: Directory '{video_directory_path}' not found. Please try again.")


    try:
        agent = GeminiAgent(api_key=api_key, video_directory_path=video_directory_path)
        logger.info("AI Agent initialized successfully by main.")
        print("AI Agent initialized successfully.")
        print("Type 'quit' or 'exit' to end the session.")
        print("Type '/save' to save the current conversation history.")
        print("----------------------------------------")
    except Exception as e:
        # ... (agent init error handling) ...
        logger.error(f"Could not initialize AI Agent: {e}", exc_info=True)
        print(f"\nERROR: Could not initialize AI Agent: {e}")
        return

    conversation_history: list[types.Content] = []

    try:
        while True:
            user_prompt = input("\nPrompt> ").strip()

            if user_prompt.lower() in ["quit", "exit"]:
                logger.info("User requested to quit.")
                print("Exiting agent...")
                break
            
            if user_prompt.lower() == "/save":
                save_conversation_history(conversation_history)
                continue # Go to next prompt without processing /save as LLM input

            if not user_prompt:
                continue

            logger.info("Agent processing started by main.")
            print("\n🤖 Agent is thinking...")
            try:
                assistant_response_text, updated_history = agent.process_prompt(
                    user_prompt_text=user_prompt,
                    conversation_history=conversation_history
                )
                conversation_history = updated_history # Persist the updated history

                logger.info(f"Assistant final response: '{assistant_response_text}'")
                print("\nAssistant:")
                print(assistant_response_text)
                print("----------------------------------------")

            except Exception as e:
                logger.error(f"An error occurred while agent was processing prompt: {e}", exc_info=True)
                print(f"\nERROR: An error occurred while processing your prompt: {e}")

    except KeyboardInterrupt:
        logger.info("Exiting agent due to KeyboardInterrupt.")
        print("\nExiting agent due to KeyboardInterrupt...")
    finally:
        logger.info("========================================")
        logger.info("         Session Ended")
        logger.info("========================================")
        print("========================================")
        print("         Session Ended")
        print("========================================")

if __name__ == "__main__":
    main()