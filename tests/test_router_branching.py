import agent


def test_router_failure_routes_to_respond_no_reply():
    assert agent.route_after_router({"success": False}) == "respond_no_reply"


def test_non_expense_routes_to_save_chat():
    state = {"router_output": {"is_expense_log": False, "chat_response": "hi"}}
    assert agent.route_after_router(state) == "save_chat"


def test_expense_with_missing_fields_routes_to_missing_fields():
    state = {"router_output": {"is_expense_log": True, "missing_fields_prompt": "amount?"}}
    assert agent.route_after_router(state) == "missing_fields"


def test_complete_expense_routes_to_persist():
    state = {"router_output": {"is_expense_log": True, "missing_fields_prompt": None}}
    assert agent.route_after_router(state) == "persist"


def test_missing_router_output_routes_to_save_chat():
    assert agent.route_after_router({}) == "save_chat"


def test_description_from_conversation_joins_user_messages_only():
    convo = [
        {"role": "user", "content": "I ate kabab"},
        {"role": "assistant", "content": "how much?"},
        {"role": "user", "content": "150"},
    ]
    assert agent._description_from_conversation(convo) == "I ate kabab | 150"
