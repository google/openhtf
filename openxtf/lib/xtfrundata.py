"""A library to parse and create xtf run data.

Format:
  The xtf run data is in the JSON format and specifies the basic information
  about a running XTF instance.

  {
    station_name: string,
    cell_count: number,
    test_type: string,
    test_version: string,
    http_port: number,
    http_host: string,  // Always localhost
    pid: number,
  }

Convention:
  These files should be put into the /var/run/openxtf directory and named
  the station name of the running openxtf instance.  If an instance cannot
  be contacted by a reader of these files they're not allowed to remove them;
  instead, the recomendation is to check back periodically to see if
  they've been updated or to just recheck the instance later.
"""

import collections
import gflags
import os
import json

gflags.DEFINE_string('rundata_dir', '/var/run/openxtf',
                     'Directory for OpenXTF rundata.')
FLAGS = gflags.FLAGS

class RunData(collections.namedtuple('RunData',
                                     ['station_name', 'cell_count', 'test_type',
                                      'test_version', 'http_host', 'http_port', 'pid'])):
  """Encapsulates the run data stored in an openxtf file."""

  @classmethod
  def FromFile(cls, filename):
    """Creates RunData from a run file."""
    with open(filename) as f:
      data = f.read()
    d = json.loads(data)
    return cls(**d)

  def SaveToFile(self, directory=FLAGS.rundata_dir):
    """Saves this run data to a file, typically in /var/run/openxtf.

    Args:
      directory: The directory in which to save this file.
    Return:
      The filename of this rundata.
    """
    filename = os.path.join(directory, self.station_name)
    with open(filename, 'w') as f:
      f.write(self.AsJson())
    return filename

  def AsJson(self):
    """Converts thie run data instance to JSON."""
    d = self._asdict()
    d['http_host'] = self.http_host
    return json.dumps(d, sort_keys=True, indent=4, separators=(',', ': '))

  def IsAlive(self):
    """Returns True if this pid is alive."""
    try:
      os.kill(self.pid, 0)
    except OSError:
      return False
    else:
      return True


def EnumerateRunDirectory(directory=FLAGS.rundata_dir):
  """Enumerates a local run directory to find stations.

  Args:
    directory: The directory to enumerate, we only list
      files in this directory no child directories.
  """
  filenames = os.listdir(directory)
  filepaths = [os.path.join(directory, filename) for filename in filenames]
  return [RunData.FromFile(filepath) for filepath in filepaths
          if os.path.isfile(filepath)]
