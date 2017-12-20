# setup.py
# A distutils setup script to install TortoiseHg in Windows and Posix
# environments.
#
# On Windows, this script is mostly used to build a stand-alone
# TortoiseHg package.  See installer\build.txt for details. The other
# use is to report the current version of the TortoiseHg source.

import time
import sys
import os
import shutil
import cgi
import tempfile
import re
import tarfile
from fnmatch import fnmatch
from distutils import log
if 'FORCE_SETUPTOOLS' in os.environ:
    from setuptools import setup
else:
    if 'py2app' in sys.argv[1:]:
        sys.exit("py2app requires FORCE_SETUPTOOLS=1 to be set in os.environ.")

    from distutils.core import setup
from distutils.core import Command
from distutils.command.build import build as _build_orig
from distutils.command.clean import clean as _clean_orig
from distutils.spawn import spawn, find_executable
from i18n.msgfmt import Msgfmt

thgcopyright = 'Copyright (C) 2010-2017 Steve Borho and others'
hgcopyright = 'Copyright (C) 2005-2017 Matt Mackall and others'

def _walklocales():
    podir = 'i18n/tortoisehg'
    for po in os.listdir(podir):
        if not po.endswith('.po'):
            continue
        pofile = os.path.join(podir, po)
        modir = os.path.join('locale', po[:-3], 'LC_MESSAGES')
        mofile = os.path.join(modir, 'tortoisehg.mo')
        yield pofile, modir, mofile

def _msgfmt(pofile, mofile):
    modata = Msgfmt(pofile).get()
    open(mofile, "wb").write(modata)

class build_mo(Command):
    description = "build translations (.mo files)"
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        for pofile, modir, mofile in _walklocales():
            self.mkpath(modir)
            self.make_file(pofile, mofile, _msgfmt, (pofile, mofile))

class import_po(Command):
    description = "import translations (.po file)"
    user_options = [
        ("package=", "p", ("launchpad export package or bzr repo "
                           "[default: launchpad-export.tar.gz]")),
        ("lang=", "l", "languages to be imported, separated by ','"),
        ]

    def initialize_options(self):
        self.package = None
        self.lang = None

    def finalize_options(self):
        if not self.package:
            self.package = 'launchpad-export.tar.gz'

        if self.lang:
            self.lang = self.lang.upper().split(',')

    def _untar(self, name, path='.'):
        tar = tarfile.open(name, 'r')
        path = os.path.abspath(path)
        for tarinfo in tar.getmembers():
            # Extract the safe file only
            p = os.path.abspath(os.path.join(path, tarinfo.name))
            if p.startswith(path):
                tar.extract(tarinfo, path)
        tar.close()

    def run(self):
        if not find_executable('msgcat'):
            self.warn("could not find msgcat executable")
            return

        dest_prefix = 'i18n/tortoisehg'
        src_prefix = 'po/tortoisehg'

        log.info('import from %s' % self.package)

        if os.path.isdir(self.package):
            self.bzrrepo = True
            self.package_path = self.package
        elif tarfile.is_tarfile(self.package):
            self.bzrrepo = False
            self.package_path = tempfile.mkdtemp()
            self._untar(self.package, self.package_path)
        else:
            self.warn('%s is not a valid tranlation package' % self.package)
            return

        if self.bzrrepo:
            filter = r'^([\S]+)\.po$'
        else:
            filter = r'^tortoisehg-([\S]+)\.po$'
        r = re.compile(filter)

        src_dir = os.path.join(self.package_path, src_prefix)
        for src_file in os.listdir(src_dir):
            m = r.match(src_file)
            if not m:
                continue

            # filter the language
            lang = m.group(1)
            if self.lang and lang.upper() not in self.lang:
                continue

            dest_file = os.path.join(dest_prefix, lang) + '.po'
            msg = 'updating %s...' % dest_file
            cmd = ['msgcat',
                   '--no-location',
                   '-o', dest_file,
                   os.path.join(src_dir, src_file)
                   ]
            self.execute(spawn, (cmd,), msg)

        if not self.bzrrepo:
            shutil.rmtree(self.package_path)

class update_pot(Command):
    description = "extract translatable strings to tortoisehg.pot"
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        if not find_executable('xgettext'):
            self.warn("could not find xgettext executable, tortoisehg.pot "
                      "won't be built")
            return

        dirlist = [
            '.',
            'contrib',
            'contrib/win32',
            'tortoisehg',
            'tortoisehg/hgqt',
            'tortoisehg/util',
            'tortoisehg/thgutil/iniparse',
            ]

        filelist = []
        for pathname in dirlist:
            if not os.path.exists(pathname):
                continue
            for filename in os.listdir(pathname):
                if filename.endswith('.py'):
                    filelist.append(os.path.join(pathname, filename))
        filelist.sort()

        potfile = 'tortoisehg.pot'

        cmd = [
            'xgettext',
            '--package-name', 'TortoiseHg',
            '--msgid-bugs-address', '<thg-devel@googlegroups.com>',
            '--copyright-holder', thgcopyright,
            '--from-code', 'ISO-8859-1',
            '--keyword=_:1,2c,2t',
            '--add-comments=i18n:',
            '-d', '.',
            '-o', potfile,
            ]
        cmd += filelist
        self.make_file(filelist, potfile, spawn, (cmd,))

class build_config(Command):
    description = 'create config module for unix installation'
    user_options = [
        ('build-lib=', 'd', 'directory to "build" (copy) to'),
        ]

    def initialize_options(self):
        self.build_lib = None

    def finalize_options(self):
        self.set_undefined_options('build',
                                   ('build_lib', 'build_lib'))

    def _generate_config(self, cfgfile):
        from tortoisehg.hgqt import qtcore
        # dirty hack to get the install root
        installcmd = self.get_finalized_command('install')
        rootlen = len(installcmd.root or '')
        sharedir = os.path.join(installcmd.install_data[rootlen:], 'share')
        data = {
            'bin_path': installcmd.install_scripts[rootlen:],
            'license_path': os.path.join(sharedir, 'doc', 'tortoisehg',
                                         'Copying.txt.gz'),
            'locale_path': os.path.join(sharedir, 'locale'),
            'icon_path': os.path.join(sharedir, 'pixmaps', 'tortoisehg',
                                      'icons'),
            'nofork': True,
            'qt_api': qtcore._detectapi(),
            }
        # Distributions will need to supply their own
        f = open(cfgfile, "w")
        try:
            for k, v in sorted(data.iteritems()):
                f.write('%s = %r\n' % (k, v))
        finally:
            f.close()

    def run(self):
        cfgdir = os.path.join(self.build_lib, 'tortoisehg', 'util')
        cfgfile = os.path.join(cfgdir, 'config.py')
        self.mkpath(cfgdir)
        self.make_file(__file__, cfgfile, self._generate_config, (cfgfile,))

class build_py2app_config(build_config):
    description = 'create config module for standalone OS X bundle'

    def _generate_config(self, cfgfile):
        from tortoisehg.hgqt import qtcore
        # Since py2app seems to ignore the build dir in favor of the src tree,
        # ignore the given path and generate it in the source tree.  The file
        # is conditionalized such that it won't interfere when run from source.
        cwd = os.path.dirname(__file__)
        cfgfile = os.path.join(cwd, 'tortoisehg', 'util', 'config.py')
        data = {
            'license_path': 'COPYING.txt',
            'locale_path': 'locale',
            'icon_path': 'icons',
            'qt_api': qtcore._detectapi(),
        }
        rsrc_dir = 'os.environ["RESOURCEPATH"]'

        f = open(cfgfile, "w")
        try:
            f.write("import os, sys\n"
                    "\n"
                    "if 'THG_OSX_APP' in os.environ:\n"
                    "    nofork = True\n")
            for k, v in sorted(data.iteritems()):
                f.write("    %s = os.path.join(%s, '%s')\n" % (k, rsrc_dir, v))
            f.write("    bin_path = os.path.dirname(sys.executable)\n")
        finally:
            f.close()

class build_ui(Command):
    description = 'build PyQt user interfaces (.ui)'
    user_options = [
        ('force', 'f', 'forcibly compile everything (ignore file timestamps)'),
        ]
    boolean_options = ('force',)

    def initialize_options(self):
        self.force = None

    def finalize_options(self):
        self.set_undefined_options('build', ('force', 'force'))

    def _compile_ui(self, ui_file, py_file):
        uic = self._impuic()
        fp = open(py_file, 'w')
        uic.compileUi(ui_file, fp)
        fp.close()

    @staticmethod
    def _impuic():
        from tortoisehg.hgqt.qtcore import QT_API
        mod = __import__(QT_API, globals(), locals(), ['uic'])
        return mod.uic

    _wrappeduic = False
    @classmethod
    def _wrapuic(cls):
        """wrap uic to use gettext's _() in place of tr()"""
        if cls._wrappeduic:
            return

        uic = cls._impuic()
        compiler = uic.Compiler.compiler
        qtproxies = uic.Compiler.qtproxies
        indenter = uic.Compiler.indenter

        class _UICompiler(compiler.UICompiler):
            def createToplevelWidget(self, classname, widgetname):
                o = indenter.getIndenter()
                o.level = 0
                o.write('from tortoisehg.util.i18n import _')
                return super(_UICompiler, self).createToplevelWidget(classname,
                                                                     widgetname)
        compiler.UICompiler = _UICompiler

        class _i18n_string(qtproxies.i18n_string):
            def __str__(self):
                return "_('%s')" % self.string.encode('string-escape')
        qtproxies.i18n_string = _i18n_string

        cls._wrappeduic = True

    def run(self):
        self._wrapuic()
        basepath = os.path.join(os.path.dirname(__file__), 'tortoisehg', 'hgqt')
        for f in os.listdir(basepath):
            if not f.endswith('.ui'):
                continue
            uifile = os.path.join(basepath, f)
            pyfile = uifile[:-3] + '_ui.py'
            # setup.py is the source of "from i18n import _" line
            self.make_file([uifile, __file__], pyfile,
                           self._compile_ui, (uifile, pyfile))

class build_qrc(Command):
    description = 'build PyQt resource files (.qrc)'
    user_options = [
        ('build-lib=', 'd', 'directory to "build" (copy) to'),
        ('force', 'f', 'forcibly compile everything (ignore file timestamps)'),
        ]
    boolean_options = ('force',)

    def initialize_options(self):
        self.build_lib = None
        self.force = None

    def finalize_options(self):
        self.set_undefined_options('build',
                                   ('build_lib', 'build_lib'),
                                   ('force', 'force'))

    def _findrcc(self):
        from tortoisehg.hgqt.qtcore import QT_API
        try:
            rcc = {'PyQt4': 'pyrcc4', 'PyQt5': 'pyrcc5'}[QT_API]
        except KeyError:
            raise RuntimeError('unsupported Qt API: %s' % QT_API)
        if os.name != 'nt' or QT_API == 'PyQt5':
            return rcc
        mod = __import__(QT_API, globals(), locals())
        return os.path.join(os.path.dirname(mod.__file__), rcc)

    def _generate_qrc(self, qrc_file, srcfiles, prefix):
        basedir = os.path.dirname(qrc_file)
        f = open(qrc_file, 'w')
        try:
            f.write('<!DOCTYPE RCC><RCC version="1.0">\n')
            f.write('  <qresource prefix="%s">\n' % cgi.escape(prefix))
            for e in srcfiles:
                relpath = e[len(basedir) + 1:]
                f.write('    <file>%s</file>\n'
                        % cgi.escape(relpath.replace(os.path.sep, '/')))
            f.write('  </qresource>\n')
            f.write('</RCC>\n')
        finally:
            f.close()

    def _build_rc(self, srcfiles, py_file, basedir, prefix):
        """Generate compiled resource including any files under basedir"""
        # For details, see http://doc.qt.nokia.com/latest/resources.html
        qrc_file = os.path.join(basedir, '%s.qrc' % os.path.basename(basedir))
        try:
            self._generate_qrc(qrc_file, srcfiles, prefix)
            spawn([self._findrcc(), qrc_file, '-o', py_file])
        finally:
            os.unlink(qrc_file)

    def _build_icons(self, basepath):
        icondir = os.path.join(os.path.dirname(__file__), 'icons')
        iconfiles = []
        for root, dirs, files in os.walk(icondir):
            if root == icondir:
                dirs.remove('svg')  # drop source of .ico files
            iconfiles.extend(os.path.join(root, f) for f in files
                             if f.endswith(('.png', '.svg')))
        pyfile = os.path.join(basepath, 'icons_rc.py')
        # we cannot detect deleted icons
        self.make_file(iconfiles, pyfile,
                       self._build_rc, (iconfiles, pyfile, icondir, '/icons'),
                       exec_msg='generating %s from %s' % (pyfile, icondir))

    def _build_translations(self, basepath):
        """Build translations_rc.py which inclues qt_xx.qm"""
        from tortoisehg.hgqt.qtcore import QT_API
        if QT_API == 'PyQt4':
            if os.name == 'nt':
                import PyQt4
                trpath = os.path.join(
                    os.path.dirname(PyQt4.__file__), 'translations')
            else:
                from PyQt4.QtCore import QLibraryInfo
                trpath = unicode(
                    QLibraryInfo.location(QLibraryInfo.TranslationsPath))
        else:
            if os.name == 'nt':
                import PyQt5
                trpath = os.path.join(
                    os.path.dirname(PyQt5.__file__), 'translations')
            else:
                from PyQt5.QtCore import QLibraryInfo
                trpath = unicode(
                    QLibraryInfo.location(QLibraryInfo.TranslationsPath))
        builddir = os.path.join(self.get_finalized_command('build').build_base,
                                'qt-translations')
        self.mkpath(builddir)

        # we have to copy .qm files to build directory because .qrc file must
        # specify files by relative paths
        qmfiles = []
        for e in os.listdir(trpath):
            if (not e.startswith(('qt_', 'qscintilla_'))
                or e.startswith('qt_help_')
                or not e.endswith('.qm')):
                continue
            f = os.path.join(builddir, e)
            self.copy_file(os.path.join(trpath, e), f)
            qmfiles.append(f)
        pyfile = os.path.join(basepath, 'translations_rc.py')
        self.make_file(qmfiles, pyfile, self._build_rc,
                       (qmfiles, pyfile, builddir, '/translations'),
                       exec_msg='generating %s from Qt translation' % pyfile)

    def run(self):
        basepath = os.path.join(self.build_lib, 'tortoisehg', 'hgqt')
        self.mkpath(basepath)
        self._build_icons(basepath)
        self._build_translations(basepath)

class clean_local(Command):
    pats = ['*.py[co]', '*_ui.py', '*.mo', '*.orig', '*.rej']
    excludedirs = ['.hg', 'build', 'dist']
    description = 'clean up generated files (%s)' % ', '.join(pats)
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        for e in self._walkpaths('.'):
            log.info("removing '%s'" % e)
            os.remove(e)

    def _walkpaths(self, path):
        for root, _dirs, files in os.walk(path):
            if any(root == os.path.join(path, e)
                   or root.startswith(os.path.join(path, e, ''))
                   for e in self.excludedirs):
                continue
            for e in files:
                fpath = os.path.join(root, e)
                if any(fnmatch(fpath, p) for p in self.pats):
                    yield fpath

class build(_build_orig):
    sub_commands = [
        ('build_config',
         lambda self: (os.name != 'nt' and
                       'py2app' not in self.distribution.commands)),
        ('build_py2app_config',
         lambda self: 'py2app' in self.distribution.commands),
        ('build_ui', None),
        ('build_qrc', lambda self: 'py2exe' in self.distribution.commands),
        ('build_mo', None),
        ] + _build_orig.sub_commands

class clean(_clean_orig):
    sub_commands = [
        ('clean_local', None),
        ] + _clean_orig.sub_commands

    def run(self):
        _clean_orig.run(self)
        for e in self.get_sub_commands():
            self.run_command(e)

cmdclass = {
    'build': build,
    'build_config': build_config,
    'build_py2app_config': build_py2app_config,
    'build_ui': build_ui,
    'build_qrc': build_qrc,
    'build_mo': build_mo,
    'clean': clean,
    'clean_local': clean_local,
    'update_pot': update_pot,
    'import_po': import_po,
    }

def setup_windows(version):
    # Specific definitios for Windows NT-alike installations
    _scripts = []
    _data_files = []
    _packages = ['tortoisehg.hgqt', 'tortoisehg.util', 'tortoisehg', 'hgext3rd']
    extra = {}
    hgextmods = []

    # py2exe needs to be installed to work
    try:
        import py2exe

        # Help py2exe to find win32com.shell
        try:
            import modulefinder
            import win32com
            for p in win32com.__path__[1:]: # Take the path to win32comext
                modulefinder.AddPackagePath("win32com", p)
            pn = "win32com.shell"
            __import__(pn)
            m = sys.modules[pn]
            for p in m.__path__[1:]:
                modulefinder.AddPackagePath(pn, p)
        except ImportError:
            pass

    except ImportError:
        if '--version' not in sys.argv:
            raise

    # Allow use of environment variables to specify the location of Mercurial
    import modulefinder
    path = os.getenv('MERCURIAL_PATH')
    if path:
        modulefinder.AddPackagePath('mercurial', path)
    path = os.getenv('HGEXT_PATH')
    if path:
        modulefinder.AddPackagePath('hgext', path)
    modulefinder.AddPackagePath('hgext3rd', 'hgext3rd')

    if 'py2exe' in sys.argv:
        import hgext
        hgextdir = os.path.dirname(hgext.__file__)
        hgextmods = set(["hgext." + os.path.splitext(f)[0]
                         for f in os.listdir(hgextdir)])
        # most icons are packed into Qt resource, but .ico files must reside
        # in filesystem so that shell extension can read them
        root = 'icons'
        _data_files.append((root,
                            [os.path.join(root, f) for f in os.listdir(root)
                             if f.endswith('.ico') or f == 'README.txt']))

    # for PyQt, see http://www.py2exe.org/index.cgi/Py2exeAndPyQt
    includes = ['sip']

    # Qt4 plugins, see http://stackoverflow.com/questions/2206406/
    def qt4_plugins(subdir, *dlls):
        import PyQt4
        pluginsdir = os.path.join(os.path.dirname(PyQt4.__file__), 'plugins')
        return (subdir, [os.path.join(pluginsdir, subdir, e) for e in dlls])

    def qt5_plugins(subdir, *dlls):
        import PyQt5
        pluginsdir = os.path.join(os.path.dirname(PyQt5.__file__), 'plugins')
        return (subdir, [os.path.join(pluginsdir, subdir, e) for e in dlls])

    from tortoisehg.hgqt.qtcore import QT_API
    if QT_API == 'PyQt4':
        _data_files.append(qt4_plugins('imageformats',
                                       'qico4.dll', 'qsvg4.dll'))
    else:
        _data_files.append(qt5_plugins('platforms', 'qwindows.dll'))
        _data_files.append(qt5_plugins('imageformats',
                                       'qico.dll', 'qsvg.dll', 'qjpeg.dll',
                                       'qgif.dll', 'qicns.dll', 'qtga.dll',
                                       'qtiff.dll', 'qwbmp.dll', 'qwebp.dll'))

    # Manually include other modules py2exe can't find by itself.
    if 'hgext.highlight' in hgextmods:
        includes += ['pygments.*', 'pygments.lexers.*', 'pygments.formatters.*',
                     'pygments.filters.*', 'pygments.styles.*']
    if 'hgext.patchbomb' in hgextmods:
        includes += ['email.*', 'email.mime.*']

    extra['options'] = {}
    extra['options']['py2exe'] = {
        "skip_archive": 0,
        # Don't pull in all this MFC stuff used by the makepy UI.
        "excludes": ("pywin,pywin.dialogs,pywin.dialogs.list,setuptools"
                     "setup,distutils"),  # required only for in-place use
        "includes": includes,
        "optimize": 1,
        }
    extra['console'] = [
        {'script': 'thg',
         'icon_resources': [(0, 'icons/thg_logo.ico')],
         'description': 'TortoiseHg GUI tools for Mercurial SCM',
         'copyright': thgcopyright,
         'product_version': version,
         },
        {'script': 'contrib/hg',
         'icon_resources': [(0, 'icons/hg.ico')],
         'description': 'Mercurial Distributed SCM',
         'copyright': hgcopyright,
         'product_version': version,
         },
        {'script': 'win32/docdiff.py',
         'icon_resources': [(0, 'icons/TortoiseMerge.ico')],
         'copyright': thgcopyright,
         'product_version': version,
         },
        ]
    extra['windows'] = [
        {'script': 'thg',
         'dest_base': 'thgw',
         'icon_resources': [(0, 'icons/thg_logo.ico')],
         'description': 'TortoiseHg GUI tools for Mercurial SCM',
         'copyright': thgcopyright,
         'product_version': version,
         },
        {'script': 'TortoiseHgOverlayServer.py',
         'icon_resources': [(0, 'icons/thg_logo.ico')],
         'description': 'TortoiseHg Overlay Icon Server',
         'copyright': thgcopyright,
         'product_version': version,
         },
        ]
    # put dlls in sub directory so that they won't pollute PATH
    extra['zipfile'] = 'lib/library.zip'

    return _scripts, _packages, _data_files, extra

def setup_osx(version):
    _extra = {}

    # This causes py2app to copy the scripts into build/ and then adjust the
    # mode, but the build dir is ignored for some reason.
    _scripts = ['thg']

    _packages = ['tortoisehg.hgqt', 'tortoisehg.util', 'tortoisehg', 'hgext3rd']
    _data_files = []

    def qt4_plugins(subdir, *libs):
        from PyQt4.QtCore import QLibraryInfo
        pluginsdir = unicode(QLibraryInfo.location(QLibraryInfo.PluginsPath))

        return ('qt_plugins/' + subdir,
                [os.path.join(pluginsdir, subdir, e) for e in libs])

    def qt5_plugins(subdir, *dlls):
        import PyQt5
        pluginsdir = os.path.join(os.path.dirname(PyQt5.__file__), 'plugins')
        return (subdir, [os.path.join(pluginsdir, subdir, e) for e in dlls])

    from tortoisehg.hgqt.qtcore import QT_API
    if QT_API == 'PyQt4':
        _data_files.append(qt4_plugins('imageformats', 'libqsvg.dylib'))
    else:
        _data_files.append(qt5_plugins('platforms', 'libqcocoa.dylib'))
        _data_files.append(qt5_plugins('imageformats', 'libqsvg.dylib'))

    _py2app_options = {
        'arch': 'x86_64',
        'argv_emulation': False,
        'no_chdir': True,
        'excludes': ['Carbon', 'curses', 'distools', 'distutils', 'docutils',
                     'PyQt4.phonon', 'PyQt4.QtDeclarative', 'PyQt4.QtDesigner',
                     'PyQt4.QtHelp', 'PyQt4.QtMultimedia', 'PyQt4.QtOpenGL',
                     'PyQt4.QtScript', 'PyQt4.QtScriptTools', 'PyQt4.QtSql',
                     'PyQt4.QtTest', 'PyQt4.QtWebKit', 'PyQt4.QtXmlPatterns',
                     'py2app', 'setup', 'setuptools', 'unittest', 'PIL'],

        'extra_scripts': ['contrib/hg'],
        'iconfile': 'contrib/TortoiseHg.icns',
        'includes': ['email.mime.text', 'sip'],
        'packages': ['hgext', 'mercurial', 'pygments', 'tortoisehg'],

        'plist': {
            'CFBundleDisplayName': 'TortoiseHg',
            'CFBundleExecutable': 'TortoiseHg',
            'CFBundleIdentifier': 'org.tortoisehg.thg',
            'CFBundleName': 'TortoiseHg',
            'CFBundleShortVersionString': version,
            'CFBundleVersion': version,
            'LSEnvironment': {
                # because launched app can't inherit environment variables from
                # console, the encoding would be set to "ascii" by default
                'HGENCODING': 'utf-8',
                'THG_OSX_APP': '1',
            },
            'NSHumanReadableCopyright': thgcopyright,
        },

        'resources': ['COPYING.txt', 'icons', 'locale'],
    }

    _extra['app'] = ['thg']
    _extra['setup_requires'] = ['py2app']
    _extra['options'] = {'py2app': _py2app_options}

    return _scripts, _packages, _data_files, _extra

def setup_posix():
    # Specific definitios for Posix installations
    _extra = {}
    _scripts = ['thg']
    _packages = ['tortoisehg', 'tortoisehg.hgqt', 'tortoisehg.util', 'hgext3rd']
    _data_files = []
    # .svg and .png are loaded by thg, .ico by nautilus extension
    for root, dirs, files in os.walk('icons'):
        if root == 'icons':
            dirs.remove('svg')  # drop source of .ico files
        _data_files.append((os.path.join('share/pixmaps/tortoisehg', root),
                            [os.path.join(root, f) for f in files]))
    _data_files.extend((os.path.join('share', modir), [mofile])
                       for pofile, modir, mofile in _walklocales())
    _data_files += [('share/nautilus-python/extensions',
                     ['contrib/nautilus-thg.py'])]

    return _scripts, _packages, _data_files, _extra

if __name__ == '__main__':
    version = ''

    if os.path.isdir('.hg'):
        from tortoisehg.util import version as _version
        branch, version = _version.liveversion()
        if version.endswith('+'):
            version += time.strftime('%Y%m%d')
    elif os.path.exists('.hg_archival.txt'):
        kw = dict([t.strip() for t in l.split(':', 1)]
                  for l in open('.hg_archival.txt'))
        if 'tag' in kw:
            version = kw['tag']
        elif 'latesttag' in kw:
            version = '%(latesttag)s+%(latesttagdistance)s-%(node).12s' % kw
        else:
            version = kw.get('node', '')[:12]

    if version:
        f = open("tortoisehg/util/__version__.py", "w")
        f.write('# this file is autogenerated by setup.py\n')
        f.write('version = "%s"\n' % version)
        f.close()

    try:
        import tortoisehg.util.__version__
        version = tortoisehg.util.__version__.version
    except ImportError:
        version = 'unknown'

    if os.name == "nt":
        (scripts, packages, data_files, extra) = setup_windows(version)
        # Windows binary file versions for exe/dll files must have the
        # form W.X.Y.Z, where W,X,Y,Z are numbers in the range 0..65535
        from tortoisehg.util.version import package_version
        setupversion = package_version()
        productname = 'TortoiseHg'
    elif sys.platform == "darwin" and 'py2app' in sys.argv[1:]:
        (scripts, packages, data_files, extra) = setup_osx(version)
        setupversion = version
        productname = 'TortoiseHg'
    else:
        (scripts, packages, data_files, extra) = setup_posix()
        setupversion = version
        productname = 'tortoisehg'

    setup(name=productname,
          version=setupversion,
          author='Steve Borho',
          author_email='steve@borho.org',
          url='https://tortoisehg.bitbucket.io',
          description='TortoiseHg dialogs for Mercurial VCS',
          license='GNU GPL2',
          scripts=scripts,
          packages=packages,
          data_files=data_files,
          cmdclass=cmdclass,
          **extra)
