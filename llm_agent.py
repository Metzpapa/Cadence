# video_editing_agent/llm_agent.py

import logging
from google.genai import types
from google import genai

from tools.tool_definitions import (
    TOOL_CONFIG,
    FILE_DIRECTORY_TOOL_NAME,
    VIEW_TOOL_NAME,
    SAVE_VIDEO_SEGMENT_TOOL_NAME # Added
)
from tools import file_system_tool
from tools import view_tool
from tools import save_video_segment_tool # New import

MODEL_NAME = "gemini-2.5-pro-preview-05-06"
MAX_TOOL_ITERATIONS = 10

logger = logging.getLogger(__name__)

class GeminiAgent:
    def __init__(self, api_key: str, video_directory_path: str):
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
            system_instruction="""
You are an Agentic Video Editor named Codec. When given a task you should do everything possible to complete the task without asking the user for clarification. Only ask for clarification when you deem it is absolutely necessary. This means you should make multiple tool calls. For example if the user asks you to edit the video titled dog walking, you should first list the videos find the exact one, and then view it. 

You have tools to:
- list video files,
- view segments of these videos,
- save segments of videos to new files.

When the 'view_video_segment' tool is used, it will first indicate success.
Then, image and audio data will be provided to you in a user message.
Your task is to provide a detailed description of the visual content of all provided image frames
and the audible content of the audio segment.
Do not output any other preliminary text or metadata before this description.
After describing, you can then suggest next steps or ask clarifying questions.

When the 'save_video_segment' tool is used, it will return a status message indicating success (including the path to the saved file) or failure.

If a tool call fails, inform the user.
"""
        )
        logger.info(f"GeminiAgent initialized with model: {MODEL_NAME}, tools, and system instruction.")

    def _invoke_tool(self, tool_name: str, tool_args: dict) -> dict:
        logger.info(f"Invoking tool: {tool_name} with args: {tool_args}")
        media_data = { # This structure is mainly for view_tool, but we use status_json for all
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
            elif tool_name == SAVE_VIDEO_SEGMENT_TOOL_NAME: # New tool handling
                status_result = save_video_segment_tool.save_video_segment_impl(
                    video_directory_path=self.video_directory_path, # Pass the source video directory
                    **tool_args
                )
                media_data["status_json"] = status_result
                # This tool does not return media directly to the LLM for description,
                # so images and audios lists remain empty.
            else:
                logger.warning(f"Unknown tool called: {tool_name}")
                media_data["status_json"] = {"error": f"Unknown tool: {tool_name}"}
        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}", exc_info=True)
            media_data["status_json"] = {"error": f"Error in tool {tool_name}: {str(e)}"}
        return media_data

    def _build_function_response_json_only(self, tool_name: str, status_json: dict) -> types.Content:
        logger.debug(f"Building JSON-only function response for {tool_name} with status: {status_json}")
        part = types.Part.from_function_response(
            name=tool_name,
            response=status_json
        )
        return types.Content(role="function", parts=[part])

    def _build_user_media_message(self, media_data: dict, prompt_text: str) -> types.Content:
        logger.debug(f"Building user media message with prompt: '{prompt_text}'")
        parts = [types.Part.from_text(text=prompt_text)]

        for img_bytes in media_data.get("images", []):
            if not isinstance(img_bytes, bytes):
                logger.error(f"Invalid image data type: {type(img_bytes)}. Expected bytes.")
                continue
            parts.append(types.Part.from_bytes(data=img_bytes, mime_type="image/png"))
            logger.info("Added image part to user media message.")

        for audio_bytes in media_data.get("audios", []):
            if not isinstance(audio_bytes, bytes):
                logger.error(f"Invalid audio data type: {type(audio_bytes)}. Expected bytes.")
                continue
            parts.append(types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav"))
            logger.info("Added audio part to user media message.")
        
        return types.Content(role="user", parts=parts)

    def process_prompt(self, user_prompt_text: str, conversation_history: list[types.Content]) -> tuple[str, list[types.Content]]:
        if not isinstance(user_prompt_text, str):
            logger.error(f"User prompt text is not a string: {user_prompt_text}")
            return "Error: Internal prompt handling error.", conversation_history

        user_text_part = types.Part.from_text(text=user_prompt_text)
        current_user_content = types.Content(parts=[user_text_part], role="user")
        conversation_history.append(current_user_content)
        logger.info(f"User prompt: '{user_prompt_text}' (History length: {len(conversation_history)})")

        for iteration in range(MAX_TOOL_ITERATIONS):
            logger.info(f"Generation call iteration: {iteration + 1}")

            try:
                token_count_response = self.client.models.count_tokens(
                    model=f"models/{MODEL_NAME}", contents=conversation_history
                )
                total_tokens = token_count_response.total_tokens
                logger.info(f"Token count for current request: {total_tokens} tokens.")
                if total_tokens > 1_800_000: # Example limit
                    logger.warning(f"Approaching token context limit! Current tokens: {total_tokens}")
            except Exception as e:
                logger.error(f"Error counting tokens: {e}", exc_info=True)

            try:
                response = self.client.models.generate_content(
                    model=MODEL_NAME, contents=conversation_history, config=self.generate_content_config_obj
                )
            except Exception as e:
                logger.error(f"Error calling Gemini API: {e}", exc_info=True)
                return f"An error occurred while communicating with the AI: {e}", conversation_history

            if not response.candidates:
                logger.error("No candidates received from Gemini API.")
                return "Error: No response from AI.", conversation_history
            
            candidate = response.candidates[0]
            model_content = candidate.content

            has_function_call = False
            tool_name = ""
            tool_args = {}

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
                logger.info(f"Model provided a direct text response. Finish reason: {candidate.finish_reason.name if candidate.finish_reason else 'N/A'}")
                if model_content:
                    conversation_history.append(model_content)
                
                response_text = ""
                if model_content and model_content.parts:
                    for part in model_content.parts:
                        if part.text:
                            response_text += part.text
                
                if not response_text and (candidate.finish_reason.name if candidate.finish_reason else "") != "STOP":
                    response_text = f"(Model finished with reason: {candidate.finish_reason.name if candidate.finish_reason else 'Unknown'})"
                elif not response_text:
                    response_text = "(The AI did not provide a text response.)"
                
                logger.info(f"Returning direct text: '{response_text}'. History length: {len(conversation_history)}")
                return response_text, conversation_history

            logger.info(f"Function call detected: {tool_name}")
            if model_content:
                conversation_history.append(model_content)
            else:
                logger.error("Function call detected but model_content was None. Creating placeholder for model's request.")
                placeholder_fc_part = types.Part.from_function_call(name=tool_name, args=tool_args)
                placeholder_fc_request = types.Content(parts=[placeholder_fc_part], role="model")
                conversation_history.append(placeholder_fc_request)
            
            logger.info(f"History length after appending func call: {len(conversation_history)}")

            media_data = self._invoke_tool(tool_name, tool_args)

            json_only_response_content = self._build_function_response_json_only(
                tool_name, media_data["status_json"]
            )
            conversation_history.append(json_only_response_content)
            logger.info(f"Appended JSON-only function response for {tool_name}. History length: {len(conversation_history)}")

            if media_data.get("images") or media_data.get("audios"):
                user_media_prompt = (
                    f"The tool '{tool_name}' has provided media output. "
                    "Please describe the visual content of the provided frames and the audible content of the audio segment."
                )
                user_media_message_content = self._build_user_media_message(media_data, user_media_prompt)
                conversation_history.append(user_media_message_content)
                logger.info(f"Appended user media message for {tool_name}. History length: {len(conversation_history)}")
            
            logger.info(f"Continuing loop after processing tool {tool_name}.")

        logger.warning(f"Max tool iterations ({MAX_TOOL_ITERATIONS}) reached. History length: {len(conversation_history)}")
        return "Max tool iterations reached. The AI could not complete the request with the available tools.", conversation_history