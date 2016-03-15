"""Module to display test summary on console."""
import os
import sys
from openhtf import util


class PrintConsole():
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
    
    as_dict = util.ConvertToBaseTypes(test_record)
    result = as_dict['outcome']
    color = None
    if result == 'PASS':
      color = self.GREEN
    elif result == 'FAIL':
      color = self.RED
    else:
      color = self.ORANGE

    output_lines = []
    text = ''.join((os.path.basename(sys.argv[0]), ': ', result))
    text = ''.join((color, self.BOLD, text, self.RESET))
    
    output_lines.append(text)

    if result == 'FAIL' or result == 'ERROR':
      phases=as_dict['phases']
      for phase in phases:
        phase_name = phase['name']
        phase_time = str((float(phase['end_time_millis']) - \
                               float(phase['start_time_millis']))/1000)

        if result == 'FAIL':
          measured = phase['measured_values']
          measurements = phase['measurements']
          for measurement in measurements:
            res = measurements[measurement]
            if res['outcome'] == 'FAIL':
              if len(phase_name) > 0:
                text = ''.join(('\nfailed phase: ', phase_name, ' [time taken(s): ', \
                        phase_time, ']'))
                output_lines.append(text)
                phase_name = ''

              failed_item = res['name']
              text = ''.join((indent2, 'failed_item: ', failed_item))
              output_lines.append(text)
              text = ''.join((indent4, 'measured_value: ',  \
                              str(measured[failed_item])))
              output_lines.append(text)
              if 'validators' in res:
                 text = ''.join((indent4, 'validator: ', res['validators'][0]))
              else:
                text = ''.join((indent4, 'validator: None'))
              output_lines.append(text)
        else:
          phase_result = phase['result']
          if phase_result['phase_result'] != 'CONTINUE':
            text = ''.join(('\nraised_exception phase: ', phase_name, ' [time taken(s): '\
                              , phase_time, ']'))
            output_lines.append(text)
            exp_type = as_dict['outcome_details'][0]['code']
            text = ''.join((indent2, 'exception type : ', exp_type))
            output_lines.append(text)
            text = ''.join((indent2, 'exception text: ', phase_result['phase_result']))
            output_lines.append(text)

    text = ''.join(output_lines)
    text = ''.join((text, '\n'))
    sys.stdout.write(text)
  # pylint: enable=invalid-name
