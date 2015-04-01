"""A onestop shop for all of your XTF versioning needs."""

import time
from google3.pyglib import build_data

VERSION_MAJOR = 3
VERSION_MINOR = 0


def _FormatTimestampAsBuildStamp(ts):
  time_tuple = time.localtime(ts)
  return time.strftime('%m%d%y.%H%m%S', time_tuple)

VERSION_MAP = {
    'major': VERSION_MAJOR,
    'minor': VERSION_MINOR,
    'build': _FormatTimestampAsBuildStamp(build_data.Timestamp())
}


def GetMajorVersion():
  return VERSION_MAP['major']


def GetMinorVersion():
  return VERSION_MAP['minor']


def GetBuildString():
  return VERSION_MAP['build']


def GetVersion():
  return float(GetVersionString())


def GetVersionString():
  return '%s.%s' % (VERSION_MAJOR, VERSION_MINOR)


def GetFullVersionAndBuildString():
  return '%s-%s' % (GetVersionString(), GetBuildString())
