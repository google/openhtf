import example_capability
import openhtf

from openhtf import htftest
import openhtf.capabilities as capabilities

TEST = htftest.TestMetadata(name='openhtf_example')
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
  openhtf.ExecuteTest(TEST, [HelloWorld, SetParam])
