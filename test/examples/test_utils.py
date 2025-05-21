"""Utilities for integration testing OpenHTF examples."""

import os
from typing import Any
import unittest


class ExampleTestBase(unittest.TestCase):
  """Base class for integration testing OpenHTF examples."""

  def setUp(self):
    super().setUp()
    self.output_file = None

  def tearDown(self):
    super().tearDown()
    if self.output_file and os.path.exists(self.output_file):
      os.remove(self.output_file)

  def get_phase_by_name(
      self, phases_data: dict[str, Any], phase_name: str
  ) -> dict[str, Any]:
    """Finds a phase by its name in a list of JSON phase data.

    Args:
      phases_data: A list of phase dictionaries (from JSON load)..
      phase_name: The name of the phase to find.

    Returns:
      The phase dictionary if found.

    Raises:
      AssertionError (via test_case.fail()): If the phase is not found.
    """
    for p in phases_data:
      if p["name"] == phase_name:
        return p
    self.fail(f"Phase '{phase_name}' not found in output.")
