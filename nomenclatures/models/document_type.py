# nomenclatures/schemas/document_type.py

"""
JSON Schema definitions for DocumentType validation

Този файл дефинира схемите за валидация на JSON полетата в DocumentType модела.
Цел: Да имаме строга валидация на конфигурационните данни.
"""

# Workflow configuration schema
WORKFLOW_CONFIG_SCHEMA = {
    "type": "object",
    "required": ["states", "transitions", "initial_state"],
    "additionalProperties": False,
    "properties": {
        "states": {
            "type": "object",
            "minProperties": 1,
            "patternProperties": {
                "^[a-z][a-z0-9_]*$": {  # state names: lowercase, underscore allowed
                    "type": "object",
                    "required": ["label"],
                    "additionalProperties": False,
                    "properties": {
                        "label": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 50
                        },
                        "description": {
                            "type": "string",
                            "maxLength": 200
                        },
                        "is_final": {
                            "type": "boolean",
                            "default": False
                        },
                        "allows_editing": {
                            "type": "boolean",
                            "default": True
                        },
                        "color": {
                            "type": "string",
                            "pattern": "^#[0-9A-Fa-f]{6}$"  # hex color
                        },
                        "icon": {
                            "type": "string",
                            "maxLength": 20
                        }
                    }
                }
            }
        },
        "transitions": {
            "type": "object",
            "patternProperties": {
                "^[a-z][a-z0-9_]*$": {  # from_state names
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["to"],
                        "additionalProperties": False,
                        "properties": {
                            "to": {
                                "type": "string",
                                "pattern": "^[a-z][a-z0-9_]*$"
                            },
                            "label": {
                                "type": "string",
                                "maxLength": 50
                            },
                            "description": {
                                "type": "string",
                                "maxLength": 200
                            },
                            "auto": {
                                "type": "boolean",
                                "default": False
                            },
                            "requires_approval": {
                                "type": "boolean",
                                "default": False
                            }
                        }
                    }
                }
            }
        },
        "initial_state": {
            "type": "string",
            "pattern": "^[a-z][a-z0-9_]*$"
        }
    }
}

# Business rules schema
BUSINESS_RULES_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "validation": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "requires_lines": {
                    "type": "boolean",
                    "default": True
                },
                "requires_supplier": {
                    "type": "boolean",
                    "default": True
                },
                "requires_customer": {
                    "type": "boolean",
                    "default": False
                },
                "min_amount": {
                    "type": ["number", "null"],
                    "minimum": 0
                },
                "max_amount": {
                    "type": ["number", "null"],
                    "minimum": 0
                },
                "required_fields": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "pattern": "^[a-zA-Z_][a-zA-Z0-9_]*$"  # valid field names
                    },
                    "uniqueItems": True
                }
            }
        },
        "auto_actions": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "auto_submit": {
                    "type": "boolean",
                    "default": False
                },
                "auto_approve_conditions": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "max_amount": {
                            "type": "number",
                            "minimum": 0
                        },
                        "user_groups": {
                            "type": "array",
                            "items": {"type": "string"},
                            "uniqueItems": True
                        },
                        "supplier_whitelist": {
                            "type": "array",
                            "items": {"type": "integer"},  # supplier IDs
                            "uniqueItems": True
                        }
                    }
                }
            }
        },
        "notifications": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "on_submit": {
                    "type": "array",
                    "items": {"type": "string"},  # group names or email addresses
                    "uniqueItems": True
                },
                "on_approve": {
                    "type": "array",
                    "items": {"type": "string"},
                    "uniqueItems": True
                },
                "on_reject": {
                    "type": "array",
                    "items": {"type": "string"},
                    "uniqueItems": True
                }
            }
        }
    }
}

# Numbering configuration schema
NUMBERING_CONFIG_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "auto_number": {
            "type": "boolean",
            "default": True
        },
        "prefix": {
            "type": "string",
            "pattern": "^[A-Z]{2,6}$",  # 2-6 uppercase letters
            "maxLength": 6
        },
        "separator": {
            "type": "string",
            "enum": ["-", "/", "_", ""],
            "default": "-"
        },
        "padding": {
            "type": "integer",
            "minimum": 3,
            "maximum": 8,
            "default": 4
        },
        "reset_yearly": {
            "type": "boolean",
            "default": False
        },
        "include_year": {
            "type": "boolean",
            "default": False
        }
    }
}


# Helper functions for validation
def validate_workflow_consistency(workflow_config):
    """
    Validate workflow configuration consistency

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []

    states = workflow_config.get('states', {})
    transitions = workflow_config.get('transitions', {})
    initial_state = workflow_config.get('initial_state')

    # Check initial state exists
    if initial_state not in states:
        errors.append(f"Initial state '{initial_state}' not found in states")

    # Check all transition targets exist
    for from_state, transition_list in transitions.items():
        if from_state not in states:
            errors.append(f"Transition from unknown state: '{from_state}'")

        for transition in transition_list:
            to_state = transition['to']
            if to_state not in states:
                errors.append(f"Transition to unknown state: '{to_state}'")

    # Check for unreachable states (except initial)
    reachable = {initial_state}
    changed = True
    while changed:
        changed = False
        for from_state, transition_list in transitions.items():
            if from_state in reachable:
                for transition in transition_list:
                    if transition['to'] not in reachable:
                        reachable.add(transition['to'])
                        changed = True

    unreachable = set(states.keys()) - reachable
    if unreachable:
        errors.append(f"Unreachable states detected: {', '.join(unreachable)}")

    # Check for states without outgoing transitions (except final states)
    for state_name, state_config in states.items():
        if not state_config.get('is_final', False):
            if state_name not in transitions or not transitions[state_name]:
                errors.append(f"Non-final state '{state_name}' has no outgoing transitions")

    return errors


def validate_business_rules_consistency(business_rules):
    """
    Validate business rules consistency

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []

    validation_rules = business_rules.get('validation', {})

    # Check amount limits
    min_amount = validation_rules.get('min_amount')
    max_amount = validation_rules.get('max_amount')

    if min_amount is not None and max_amount is not None:
        if min_amount > max_amount:
            errors.append("min_amount cannot be greater than max_amount")

    # Check auto approve conditions
    auto_actions = business_rules.get('auto_actions', {})
    auto_approve = auto_actions.get('auto_approve_conditions', {})

    if auto_approve.get('max_amount') is not None:
        auto_max = auto_approve['max_amount']
        if max_amount is not None and auto_max > max_amount:
            errors.append("auto_approve max_amount cannot exceed validation max_amount")

    return errors