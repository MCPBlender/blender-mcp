import pytest

from blender_mcp.server import _process_bbox


@pytest.mark.parametrize("bbox", ([0, 1, 1], [-1, 1, 1]))
def test_process_bbox_rejects_nonpositive_integers(bbox):
    with pytest.raises(ValueError, match="bbox must be bigger than zero"):
        _process_bbox(bbox)
