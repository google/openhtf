# coding: iso-8859-1

# Copyright 2015 Google Inc. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""Units of measure for OpenHTF.

Used to retrieve ANSI UOM codes/suffixes as follows:

from openhtf.utils.units import UOM

UOM['BYTE'].uom_code        # 'AD'
UOM['MILLIAMP'].uom_suffix  # 'mA'
"""


import collections


Unit = collections.namedtuple('Unit', 'uom_code uom_suffix')

UOM = {}

UOM['NONE'] = Unit(None, None)
UOM['PERCENT'] = Unit('P1', '%')

# NO_DIMENSION means that there are units set, but they cannot be expressed
# by a known dimension (such as a ratio)
UOM['NO_DIMENSION'] = Unit('NDL', None)

UOM['PIXEL'] = Unit('PX', 'px')
UOM['PIXEL_LEVEL'] = Unit('PXL', None)

UOM['ROTATIONS_PER_MINUTE'] = Unit('RPM', 'rpm')

UOM['SECOND'] = Unit('SEC', 's')
UOM['MHZ'] = Unit('MHZ', 'MHz')
UOM['HERTZ'] = Unit('HTZ', 'Hz')
UOM['MICROSECOND'] = Unit('B98', r'µs')

UOM['MILLIMETER'] = Unit('MMT', 'mm')
UOM['CENTIMETER'] = Unit('LC', 'cm')
UOM['METER'] = Unit('MTR', 'm')
UOM['PER_METER'] = Unit('M0R', 'm⁻¹')
UOM['MILLILITER'] = Unit('MLT', 'mL')
UOM['CUBIC_FOOT'] = Unit('MTQ', 'Ft³')

UOM['DECIBEL'] = Unit('2N', 'dB')
UOM['DECIBEL_MW'] = Unit('2N', 'dBmW')

UOM['MICROAMP'] = Unit('B84', 'µA')
UOM['MILLIAMP'] = Unit('4K', 'mA')
UOM['MICROVOLT'] = Unit('D82', 'µV')
UOM['VOLT'] = Unit('VLT', 'V')
UOM['PICOFARAD'] = Unit('4T', 'pF')
UOM['COULOMB'] = Unit('COU', None)
UOM['MILLIVOLT'] = Unit('2Z', 'mV')
UOM['WATT'] = Unit('WTT', 'W')
UOM['AMPERE'] = Unit('AMP', 'A')

UOM['DEGREE_CELSIUS'] = Unit('CEL', '°C')
UOM['KELVIN'] = Unit('KEL', 'K')

UOM['BYTE'] = Unit('AD', None)
UOM['MEGA_BYTES_PER_SECOND'] = Unit('MBPS', 'MB/s')

UOM['DEGREE'] = Unit('DD', '°')
UOM['RADIAN'] = Unit('C81', 'rad')

UOM['NEWTON'] = Unit('NEW', 'N')

UOM['CUBIC_CENTIMETER_PER_SEC'] = Unit('2J', 'cm³/s')
UOM['MILLIBAR'] = Unit('MBR', 'mbar')
