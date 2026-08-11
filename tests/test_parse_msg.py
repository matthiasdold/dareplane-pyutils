import pytest

from dareplane_utils.default_server.functions import noop, parse_msg


def my_func(**kwargs) -> int:
    return 0


PCOMMAND_MAP = {"CMD": my_func}


@pytest.mark.parametrize(
    "msg, kwargs",
    [
        (b"CMD", {}),
        (b"CMD|", {}),
        (b"CMD|{}", {}),
        (b"CMD|{\"a\": 1}", {"a": 1}),
        (b"CMD|{\"a\": 1, \"b\": [1, 2]}", {"a": 1, "b": [1, 2]}),
    ],
)
def test_valid_msgs_parse_to_kwargs(msg, kwargs):
    func, args, kw = parse_msg(msg, pcommand_map=PCOMMAND_MAP)

    assert func == my_func
    assert args == ()
    assert kw == kwargs


@pytest.mark.parametrize(
    "msg",
    [
        b"CMD|pos1|{}",  # positional args are no longer supported
        b"CMD|pos1|{\"b\": 2}",
        b"CMD|{}|{}",
        b"CMD|abc",  # not valid json
        b"CMD|[1, 2]",  # valid json, but no object of kwargs
        b"CMD|1",
        b'CMD|"a"',
    ],
)
def test_invalid_msgs_map_to_noop(msg):
    func, args, kwargs = parse_msg(msg, pcommand_map=PCOMMAND_MAP)

    assert func == noop
    assert args == ()
    assert kwargs == {}
