import logging
from typing import Dict, Any, Callable, Optional
from detection_store import DetectionStore
import tools

logger = logging.getLogger(__name__)

LOCAL_TOOLS: Dict[str, Callable[..., Dict[str, Any]]] = {
    "get_active_objects": tools.get_active_objects,
    "get_recent_objects": tools.get_recent_objects,
    "get_object_summary": tools.get_object_summary,
    "get_recent_events": tools.get_recent_events,
    "request_toilet_guide": tools.request_toilet_guide,
    "request_lab_guide": tools.request_lab_guide,
}

class ToolDispatcher:
    def __init__(self, store: Optional[DetectionStore] = None):
        self.store = store

    def dispatch(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Dispatches a tool call by name with given arguments.
        Returns a dict payload suitable for LLM function response.
        """
        if arguments is None:
            arguments = {}

        if tool_name not in LOCAL_TOOLS:
            logger.warning(f"Unknown tool name requested: {tool_name}")
            return {
                "error": f"Unknown tool: '{tool_name}'. Available tools: {list(LOCAL_TOOLS.keys())}"
            }

        func = LOCAL_TOOLS[tool_name]

        # Prepare kwargs
        kwargs = dict(arguments)
        if self.store is not None:
            kwargs["store"] = self.store

        # Input validation
        try:
            if "seconds" in kwargs and kwargs["seconds"] is not None:
                try:
                    kwargs["seconds"] = int(kwargs["seconds"])
                except (ValueError, TypeError):
                    return {"error": f"Invalid type for 'seconds': {kwargs['seconds']}. Must be integer between 1 and 60."}
                
                if not (1 <= kwargs["seconds"] <= 60):
                    return {"error": f"Invalid value for 'seconds': {kwargs['seconds']}. Must be between 1 and 60."}

            if "min_confidence" in kwargs and kwargs["min_confidence"] is not None:
                try:
                    kwargs["min_confidence"] = float(kwargs["min_confidence"])
                except (ValueError, TypeError):
                    return {"error": f"Invalid type for 'min_confidence': {kwargs['min_confidence']}."}

            if "event_type" in kwargs and kwargs["event_type"] is not None:
                valid_types = ("OBJECT_APPEARED", "OBJECT_DISAPPEARED")
                if kwargs["event_type"] not in valid_types:
                    return {"error": f"Invalid event_type '{kwargs['event_type']}'. Must be one of {valid_types}."}

            logger.info(f"Dispatching tool '{tool_name}' with args {arguments}")
            result = func(**kwargs)
            return result

        except Exception as e:
            logger.error(f"Error executing tool '{tool_name}': {e}", exc_info=True)
            return {"error": f"Tool execution failed: {str(e)}"}
