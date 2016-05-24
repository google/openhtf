"""Module to display test summary on console."""

import os
import sys
import __main__ as main

from openhtf import util
from openhtf.io import test_record
from openhtf.util import measurements as measurement


class ConsoleSummary():
  """Print test results with failure info on console. """

  # pylint: disable=invalid-name
  def __init__(self):
    if os.name == 'posix':    #Linux and Mac
      self.RED = '\033[91m'
      self.GREEN = '\033[92m'
      self.ORANGE = '\033[93m'
      self.RESET = '\033[0m'
      self.BOLD = '\033[1m'
    else:
      self.RED = ""
      self.GREEN = ""
      self.ORANGE = ""
      self.RESET = ""
      self.BOLD = ""

    self.color_table = {
        test_record.Outcome.PASS:self.GREEN, 
        test_record.Outcome.FAIL:self.RED, 
        test_record.Outcome.ERROR:self.ORANGE, 
        test_record.Outcome.TIMEOUT:self.ORANGE, 
    }
  # pylint: enable=invalid-name

  def __call__(self, record):
    indent2 = ' '*2
    indent4 = ' '*4
    color = self.color_table[record.outcome]
    output_lines = []
    msg = ''.join((color,
                   self.BOLD,
                   main.__file__,
                   ': ',
                   record.outcome.name,
                   self.RESET))

    output_lines.append(msg)

    if record.outcome in (test_record.Outcome.FAIL, test_record.Outcome.ERROR):
      phases = record.phases
      for phase in phases:
        new_phase = True
        phase_time = str((float(phase.end_time_millis)
                          - float(phase.start_time_millis))/1000)
        if record.outcome == test_record.Outcome.FAIL:
          measured = phase.measured_values
          measurements = phase.measurements
          for key in measurements:
            result = measurements[key]
            if result.outcome == measurement.Outcome.FAIL:
              if new_phase:
                text = ''.join(('failed phase: ',
                                phase.name,
                                ' [time taken(s): ',
                                phase_time,
                                ']'))
                output_lines.append(text)
                new_phase = False

              failed_item = result.name
              text = ''.join((indent2,
                              'failed_item: ',
                              failed_item))
              output_lines.append(text)
              text = ''.join((indent4,
                              'measured_value: ',
                              str(measured[failed_item])))
              output_lines.append(text)
              text = ''.join((indent4,
                              'validator: ',
                              str(result.validators)))
              output_lines.append(text)
        else:
          phase_result = phase.result.phase_result
          if 'CONTINUE' not in phase_result:
            text = ''.join(('raised_exception phase: ',
                            phase_name,
                            ' [time taken(s): ',
                            phase_time,
                            ']'))
            output_lines.append(text)
            exp_type = record.outcome_details[0].code
            text = ''.join((indent2,
                            'exception type : ',
                            exp_type))
            output_lines.append(text)
            text = ''.join((indent2,
                            'exception text: ',
                            record.outcome_details[0].description))
            output_lines.append(text)

    output_lines.append('\n')
    text = '\n'.join(output_lines)
    sys.stdout.write(text)
