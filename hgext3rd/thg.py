# thg - mercurial extension for TortoiseHg repository browser
#
# Copyright (C) 2014 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.
"""browse the repository in a graphical way using tortoisehg

The 'tortoisehg' extension introduces a :hg:`view` command to spawn a light
version of the tortoisehg workbench.
"""


from __future__ import absolute_import

import os
import sys

from mercurial.i18n import _
from mercurial import registrar, ui

testedwith = '4.3'

cmdtable = {}
command = registrar.command(cmdtable)

if hasattr(sys, "frozen"):
    if sys.frozen == 'windows_exe':
        # sys.stdin is invalid, should be None.  Fixes svn, git subrepos
        sys.stdin = None
        if 'THGDEBUG' in os.environ:
            import win32traceutil
            print 'starting'
    # os.Popen() needs this, and Mercurial still uses os.Popen
    if 'COMSPEC' not in os.environ:
        comspec = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'),
                               'system32', 'cmd.exe')
        os.environ['COMSPEC'] = comspec
else:
    thgpath = os.path.dirname(os.path.realpath(__file__))
    thgpath = os.path.dirname(thgpath)
    testpath = os.path.join(thgpath, 'tortoisehg')
    if os.path.isdir(testpath) and thgpath not in sys.path:
        sys.path.insert(0, thgpath)

    if 'HGPATH' in os.environ:
        hgpath = os.environ['HGPATH']
        testpath = os.path.join(hgpath, 'mercurial')
        if os.path.isdir(testpath) and hgpath not in sys.path:
            sys.path.insert(0, hgpath)

# Make sure to load threading by main thread; otherwise, _MainThread instance
# may have wrong thread id and results KeyError at exit.
import threading

from mercurial import demandimport
demandimport.ignore.extend([
    'win32com.shell',
    'numpy',  # comtypes.npsupport does try-import
    'tortoisehg.util.config',
    'tortoisehg.hgqt.icons_rc',
    'tortoisehg.hgqt.translations_rc',
    # don't create troublesome demandmods for bunch of Q* attributes
    'tortoisehg.hgqt.qsci',
    'tortoisehg.hgqt.qtcore',
    'tortoisehg.hgqt.qtgui',
    'tortoisehg.hgqt.qtnetwork',
    # TODO: fix name resolution in demandimporter and remove these
    'qsci',
    'qtcore',
    'qtgui',
    'qtnetwork',
    # pygments seems to have trouble on loading plugins (see #4271, #4298)
    'pkgutil',
    'pkg_resources',
])
demandimport.enable()

# Verify we can reach TortoiseHg sources first
try:
    import tortoisehg.hgqt.run
except ImportError, e:
    sys.stderr.write(str(e)+'\n')
    sys.stderr.write("abort: couldn't find tortoisehg libraries in [%s]\n" %
                     os.pathsep.join(sys.path))
    sys.stderr.write("(check your install and PYTHONPATH)\n")
    sys.exit(-1)

def enforceversion():
    """Verify we have an acceptable version of Mercurial

    Display an error dialog in the contrary.
    """
    from tortoisehg.util.hgversion import hgversion, checkhgversion
    errmsg = checkhgversion(hgversion)
    if errmsg:
        from tortoisehg.hgqt.bugreport import run
        from tortoisehg.hgqt.run import qtrun
        opts = {}
        opts['cmd'] = ' '.join(sys.argv)
        opts['error'] = '\n' + errmsg + '\n'
        opts['nofork'] = True
        qtrun(run, ui.ui(), **opts)
        sys.exit(1)

@command('view', [], _("hg view`"), inferrepo=True)
def cmdview(ui, repo, *pats, **opts):
    """start light interactive history viewer from tortoisehg"""
    enforceversion()
    import cStringIO
    mystderr = cStringIO.StringIO()
    origstderr = sys.stderr
    sys.stderr = mystderr
    sys.__stdout__ = sys.stdout
    sys.__stderr__ = sys.stderr
    ret = 0
    try:
        from tortoisehg.hgqt.run import qtrun
        from tortoisehg.hgqt.run import debuglighthg as startfunc
        opts['repository'] = repo.root
        qtrun(startfunc, ui, *pats, **opts)

        sys.stderr = origstderr
        stderrout = mystderr.getvalue()
        errors = ('Traceback', 'TypeError', 'NameError', 'AttributeError',
                  'NotImplementedError')
        for l in stderrout.splitlines():
            if l.startswith(errors):
                from tortoisehg.hgqt.bugreport import run
                opts = {}
                opts['cmd'] = ' '.join(sys.argv)
                opts['error'] = 'Recoverable error (stderr):\n' + stderrout
                opts['nofork'] = True
                qtrun(run, ui.ui(), **opts)
                break
        sys.exit(ret)
    except SystemExit:
        raise
    except:
        sys.__stderr__ = sys.stderr = origstderr
        raise
