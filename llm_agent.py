# video_editing_agent/llm_agent.py

import logging
from google.genai import types # Correct import for google-genai package
from google import genai # For genai.Client

# Tool definitions and implementations
from tools.tool_definitions import TOOL_CONFIG, FILE_DIRECTORY_TOOL_NAME, VIEW_TOOL_NAME
from tools import file_system_tool
from tools import view_tool

# Model name from the research report
MODEL_NAME = "gemini-2.5-pro-preview-05-06"

# Maximum number of consecutive tool calls before halting
MAX_TOOL_ITERATIONS = 50 # Increased as per previous discussion

# Configure logging for better traceability (application level)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__) # Use a logger specific to this module

class GeminiAgent:
    """
    The GeminiAgent class handles interactions with the Google Gemini API,
    including managing conversation history and tool usage.
    """
    def __init__(self, api_key: str, video_directory_path: str):
        """
        Initializes the Gemini Agent.

        Args:
            api_key: The Google API key for accessing Gemini.
            video_directory_path: The path to the directory containing video files.
        """
        try:
            self.client = genai.Client(api_key=api_key)
            logger.info("Google GenAI Client initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Google GenAI Client: {e}")
            raise

        self.video_directory_path = video_directory_path
        self.tool_config_for_api = TOOL_CONFIG

        self.generate_content_config_obj = types.GenerateContentConfig(
            tools=[self.tool_config_for_api],
            system_instruction=(
                "You are an AI video editing assistant. With tools. "
                "You can list video files and view segments of videos (frames and audio). "
                "When viewing videos, clearly state what you are seeing and hearing from the provided frames and audio snippets. "
                "Be precise about timestamps if they are available with the frames. "
                "If a tool call fails or returns an error, inform the user about the error."
                "If a user askes you to to do something, keep using your tools until you have completed the task."
            )
        )
        logger.info(f"GeminiAgent initialized with model: {MODEL_NAME}, tools, and system instruction.")

    def _invoke_tool(self, tool_name: str, tool_args: dict) -> dict:
        """
        Invokes the appropriate Python function for the given tool name and arguments.
        Returns a dictionary: {"status_json": {...}, "images": [...], "audios": [...]}.
        """
        logger.info(f"Invoking tool: {tool_name} with args: {tool_args}")
        media_data = {
            "status_json": {},
            "images": [],
            "audios": []
        }
        try:
            if tool_name == FILE_DIRECTORY_TOOL_NAME:
                result_str = file_system_tool.list_directory_contents_impl(self.video_directory_path)
                media_data["status_json"] = {"result": result_str}
            elif tool_name == VIEW_TOOL_NAME:
                raw_media_output = view_tool.view_video_segment_impl(
                    video_directory_path=self.video_directory_path,
                    **tool_args
                )
                media_data["status_json"] = raw_media_output.get("status_json", {"error": "Tool implementation error: missing status_json"})
                media_data["images"] = raw_media_output.get("images", [])
                media_data["audios"] = raw_media_output.get("audios", [])
            else:
                logger.warning(f"Unknown tool called: {tool_name}")
                media_data["status_json"] = {"error": f"Unknown tool: {tool_name}"}
        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}", exc_info=True)
            media_data["status_json"] = {"error": f"Error in tool {tool_name}: {str(e)}"}
        return media_data

    def _build_function_response_with_media(self, tool_name: str, media_data: dict) -> types.Content:
        """
        Builds a single types.Content object for the function response,
        including the JSON status and any associated media parts.
        Uses Part.from_bytes for raw byte data.
        """
        parts = []
        parts.append(types.Part.from_function_response(
            name=tool_name,
            response=media_data["status_json"]
        ))

        for img_bytes in media_data.get("images", []):
            if not isinstance(img_bytes, bytes):
                logger.error(f"Invalid image data type for tool {tool_name}: {type(img_bytes)}. Expected bytes.")
                continue
            parts.append(types.Part.from_bytes(data=img_bytes, mime_type="image/png"))
            logger.info(f"Added image part (using from_bytes) to function response for tool {tool_name}")

        for audio_bytes in media_data.get("audios", []):
            if not isinstance(audio_bytes, bytes):
                logger.error(f"Invalid audio data type for tool {tool_name}: {type(audio_bytes)}. Expected bytes.")
                continue
            parts.append(types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav"))
            logger.info(f"Added audio part (using from_bytes) to function response for tool {tool_name}")

        return types.Content(role="function", parts=parts)

    def process_prompt(self, user_prompt_text: str, conversation_history: list[types.Content]) -> tuple[str, list[types.Content]]:
        """
        Processes a user prompt, interacts with the Gemini model, handles tool calls,
        and manages conversation history.
        """
        if not isinstance(user_prompt_text, str):
            logger.error(f"User prompt text is not a string: {user_prompt_text}")
            return "Error: Internal prompt handling error.", conversation_history

        user_text_part = types.Part.from_text(text=user_prompt_text)
        current_user_content = types.Content(parts=[user_text_part], role="user")
        conversation_history.append(current_user_content)
        logger.info(f"User prompt: '{user_prompt_text}' (History length: {len(conversation_history)})")

        for iteration in range(MAX_TOOL_ITERATIONS):
            logger.info(f"Generation call iteration: {iteration + 1}")

            # --- Count Tokens based on the current complete history ---
            try:
                # Model name for count_tokens needs "models/" prefix
                token_count_response = self.client.models.count_tokens(
                    model=f"models/{MODEL_NAME}",
                    contents=conversation_history # Count tokens for the entire history to be sent
                )
                total_tokens = token_count_response.total_tokens
                logger.info(f"Token count for current request: {total_tokens} tokens.")
                # Example: Warn if approaching a hypothetical 1.8M token operational limit for context
                if total_tokens > 1_800_000:
                    logger.warning(f"Approaching token context limit! Current tokens: {total_tokens}")
            except Exception as e:
                logger.error(f"Error counting tokens: {e}", exc_info=True)
                # Decide if you want to proceed or halt; for now, log and proceed

            # --- Generate Content ---
            try:
                # Model name for generate_content is just the ID
                response = self.client.models.generate_content(
                    model=MODEL_NAME,
                    contents=conversation_history, # Send the current complete history
                    config=self.generate_content_config_obj
                )
            except Exception as e:
                logger.error(f"Error calling Gemini API: {e}", exc_info=True)
                return f"An error occurred while communicating with the AI: {e}", conversation_history

            if not response.candidates:
                logger.error("No candidates received from Gemini API.")
                return "Error: No response from AI.", conversation_history
            
            candidate = response.candidates[0]
            model_content = candidate.content # This is the model's response (text or function call request)

            has_function_call = False
            tool_name = ""
            tool_args = {}

            # Check for function call
            if hasattr(response, 'function_calls') and response.function_calls:
                fc_response_obj = response.function_calls[0]
                tool_name = fc_response_obj.name
                tool_args = dict(fc_response_obj.args)
                has_function_call = True
            elif model_content and model_content.parts and model_content.parts[0].function_call:
                fc_part_obj = model_content.parts[0].function_call
                tool_name = fc_part_obj.name
                tool_args = dict(fc_part_obj.args)
                has_function_call = True

            if not has_function_call:
                logger.info("Model provided a direct text response.")
                if model_content:
                    conversation_history.append(model_content) # Add model's text response to history
                
                response_text = ""
                if model_content and model_content.parts:
                    for part in model_content.parts:
                        if part.text:
                            response_text += part.text
                
                if not response_text and candidate.finish_reason.name != "STOP":
                    response_text = f"(Model finished with reason: {candidate.finish_reason.name})"
                elif not response_text:
                    response_text = "(The AI did not provide a text response.)"
                
                logger.info(f"Returning direct text. History length: {len(conversation_history)}")
                return response_text, conversation_history # Exit loop and return

            # --- Function Call Detected ---
            logger.info(f"Function call detected: {tool_name}")
            if model_content: # Append the model's request to call the function
                conversation_history.append(model_content)
            else:
                logger.error("Function call detected but model_content was None. This is unexpected.")
                placeholder_fc_part = types.Part.from_function_call(name=tool_name, args=tool_args)
                placeholder_fc_request = types.Content(parts=[placeholder_fc_part], role="model")
                conversation_history.append(placeholder_fc_request)
            
            logger.info(f"History length after appending func call: {len(conversation_history)}")

            media_data = self._invoke_tool(tool_name, tool_args)
            function_response_content = self._build_function_response_with_media(tool_name, media_data)
            
            conversation_history.append(function_response_content) # Append tool's response to history
            logger.info(f"Appended function response for {tool_name}. History length: {len(conversation_history)}. Continuing loop.")
            # Loop continues, history is now updated for the next iteration's token count and API call

        # If loop finishes due to max iterations
        logger.warning(f"Max tool iterations ({MAX_TOOL_ITERATIONS}) reached. History length: {len(conversation_history)}")
        return "Max tool iterations reached. The AI could not complete the request with the available tools.", conversation_history