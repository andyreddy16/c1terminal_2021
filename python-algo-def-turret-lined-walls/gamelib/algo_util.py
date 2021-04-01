def get_points_on_vertical_line(line):
    """Gets the coordinates for a vertical straight line level, where line = 0 is left edge.

    Args:
        line: which level to get points from. 0 <= line <= 13

    Returns:
        Coordinates of points on level.

    """

    if line > 27:
        raise Exception("Line is not in range of 0 to 27");

    length = line
    if line > 13:
        length = 27 - line

    positions = []
    for x in range(0, length + 1):
        positions.append([line, 13 - x])
    return positions


def get_points_on_line(line):
    """Gets the coordinates for a straight line level, where line = 0 is closest to corner edge.

    Args:
        line: which level to get points from. 0 <= line <= 13

    Returns:
        Coordinates of points on level.

    """
    left_middle = 13

    if line > left_middle:
        raise Exception("Line is not in range of 0 to 13");

    positions = []
    for x in range(left_middle - line, left_middle + 1):
        positions.append([x, line])
        positions.append([left_middle * 2 + 1 - x, line])
    return positions


def get_points_on_v_level(line):
    """Gets the coordinates for a v-shaped level, where line = 0 is closest to edges.

    Args:
        line: which level to get points from. 0 <= line <= 13

    Returns:
        Coordinates of points on level.

    """
    left_edge = 0
    left_middle = 13
    right_edge = 27

    if line > left_middle:
        raise Exception("Line is not in range of 0 to 13");

    positions = []
    for x in range(left_edge, left_middle + 1 - line):
        positions.append([x + line, left_middle - x])
        positions.append([right_edge - x - line, left_middle - x])
    return positions
