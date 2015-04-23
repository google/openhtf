"""Tests for xtfrundata."""

import json
import tempfile
import unittest
import xtfrundata

TESTDATA = xtfrundata.RunData('station', 1, 'test', '1.0.0', 'localhost',
                              9000, 10)


class RunDataTest(unittest.TestCase):

  def testWritesAndReadsBack(self):
    temprundir = tempfile.mkdtemp()
    filename = TESTDATA.SaveToFile(temprundir)
    loaded = xtfrundata.RunData.FromFile(filename)
    self.assertEquals(loaded, TESTDATA)

  def testLooksWriteAsJson(self):
    d = json.loads(TESTDATA.AsJson())
    self.assertDictContainsSubset(d, {
        'station_name': 'station',
        'cell_count': 1,
        'test_type': 'test',
        'test_version': '1.0.0',
        'http_host': 'localhost',
        'http_port': 9000,
        'pid': 10
    })


class EnumerateTest(unittest.TestCase):

  STATION1 = TESTDATA
  STATION2 = xtfrundata.RunData('station2', 2, 'test2', '1.0.0', 'localhost',
                                9001, 10)

  def setUp(self):
    self.rundir = tempfile.mkdtemp()
    self.STATION1.SaveToFile(self.rundir)
    self.STATION2.SaveToFile(self.rundir)

  def testEnumeratesAllRunData(self):
    data = xtfrundata.EnumerateRunDirectory(self.rundir)
    self.assertItemsEqual(data, (self.STATION1, self.STATION2))


if __name__ == '__main__':
  unittest.main()
