import sys
sys.path.append('../')
import unittest
from plug34461A import *

class TestPlug34461A(unittest.TestCase):

    def setUp(self):
        self.a = 2
    def tearDown(self):
        print(self.a)
    def test_init(self):
        self.assertEqual(1,1)

if __name__ == '__main__':
    unittest.main()