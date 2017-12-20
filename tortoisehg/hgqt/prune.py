# prune.py - simple dialog to prune revisions
#
# Copyright 2014 Yuya Nishihara <yuya@tcha.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version.

from __future__ import absolute_import

from .qtcore import (
    QTimer,
    pyqtSlot,
)
from .qtgui import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QSizePolicy,
    QVBoxLayout,
)

from ..util import hglib
from ..util.i18n import _
from . import (
    cmdcore,
    cmdui,
    cslist,
    qtlib,
)

class PruneWidget(cmdui.AbstractCmdWidget):

    def __init__(self, repoagent, parent=None):
        super(PruneWidget, self).__init__(parent)
        self._repoagent = repoagent

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        vbox = QVBoxLayout(self)
        form = QFormLayout()
        vbox.addLayout(form)

        self._revedit = w = QComboBox(self)
        w.setEditable(True)
        qtlib.allowCaseChangingInput(w)
        w.installEventFilter(qtlib.BadCompletionBlocker(w))
        w.activated.connect(self._updateRevset)
        w.lineEdit().textEdited.connect(self._onRevsetEdited)
        form.addRow(_('Target:'), w)

        optbox = QVBoxLayout()
        form.addRow('', optbox)
        self._optchks = {}
        for name, text in [
                ('keep', _('Do not modify working copy (-k/--keep)')),
        ]:
            self._optchks[name] = w = QCheckBox(text, self)
            optbox.addWidget(w)

        repo = repoagent.rawRepo()
        self._cslist = w = cslist.ChangesetList(repo, self)
        vbox.addWidget(w)

        self._querysess = cmdcore.nullCmdSession()
        # slightly longer delay than common keyboard auto-repeat rate
        self._querylater = QTimer(self, interval=550, singleShot=True)
        self._querylater.timeout.connect(self._updateRevset)

        self._revedit.setFocus()

    def revset(self):
        return unicode(self._revedit.currentText())

    def setRevset(self, revspec):
        if self.revset() == unicode(revspec):
            return
        w = self._revedit
        i = w.findText(revspec)
        if i < 0:
            i = 0
            w.insertItem(i, revspec)
        w.setCurrentIndex(i)
        self._updateRevset()

    @pyqtSlot()
    def _onRevsetEdited(self):
        self._querysess.abort()
        self._querylater.start()
        self.commandChanged.emit()

    @pyqtSlot()
    def _updateRevset(self):
        self._querysess.abort()
        self._querylater.stop()
        cmdline = hglib.buildcmdargs('log', rev=self.revset(), T='{rev}\n')
        self._querysess = sess = self._repoagent.runCommand(cmdline, self)
        sess.setCaptureOutput(True)
        sess.commandFinished.connect(self._onQueryFinished)
        self.commandChanged.emit()

    @pyqtSlot(int)
    def _onQueryFinished(self, ret):
        sess = self._querysess
        if not sess.isFinished() or self._querylater.isActive():
            # new query is already or about to be running
            return
        if ret == 0:
            revs = map(int, str(sess.readAll()).splitlines())
        else:
            revs = []
        self._cslist.update(revs)
        self.commandChanged.emit()

    def canRunCommand(self):
        sess = self._querysess
        return (sess.isFinished() and sess.exitCode() == 0
                and not self._querylater.isActive())

    def runCommand(self):
        opts = {}
        opts.update((n, w.isChecked()) for n, w in self._optchks.iteritems())
        cmdline = hglib.buildcmdargs('prune', rev=self.revset(), **opts)
        return self._repoagent.runCommand(cmdline, self)


def createPruneDialog(repoagent, revspec, parent=None):
    dlg = cmdui.CmdControlDialog(parent)
    dlg.setWindowIcon(qtlib.geticon('edit-cut'))
    dlg.setWindowTitle(_('Prune - %s') % repoagent.displayName())
    dlg.setObjectName('prune')
    dlg.setRunButtonText(_('&Prune'))
    cw = PruneWidget(repoagent, dlg)
    cw.setRevset(revspec)
    dlg.setCommandWidget(cw)
    return dlg
