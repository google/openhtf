"""Module to display test summary on console."""
import os
import sys
from openhtf import util
from openhtf.io import test_record as tr
from openhtf.util import measurements as mea

class PrintToConsole():
  """Print test results with failur info on console. """

  def __init__(self):
    if os.name == 'posix':    #Linux and Mac
      self.RED =  '\033[91m'
      self.GREEN =  '\033[92m'
      self.ORANGE = '\033[93m'
      self.RESET =  '\033[0m'
      self.BOLD =  '\033[1m'
    else: 
      self.RED    = ""
      self.GREEN  = ""
      self.ORANGE = ""
      self.RESET  = ""
      self.BOLD   = ""


  # pylint: disable=invalid-name
  def __call__(self, test_record):
    indent2 = ''.join(('\n', ' '*2))
    indent4 = ''.join(('\n', ' '*4))
  
    #as_dict = util.ConvertToBaseTypes(test_record)
    result = test_record.outcome
    status = ''
    color = None
    if result == tr.Outcome.PASS:
      color = self.GREEN
      status = 'PASS'
    elif result == tr.Outcome.FAIL:
      color = self.RED
      status = 'FAIL'
    else:
      color = self.ORANGE
      status = 'ERROR'

    output_lines = []
    msg = ''.join((os.path.basename(sys.argv[0]), ': ', status))
    msg = ''.join((color, self.BOLD, msg, self.RESET))
    
    output_lines.append(msg)

    if status == 'FAIL' or status == 'ERROR':      
      phases=test_record.phases
      for phase in phases:
        phase_name = phase.name
        phase_time = str((float(phase.end_time_millis) - \
                               float(phase.start_time_millis))/1000)
        if status == 'FAIL':
          measured = phase.measured_values
          measurements = phase.measurements
          for measurement in measurements:
            res = measurements[measurement]
            if res.outcome == mea.Outcome.FAIL:
              if len(phase_name) > 0:
                text = ''.join(('\nfailed phase: ', phase_name, ' [time taken(s): ', \
                        phase_time, ']'))
                output_lines.append(text)
                phase_name = ''

              failed_item = res.name
              text = ''.join((indent2, 'failed_item: ', failed_item))
              output_lines.append(text)
              text = ''.join((indent4, 'measured_value: ',  \
                              str(measured[failed_item])))
              output_lines.append(text)
              text = ''.join((indent4, 'validator: ', str(res.validators)))              
              output_lines.append(text)
        else:
          phase_result = phase.result.phase_result
          if 'CONTINUE' not in phase_result:
            text = ''.join(('\nraised_exception phase: ', phase_name, ' [time taken(s): '\
                              , phase_time, ']'))
            output_lines.append(text)
            exp_type = test_record.outcome_details[0].code
            text = ''.join((indent2, 'exception type : ', exp_type))
            output_lines.append(text)
            text = ''.join((indent2, 'exception text: ', \
                                     test_record.outcome_details[0].description))
            output_lines.append(text)

    text = ''.join(output_lines)
    text = ''.join((text, '\n'))
    sys.stdout.write(text)
  # pylint: enable=invalid-name
