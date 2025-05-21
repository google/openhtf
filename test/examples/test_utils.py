def get_phase_by_name(test_case, phases_data, phase_name):
    """
    Finds a phase by its name in a list of phase data.

    Args:
        test_case: An instance of unittest.TestCase, used for calling .fail().
        phases_data: A list of phase dictionaries. Each dictionary is expected
                     to have a "name" key.
        phase_name: The name of the phase to find.

    Returns:
        The phase dictionary if found.

    Raises:
        AssertionError (via test_case.fail()): If the phase is not found.
    """
    for p in phases_data:
        if p["name"] == phase_name:
            return p
    test_case.fail(f"Phase '{phase_name}' not found in output.")
