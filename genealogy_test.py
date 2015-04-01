"""Tests for google3.googlex.glass.xtf.openxtf.openxtf.genealogy."""

from google3.testing.pybase import googletest
from google3.googlex.glass.xtf.openxtf.openxtf import assembly_pb2
from google3.googlex.glass.xtf.openxtf.openxtf import genealogy


class GenealogyTest(googletest.TestCase):

  def setUp(self):
    self.component_graph = genealogy.ComponentGraph(assembly_pb2.Assembly())

  def CreateComponents(self, num):
    components = [
        self.component_graph.AddComponent('partnbr')
        for _ in range(num)
    ]
    if num == 1:
      return components[0]
    return components

  def testAddComponent(self):
    self.CreateComponents(1)
    comp_pb = self.component_graph.assembly.component[0]
    self.assertEqual(1, len(self.component_graph.assembly.component))
    self.assertEqual('partnbr', comp_pb.part_number)

  def testAddChild(self):
    comp1, comp2 = self.CreateComponents(2)
    comp1.AddChild(comp2)
    with self.assertRaises(ValueError):
      comp1.AddChild(comp2)

  def testSetTopLevelAssembly(self):
    comp1, comp2 = self.CreateComponents(2)
    comp1.AddChild(comp2)
    comp1.SetTopLevelAssembly()
    with self.assertRaises(ValueError):
      comp2.SetTopLevelAssembly()

  def testSetInfo(self):
    comp1, comp2 = self.CreateComponents(2)
    comp1.SetSerialNumber('aoe')
    comp2.SetLot('lot2')
    comp_pb1 = self.component_graph.assembly.component[0]
    comp_pb2 = self.component_graph.assembly.component[1]
    self.assertEqual('lot2', comp_pb2.lot.lot_number)
    self.assertEqual('aoe', comp_pb1.serial_number)
    comp1.SetDescription('described')
    self.assertEqual('described', comp_pb1.description)
    comp1.AddDeviation('some deviation string')
    self.assertEqual('some deviation string', comp_pb1.deviation[0])

  def testAddAttribute(self):
    comp = self.CreateComponents(1)
    comp_pb1 = self.component_graph.assembly.component[0]
    comp.AddAttribute('key', 1)
    self.assertEqual('key', comp_pb1.attribute[0].key)
    self.assertEqual(1, comp_pb1.attribute[0].as_int)
    comp.AddAttribute('keyb', 'bytes')
    self.assertEqual('keyb', comp_pb1.attribute[1].key)
    self.assertEqual('bytes', comp_pb1.attribute[1].as_bytes)
    comp.AddAttribute('keys', u'string')
    self.assertEqual('keys', comp_pb1.attribute[2].key)
    self.assertEqual(u'string', comp_pb1.attribute[2].as_string)


if __name__ == '__main__':
  googletest.main()
