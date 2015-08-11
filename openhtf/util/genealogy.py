# Copyright 2014 Google Inc. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""Device genealogy API for TestRuns."""

import collections

from openhtf.proto import assembly_pb2


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
    """Add the part to the component graph."""
    idx = len(self.assembly.component)
    component = self.assembly.component.add(part_number=part_number)
    return Component(self, idx, component)

  @property
  def components(self):  # pylint: disable=missing-docstring
    for i, component in enumerate(self.assembly.component):
      yield Component(self, i, component)


class Component(collections.namedtuple(
    'Component', ['graph', 'idx', 'component'])):
  """Assembly Component wrapper."""

  @property
  def edges(self):  # pylint: disable=missing-docstring
    for edge in self.graph.assembly.edge:
      if edge.parent == self.idx or edge.child == self.idx:
        yield edge

  def AddChild(self, child):
    """Make child a child of this Component."""
    new_edge = assembly_pb2.Assembly.Edge(parent=self.idx, child=child.idx)
    for edge in self.edges:
      if new_edge == edge:
        raise ValueError('Double-adding edge', edge)
    self.graph.assembly.edge.add().CopyFrom(new_edge)

  def SetSerialNumber(self, serial_number):
    """Set this Component's serial to the specified value."""
    self.component.serial_number = serial_number
    return self

  def SetLot(self, lot_number, lot_index=None):
    """Set this Component's lot number."""
    self.component.lot.lot_number = lot_number
    if lot_index is not None:
      self.component.lot.lot_index = lot_index
    return self

  def SetSku(self, sku):
    """Set this Component's SKU."""
    self.component.sku = sku
    return self

  @property
  def deviations(self):  # pylint: disable=missing-docstring
    return iter(self.component.deviation)

  def AddDeviation(self, deviation):
    """Add a deviation for this Component."""
    self.component.deviation.append(deviation)
    return self

  def SetDescription(self, description):
    """Set this Component's description."""
    self.component.description = description
    return self

  @property
  def attributes(self):  # pylint: disable=missing-docstring
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
    """Set this Component's top-level assembly."""
    if any(edge.child == self.idx for edge in self.edges):
      raise ValueError('Cannot make a child component the top-level assembly.')
    self.graph.assembly.top_level_assembly = self.idx
    return self
