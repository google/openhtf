# Copyright 2018 Google Inc. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Example OpenHTF Phase Groups.

PhaseGroups are used to control phase shortcutting due to terminal errors to
better guarentee when teardown phases run.
"""

import openhtf as htf


def setup_phase(test):
  test.logger.info('Setup in a group.')


def main_phase(test):
  test.logger.info('This is a main phase.')


def teardown_phase(test):
  test.logger.info('Teardown phase.')


def inner_main_phase(test):
  test.logger.info('Inner main phase.')


def inner_teardown_phase(test):
  test.logger.info('Inner teardown phase.')


def error_setup_phase(test):
  test.logger.info('Error in setup phase.')
  return htf.PhaseResult.STOP


def error_main_phase(test):
  test.logger.info('Error in main phase.')
  return htf.PhaseResult.STOP


def run_basic_group():
  """Run the basic phase group example.

  In this example, there are no terminal phases; all phases are run.
  """
  test = htf.Test(
      htf.PhaseGroup(
          setup=[setup_phase],
          main=[main_phase],
          teardown=[teardown_phase],
      ))
  test.execute()


def run_setup_error_group():
  """Run the phase group example where an error occurs in a setup phase.

  The terminal setup phase shortcuts the test.  The main phases are
  skipped.  The PhaseGroup is not entered, so the teardown phases are also
  skipped.
  """
  test = htf.Test(
      htf.PhaseGroup(
          setup=[error_setup_phase],
          main=[main_phase],
          teardown=[teardown_phase],
      ))
  test.execute()


def run_main_error_group():
  """Run the phase group example where an error occurs in a main phase.

  The main phase in this example is terminal.  The PhaseGroup was entered
  because the setup phases ran without error, so the teardown phases are run.
  The other main phase is skipped.
  """
  test = htf.Test(
      htf.PhaseGroup(
          setup=[setup_phase],
          main=[error_main_phase, main_phase],
          teardown=[teardown_phase],
      ))
  test.execute()


def run_nested_groups():
  """Run the nested groups example.

  This example shows a PhaseGroup in a PhaseGroup.  No phase is terminal, so all
  are run in the order;
    main_phase
    inner_main_phase
    inner_teardown_phase
    teardown_phase
  """
  test = htf.Test(
      htf.PhaseGroup(
          main=[
              main_phase,
              htf.PhaseGroup.with_teardown(inner_teardown_phase)(
                  inner_main_phase),
          ],
          teardown=[teardown_phase]))
  test.execute()


def run_nested_error_groups():
  """Run nested groups example where an error occurs in nested main phase.

  In this example, the first main phase in the nested PhaseGroup errors out.
  The other inner main phase is skipped, as is the outer main phase.  Both
  PhaseGroups were entered, so both teardown phases are run.
  """
  test = htf.Test(
      htf.PhaseGroup(
          main=[
              htf.PhaseGroup.with_teardown(inner_teardown_phase)(
                  error_main_phase, main_phase),
              main_phase,
          ],
          teardown=[teardown_phase],
      ))
  test.execute()


def run_nested_error_skip_unentered_groups():
  """Run nested groups example where an error occurs in outer main phase.

  Lastly, the first main phase in the outer PhaseGroup errors out.  This skips
  the nested PhaseGroup and the other outer main phase.  The outer PhaseGroup
  was entered, so its teardown phase runs.
  """
  test = htf.Test(
      htf.PhaseGroup(
          main=[
              error_main_phase,
              htf.PhaseGroup.with_teardown(inner_teardown_phase)(main_phase),
              main_phase,
          ],
          teardown=[teardown_phase],
      ))
  test.execute()


def main():
  run_basic_group()
  run_setup_error_group()
  run_main_error_group()
  run_nested_groups()
  run_nested_error_groups()
  run_nested_error_skip_unentered_groups()


if __name__ == '__main__':
  main()
