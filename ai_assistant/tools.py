COMMAND_TOOLS = [
    {
        "type": "function",
        "name": "propose_add_grocery_items",
        "description": "Propose one or more grocery items for one active grocery list.",
        "strict": True,
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "shopping_list_id": {
                    "type": "integer",
                    "description": "Authorized active list ID.",
                },
                "items": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 20,
                    "description": "Items to add to the selected list.",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "item_name": {
                                "type": "string",
                                "maxLength": 255,
                                "description": "Item name.",
                            },
                            "quantity": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 99,
                                "description": "Number of items.",
                            },
                            "description": {
                                "type": "string",
                                "maxLength": 1000,
                                "description": "Optional item detail.",
                            },
                        },
                        "required": ["item_name", "quantity", "description"],
                    },
                },
            },
            "required": ["shopping_list_id", "items"],
        },
    },
    {
        "type": "function",
        "name": "propose_add_chore_task",
        "description": "Propose one task for an active chore session.",
        "strict": True,
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "chore_session_id": {
                    "type": "integer",
                    "description": "Authorized active session ID.",
                },
                "task_title": {
                    "type": "string",
                    "maxLength": 160,
                    "description": "Task title.",
                },
                "assignee_user_id": {
                    "type": ["integer", "null"],
                    "description": "Authorized household member ID or null.",
                },
            },
            "required": ["chore_session_id", "task_title", "assignee_user_id"],
        },
    },
    {
        "type": "function",
        "name": "propose_add_talk_later_topic",
        "description": "Propose one Talk Later topic.",
        "strict": True,
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "title": {
                    "type": "string",
                    "maxLength": 180,
                    "description": "Topic title.",
                },
                "notes": {
                    "type": "string",
                    "maxLength": 2000,
                    "description": "Optional notes.",
                },
                "scheduled_for": {
                    "type": ["string", "null"],
                    "description": "ISO-8601 datetime with timezone, or null.",
                },
            },
            "required": ["title", "notes", "scheduled_for"],
        },
    },
    {
        "type": "function",
        "name": "report_unresolved_command",
        "description": "Report a command that cannot safely become one addition.",
        "strict": True,
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "reason": {
                    "type": "string",
                    "enum": [
                        "unsupported_action",
                        "not_an_addition",
                        "multiple_actions",
                        "target_not_found",
                        "ambiguous_target",
                        "missing_information",
                        "invalid_datetime",
                    ],
                    "description": "Why no addition is proposed.",
                },
                "target_type": {
                    "type": "string",
                    "enum": [
                        "grocery_list",
                        "chore_session",
                        "household_member",
                        "talk_later",
                        "action",
                        "unknown",
                    ],
                    "description": "Missing or ambiguous target type.",
                },
                "requested_name": {
                    "type": "string",
                    "maxLength": 255,
                    "description": "Requested name, if any.",
                },
                "clarification_question": {
                    "type": "string",
                    "maxLength": 300,
                    "description": "Short question for the user.",
                },
            },
            "required": [
                "reason",
                "target_type",
                "requested_name",
                "clarification_question",
            ],
        },
    },
]

TOOL_NAMES = {tool["name"] for tool in COMMAND_TOOLS}
