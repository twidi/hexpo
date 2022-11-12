"""Basic test for tooling."""
from hexpo_game.echo import echo


def test_ok():
    """Test function for tooling."""
    assert echo("foo") == "foo"
