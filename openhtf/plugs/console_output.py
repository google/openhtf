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


"""User input module for OpenHTF.

Allows tests to prompt for user input using the framework, so prompts can be
presented via the CLI interface, the included web frontend, and custom
frontends alike. Any other part of the framework that needs to access shared
prompt state should use the openhtf.prompts pseudomodule.
"""

from __future__ import print_function
from builtins import input
import collections
import functools
import logging
import math
import os
import platform
import select
import sys
import threading
import time
import uuid

import colorama
import contextlib2 as contextlib

from openhtf import PhaseOptions
from openhtf import plugs
from openhtf.util import argv
from openhtf.util import exceptions


if platform.system() != 'Windows':
  import termios

colorama.init()

_LOG = logging.getLogger(__name__)


class ActionFailedError(Exception):
  """Raised (and caught) when an action is marked as failed."""


def banner_print(msg, color='', width=60, file=sys.stdout):
  lpad = int(math.ceil((width - len(msg) - 2) / 2.0)) * '='
  rpad = int(math.floor((width - len(msg) - 2) / 2.0)) * '='
  file.write('{color}{lpad} {msg} {rpad}\n'.format(
      color=color, lpad=lpad, msg=msg, rpad=rpad))
  file.write(colorama.Style.RESET_ALL)
  file.flush()


def bracket_print(msg, color='', width=8, file=sys.stdout):
  """Prints the message in brackets in the specified color and end the line."""
  lpad = int(math.ceil((width - 2 - len(msg)) / 2.0)) * ' '
  rpad = int(math.floor((width - 2 - len(msg)) / 2.0)) * ' '
  file.write('[{lpad}{bright}{color}{msg}{reset}{rpad}]'.format(
      lpad=lpad, bright=colorama.Style.BRIGHT, color=color, msg=msg,
      reset=colorama.Style.RESET_ALL, rpad=rpad))
  file.write(colorama.Style.RESET_ALL)
  file.write('\n')
  file.flush()


class ActionResult(object):
  """Used with an action_result_context to signal the result of an action."""
  def __init__(self):
    self.success = None

  def succeed(self):
    """Mark the action as having succeeded."""
    self.success = True

  def fail(self):
    """Mark the action as having failed.

    Raises:
      ActionFailedError: This exception is always raised, by this function,
          but should be caught by the contextmanager.
    """
    self.success = False
    raise ActionFailedError()


@contextlib.contextmanager
def action_result_context(action_text,
                          width=60,
                          status_width=8,
                          succeed_text='OK',
                          fail_text='FAIL',
                          unknown_text='????',
                          file=sys.stdout,
                          logger=_LOG):
  """A contextmanager that prints actions and results to the CLI.

  When entering the context, the action will be printed, and when the context
  is exited, the result will be printed. The object yielded by the context is
  used to mark the action as a success of failure, whereas a raise from inside
  the context will also result in the action being marked fail. If the result is
  left unset, then indicative text ("????") will be printed as the result.

  Args:
    action_text: Text to be displayed that describes the action being taken.
    width: Total width for each line of output.
    status_width: Width of the just the status message portion of each line.
    succeed_text: Status message displayed when the action succeeds.
    fail_text: Status message displayed when the action fails.
    unknown_text: Status message displayed when the result is left unset.
    file: Specific file object to write to write CLI output to.
    logger: Logger to which to send analogous output for each status message.

  Example usage:
    with action_result_context('Doing an action that will succeed...') as act:
      time.sleep(2)
      act.succeed()

    with action_result_context('Doing an action with unset result...') as act:
      time.sleep(2)

    with action_result_context('Doing an action that will fail...') as act:
      time.sleep(2)
      act.fail()

    with action_result_context('Doing an action that will raise...') as act:
      time.sleep(2)
      import textwrap
      raise RuntimeError(textwrap.dedent('''\
          Crap, there was a raise in the mix.

          If you see this message, it means you are running the console_output
          module directly rather than using it as a library. Things to try:

            * Not running it as a module.
            * Running it as a module and not worrying about it.
            * Use the magic words.'''))

  Example output:
    Doing an action that will succeed...                [  OK  ]
    Doing an action with unset result...                [ ???? ]
    Doing an action that will fail...                   [ FAIL ]
    Doing an action that will raise...                  [ FAIL ]

  """
  logger.info(action_text)
  file.write(action_text)
  file.write((width - status_width - len(action_text)) * ' ')
  file.flush()
  result = ActionResult()
  try:
    yield result
  except Exception as err:
    logger.info('%s: %s', action_text, fail_text)
    bracket_print(fail_text, width=status_width, color=colorama.Fore.RED)
    if not isinstance(err, ActionFailedError):
      raise
  if result.success:
    logger.info('%s: %s', action_text, succeed_text)
    bracket_print(succeed_text, width=status_width, color=colorama.Fore.GREEN)
  elif result.success is None:
    logger.info('%s: %s', action_text, 'Result unknown.')
    bracket_print(unknown_text, width=status_width, color=colorama.Fore.YELLOW)


# If invoked as a runnable module, this module will invoke its action result
# context in order to print colorized example output.
if __name__ == '__main__':
  sys.excepthook = exceptions.get_handler_for_logger(_LOG)
  banner_print('Running pre-flight checks.')

  with action_result_context('Doing an action that will succeed...') as act:
    time.sleep(2)
    act.succeed()

  with action_result_context('Doing an action with unset result...') as act:
    time.sleep(2)

  with action_result_context('Doing an action that will fail...') as act:
    time.sleep(2)
    act.fail()

  with action_result_context('Doing an action that will raise...') as act:
    time.sleep(2)
    import textwrap
    raise RuntimeError(textwrap.dedent('''\
        Crap, there was a raise in the mix.

        If you see this message, it means you are running the console_output
        module directly rather than using it as a library. Things to try:

          * Not running it as a module.
          * Running it as a module and not worrying about it.
          * Use the magic words.'''))
