"""Device genealogy API for TestRuns.

For a C++ implementation, please see:
//depot/google3/googlex/glass/inspector/util/glassbuild.h
"""

import collections

from proto import assembly_pb2


class ComponentGraph(collections.namedtuple('ComponentGraph', ['assembly'])):
  """ComponentGraph object for adding components to the Genealogy API.

  The ComponentGraph is essentially a series of Component objects with data
  attached to them. One of these Components can be set as the top-level
  assembly, and only one, and it must not be the child of any other component.

  Let's say you're assembling a simple pair of scissors with handles and it gets
  built in this order: Left handle gets attached to left blade, right handle
  gets attached to right blade, then the pair assembled with a screw. This is
  then 5 parts (with distinct part numbers) and 3 assemblies (2 sub-assemblies
  and a top-level assembly).

  In the left-handle station, this would occur:
    lh = graph.AddComponent('left-handle')
    lb = graph.AddComponent('left-blade')
    ls = graph.AddComponent('left-subassembly')
    ls.AddChild(lh)
    ls.AddChild(lb)
    ls.SetTopLevelAssembly()

  The same would occur for the right-handle station but with different part
  numbers. In the final assembly code, we would run this:
    ls = graph.AddComponent('left-subassembly')
    rs = graph.AddComponent('right-subassembly')
    assy = graph.AddComponent('scissors')
    assy.AddChild(ls)
    assy.AddChild(rs)
    assy.SetTopLevelAssembly()

  This would all get combined up later in the pipeline to provide a combined
  component graph of all assemblies.
  """

  def AddComponent(self, part_number):
    idx = len(self.assembly.component)
    component = self.assembly.component.add(part_number=part_number)
    return Component(self, idx, component)

  @property
  def components(self):
    for i, component in enumerate(self.assembly.component):
      yield Component(self, i, component)


class Component(collections.namedtuple(
    'Component', ['graph', 'idx', 'component'])):
  """Assembly Component wrapper."""

  @property
  def edges(self):
    for edge in self.graph.assembly.edge:
      if edge.parent == self.idx or edge.child == self.idx:
        yield edge

  def AddChild(self, child):
    new_edge = assembly_pb2.Assembly.Edge(parent=self.idx, child=child.idx)
    for edge in self.edges:
      if new_edge == edge:
        raise ValueError('Double-adding edge', edge)
    self.graph.assembly.edge.add().CopyFrom(new_edge)

  def SetSerialNumber(self, serial_number):
    self.component.serial_number = serial_number
    return self

  def SetLot(self, lot_number, lot_index=None):
    self.component.lot.lot_number = lot_number
    if lot_index is not None:
      self.component.lot.lot_index = lot_index
    return self

  def SetSku(self, sku):
    self.component.sku = sku
    return self

  @property
  def deviations(self):
    return iter(self.component.deviation)

  def AddDeviation(self, deviation):
    self.component.deviation.append(deviation)
    return self

  def SetDescription(self, description):
    self.component.description = description
    return self

  @property
  def attributes(self):
    return iter(self.component.attribute)

  def AddAttribute(self, key, value):
    """Adds an attribute for key with the given value."""
    attr = self.component.attribute.add(key=key)
    if isinstance(value, int):
      attr.as_int = value
    elif isinstance(value, bytes):
      attr.as_bytes = value
    elif isinstance(value, unicode):
      attr.as_string = value
    else:
      attr.as_bytes = bytes(value)
    return self

  def SetTopLevelAssembly(self):
    if any(edge.child == self.idx for edge in self.edges):
      raise ValueError('Cannot make a child component the top-level assembly.')
    self.graph.assembly.top_level_assembly = self.idx
    return self
