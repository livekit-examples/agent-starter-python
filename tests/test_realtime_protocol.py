from realtime_protocol import (
    ControlMessage,
    ConversationState,
    parse_control_packet,
    parse_conversation_id,
    route_mention,
)


def test_control_parser_accepts_versioned_stop():
    message = parse_control_packet(b'{"version":1,"op_id":"op-17","command":"stop"}')

    assert message == ControlMessage(1, "op-17", "stop", None)


def test_control_parser_accepts_new_with_conversation_identifier():
    message = parse_control_packet(
        b'{"version":1,"op_id":"op-18","command":"new","conversation_id":"conv-next"}'
    )

    assert message == ControlMessage(1, "op-18", "new", "conv-next")


def test_control_parser_rejects_approve_and_unknown_fields():
    assert (
        parse_control_packet(b'{"version":1,"op_id":"x","command":"approve"}') is None
    )
    assert (
        parse_control_packet(b'{"version":1,"op_id":"x","command":"stop","secret":"x"}')
        is None
    )


def test_control_parser_rejects_invalid_payloads():
    assert parse_control_packet(b"\xff") is None
    assert parse_control_packet(b"[]") is None
    assert parse_control_packet(b"{" + (b'"x"' * 4096) + b"}") is None
    assert parse_control_packet(b'{"version":2,"op_id":"x","command":"stop"}') is None
    assert (
        parse_control_packet(b'{"version":1,"op_id":"../x","command":"stop"}') is None
    )


def test_conversation_state_rotates_only_to_valid_identifier():
    state = ConversationState("conv-original")

    assert state.reset("conv-next") is True
    assert state.current == "conv-next"
    assert state.reset("../../bad") is False
    assert state.current == "conv-next"


def test_conversation_id_uses_valid_fallback():
    assert parse_conversation_id("conv.valid:1", "fallback") == "conv.valid:1"
    assert parse_conversation_id("bad/value", "fallback-1") == "fallback-1"
    assert parse_conversation_id(None, "bad/value") == ""


def test_coder_mention_routes_through_hermes_main():
    route = route_mention("@coder backendটা check করো")

    assert route.mention == "coder"
    assert "Hermes Main" in route.hermes_input
    assert "delegate" in route.hermes_input
    assert "backendটা check করো" in route.hermes_input
    assert route.status == "Coder assigned"


def test_computer_operator_stays_in_foreground_main_run_for_mobile_approvals():
    route = route_mention("@computer-operator use calculator gui 7x8")

    assert route.mention == "computer-operator"
    assert "Hermes Main" in route.hermes_input
    assert "Do not call delegate_task" in route.hermes_input
    assert "foreground" in route.hermes_input
    assert "use calculator gui 7x8" in route.hermes_input
    assert route.status == "Computer Operator assigned"


def test_unmentioned_and_unknown_mention_text_is_preserved():
    assert route_mention("normal request").hermes_input == "normal request"
    unknown = route_mention("@unknown do something")
    assert unknown.mention is None
    assert unknown.hermes_input == "@unknown do something"
    assert unknown.status is None
