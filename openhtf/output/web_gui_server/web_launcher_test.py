"""Tests for google3.third_party.car.hw.testing.web_gui.web_launcher."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import os

import google3
import mock

from google3.testing.pybase import googletest
from google3.third_party.car.hw.testing.web_gui import web_launcher


class WebLauncherTest(googletest.TestCase):

  @mock.patch('webbrowser.open')
  @mock.patch.dict(os.environ, {'DISPLAY': ':123'})
  def testNormalLaunch(self, mock_open):
    web_launcher.launch('url')
    mock_open.assert_called_once_with('url')

  @mock.patch.object(os, 'listdir')
  @mock.patch.dict('os.environ', clear=True)
  def testNoXLaunch(self, mock_listdir):
    mock_listdir.return_value = []
    with self.assertRaisesRegexp(ValueError, 'No running X11 display.'):
      web_launcher.launch('url')

  @mock.patch.object(os, 'listdir')
  @mock.patch('pwd.getpwnam')
  @mock.patch.object(os, 'getuid', lambda: 10)
  @mock.patch.object(web_launcher, '_get_display_owner', lambda _: 'owner')
  @mock.patch.dict('os.environ', clear=True)
  def testNonRootWrongUserLaunch(self, mock_pwnam, mock_listdir):
    mock_listdir.return_value = ['X123']
    mock_pwnam.return_value = mock.Mock(pw_dir='/HOME', pw_uid=100, pw_gid=100)
    with self.assertRaisesRegexp(ValueError, 'Cannot run as non-root.*'):
      web_launcher.launch('url')

  @mock.patch.object(os, 'listdir')
  @mock.patch('pwd.getpwnam')
  @mock.patch.object(os, 'getuid', lambda: 0)
  @mock.patch.object(web_launcher, '_get_display_owner', lambda _: 'owner')
  @mock.patch.dict('os.environ', clear=True)
  def testNoXauthLaunch(self, mock_pwnam, mock_listdir):
    mock_listdir.return_value = ['X123']
    mock_pwnam.return_value = mock.Mock(pw_dir='/HOME', pw_uid=100, pw_gid=100)
    with self.assertRaisesRegexp(ValueError, '.*Xauthority does not exist'):
      web_launcher.launch('url')

  @mock.patch.object(os, 'listdir')
  @mock.patch('pwd.getpwnam')
  @mock.patch('subprocess.Popen', mock.Mock())
  @mock.patch.object(os, 'getuid', lambda: 100)
  @mock.patch.object(os.path, 'exists', lambda _: True)
  @mock.patch.object(web_launcher, '_get_display_owner', lambda _: 'owner')
  @mock.patch.dict('os.environ', clear=True)
  def testNonRootCorrectUserLaunch(self, mock_pwnam, mock_listdir):
    mock_listdir.return_value = ['X123']
    mock_pwnam.return_value = mock.Mock(pw_dir='/HOME', pw_uid=100, pw_gid=100)
    web_launcher.launch('url')

  @mock.patch.object(os, 'listdir')
  @mock.patch('pwd.getpwnam')
  @mock.patch('subprocess.Popen', mock.Mock())
  @mock.patch.object(os, 'getuid', lambda: 0)
  @mock.patch.object(os.path, 'exists', lambda _: True)
  @mock.patch.object(web_launcher, '_get_display_owner', lambda _: 'owner')
  @mock.patch.dict('os.environ', clear=True)
  def testRootSuccess(self, mock_pwnam, mock_listdir):
    mock_listdir.return_value = ['X123']
    mock_pwnam.return_value = mock.Mock(pw_dir='/HOME', pw_uid=100, pw_gid=100)
    web_launcher.launch('url')

  @mock.patch('utmp.UtmpFile')
  def testDisplayOwner(self, mock_utmp):
    mock_utmp.return_value.__iter__.return_value = [
        mock.Mock(ut_host=':123', ut_user='owner')]
    self.assertEquals(web_launcher._get_display_owner(':123'), 'owner')


if __name__ == '__main__':
  googletest.main()
