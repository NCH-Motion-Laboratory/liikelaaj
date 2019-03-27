# -*- coding: utf-8 -*-
"""

Program for input and reporting of ROM (range of motion), strength and other
measurements.

Py2/3 compatible via futurize.

Design:

-uses an ui file made with Qt Designer

-custom widget (CheckDegSpinBox): plugin file should be made available to Qt
 designer (checkspinbox_plugin.py). export PYQTDESIGNERPATH=path

-input widget naming convention: first 2-3 chars indicate widget type
 (mandatory), next word indicate variable category or page where widget
 resides the rest indicates the variable. E.g. 'lnTiedotNimi'

-widget inputs are updated into an internal dict whenever any value changes

-dict keys are taken automatically from widget names by removing first 2-3
 chars (widget type)

-for saving, dict data is turned into json unicode and written out in utf-8

-data is saved into temp directory whenever any values are changed by user

-magic mechanism for weight normalized data: widgets can have names ending
with 'NormUn' which creates a weight unnormalized value. The
corresponding widget name with UnNorm replaced by Norm (which must exist)
is then automatically updated whenever either weight or the unnormalized value
changes

-files do not include any version info (maybe a stupid decision), instead
 mismatches between the input widgets and loaded json are detected and reported
 to the user. Missing data in JSON is quietly assumed to be ok (perhaps from
 an older version). Extra data in JSON (no corresponding widget) is reported
 (but not fatal).

@author: Jussi (jnu@iki.fi)
"""


from __future__ import print_function

from PyQt5 import uic, QtCore, QtWidgets
import sys
import traceback
import io
import os
import os.path as op
import json
import webbrowser
import logging
import psutil
from pkg_resources import resource_filename

from .config import Config
from .widgets import (MyLineEdit, DegLineEdit, CheckDegSpinBox, message_dialog,
                      confirm_dialog)
from .utils import _check_hetu
from . import reporter, ll_msgs

logger = logging.getLogger(__name__)


class EntryApp(QtWidgets.QMainWindow):
    """ Main window of application. """

    def __init__(self, check_temp_file=True):
        super(EntryApp, self).__init__()
        # load user interface made with Qt Designer
        uifile = resource_filename('liikelaaj', 'tabbed_design.ui')
        uic.loadUi(uifile, self)
        self.init_widgets()
        self.data = {}
        # save empty form (default states for widgets)
        self.read_forms()
        self.data_empty = self.data.copy()
        # whether to save to temp file whenever input widget data changes
        self.save_to_tmp = True
        # whether data was saved into a patient-specific file
        self.saved_to_file = True
        self.last_saved_filename = ''
        # whether to update internal dict of variables
        self.update_dict = True
        # load tmp file if it exists
        if op.isfile(Config.tmpfile) and check_temp_file:
            message_dialog(ll_msgs.temp_found)
            self.load_temp()
        self.text_template = resource_filename('liikelaaj',
                                               Config.text_template)
        self.xls_template = resource_filename('liikelaaj', Config.xls_template)
        # TODO: set locale and options if needed
        # loc = QtCore.QLocale()
        # loc.setNumberOptions(loc.OmitGroupSeparator |
        #            loc.RejectGroupSeparator)
        # DEBUG: print all vars
        # for key in sorted(self.data.keys()):
        #    print('{%s}'%key)
        # print(self.units)

    def init_widgets(self):
        """ Make a dict of our input widgets and install some callbacks and
        convenience methods etc. """
        self.input_widgets = {}

        def spinbox_getval(w):
            """ Return spinbox value. If it is at minimum, the special
            value mintext will be returned. """
            val = w.value()
            if val == w.minimum():
                return w.no_value_text
            else:
                return val

        def spinbox_setval(w, val):
            """ Set spinbox value. val == mintext causes value to
            be set to minimum. """
            if val == w.no_value_text:
                w.setValue(w.minimum())
            else:
                w.setValue(val)

        def checkbox_getval(w):
            """ Return yestext or notext for checkbox enabled/disabled,
            respectively. """
            val = int(w.checkState())
            if val == 0:
                return w.no_text
            elif val == 2:
                return w.yes_text
            else:
                raise Exception('Unexpected checkbox value')

        def checkbox_setval(w, val):
            """ Set checkbox value to enabled for val == yestext and
            disabled for val == notext """
            if val == w.yes_text:
                w.setCheckState(2)
            elif val == w.no_text:
                w.setCheckState(0)
            else:
                raise Exception('Unexpected checkbox entry value')

        def combobox_getval(w):
            """ Get combobox current choice as text """
            return w.currentText()

        def combobox_setval(w, val):
            """ Set combobox value according to val (unicode) (must be one of
            the combobox items) """
            idx = w.findText(val)
            if idx >= 0:
                w.setCurrentIndex(idx)
            else:
                raise ValueError('Tried to set combobox to invalid value.')

        def keyPressEvent_resetOnEsc(obj, event):
            """ Special event handler for spinboxes. Resets value (sets it
            to minimum) when Esc is pressed. """
            if event.key() == QtCore.Qt.Key_Escape:
                obj.setValue(obj.minimum())
            else:
                super(obj.__class__, obj).keyPressEvent(event)

        def isint(x):
            """ Test for integer """
            try:
                int(x)
                return True
            except ValueError:
                return False

        """ Change lineEdit to custom one for spinboxes. This cannot be done in
        the main widget loop below, because the old QLineEdits get destroyed in
        the process (by Qt) and the loop then segfaults while trying to
        dereference them (the loop collects all QLineEdits at the start).
        Also install special keypress event handler. """
        for w in self.findChildren((QtWidgets.QSpinBox,
                                    QtWidgets.QDoubleSpinBox)):
            wname = w.objectName()
            if wname[:2] == 'sp':
                w.setLineEdit(MyLineEdit())
                w.keyPressEvent = (lambda event, w=w:
                                   keyPressEvent_resetOnEsc(w, event))

        """ CheckDegSpinBox class gets a special LineEdit that catches space
        and mouse press events """
        for w in self.findChildren(CheckDegSpinBox):
            w.degSpinBox.setLineEdit(DegLineEdit())

        allwidgets = self.findChildren(QtWidgets.QWidget)

        def _weight_normalize(w):
            """Auto calculate callback for weight normalized widgets"""
            val, weight = (w.getVal() for w in w._autoinputs)
            try:
                w.setVal(val/weight)
            except TypeError:
                pass

        # autowidgets are special widgets with automatically computed values
        # they must have ._autocalculate() method which updates the widget
        # and ._autoinputs list which lists needed input widgets
        self.autowidgets = list()
        weight_widget = self.spAntropPaino
        for w in allwidgets:
            wname = w.objectName()
            # handle the 'magic' autowidgets with weight normalized data
            if wname[-4:] == 'Norm':
                self.autowidgets.append(w)
                # corresponding unnormalized widget
                wname_unnorm = wname.replace('Norm', 'NormUn')
                w_unnorm = self.__dict__[wname_unnorm]
                w._autoinputs = [w_unnorm, weight_widget]
                w._autocalculate = lambda w=w: _weight_normalize(w)

        # autowidget values cannot be directly modified
        for w in self.autowidgets:
            w.setEnabled(False)

        """ Set various widget convenience methods/properties """
        for w in allwidgets:
            wname = w.objectName()
            wsave = True
            w.unit = lambda: ''  # if a widget input has units, set it below
            if wname[:2] == 'sp':  # spinbox or doublespinbox
                # -lambdas need default arguments because of late binding
                # -lambda expression needs to consume unused 'new value' arg,
                # therefore two parameters (except for QTextEdit...)
                w.valueChanged.connect(lambda x, w=w: self.values_changed(w))
                w.no_value_text = Config.spinbox_novalue_text
                w.setVal = lambda val, w=w: spinbox_setval(w, val)
                w.getVal = lambda w=w: spinbox_getval(w)
                w.unit = lambda w=w: w.suffix() if isint(w.getVal()) else ''
            elif wname[:2] == 'ln':  # lineedit
                w.textChanged.connect(lambda x, w=w: self.values_changed(w))
                w.setVal = w.setText
                w.getVal = lambda w=w: w.text().strip()
            elif wname[:2] == 'cb':  # combobox
                w.currentIndexChanged.connect(lambda x,
                                              w=w: self.values_changed(w))
                w.setVal = lambda val, w=w: combobox_setval(w, val)
                w.getVal = lambda w=w: combobox_getval(w)
            elif wname[:3] == 'cmt':  # comment text field
                w.textChanged.connect(lambda w=w: self.values_changed(w))
                w.setVal = w.setPlainText
                w.getVal = lambda w=w: w.toPlainText().strip()
            elif wname[:2] == 'xb':  # checkbox
                w.stateChanged.connect(lambda x, w=w: self.values_changed(w))
                w.yes_text = Config.checkbox_yestext
                w.no_text = Config.checkbox_notext
                w.setVal = lambda val, w=w: checkbox_setval(w, val)
                w.getVal = lambda w=w: checkbox_getval(w)
            elif wname[:3] == 'csb':  # checkdegspinbox
                w.valueChanged.connect(lambda w=w: self.values_changed(w))
                w.getVal = w.value
                w.setVal = w.setValue
                w.unit = lambda w=w: w.getSuffix() if isint(w.getVal()) else ''
            else:
                wsave = False
            if wsave:
                self.input_widgets[wname] = w
                # TODO: specify whether input value is 'mandatory' or not
                w.important = False

        self.btnSave.clicked.connect(self.save_dialog)
        self.btnLoad.clicked.connect(self.load_dialog)
        self.btnClear.clicked.connect(self.clear_forms_dialog)
        self.btnReport.clicked.connect(self.save_report_dialog)
        self.btnExcelReport.clicked.connect(self.save_excel_report_dialog)
        self.btnHelp.clicked.connect(self.open_help)
        self.btnQuit.clicked.connect(self.close)

        # slot called on tab change
        self.maintab.currentChanged.connect(self.page_change)

        """ First widget of each page. This is used to do focus/selectall on
        the 1st widget on page change so that data can be entered immediately.
        Only needed for spinbox / lineedit widgets. """
        self.firstwidget = dict()
        # TODO: check/fix
        self.firstwidget[self.tabTiedot] = self.lnTiedotNimi
        self.firstwidget[self.tabKysely] = self.lnKyselyPaivittainenMatka
        self.firstwidget[self.tabAntrop] = self.spAntropAlaraajaOik
        self.firstwidget[self.tabLonkka] = self.csbLonkkaFleksioOik
        self.firstwidget[self.tabNilkka] = self.csbNilkkaSoleusCatchOik
        self.firstwidget[self.tabPolvi] = self.csbPolviEkstensioVapOik
        self.firstwidget[self.tabVirheas] = self.spVirheasAnteversioOik
        self.firstwidget[self.tabTasap] = self.spTasapOik
        self.total_widgets = len(self.input_widgets)

        self.statusbar.showMessage(ll_msgs.ready.format(n=self.total_widgets))

        """ Set up widget -> varname translation dict. Currently variable names
        are derived by removing 2 first characters from widget names (except
        for comment box variables cmt* which are identical with widget names).
        """
        self.widget_to_var = dict()
        for wname in self.input_widgets:
            if wname[:3] == 'cmt':
                varname = wname
            elif wname[:3] == 'csb':  # custom widget
                varname = wname[3:]
            else:
                varname = wname[2:]
            self.widget_to_var[wname] = varname

        # try to increase font size
        self.setStyleSheet('QWidget { font-size: %dpt;}'
                           % Config.global_fontsize)

        # FIXME: make sure we always start on 1st tab

    @property
    def units(self):
        """ Return dict indicating the units for each variable. This may change
        dynamically as the unit may be set to '' for special values. """
        return {self.widget_to_var[wname]: self.input_widgets[wname].unit()
                for wname in self.input_widgets}

    @property
    def vars_default(self):
        """ Return a list of variables that are at their default (unmodified)
        state. """
        return [key for key in self.data if
                self.data[key] == self.data_empty[key]]

    def closeEvent(self, event):
        """ Confirm and close application. """
        if not self.saved_to_file:
            reply = confirm_dialog(ll_msgs.quit_not_saved)
        else:
            reply = confirm_dialog(ll_msgs.quit_)
        if reply == QtWidgets.QMessageBox.YesRole:
            self.rm_temp()
            event.accept()
        else:
            event.ignore()

    @staticmethod
    def open_help():
        """ Show help. """
        webbrowser.open(Config.help_url)

    @property
    def data_with_units(self):
        """Return data dict, with units appended to values"""
        return {key: u'%s%s' % (self.data[key], self.units[key]) for key in
                self.data}

    @property
    def report(self):
        """Return Report instance with current data"""
        return reporter.Report(self.data_with_units, self.vars_default)

    def debug_make_report(self):
        """ DEBUG: make and save text report using the input data. """
        report_txt = self.report.make_report(self.text_template)
        fname = 'report_koe.txt'
        with io.open(fname, 'w', encoding='utf-8') as f:
            f.write(report_txt)
        self.statusbar.showMessage(ll_msgs.wrote_report.format(filename=fname))

    def debug_make_excel_report(self):
        """ DEBUG: save into temporary .xls """
        self.report.make_excel('test_excel_report.xls',
                               self.xls_template)

    def values_changed(self, w):
        """Called whenever widget w value changes"""
        # find autowidgets that depend on w and update them
        autowidgets_this = [widget for widget in self.autowidgets if w
                            in widget._autoinputs]
        for widget in autowidgets_this:
            widget._autocalculate()
        if self.update_dict:  # update internal data dict
            # DEBUG
            # print('updating dict:', w.objectName(),'new value:',w.getVal())
            wname = w.objectName()
            self.data[self.widget_to_var[wname]] = w.getVal()
            # DEBUG: make text report on every widget update
            # reload(reporter)  # can edit reporter / template while running
            # self.debug_make_report()
            # DEBUG: make xls report at every update
            # self.debug_make_excel_report()
        self.saved_to_file = False
        if self.save_to_tmp:
            self.save_temp()

    def load_file(self, fname):
        """ Load data from JSON file and restore forms. """
        if op.isfile(fname):
            with io.open(fname, 'r', encoding='utf-8') as f:
                data_loaded = json.load(f)
            keys, loaded_keys = set(self.data), set(data_loaded)
            # warn the user about key mismatch
            if keys != loaded_keys:
                self.keyerror_dialog(keys, loaded_keys)
            # reset data before load (loaded data might not have all vars)
            self.data = self.data_empty.copy()
            # update values (but exclude unknown keys)
            for key in keys.intersection(loaded_keys):
                self.data[key] = data_loaded[key]
            self.restore_forms()
            self.statusbar.showMessage(ll_msgs.status_loaded.format(
                                       filename=fname, n=self.n_modified()))

    def keyerror_dialog(self, origkeys, newkeys):
        """ Report missing / unknown keys to user. """
        cmnkeys = origkeys.intersection(newkeys)
        extra_in_new = newkeys - cmnkeys
        not_in_new = origkeys - cmnkeys
        li = list()
        if extra_in_new:
            # keys in data but not in UI - data lost
            li.append(ll_msgs.keys_extra.format(keys=', '.join(extra_in_new)))
        if not_in_new:
            # keys in UI but not in data. this is acceptable
            li.append(ll_msgs.keys_not_found.format(
                      keys=', '.join(not_in_new)))
        # only show the dialog if data was lost (not for missing values)
        if extra_in_new:
            message_dialog(''.join(li))

    def save_file(self, fname):
        """ Save data into given file in utf-8 encoding. """
        with io.open(fname, 'w', encoding='utf-8') as f:
            f.write(json.dumps(self.data, ensure_ascii=False))

    def load_dialog(self):
        """ Bring up load dialog and load selected file. """
        if self.saved_to_file or confirm_dialog(ll_msgs.load_not_saved):
            fout = QtWidgets.QFileDialog.getOpenFileName(self,
                                                         ll_msgs.open_title,
                                                         Config.data_root_fldr,
                                                         Config.json_filter)
            fname = fout[0]
            if fname:
                try:
                    self.load_file(fname)
                    self.last_saved_filename = fname
                    self.saved_to_file = True
                except Config.json_io_exceptions:
                    message_dialog(ll_msgs.cannot_open+fname)

    def save_dialog(self):
        """ Bring up save dialog and save data. """
        # special ops for certain widgets
        hetu = self.lnTiedotHetu.getVal()
        if hetu and not _check_hetu(hetu):
            message_dialog(ll_msgs.invalid_hetu)

        fout = QtWidgets.QFileDialog.getSaveFileName(self,
                                                     ll_msgs.save_report_title,
                                                     Config.data_root_fldr,
                                                     Config.json_filter)
        fname = fout[0]
        if fname:
            try:
                self.save_file(fname)
                self.saved_to_file = True
                self.last_saved_filename = fname
                self.statusbar.showMessage(ll_msgs.status_saved+fname)
            except Config.json_io_exceptions:
                message_dialog(ll_msgs.cannot_save+fname)

    def save_report_dialog(self):
        """ Bring up save dialog and save report. """
        if self.last_saved_filename:
            fn_base = op.splitext(op.basename(self.last_saved_filename))[0]
            filename_def = (Config.text_report_fldr + '/' +
                            Config.text_report_prefix +
                            fn_base + '.txt')
        else:
            filename_def = Config.data_root_fldr
        fout = QtWidgets.QFileDialog.getSaveFileName(self, ll_msgs.save_title,
                                                     filename_def,
                                                     Config.text_filter)
        fname = fout[0]
        if fname:
            try:
                report_txt = self.report.make_report(self.text_template)
                with io.open(fname, 'w', encoding='utf-8') as f:
                    f.write(report_txt)
                self.statusbar.showMessage(ll_msgs.status_report_saved+fname)
            except (IOError):
                message_dialog(ll_msgs.cannot_save+fname)

    def save_excel_report_dialog(self):
        """ Bring up save dialog and save Excel report. """
        if self.last_saved_filename:
            fn_base = op.splitext(op.basename(self.last_saved_filename))[0]
            filename_def = (Config.excel_report_fldr + '/' +
                            Config.excel_report_prefix + fn_base + '.xls')
        else:
            filename_def = Config.data_root_fldr
        fout = QtWidgets.QFileDialog.getSaveFileName(self, ll_msgs.save_title,
                                                     filename_def,
                                                     Config.excel_filter)
        fname = fout[0]
        if fname:
            try:
                self.report.make_excel(fname, self.xls_template)
                self.statusbar.showMessage(ll_msgs.status_report_saved+fname)
            except (IOError):
                message_dialog(ll_msgs.cannot_save+fname)

    def n_modified(self):
        """ Count modified values. """
        return len([x for x in self.data if
                    self.data[x] != self.data_empty[x]])

    def page_change(self):
        """ Method called whenever page (tab) changes. Currently only does
        focus / selectall on the first widget of page. """
        newpage = self.maintab.currentWidget()
        # focus / selectAll on 1st widget of new tab
        if newpage in self.firstwidget:
            widget = self.firstwidget[newpage]
            if widget.isEnabled():
                widget.selectAll()
                widget.setFocus()

    def save_temp(self):
        """ Save form input data into temporary backup file. Exceptions will be
        caught by the fatal exception mechanism. """
        self.save_file(Config.tmpfile)
        msg = ll_msgs.status_value_change.format(n=self.n_modified(),
                                                 tmpfile=Config.tmpfile)
        self.statusbar.showMessage(msg)

    def load_temp(self):
        """ Load form input data from temporary backup file. """
        try:
            self.load_file(Config.tmpfile)
        except Config.json_io_exceptions:
            message_dialog(ll_msgs.cannot_open_tmp)

    @staticmethod
    def rm_temp():
        """ Remove temp file.  """
        if op.isfile(Config.tmpfile):
            os.remove(Config.tmpfile)

    def clear_forms_dialog(self):
        """ Ask whether to clear forms. If yes, set widget inputs to default
        values. """
        if self.saved_to_file:
            reply = confirm_dialog(ll_msgs.clear)
        else:
            reply = confirm_dialog(ll_msgs.clear_not_saved)
        if reply == QtWidgets.QMessageBox.YesRole:
            self.data = self.data_empty.copy()
            self.restore_forms()
            self.statusbar.showMessage(ll_msgs.status_cleared)
            self.saved_to_file = True  # empty data assumed 'saved'

    def restore_forms(self):
        """ Restore widget input values from self.data. Need to disable widget
        callbacks and automatic data saving while programmatic updating of
        widgets is taking place. """
        self.save_to_tmp = False
        self.update_dict = False
        for wname in self.input_widgets:
            self.input_widgets[wname].setVal(self.data[
                                             self.widget_to_var[wname]])
        self.save_to_tmp = True
        self.update_dict = True

    def read_forms(self):
        """ Read self.data from widget inputs. Usually not needed, since
        it's updated automatically. """
        for wname in self.input_widgets:
            var = self.widget_to_var[wname]
            self.data[var] = self.input_widgets[wname].getVal()


def main():

    def _already_running():
        """Try to figure out if we are already running"""
        SCRIPT_NAMES = ['liikelaaj-script.py']
        nprocs = 0
        for proc in psutil.process_iter():
            try:
                cmdline = proc.cmdline()
                if cmdline:
                    if 'python' in cmdline[0] and len(cmdline) > 1:
                        if any([scr in cmdline[1] for scr in SCRIPT_NAMES]):
                            nprocs += 1
                            if nprocs == 2:
                                return True
            # catch NoSuchProcess for procs that disappear inside loop
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                pass
        return False

    logging.basicConfig(level=logging.DEBUG)

    """ Work around stdout and stderr not being available, if app is run
    using pythonw.exe on Windows. Without this, exception will be raised
    e.g. on any print statement. """
    if sys.platform.find('win') != -1 and sys.executable.find('pythonw') != -1:
        blackhole = open(os.devnull, 'w')
        sys.stdout = sys.stderr = blackhole

    if not Config.allow_multiple_instances and _already_running():
        message_dialog(ll_msgs.already_running)
        return

    app = QtWidgets.QApplication(sys.argv)
    eapp = EntryApp()

    def my_excepthook(type, value, tback):
        """ Custom exception handler for fatal (unhandled) exceptions:
        report to user via GUI and terminate program. """
        tb_full = u''.join(traceback.format_exception(type, value, tback))
        message_dialog(ll_msgs.unhandled_exception+tb_full)
        # dump traceback to file
        try:
            with io.open(Config.traceback_file, 'w', encoding='utf-8') as f:
                f.write(tb_full)
        # here is a danger of infinitely looping the exception hook,
        # so try to catch any exceptions...
        except Exception:
            print('Cannot dump traceback!')
        sys.__excepthook__(type, value, tback)
        app.quit()

    sys.excepthook = my_excepthook

    eapp.show()
    app.exec_()
