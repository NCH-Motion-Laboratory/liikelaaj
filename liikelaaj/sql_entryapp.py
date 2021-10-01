# -*- coding: utf-8 -*-
"""
Program for input and reporting of ROM (range of motion), strength and other
measurements.

Instead of saving to JSON, this version works directly with a SQL database.


TODO:

-app should take a sql connection
    -the database is already open at callers' end
    -pass cursor as parameter?
    -need to execute sql statements 
        -mostly SELECT to fetch data, UPDATE to update it
        -we are updating a particular record in the ROM table, corresponding to a measurement
    -we cannot defer sql ops to the caller, since the database needs to be updated on modifications
        -or maybe we could (via callbacks etc.) but this requires passing json back and forth
    -when widgets are changed, we run sql updates and commit

-patient info -> must be taken from patients table, not rom table
    -do we keep the rom patient info widgets, or not?
        -can hide the tab
    

-reporting -> can keep for now



@author: Jussi (jnu@iki.fi)
"""

import sqlite3
from PyQt5 import uic, QtCore, QtWidgets
import webbrowser
import logging
from pkg_resources import resource_filename


from .config import Config
from .widgets import (
    MyLineEdit,
    DegLineEdit,
    CheckDegSpinBox,
    message_dialog,
    confirm_dialog,
)
from . import reporter, ll_msgs

logger = logging.getLogger(__name__)


class EntryApp(QtWidgets.QMainWindow):
    """Data entry window"""

    def __init__(self, db_name, rom_id):
        super().__init__()
        # load user interface made with Qt Designer
        uifile = resource_filename('liikelaaj', 'tabbed_design_sql.ui')
        uic.loadUi(uifile, self)
        """
        Explicit tab order needs to be set because Qt does not handle focus correctly
        for custom (compound) widgets (QTBUG-10907). For custom widgets, the focus proxy
        needs to be explicitly inserted into focus chain. The code in fix_taborder.py can
        be generated by running:
        pyuic5.bat tabbed_design.ui | grep TabOrder | sed "s/csb[a-zA-Z0-9]*/&.focusProxy()/g" | sed "s/    MainWindow/self/g" >fix_taborder.py
        (replaces csb* widget names with csb*.focusProxy())
        It should be regenerated whenever new widgets are introduced that are part of the focus chain.
        Before that, define focus chain in Qt Designer.
        """
        # taborder_file = resource_filename('liikelaaj', 'fix_taborder.py')
        # exec(open(taborder_file, "rb").read())
        self.init_widgets()
        self.data = {}
        # save empty form (default states for widgets)
        self.read_forms()
        self.data_empty = self.data.copy()
        # variable list, mostly for SQL statements
        self._varlist = ','.join(self.data)
        # whether to update internal dict of variables on input changes
        self.update_dict = True
        self.text_template = resource_filename('liikelaaj', Config.text_template)
        self.isokin_text_template = resource_filename(
            'liikelaaj', Config.isokin_text_template
        )
        self.xls_template = resource_filename('liikelaaj', Config.xls_template)
        # DB setup
        self.conn = sqlite3.connect(db_name)
        self.cr = self.conn.cursor()
        self.cr.execute('PRAGMA foreign_keys = ON;')
        self.rom_id = rom_id  # unique ID for the rom in the database
        self._read_data()
        self.init_readonly_fields()
        # TODO: set locale and options if needed
        # loc = QtCore.QLocale()
        # loc.setNumberOptions(loc.OmitGroupSeparator |
        #            loc.RejectGroupSeparator)

    def init_readonly_fields(self):
        """Fill the read-only patient info widgets"""
        query = f'SELECT patient_id FROM roms WHERE rom_id=:rom_id'
        self.cr.execute(query, {'rom_id': self.rom_id})
        if (row := self.cr.fetchone()) is None:
            raise RuntimeError('Database error: no patient for given ROM id')
        patient_id = row[0]
        vars = 'firstname,lastname,ssn,patient_code'
        query = f'SELECT {vars} FROM patients WHERE patient_id=:patient_id'
        self.cr.execute(query, {'patient_id': patient_id})
        for var, val in zip(vars.split(','), self.cr.fetchone()):
            # automatically compose the widget name and set content to corresponding variable
            widget_name = 'rdonly_' + var
            self.__dict__[widget_name].setText(val)

    def init_widgets(self):
        """Make a dict of our input widgets and install some callbacks and
        convenience methods etc."""
        self.input_widgets = {}

        def spinbox_getval(w):
            """Return spinbox value"""
            return w.no_value_text if w.value() == w.minimum() else w.value()

        def spinbox_setval(w, val):
            """Set spinbox value"""
            val = w.minimum() if val == w.no_value_text else val
            w.setValue(val)

        def checkbox_getval(w):
            """Return yestext or notext for checkbox enabled/disabled,
            respectively."""
            val = int(w.checkState())
            if val == 0:
                return w.no_text
            elif val == 2:
                return w.yes_text
            else:
                raise RuntimeError(
                    f'Unexpected checkbox value: {val} for {w.objectName()}'
                )

        def checkbox_setval(w, val):
            """Set checkbox value to enabled for val == yestext and
            disabled for val == notext"""
            if val == w.yes_text:
                w.setCheckState(2)
            elif val == w.no_text:
                w.setCheckState(0)
            else:
                raise RuntimeError(
                    f'Unexpected checkbox entry value: {val} for {w.objectName()}'
                )

        def combobox_getval(w):
            """Get combobox current choice as text"""
            return w.currentText()

        def combobox_setval(w, val):
            """Set combobox value according to val (unicode) (must be one of
            the combobox items)"""
            idx = w.findText(val)
            if idx >= 0:
                w.setCurrentIndex(idx)
            else:
                raise ValueError(f'Tried to set combobox to invalid value {val}')

        def keyPressEvent_resetOnEsc(obj, event):
            """Special event handler for spinboxes. Resets value (sets it
            to minimum) when Esc is pressed."""
            if event.key() == QtCore.Qt.Key_Escape:
                obj.setValue(obj.minimum())
            else:
                # delegate the event to the overridden superclass handler
                super(obj.__class__, obj).keyPressEvent(event)

        def isint(x):
            """Test for integer"""
            try:
                int(x)
                return True
            except ValueError:
                return False

        # Change lineEdit to custom one for spinboxes. This cannot be done in
        # the main widget loop below, because the old QLineEdits get destroyed in
        # the process (by Qt) and the loop then segfaults while trying to
        # dereference them (the loop collects all QLineEdits at the start).
        # Also install special keypress event handler. """
        for w in self.findChildren((QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox)):
            wname = w.objectName()
            if wname[:2] == 'sp':
                w.setLineEdit(MyLineEdit())
                w.keyPressEvent = lambda event, w=w: keyPressEvent_resetOnEsc(w, event)

        # CheckDegSpinBoxes get a special LineEdit that catches space
        # and mouse press events
        for w in self.findChildren(CheckDegSpinBox):
            w.degSpinBox.setLineEdit(DegLineEdit())

        allwidgets = self.findChildren(QtWidgets.QWidget)

        def _weight_normalize(w):
            """Auto calculate callback for weight normalized widgets"""
            val, weight = (w.getVal() for w in w._autoinputs)
            noval = Config.spinbox_novalue_text
            w.setVal(noval if val == noval or weight == noval else val / weight)

        # Autowidgets are special widgets with automatically computed values.
        # They must have an ._autocalculate() method which updates the widget
        # and ._autoinputs list which lists the necessary input widgets.
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

        # set various widget convenience methods/properties
        # input widgets are specially named and will be automatically
        # collected into a dict
        for w in allwidgets:
            wname = w.objectName()
            wsave = True
            # w.unit returns the unit for each input (may change dynamically)
            w.unit = lambda: ''
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
                w.currentIndexChanged.connect(lambda x, w=w: self.values_changed(w))
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

        self.actionTekstiraportti.triggered.connect(
            self._save_default_text_report_dialog
        )
        self.actionTekstiraportti_isokineettinen.triggered.connect(
            self._save_isokin_text_report_dialog
        )
        self.actionExcel_raportti.triggered.connect(
            self._save_default_excel_report_dialog
        )
        self.actionWeb_sivu.triggered.connect(self.open_help)
        self.actionLopeta.triggered.connect(self.close)

        # slot called on tab change
        self.maintab.currentChanged.connect(self.page_change)

        """ First widget of each page. This is used to do focus/selectall on
        the 1st widget on page change so that data can be entered immediately.
        Only needed for spinbox / lineedit widgets. """
        self.firstwidget = dict()
        # TODO: check/fix
        self.firstwidget[self.tabTiedot] = self.rdonly_firstname
        self.firstwidget[self.tabKysely] = self.lnKyselyPaivittainenMatka
        self.firstwidget[self.tabAntrop] = self.spAntropAlaraajaOik
        self.firstwidget[self.tabLonkka] = self.csbLonkkaFleksioOik
        self.firstwidget[self.tabNilkka] = self.csbNilkkaSoleusCatchOik
        self.firstwidget[self.tabPolvi] = self.csbPolviEkstensioVapOik
        self.firstwidget[self.tabIsokin] = self.spIsokinPolviEkstensioOik
        self.firstwidget[self.tabVirheas] = self.spVirheasAnteversioOik
        self.firstwidget[self.tabTasap] = self.spTasapOik
        self.total_widgets = len(self.input_widgets)

        self.statusbar.showMessage(ll_msgs.ready.format(n=self.total_widgets))

        """ Set up widget -> varname translation dict. Variable names
        are derived by removing 2-3 leading characters (indicating widget type)
        from widget names (except for comment box variables cmt* which are
        identical with widget names).
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
        self.setStyleSheet('QWidget { font-size: %dpt;}' % Config.global_fontsize)

        # FIXME: make sure we always start on 1st tab

    @property
    def units(self):
        """Return dict indicating the units for each variable. This may change
        dynamically as the unit may be set to '' for special values."""
        return {
            self.widget_to_var[wname]: self.input_widgets[wname].unit()
            for wname in self.input_widgets
        }

    @property
    def vars_default(self):
        """Return a list of variables that are at their default (unmodified)
        state."""
        return [key for key in self.data if self.data[key] == self.data_empty[key]]

    def closeEvent(self, event):
        """Confirm and close application."""
        reply = confirm_dialog(ll_msgs.quit_)
        if reply == QtWidgets.QMessageBox.YesRole:
            # cleanup
            event.accept()
        else:
            event.ignore()

    @staticmethod
    def open_help():
        """Show help."""
        webbrowser.open(Config.help_url)

    def values_changed(self, w):
        """Called whenever value of a widget (w) changes"""
        # find autowidgets that depend on w and update them
        autowidgets_this = [
            widget for widget in self.autowidgets if w in widget._autoinputs
        ]
        for widget in autowidgets_this:
            widget._autocalculate()
        if self.update_dict:  # update internal data dict
            wname = w.objectName()
            varname = self.widget_to_var[wname]
            newval = w.getVal()
            self.data[varname] = newval
            query = f'UPDATE roms SET {varname}=:newval WHERE rom_id=:rom_id'
            self.cr.execute(
                query, {'varname': varname, 'newval': newval, 'rom_id': self.rom_id}
            )
            self.conn.commit()

    def keyerror_dialog(self, origkeys, newkeys):
        """Report missing / unknown keys to user."""
        cmnkeys = origkeys.intersection(newkeys)
        extra_in_new = newkeys - cmnkeys
        not_in_new = origkeys - cmnkeys
        li = list()
        if extra_in_new:
            # keys in data but not in UI - data lost
            li.append(ll_msgs.keys_extra.format(keys=', '.join(extra_in_new)))
        if not_in_new:
            # keys in UI but not in data. this is acceptable
            li.append(ll_msgs.keys_not_found.format(keys=', '.join(not_in_new)))
        # only show the dialog if data was lost (not for missing values)
        if extra_in_new:
            message_dialog(''.join(li))

    @property
    def data_with_units(self):
        """Append units to values"""
        return {key: f'{self.data[key]}{self.units[key]}' for key in self.data}

    def _read_data(self):
        """Read input data from database"""
        query = f'SELECT {self._varlist} FROM roms WHERE rom_id=:rom_id'
        self.cr.execute(query, {'rom_id': self.rom_id})
        if (row := self.cr.fetchone()) is None:
            raise RuntimeError('Database error: no results for given id')
        # pick only the values which are non-NULL in the database
        record_di = {var: val for var, val in zip(self.data, row) if val is not None}
        self.data = self.data_empty | record_di
        self.restore_forms()

    def make_txt_report(self, template, include_units=True):
        """Create text report from current data"""
        # uncomment to respond to template changes while running
        # importlib.reload(reporter)
        data = self.data_with_units if include_units else self.data
        rep = reporter.Report(data, self.vars_default)
        return rep.make_report(template)

    def make_excel_report(self, xls_template):
        """Create Excel report from current data"""
        rep = reporter.Report(self.data, self.vars_default)
        return rep.make_excel(xls_template)

    def _save_default_text_report_dialog(self):
        """Create text report and open dialog for saving it"""
        txt = self.make_txt_report(self.text_template)
        self._save_text_report_dialog(txt, Config.text_report_prefix)

    def _save_isokin_text_report_dialog(self):
        """Create isokinetic text report and open dialog for saving it"""
        txt = self.make_txt_report(self.isokin_text_template, include_units=False)
        self._save_text_report_dialog(txt, Config.isokin_text_report_prefix)

    def _save_default_excel_report_dialog(self):
        """Create Excel report and open dialog for saving it"""
        wb = self.make_excel_report(self.xls_template)
        self._save_excel_report_dialog(wb)

    def _save_text_report_dialog(self, report_txt, prefix):
        """Bring up save dialog and save text report"""
        if self.last_saved_filepath:
            destpath = Config.text_report_path / (
                prefix + self.last_saved_filepath.stem + '.txt'
            )
        else:
            destpath = Config.data_root_path
        path = self._save_dialog(destpath, Config.text_filter)
        if path is None:
            return
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(report_txt)
            self.statusbar.showMessage(ll_msgs.status_report_saved + str(path))
        except (IOError):
            message_dialog(ll_msgs.cannot_save + str(path))

    def _save_excel_report_dialog(self, workbook):
        """Bring up file dialog and save Excel workbook"""
        if self.last_saved_filepath:
            destpath = Config.excel_report_path / (
                Config.excel_report_prefix + self.last_saved_filepath.stem + '.xls'
            )
        else:
            destpath = Config.data_root_path
        path = self._save_dialog(destpath, Config.excel_filter)
        try:
            workbook.save(str(path))
            self.statusbar.showMessage(ll_msgs.status_report_saved + str(path))
        except (IOError):
            message_dialog(ll_msgs.cannot_save + str(path))

    def n_modified(self):
        """Count modified values."""
        return len([x for x in self.data if self.data[x] != self.data_empty[x]])

    def page_change(self):
        """Callback for tab change"""
        newpage = self.maintab.currentWidget()
        # focus / selectAll on 1st widget of new tab
        if newpage in self.firstwidget:
            widget = self.firstwidget[newpage]
            if widget.isEnabled():
                widget.selectAll()
                widget.setFocus()

    def restore_forms(self):
        """Restore widget input values from self.data. Need to disable widget
        callbacks and automatic data saving while programmatic updating of
        widgets is taking place."""
        self.save_to_tmp = False
        self.update_dict = False
        for wname in self.input_widgets:
            self.input_widgets[wname].setVal(self.data[self.widget_to_var[wname]])
        self.save_to_tmp = True
        self.update_dict = True

    def read_forms(self):
        """Read self.data from widget inputs. Usually not needed, since
        it's updated automatically."""
        for wname in self.input_widgets:
            var = self.widget_to_var[wname]
            self.data[var] = self.input_widgets[wname].getVal()
