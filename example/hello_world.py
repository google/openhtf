import example_capability
import openxtf

from openxtf import xtftest
import openxtf.capabilities as capabilities

TEST = xtftest.TestMetadata(name='openxtf_example')
TEST.SetVersion(1)
TEST.Doc('Example tester')

TEST.AddParameter('number').Number().InRange(0, 10).Doc(
    "Example numeric parameter.")


@capabilities.RequiresCapability(example=example_capability.Example)
def HelloWorld(test, example):
  test.logger.info('Hello World!')
  test.logger.info('Example says: %s', example.DoStuff())


def SetParam(test):
  test.parameters.number = 1


if __name__ == '__main__':
  openxtf.ExecuteTest(TEST, [HelloWorld, SetParam])
