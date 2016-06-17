# coding: iso-8859-1

# Copyright 2016 Google Inc. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""Read in a .xls file and generate OpenHTF Unit objects.

UNECE, the United Nations Economic Commision for Europe, publishes a set of
unit codes for international trade in the form of Excel spreadsheets (.xls
files) here:

http://www.unece.org/cefact/codesfortrade/codes_index.html

This tool is used to parse those spreadsheets and turn the published standard
code set into a .py file that OpenHTF can import.

Typical usage looks like:

python ./bin/units_from_xls.py --infile ./Rec20_Rev6e_2009.xls \
--outfile ./__init__.py

"""


import argparse
import os
import shutil
import sys
from tempfile import mkstemp

import xlrd


# Column names for the columns we care about. This list must be populated in
# the expected order: [<name label>, <code label>, <suffix label>].
COLUMN_NAMES = ['Name',
                'Common\nCode',
                'Symbol']

# The contents of the lines of the output file between which the generated code
# will be inserted.
START_DELIMITER = '######## BEGIN_UNITS ########'
END_DELIMITER = '######## END_UNITS ########'

SHEET_NAME = 'Annex I'
REPLACEMENTS = {' ': '_',
                '[': '',
                ']': '',
                '(': '',
                ')': '',
                ',': '.',
                u'°': 'DEG_',
               }


def main():
  """Main entry point for UNECE code .xls parsing."""
  parser = argparse.ArgumentParser(description='Units From XLS',
                                   prog='python units_from_xls.py')
  parser.add_argument('--infile', type=str,
                      help='A .xls file to parse.')
  parser.add_argument('--outfile', type=str, default='__init__.py',
                      help='Where to put the generated .py file.')
  args = parser.parse_args()

  code = code_generator(
      xlrd.open_workbook(args.infile).sheet_by_name(SHEET_NAME))

  insert_into_file(args.outfile, code, START_DELIMITER, END_DELIMITER)


def code_generator(sheet):
  """A generator that parses a worksheet containing UNECE code definitions.

  Args:
    sheet: An xldr.sheet object representing a UNECE code worksheet.
  Yields: An iterable of lines of Python source code defining OpenHTF Units.
  """
  seen = set()
  try:
    col_indices = {}
    rows = sheet.get_rows()
    
    # Find the indices for the columns we care about.
    for idx, cell in enumerate(rows.next()):
      if cell.value in COLUMN_NAMES:
        col_indices[cell.value] = idx

    # loop over all remaining rows and pull out units.
    for row in rows:
      name = row[col_indices[COLUMN_NAMES[0]]].value
      code = row[col_indices[COLUMN_NAMES[1]]].value
      suffix = multi_replace(row[col_indices[COLUMN_NAMES[2]]].value,
                             {"'": "\\\'", '"': '\\\"'})
      if name in seen:
        continue
      seen.add(name)

      yield 'UNITS[\'%s\'] = Unit(\'%s\', \'%s\', \'%s\')\n' % (
          multi_replace(name.upper(), REPLACEMENTS), name, code, suffix)

  except xlrd.XLRDError:
    sys.stdout.write('Unable to process the .xls file.')


def multi_replace(string, replacements=None):
  """Return the string in uppercase with the specified substitutions."""
  replacements = replacements or {}
  result = string

  for old, new in replacements.iteritems():
    result = result.replace(old, new)

  return result


def insert_into_file(filepath, code, start, end):
  """Replace the contents of the file between the start and end markers.

  Args:
    file: A file-like object whose contents to modify.
    code: An iterable of lines of code to replace part of the file with.
    start: The contents of the line below which to replace text.
    end: The contents of the line after which to leave contents intact.
  """
  tmp_handle, tmp_path = mkstemp()
  skipping = False

  with open(filepath) as old_file, open(tmp_path, 'w') as new_file:
    for old_line in old_file:
      if old_line.find(start) == 0:
        new_file.write(old_line)
        new_file.writelines(
            [line.encode('utf8', 'replace') for line in code])
        skipping = True
      elif old_line.find(end) == 0:
        new_file.write(old_line)
        skipping = False
      elif not skipping:
        new_file.write(old_line)
    new_file.flush()

    os.remove(filepath)
    shutil.move(tmp_path, filepath)


if __name__ == '__main__':
  main()
