"""Output to file.

Output modules inherit from OutputToFile and overload methods
based on output file requirements.

"""

import os
import tempfile


class OutputToFile(object):
  """Class for saving to file."""

  def GetData(self):
    """Get data to store."""
    self.data = self.test_record_dict

  def Save(self):
    """Save to file or file object."""

    self.GetData()
    self.filename = None
    if isinstance(self.filename_pattern, basestring):
      if '{' in self.filename_pattern:
        self.filename = self.filename_pattern.format(**self.test_record_dict)
      else:
        self.filename = self.filename_pattern % self.test_record_dict
      self.SaveFile()
    else:
      self.filename_pattern.write(self.GetData())
    return self.filename

  def SaveFile(self):
    with tempfile.NamedTemporaryFile(delete=False) as temp:
      temp.write(self.data)
      temp.flush()
      os.rename(temp.name, self.filename)
